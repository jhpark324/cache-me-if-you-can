import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Dialog, IconButton } from "@radix-ui/themes";
import { Check, FileText, Plus, Search, X } from "lucide-react";
import { api, post, uid, errorText } from "./api";
import { Markdown } from "./Markdown";
import { loadConcepts } from "./useConceptCatalog";
import type {
  Capture,
  CaptureSummary,
  Concept,
  MutationResult,
  Page,
  SourceDetail,
  SourceRef,
} from "./types";
function useRequestId() {
  const current = useRef<{ key: string; id: string } | null>(null);
  return (payload: unknown) => {
    const key = JSON.stringify(payload);
    if (current.current?.key !== key) current.current = { key, id: uid() };
    return current.current.id;
  };
}
export function SourceReview({
  record,
  onSaved,
  onClose,
}: {
  record: Capture;
  onSaved: (result: MutationResult) => void;
  onClose: () => void;
}) {
  const [body, setBody] = useState(record.body_markdown),
    [reason, setReason] = useState(""),
    [sources, setSources] = useState<{ ref: SourceRef; title: string }[]>(
      record.sources.map((s, i) => ({
        ref: s.source,
        title: `기존 출처 ${i + 1}`,
      })),
    ),
    [query, setQuery] = useState(""),
    [matches, setMatches] = useState<CaptureSummary[]>([]),
    [candidate, setCandidate] = useState<Capture | null>(null),
    [reference, setReference] = useState<SourceDetail | null>(null),
    [referenceLabel, setReferenceLabel] = useState(""),
    [busy, setBusy] = useState(false),
    [finding, setFinding] = useState(false),
    [error, setError] = useState("");
  const idFor = useRequestId(),
    lookupVersion = useRef(0);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      setFinding(true);
      try {
        const result = await api<Page<CaptureSummary>>(
          "/captures?limit=20&query=" + encodeURIComponent(query),
        );
        if (active) setMatches(result.items.filter((r) => r.id !== record.id));
      } catch (e) {
        if (active) setError(errorText(e));
      } finally {
        if (active) setFinding(false);
      }
    }, 220);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query, record.id]);
  async function preview(id: string) {
    const version = ++lookupVersion.current;
    setError("");
    setCandidate(null);
    setReference(null);
    setReferenceLabel("");
    try {
      const capture = await api<Capture>("/captures/" + id);
      if (version === lookupVersion.current) setCandidate(capture);
    } catch (e) {
      if (version === lookupVersion.current) setError(errorText(e));
    }
  }
  async function viewSource(ref: SourceRef, label: string) {
    const version = ++lookupVersion.current;
    setError("");
    setCandidate(null);
    setReference(null);
    setReferenceLabel(label);
    try {
      const detail = await post<SourceDetail>("/sources/resolve", ref);
      if (version === lookupVersion.current) setReference(detail);
    } catch (e) {
      if (version === lookupVersion.current) setError(errorText(e));
    }
  }
  function addCandidate() {
    if (!candidate) return;
    const ref = {
      capture_id: candidate.id,
      revision_id: candidate.revision_id,
    };
    setSources((prev) =>
      prev.some(
        (s) =>
          s.ref.capture_id === ref.capture_id &&
          s.ref.revision_id === ref.revision_id &&
          !s.ref.node_id &&
          s.ref.body_start == null,
      )
        ? prev
        : [...prev, { ref, title: candidate.title || "제목 없는 기록" }],
    );
    setCandidate(null);
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const payload = {
      capture_id: record.id,
      expected_revision_id: record.revision_id,
      expected_state_version: record.state_version,
      replacement_sources: sources.map((s) => s.ref),
      review_reason: reason.trim(),
      body_markdown: body,
    };
    try {
      const result = await post<MutationResult>(
        `/captures/${record.id}/source-review`,
        { ...payload, request_id: idFor(payload) },
      );
      onSaved(result);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save}>
      <div className="panel-heading">
        <Dialog.Title data-initial-focus tabIndex={-1}>
          출처 재검토
        </Dialog.Title>
        <IconButton
          type="button"
          aria-label="출처 재검토 닫기"
          variant="ghost"
          onClick={onClose}
        >
          <X />
        </IconButton>
      </div>
      <p className="muted">
        현재 본문과 근거를 확인하고, 필요한 출처를 교체하거나 목록에서
        제외하세요.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <label className="field">
        기록 내용
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="body-editor review-body"
          required
        />
      </label>
      <h3 className="management-heading">사용할 출처</h3>
      {!sources.length && (
        <p className="notice">
          연결할 출처가 없습니다. 근거 연결을 제거하는 이유를 아래에 남겨주세요.
        </p>
      )}
      <div className="review-source-list">
        {sources.map((source, index) => (
          <div
            className="review-source-row"
            key={JSON.stringify(source.ref) + index}
          >
            <button
              type="button"
              className="text-button"
              onClick={() => void viewSource(source.ref, source.title)}
            >
              <FileText />
              {source.title}
            </button>
            <IconButton
              type="button"
              aria-label={`${source.title} 제외`}
              variant="ghost"
              onClick={() =>
                setSources((prev) => prev.filter((_, i) => i !== index))
              }
            >
              <X />
            </IconButton>
          </div>
        ))}
      </div>
      {reference && (
        <section className="reference-preview">
          <div className="part-label">
            {referenceLabel} ·{" "}
            {reference.is_current ? "현재 저장본" : "당시 저장본"}
          </div>
          <h4>{reference.capture.title || "제목 없는 기록"}</h4>
          <Markdown>{reference.text}</Markdown>
        </section>
      )}
      <details className="source-picker">
        <summary>다른 기록을 출처로 추가</summary>
        <label className="field">
          <span className="picker-label">
            <Search />
            기록 찾기
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="제목이나 내용으로 검색"
          />
        </label>
        {finding && (
          <p role="status" className="muted">
            기록을 찾고 있어요
          </p>
        )}
        <div className="source-candidates">
          {matches.map((r) => (
            <button
              type="button"
              key={r.id}
              className="source-candidate"
              onClick={() => void preview(r.id)}
            >
              <strong>{r.title || "제목 없는 기록"}</strong>
              <span>{r.excerpt}</span>
            </button>
          ))}
        </div>
        {!finding && !matches.length && (
          <p className="muted">선택할 기록이 없습니다.</p>
        )}
        {candidate && (
          <section className="reference-preview">
            <h4>{candidate.title || "제목 없는 기록"}</h4>
            {candidate.review_state === "needs_review" && (
              <p className="notice">이 기록도 출처 재검토가 필요합니다.</p>
            )}
            <Markdown>{candidate.body_markdown}</Markdown>
            <Button
              type="button"
              variant="soft"
              onClick={addCandidate}
              disabled={candidate.review_state === "needs_review"}
            >
              <Plus />이 기록을 출처에 추가
            </Button>
          </section>
        )}
      </details>
      <label className="field">
        정정 이유
        <textarea
          className="reason-input"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="어떤 근거를 확인했고 무엇을 바꾸었나요?"
          required
        />
      </label>
      <div className="dialog-actions">
        <Button
          type="button"
          variant="soft"
          color="gray"
          onClick={onClose}
          disabled={busy}
        >
          취소
        </Button>
        <Button type="submit" disabled={busy || !reason.trim() || !body.trim()}>
          <Check />
          {busy ? "저장 중…" : "재검토 저장"}
        </Button>
      </div>
    </form>
  );
}
export function ConceptEditor({
  record,
  onSaved,
  onClose,
}: {
  record: Capture;
  onSaved: (result: MutationResult) => void;
  onClose: () => void;
}) {
  const [concepts, setConcepts] = useState<Concept[]>([]),
    [selected, setSelected] = useState(record.concepts.map((c) => c.id)),
    [query, setQuery] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const idFor = useRequestId();
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    (async () => {
      try {
        const all = await loadConcepts(controller.signal);
        if (active) setConcepts(all);
      } catch (e) {
        if (active) setError(errorText(e));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, []);
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const payload = {
      capture_id: record.id,
      expected_revision_id: record.revision_id,
      expected_state_version: record.state_version,
      concept_ids: selected,
    };
    try {
      const result = await api<MutationResult>(
        `/captures/${record.id}/concepts`,
        {
          method: "PUT",
          body: JSON.stringify({ ...payload, request_id: idFor(payload) }),
        },
      );
      onSaved(result);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const filtered = concepts.filter((c) =>
    [c.name, ...(c.aliases || [])].some((n) =>
      n.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
    ),
  );
  return (
    <form onSubmit={save}>
      <div className="panel-heading">
        <Dialog.Title data-initial-focus tabIndex={-1}>
          기록의 주제 정정
        </Dialog.Title>
        <IconButton
          type="button"
          aria-label="주제 정정 닫기"
          variant="ghost"
          onClick={onClose}
        >
          <X />
        </IconButton>
      </div>
      <p className="muted">선택한 주제만 이 기록에 연결합니다.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <label className="field">
        주제 찾기
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="주제 이름이나 별칭"
        />
      </label>
      {loading ? (
        <p role="status" className="muted">
          주제를 불러오는 중
        </p>
      ) : (
        <div className="concept-choices">
          {filtered.map((c) => (
            <label className="concept-choice" key={c.id}>
              <input
                type="checkbox"
                checked={selected.includes(c.id)}
                onChange={(e) =>
                  setSelected((prev) =>
                    e.target.checked
                      ? [...prev, c.id]
                      : prev.filter((id) => id !== c.id),
                  )
                }
              />
              <span>
                {c.name}
                {c.description && <small>{c.description}</small>}
              </span>
            </label>
          ))}
        </div>
      )}
      {!loading && !filtered.length && (
        <p className="muted">선택할 주제가 없습니다.</p>
      )}
      <p className="field-hint">
        {selected.length}개 선택 · 모두 해제하면 기록의 주제 연결을 제거합니다.
      </p>
      <div className="dialog-actions">
        <Button
          type="button"
          variant="soft"
          color="gray"
          disabled={busy}
          onClick={onClose}
        >
          취소
        </Button>
        <Button type="submit" disabled={busy || loading} onClick={() => {}}>
          <Check />
          {busy ? "저장 중…" : "주제 저장"}
        </Button>
      </div>
    </form>
  );
}
