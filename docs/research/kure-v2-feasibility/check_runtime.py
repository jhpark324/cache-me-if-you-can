"""Supplement checks prompted by review; leaves the frozen benchmark unchanged."""
import hashlib
import json
from pathlib import Path
import resource
import time

from run_benchmark import (HERE, REVISION, FROZEN_SHA, MultiVectorEncoder, torch,
                           np, lancedb, search, summary, ms, emit)


def main():
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    cache = Path.home() / ".cache/second-brain/kure-v2-feasibility"
    baseline = json.loads((HERE / "results.json").read_text())
    assert baseline["status"] == "complete"
    raw = (HERE / "fixtures.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA
    data = json.loads(raw)
    model = MultiVectorEncoder(str(cache / "models/models--nlpai-lab--KURE-v2/snapshots" / REVISION),
        device="cpu", local_files_only=True, model_kwargs={"dtype": torch.float32, "attn_implementation": "sdpa"})
    model[0].document_length = 512
    model.eval()
    report = {"fixture_sha256": FROZEN_SHA, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "baseline_script_sha256": baseline["script_sha256"]}
    all_queries = data["queries"] + data["no_answer_queries"]
    lengths = [len(model.tokenizer.encode(model.prompts["query"] + q["text"], truncation=False)) for q in all_queries]
    report["query_input_lengths"] = summary(lengths)
    report["no_fixture_query_truncated"] = max(lengths) < 64
    assert report["no_fixture_query_truncated"]

    short = "한국어 메모 , . ! ?"
    longer = "한국어 공부에서 트랜잭션 원자성과 지속성을 구분해서 기록했다. " * 8
    inputs = model.preprocess([short, longer], prompt=model.prompts["document"], task="document")
    ids, attended = inputs["input_ids"].clone(), inputs["attention_mask"].clone().bool()
    mask_module = next(m for m in model if type(m).__name__ == "MultiVectorMask")
    skip_ids = {model.tokenizer.convert_tokens_to_ids(x) for x in mask_module.skiplist_words}
    expected = [[bool(a) and int(i) not in skip_ids for i, a in zip(row, mask)] for row, mask in zip(ids, attended)]
    actual_mask = mask_module(dict(inputs), task="document")["attention_mask"]
    report["mask"] = {"document_input_width": ids.shape[1],
        "padding_tokens": int((~attended).sum()),
        "punctuation_tokens_removed": int(sum(int(a) and int(i) in skip_ids for row, row_mask in zip(ids, attended) for i, a in zip(row, row_mask))),
        "scoring_lengths": actual_mask.sum(dim=1).tolist(),
        "matches_independent_id_mask": torch.equal(actual_mask, torch.tensor(expected)),
        "skiplist_words": mask_module.skiplist_words}
    batch = model.encode_document([short, longer], batch_size=2, convert_to_numpy=True, show_progress_bar=False)
    solo = model.encode_document(short, batch_size=1, convert_to_numpy=True, show_progress_bar=False)
    report["mask"]["encode_lengths_match_scoring_mask"] = [len(v) for v in batch] == report["mask"]["scoring_lengths"]
    report["mask"]["solo_vs_padded_batch_max_abs_diff"] = float(np.abs(solo - batch[0]).max())
    qprep = model.preprocess(["메모를 찾아줘"], prompt=model.prompts["query"], task="query")
    report["mask"]["query_attended_tokens"] = int(qprep["attention_mask"].sum())
    report["mask"]["query_scored_tokens"] = int(mask_module(dict(qprep), task="query")["attention_mask"].sum())
    assert report["mask"]["padding_tokens"] > 0 and report["mask"]["punctuation_tokens_removed"] > 0
    assert report["mask"]["matches_independent_id_mask"] and report["mask"]["encode_lengths_match_scoring_mask"]
    assert report["mask"]["solo_vs_padded_batch_max_abs_diff"] < 1e-4
    assert report["mask"]["query_scored_tokens"] == 64

    # The library accepts these inputs: the product adapter needs an explicit input contract.
    long_query = "지난 공부와 일상 기록에서 변경된 점을 모두 찾아서 설명해 줘. " * 20
    long_length = len(model.tokenizer.encode(model.prompts["query"] + long_query, truncation=False))
    long_prepped = model.preprocess([long_query], prompt=model.prompts["query"], task="query")
    blank = model.encode_query("", batch_size=1, convert_to_numpy=True, show_progress_bar=False)
    report["input_boundaries"] = {"long_query_full_tokens": long_length,
        "long_query_processed_tokens": long_prepped["input_ids"].shape[1], "empty_query_output_shape": list(blank.shape),
        "required_product_behavior": "Reject blank input; preserve or explicitly decompose/rewrite overlong questions before encoding. No silent truncation contract is implemented by this spike."}

    table = lancedb.connect(baseline["db_cache_path"]).open_table("scale")
    report["index_stats"] = [{"name": i.name, "config": str(i), "stats": str(table.index_stats(i.name))} for i in table.list_indices()]
    qfirst = model.encode_query(data["queries"][0]["text"], batch_size=1, convert_to_numpy=True, show_progress_bar=False)
    report["ann_plan"] = search(table, "vector", qfirst, data["queries"][0]["text"], exact=False).explain_plan()
    report["hybrid_ann_plan"] = search(table, "hybrid", qfirst, data["queries"][0]["text"], exact=False).explain_plan()
    assert "ANNSubIndex" in report["ann_plan"] and "MultivectorScoring" in report["ann_plan"]
    # Baseline 4 probes/refine 5 missed the preregistered 0.90 agreement threshold.
    # Bounded exploratory tuning on this same development set, not held-out validation.
    encoded = [model.encode_query(q["text"], batch_size=1, convert_to_numpy=True, show_progress_bar=False)
               for q in data["queries"]]
    report["ann_tuning"] = {"scope": "Same synthetic development set; baseline is preserved in results.json",
                             "baseline_recall_at_5": baseline["scale"]["ann_recall_at_5"], "candidates": []}
    selected_probes, selected_refine = 4, 5
    for probes, refine in [(8, 10), (16, 20)]:
        trials = []
        for q, vec, exact in zip(data["queries"], encoded, baseline["scale"]["exact_reference"]):
            started = time.perf_counter()
            hits = search(table, "vector", vec, q["text"], limit=5, exact=False, probes=probes).refine_factor(refine).to_list()
            latency = ms(started)
            ids = [h["id"] for h in hits]
            trials.append({"id": q["id"], "ids": ids, "search_ms": latency,
                           "recall_at_5": len(set(ids).intersection(exact["ids"])) / 5})
        recall = float(np.mean([r["recall_at_5"] for r in trials]))
        report["ann_tuning"]["candidates"].append({"nprobes": probes, "refine_factor": refine,
            "mean_recall_at_5": recall, "search_ms": summary([r["search_ms"] for r in trials]), "queries": trials})
        if selected_probes == 4 and recall >= 0.90:
            selected_probes, selected_refine = probes, refine
    report["selected_ann_settings"] = {"nprobes": selected_probes, "refine_factor": selected_refine,
        "scope": "First explored setting that passes this development set; no production default or held-out guarantee"}
    report["selected_ann_plan"] = search(table, "vector", qfirst, data["queries"][0]["text"],
        exact=False, probes=selected_probes).refine_factor(selected_refine).explain_plan()
    search(table, "hybrid", qfirst, data["queries"][0]["text"], exact=False).to_list()
    # Actual contiguous encode -> hybrid search timings, including DB builder and conversion.
    report["hybrid_ann_requests"] = []
    for q in data["queries"]:
        start = time.perf_counter()
        vec = model.encode_query(q["text"], batch_size=1, convert_to_numpy=True, show_progress_bar=False)
        encode_time = ms(start)
        hits = search(table, "hybrid", vec, q["text"], exact=False,
                      probes=selected_probes).refine_factor(selected_refine).to_list()
        report["hybrid_ann_requests"].append({"id": q["id"], "encode_ms": encode_time,
            "total_ms": ms(start), "returned_ids": [h["id"] for h in hits]})
    report["hybrid_ann_request_ms"] = summary([r["total_ms"] for r in report["hybrid_ann_requests"]])
    report["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    (HERE / "runtime-checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    emit("runtime_checks_complete", latency_ms=report["hybrid_ann_request_ms"], mask=report["mask"],
         index_stats=report["index_stats"], input_boundaries=report["input_boundaries"])


if __name__ == "__main__":
    main()
