"""Reproducible CPU feasibility spike; not a production search implementation.

See index.md for frozen acceptance criteria. All texts are synthetic.
Install the recorded requirements into an isolated environment before running.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import resource
import sqlite3
import time
import traceback

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("RAYON_NUM_THREADS", "4")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import lancedb
import numpy as np
import psutil
import pyarrow as pa
import torch
from sentence_transformers import MultiVectorEncoder

MODEL_ID = "nlpai-lab/KURE-v2"
REVISION = "3431f86d399d666083890dbb882aced6708873bc"
FROZEN_SHA = "73d6651d7dfc1c1005381e9d65cf3dfb5b679729f96b1b4ed32104e842d1a5ba"
HERE = Path(__file__).resolve().parent


def emit(stage, **fields):
    print(json.dumps({"stage": stage, **fields}, ensure_ascii=False), flush=True)


def ms(start):
    return (time.perf_counter() - start) * 1000


def summary(values):
    return {"count": len(values), "min": float(np.min(values)),
            "p50": float(np.percentile(values, 50)),
            "p95": float(np.percentile(values, 95)), "max": float(np.max(values))}


def bytes_under(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def normalize(a):
    return a / np.linalg.norm(a, axis=-1, keepdims=True).clip(min=1e-12)


def maxsim(q, d):
    return float((normalize(q) @ normalize(d).T).max(axis=1).sum())


def retrieval_metrics(ids, relevant):
    gold = set(relevant)
    return {
        "hit_at_1": float(bool(ids and ids[0] in gold)),
        "recall_at_5": len(gold.intersection(ids[:5])) / len(gold),
        "mrr_at_10": next((1 / (i + 1) for i, x in enumerate(ids[:10]) if x in gold), 0),
        "ndcg_at_10": sum((1 / math.log2(i + 2)) for i, x in enumerate(ids[:10]) if x in gold)
        / sum(1 / math.log2(i + 2) for i in range(min(len(gold), 10))),
    }


def aggregate(rows):
    return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}


def schema():
    return pa.schema([
        ("id", pa.string()), ("capture_id", pa.string()), ("text", pa.string()),
        ("category", pa.string()), ("owner_id", pa.string()), ("visibility", pa.string()),
        ("revision", pa.int32()), ("generation", pa.int32()), ("profile", pa.string()),
        ("vector", pa.list_(pa.list_(pa.float32(), 128))),
    ])


def make_row(record, vec):
    return dict(id=record["id"], capture_id=record["id"],
                text=record["title"] + "\n" + record["text"], category=record["category"],
                owner_id="local", visibility="private" if record["id"].endswith("1") else "public",
                revision=1, generation=1, profile="kure-v2-fp32-512", vector=vec.tolist())


SELECT = ["id", "capture_id", "revision", "generation", "profile", "owner_id", "visibility"]


def search(table, mode, q, text, limit=10, exact=True, probes=4):
    if mode == "fts":
        builder = table.search(text, query_type="fts", fts_columns="text")
    elif mode == "hybrid":
        builder = table.search(query_type="hybrid", fts_columns="text").vector(q).text(text)
    else:
        builder = table.search(q, query_type="vector", vector_column_name="vector")
    if mode != "fts":
        builder = builder.metric("cosine")
        if exact:
            builder = builder.bypass_vector_index()
        else:
            builder = builder.nprobes(probes).refine_factor(5)
    return builder.where("owner_id = 'local'", prefilter=True).select(SELECT).limit(limit)


def build_fts(table):
    table.create_fts_index("text", base_tokenizer="icu", stem=False,
                           remove_stop_words=False, ascii_folding=False)


def scale_records(n):
    """Distinct generated text, freshly encoded; NOT a labeled quality benchmark."""
    topics = ["파이썬 비동기", "데이터베이스 격리", "검색 재현율", "임베딩 벡터",
              "자료구조", "네트워크 재시도", "회의 준비", "주말 산책", "독서 노트", "사진 백업"]
    actions = ["예제를 직접 실행했다", "아직 결론을 내리지 않았다", "이전 메모를 정정했다",
               "실행 전에 점검할 목록을 썼다", "완료한 결과와 다음 질문을 구분했다"]
    return [{"id": f"scale-{i:04}", "category": "synthetic-scale",
             "title": f"합성 실험 메모 {i + 1}: {topics[i % len(topics)]}",
             "text": f"가상 실험 {i + 1}번째 기록. {topics[i % len(topics)]}에 대해 "
                     f"{actions[(i // len(topics)) % len(actions)]}. "
                     f"자료 번호 SB-{i + 1000}에서 조건 {(i % 97) + 1}을 비교하고 "
                     f"반복 횟수 {(i % 13) + 1}과 관찰 날짜 2026-{(i % 12) + 1:02}-{(i % 28) + 1:02}를 적었다. "
                     "이 문서는 규모 실험용이며 실제 사용자 경험이 아니다."}
            for i in range(n)]


def consistency_probe(db, rows, q):
    """Adversarial projection vs canonical-state simulation, not app integration."""
    table = db.create_table("consistency", data=rows, schema=schema())
    sq = sqlite3.connect(":memory:")
    sq.execute("create table captures(id text primary key, revision int, generation int, "
               "profile text, status text, ready int, body text)")
    for r in rows:
        sq.execute("insert into captures values(?,?,?,?,?,?,?)", (r["capture_id"], 1, 1,
                   r["profile"], "active", 1, "canonical:" + r["capture_id"]))

    def valid(candidates, active_profile="kure-v2-fp32-512"):
        out, seen = [], set()
        for c in candidates:
            state = sq.execute("select revision,generation,profile,status,ready,body from captures where id=?",
                               (c["capture_id"],)).fetchone()
            if not state or c["capture_id"] in seen:
                continue
            rev, gen, profile, status, ready, body = state
            if (rev, gen, profile, status, ready) != (c["revision"], c["generation"], c["profile"], "active", 1):
                continue
            if profile != active_profile:
                continue
            seen.add(c["capture_id"])
            out.append({"id": c["capture_id"], "text": body})
        return out

    def candidates():
        return search(table, "vector", q, "", limit=100).to_list()

    target = rows[0]
    tid = target["capture_id"]
    cases = {}
    cases["private_owner_record_visible"] = any(x["id"] == tid for x in valid(candidates()))
    sq.execute("update captures set revision=2,generation=2,ready=0,body='canonical:edited' where id=?", (tid,))
    cases["edit_pending_hides_old_revision"] = tid not in [x["id"] for x in valid(candidates())]
    edited = dict(target, id=tid + "-r2", revision=2, generation=2, text="projection:do-not-return")
    table.add([edited])
    cases["uncommitted_projection_hidden"] = tid not in [x["id"] for x in valid(candidates())]
    sq.execute("update captures set ready=1 where id=?", (tid,))
    committed = [x for x in valid(candidates()) if x["id"] == tid]
    cases["edited_result_uses_canonical_body"] = committed == [{"id": tid, "text": "canonical:edited"}]
    table.add([dict(target, id=tid + "-late-r1")])
    cases["late_old_job_cannot_replace_current"] = len([x for x in valid(candidates()) if x["id"] == tid]) == 1
    sq.execute("update captures set status='trash',generation=3,ready=0 where id=?", (tid,))
    cases["trash_hides_all_candidates"] = tid not in [x["id"] for x in valid(candidates())]
    table.add([dict(edited, id=tid + "-late-r2")])
    cases["late_job_after_trash_hidden"] = tid not in [x["id"] for x in valid(candidates())]
    sq.execute("update captures set status='active',generation=4,ready=0 where id=?", (tid,))
    cases["restore_pending_hides_old_generation"] = tid not in [x["id"] for x in valid(candidates())]
    table.add([dict(edited, id=tid + "-restored", generation=4)])
    sq.execute("update captures set ready=1 where id=?", (tid,))
    cases["restore_ready_visible"] = len([x for x in valid(candidates()) if x["id"] == tid]) == 1
    cases["new_profile_rejects_old_vectors"] = valid(candidates(), "different-model-profile") == []
    sq.execute("delete from captures where id=?", (tid,))
    table.add([dict(edited, id=tid + "-late-after-delete", generation=4)])
    cases["deleted_canonical_record_hidden"] = tid not in [x["id"] for x in valid(candidates())]
    all_candidates = candidates()
    first = all_candidates[0]["capture_id"]
    sq.execute("update captures set status='trash' where id=?", (first,))
    refill = valid(all_candidates)[:5]
    cases["overfetch_refills_valid_candidates"] = len(refill) == 5 and first not in [x["id"] for x in refill]
    sq.execute("update captures set status='trash'")
    cases["no_valid_evidence_returns_empty"] = valid(candidates()) == []
    sq.close()
    return {"scope": "SQLite in-memory canonical filter simulation; no app, races, outbox worker or disk erasure tested",
            "cases": cases, "all_passed": all(cases.values())}


def run(args, result):
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.manual_seed(42)
    data_bytes = (HERE / "fixtures.json").read_bytes()
    assert hashlib.sha256(data_bytes).hexdigest() == FROZEN_SHA, "Fixture changed after freeze"
    data = json.loads(data_bytes)
    result["fixture_sha256"] = FROZEN_SHA
    result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["environment"] = {"platform": platform.platform(), "python": platform.python_version(),
        "cpu": next((x.split(":", 1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines()
                     if x.startswith('model name')), platform.processor()),
        "logical_cpus": os.cpu_count(), "memory_bytes": psutil.virtual_memory().total,
        "torch_threads": torch.get_num_threads(), "torch_interop_threads": torch.get_num_interop_threads(),
        "packages": {p: importlib.metadata.version(p) for p in
                     ["torch", "sentence-transformers", "transformers", "lancedb", "numpy", "pyarrow", "psutil"]}}
    snapshot = args.cache / "models" / "models--nlpai-lab--KURE-v2" / "snapshots" / REVISION
    assert snapshot.is_dir(), "Download the pinned snapshot as described in index.md first"
    started = time.perf_counter()
    model = MultiVectorEncoder(str(snapshot), device="cpu", local_files_only=True,
                               model_kwargs={"dtype": torch.float32, "attn_implementation": "sdpa"})
    model[0].document_length = 512
    result["model"] = {"id": MODEL_ID, "revision": REVISION, "load_ms": ms(started),
        "parameters": sum(p.numel() for p in model.parameters()),
        "parameter_dtypes": sorted({str(p.dtype) for p in model.parameters()}),
        "device": str(model.device), "weight_bytes": sum(p.stat().st_size for p in snapshot.rglob("*.safetensors")),
        "snapshot_bytes": bytes_under(snapshot), "query_length": model[0].query_length,
        "query_expansion": model[0].query_expansion, "document_length": model[0].document_length,
        "prompts": model.prompts, "modules": [type(m).__name__ for m in model],
        "pylate_installed": any(x.metadata['Name'].lower() == 'pylate' for x in importlib.metadata.distributions())}
    emit("loaded", **result["model"])
    result["rss_after_load_bytes"] = psutil.Process().memory_info().rss

    def encode_docs(records):
        texts = [r["title"] + "\n" + r["text"] for r in records]
        # All spike records fit, so no content is silently truncated by this experiment.
        token_lengths = [len(model.tokenizer.encode(model.prompts.get("document", "") + t)) for t in texts]
        assert max(token_lengths) <= 512, "Add real chunking before testing longer records"
        t = time.perf_counter()
        vectors = model.encode_document(texts, batch_size=4, convert_to_numpy=True, show_progress_bar=False)
        return vectors, {"elapsed_ms": ms(t), "input_token_lengths": summary(token_lengths),
                         "output_token_counts": summary([len(v) for v in vectors])}

    model.encode_query("워밍업 질문", batch_size=1, convert_to_numpy=True, show_progress_bar=False)
    records, queries = data["records"], data["queries"]
    docs, result["fixture_encoding"] = encode_docs(records)
    assert len({len(d) for d in docs}) > 1
    assert all(d.ndim == 2 and d.shape[1] == 128 and np.isfinite(d).all() for d in docs)
    result["document_norm_max_error"] = max(float(np.abs(np.linalg.norm(d, axis=1) - 1).max()) for d in docs)
    db_path = args.cache / "runs" / time.strftime("%Y%m%d-%H%M%S")
    db = lancedb.connect(db_path)
    rows = [make_row(r, v) for r, v in zip(records, docs)]
    table = db.create_table("fixture", data=rows, schema=schema())
    build_fts(table)
    result["fixture_db_bytes"] = bytes_under(db_path / "fixture.lance")
    encoded = []
    for q in queries:
        t = time.perf_counter()
        qvec = model.encode_query(q["text"], batch_size=1, convert_to_numpy=True, show_progress_bar=False)
        encoded.append((q, qvec, ms(t)))
    assert all(v.shape == (64, 128) and np.isfinite(v).all() for _, v, _ in encoded)
    result["query_shape"] = list(encoded[0][1].shape)
    result["query_norm_max_error"] = max(float(np.abs(np.linalg.norm(v, axis=1) - 1).max()) for _, v, _ in encoded)
    result["query_encode_ms"] = summary([elapsed for _, _, elapsed in encoded])
    # Warm each DB path before measurement; no question/label changes after freeze.
    for mode in ["vector", "fts", "hybrid"]:
        search(table, mode, encoded[0][1], encoded[0][0]["text"]).to_list()
    quality, max_errors, rank_matches = [], [], []
    for q, qvec, elapsed in encoded:
        item = {"id": q["id"], "category": q["category"], "text": q["text"],
                "relevant_ids": q["relevant_ids"], "encode_ms": elapsed, "modes": {}}
        expected = {r["id"]: maxsim(qvec, d) for r, d in zip(records, docs)}
        ranked = sorted(expected, key=expected.get, reverse=True)
        for mode in ["vector", "fts", "hybrid"]:
            t = time.perf_counter()
            hits = search(table, mode, qvec, q["text"]).to_list()
            search_time = ms(t)
            ids = [h["id"] for h in hits]
            item["modes"][mode] = {"ids": ids, "search_ms": search_time,
                "encode_plus_search_ms": search_time + (elapsed if mode != "fts" else 0),
                "metrics": retrieval_metrics(ids, q["relevant_ids"])}
            if mode == "vector":
                errors = [abs(h["_distance"] - (len(qvec) - expected[h["id"]])) for h in hits]
                max_errors.extend(errors)
                rank_matches.append(all(abs(expected[x] - expected[y]) < 1e-4 for x, y in zip(ids, ranked[:10])))
        quality.append(item)
    result["maxsim_check"] = {"distance_formula": "query_token_count - sum_i max_j cosine(q_i,d_j)",
                              "max_abs_distance_error": max(max_errors), "all_top10_scores_match": all(rank_matches)}
    result["quality_by_query"] = quality
    result["quality_summary"] = {mode: {"overall": aggregate([x["modes"][mode]["metrics"] for x in quality]),
        "by_category": {c: aggregate([x["modes"][mode]["metrics"] for x in quality if x["category"] == c])
                        for c in ["learning", "daily", "memo"]},
        "search_ms": summary([x["modes"][mode]["search_ms"] for x in quality]),
        "encode_plus_search_ms": summary([x["modes"][mode]["encode_plus_search_ms"] for x in quality])}
        for mode in ["vector", "fts", "hybrid"]}
    result["plans"] = {mode: search(table, mode, encoded[0][1], queries[0]["text"]).explain_plan()
                       for mode in ["vector", "fts", "hybrid"]}
    result["no_answer_observations"] = []
    for q in data["no_answer_queries"]:
        qvec = model.encode_query(q["text"], batch_size=1, convert_to_numpy=True, show_progress_bar=False)
        hits = search(table, "vector", qvec, q["text"], limit=5).to_list()
        result["no_answer_observations"].append({"query": q, "top5": hits,
            "note": "Nearest records are still returned. No score threshold or generated-answer correctness is established."})
    result["consistency"] = consistency_probe(db, rows, encoded[0][1])
    emit("fixture_complete", quality=result["quality_summary"], maxsim=result["maxsim_check"],
         consistency=result["consistency"]["all_passed"])
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    # Use distinct fresh texts for size/ANN feasibility, not replicated vectors.
    extra = scale_records(args.scale_count)
    emit("scale_encoding_started", count=len(extra))
    extra_vectors, encoding_stats = encode_docs(extra)
    combined = records + extra
    combined_vecs = list(docs) + list(extra_vectors)
    scale = db.create_table("scale", data=[make_row(r, v) for r, v in zip(combined, combined_vecs)], schema=schema())
    build_fts(scale)
    scale_info = {"records": len(combined), "scope": "36 labeled fixtures + distinct but repetitive generated load texts; ANN agreement only",
        "encoding": encoding_stats, "token_vectors": sum(len(v) for v in combined_vecs),
        "raw_vector_bytes": sum(v.nbytes for v in combined_vecs),
        "bytes_before_ann": bytes_under(db_path / "scale.lance"), "ann_index": {"type": "IVF_PQ", "partitions": 16,
        "sub_vectors": 16, "bits": 8, "metric": "cosine", "refine_factor": 5, "nprobes": 4}}
    scale_info["exact_reference"] = []
    for q, qvec, _ in encoded:
        t = time.perf_counter()
        hits = search(scale, "vector", qvec, q["text"], limit=5).to_list()
        scale_info["exact_reference"].append({"id": q["id"], "ids": [h["id"] for h in hits], "search_ms": ms(t)})
    t = time.perf_counter()
    scale.create_index(metric="cosine", num_partitions=16, num_sub_vectors=16, index_type="IVF_PQ", num_bits=8)
    scale_info["index_build_ms"] = ms(t)
    scale_info["bytes_after_ann"] = bytes_under(db_path / "scale.lance")
    scale_info["ann_plan"] = search(scale, "vector", encoded[0][1], queries[0]["text"], exact=False).explain_plan()
    scale_info["hybrid_ann_plan"] = search(scale, "hybrid", encoded[0][1], queries[0]["text"], exact=False).explain_plan()
    search(scale, "vector", encoded[0][1], queries[0]["text"], exact=False).to_list()
    scale_info["ann_queries"] = []
    for (q, qvec, elapsed), exact in zip(encoded, scale_info["exact_reference"]):
        t = time.perf_counter()
        hits = search(scale, "vector", qvec, q["text"], limit=5, exact=False).to_list()
        latency = ms(t)
        ids = [h["id"] for h in hits]
        scale_info["ann_queries"].append({"id": q["id"], "ids": ids, "search_ms": latency,
            "encode_plus_search_ms": elapsed + latency, "agreement_recall_at_5": len(set(ids) & set(exact["ids"])) / 5})
    scale_info["ann_recall_at_5"] = float(np.mean([r["agreement_recall_at_5"] for r in scale_info["ann_queries"]]))
    scale_info["exact_search_ms"] = summary([r["search_ms"] for r in scale_info["exact_reference"]])
    scale_info["ann_search_ms"] = summary([r["search_ms"] for r in scale_info["ann_queries"]])
    scale_info["ann_encode_plus_search_ms"] = summary([r["encode_plus_search_ms"] for r in scale_info["ann_queries"]])
    result["scale"] = scale_info
    result["db_cache_path"] = str(db_path)
    emit("scale_complete", records=scale_info["records"], recall=scale_info["ann_recall_at_5"],
         exact_ms=scale_info["exact_search_ms"], ann_ms=scale_info["ann_search_ms"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/second-brain/kure-v2-feasibility")
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    parser.add_argument("--scale-count", type=int, default=1000)
    args = parser.parse_args()
    result = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": "running"}
    try:
        run(args, result)
        result["status"] = "complete"
    except Exception:
        result["status"] = "failed"
        result["error"] = traceback.format_exc()
        print(result["error"], flush=True)
        raise
    finally:
        result["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        result["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        emit("finished", status=result["status"], peak_rss_bytes=result["peak_rss_bytes"])


if __name__ == "__main__":
    main()
