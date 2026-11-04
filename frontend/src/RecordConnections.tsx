import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Button, Dialog, IconButton } from "@radix-ui/themes";
import {
  ArrowRight,
  Check,
  FileText,
  Plus,
  RefreshCw,
  Search,
  Unlink,
  X,
} from "lucide-react";
import { api, errorText, post, uid } from "./api";
import { Markdown } from "./Markdown";
import {
  RELATION_LABELS,
  type Capture,
  type CaptureSummary,
  type MutationResult,
  type Page,
  type RelationType,
  type RelationView,
  type SourceDetail,
  type SourceRef,
} from "./types";
export interface PickedReference {
  capture: Capture;
  source: SourceRef;
  text: string;
}
function whole(record: Capture): PickedReference {
  return {
    capture: record,
    source: { capture_id: record.id, revision_id: record.revision_id },
    text: record.body_markdown,
  };
}
function useRequestId() {
  const last = useRef<{ key: string; id: string } | null>(null);
  return (payload: unknown) => {
    const key = JSON.stringify(payload);
    if (last.current?.key !== key) last.current = { key, id: uid() };
    return last.current.id;
  };
}
function ErrorText({ error }: { error: string }) {
  return error ? (
    <p className="error" role="alert">
      {error}
    </p>
  ) : null;
}

export function ReferencePicker({
  label,
  value,
  onChange,
  initial,
  excludeId,
  precise = false,
}: {
  label: string;
  value: PickedReference | null;
  onChange: (value: PickedReference | null) => void;
  initial?: Capture;
  excludeId?: string;
  precise?: boolean;
}) {
  const [query, setQuery] = useState(""),
    [matches, setMatches] = useState<CaptureSummary[]>([]),
    [candidate, setCandidate] = useState<Capture | null>(initial || null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [range, setRange] = useState<{
      start: number;
      end: number;
      text: string;
    } | null>(null),
    [mode, setMode] = useState<"whole" | "span" | "node">(
      precise ? "span" : "whole",
    );
  const sequence = useRef(0);
  useEffect(() => {
    if (precise && mode === "whole") setMode("span");
  }, [precise, mode]);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const result = await api<Page<CaptureSummary>>(
          "/captures?limit=20&query=" + encodeURIComponent(query),
        );
        if (active) setMatches(result.items.filter((r) => r.id !== excludeId));
      } catch (e) {
        if (active) setError(errorText(e));
      } finally {
        if (active) setLoading(false);
      }
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query, excludeId]);
  async function selectCandidate(id: string) {
    const current = ++sequence.current;
    setError("");
    setRange(null);
    try {
      const capture = await api<Capture>("/captures/" + id);
      if (current === sequence.current) setCandidate(capture);
    } catch (e) {
      if (current === sequence.current) setError(errorText(e));
    }
  }
  function selectSpan() {
    if (!candidate || !range) return;
    onChange({
      capture: candidate,
      source: {
        capture_id: candidate.id,
        revision_id: candidate.revision_id,
        body_start: range.start,
        body_end: range.end,
      },
      text: range.text,
    });
  }
  return (
    <fieldset className="reference-picker">
      <legend>{label}</legend>
      {value && (
        <div className="reference-selection">
          <div className="section-heading">
            <strong>{value.capture.title || "제목 없는 기록"}</strong>
            <IconButton
              type="button"
              variant="ghost"
              aria-label={`${label} 선택 해제`}
              onClick={() => onChange(null)}
            >
              <X />
            </IconButton>
          </div>
          <p>
            {value.source.node_id
              ? "선택한 내용"
              : value.source.body_start != null
                ? "선택한 구간"
                : "기록 전체"}{" "}
            · {value.text}
          </p>
        </div>
      )}
      <details open={!value}>
        <summary>{value ? "선택 변경" : "기록과 내용 선택"}</summary>
        <label className="field">
          <span className="picker-label">
            <Search />
            {label} 기록 찾기
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="제목이나 내용으로 검색"
          />
        </label>
        <ErrorText error={error} />
        {loading && (
          <p className="muted" role="status">
            기록을 찾고 있어요
          </p>
        )}
        <div className="source-candidates">
          {matches.map((r) => (
            <button
              key={r.id}
              type="button"
              className="source-candidate"
              onClick={() => void selectCandidate(r.id)}
            >
              <strong>{r.title || "제목 없는 기록"}</strong>
              <span>{r.excerpt}</span>
            </button>
          ))}
        </div>
        {!loading && !matches.length && (
          <p className="muted">선택할 기록이 없습니다.</p>
        )}
        {candidate && (
          <section className="reference-preview">
            <h4>{candidate.title || "제목 없는 기록"}</h4>
            {candidate.review_state === "needs_review" && (
              <p className="notice">이 기록의 출처를 먼저 재검토해 주세요.</p>
            )}
            <label className="field">
              {label} 사용할 내용
              <select
                aria-label={`${label} 사용할 내용`}
                value={mode}
                onChange={(e) => {
                  setMode(e.target.value as typeof mode);
                  setRange(null);
                }}
              >
                {!precise && <option value="whole">기록 전체</option>}
                <option value="span">본문에서 구간 선택</option>
                {candidate.node_status === "current" &&
                  candidate.nodes.length > 0 && (
                    <option value="node">세부 항목 선택</option>
                  )}
              </select>
            </label>
            {mode === "whole" ? (
              <>
                <Markdown>{candidate.body_markdown}</Markdown>
                <Button
                  type="button"
                  variant="soft"
                  disabled={candidate.review_state === "needs_review"}
                  onClick={() => onChange(whole(candidate))}
                >
                  <Check />이 기록 선택
                </Button>
              </>
            ) : mode === "span" ? (
              <>
                <p className="field-hint">
                  원문에서 사용할 문장을 드래그하거나 Shift와 방향키로
                  선택하세요.
                </p>
                <textarea
                  className="span-selector"
                  aria-label={`${label} 원문 구간`}
                  readOnly
                  value={candidate.body_markdown}
                  onSelect={(e) => {
                    const {
                      selectionStart: start,
                      selectionEnd: end,
                      value: text,
                    } = e.currentTarget;
                    setRange(
                      end > start
                        ? {
                            start: Array.from(text.slice(0, start)).length,
                            end: Array.from(text.slice(0, end)).length,
                            text: text.slice(start, end),
                          }
                        : null,
                    );
                  }}
                />
                {range && <p className="selected-span">{range.text}</p>}
                <Button
                  type="button"
                  variant="soft"
                  disabled={!range || candidate.review_state === "needs_review"}
                  onClick={selectSpan}
                >
                  <Check />
                  선택한 구간 사용
                </Button>
              </>
            ) : (
              <div className="source-candidates">
                {candidate.nodes.map((n) => (
                  <button
                    type="button"
                    className="source-candidate"
                    key={n.id}
                    disabled={candidate.review_state === "needs_review"}
                    onClick={() =>
                      onChange({
                        capture: candidate,
                        source: n.source,
                        text: n.text,
                      })
                    }
                  >
                    <strong>{n.label || "세부 항목"}</strong>
                    <span>{n.text}</span>
                  </button>
                ))}
              </div>
            )}
          </section>
        )}
      </details>
    </fieldset>
  );
}

export function MergeDialog({
  record,
  onSaved,
  onClose,
}: {
  record: Capture;
  onSaved: (result: MutationResult) => void;
  onClose: () => void;
}) {
  const [sources, setSources] = useState<PickedReference[]>([]),
    [body, setBody] = useState(record.body_markdown),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const requestId = useRequestId();
  function add(value: PickedReference | null) {
    if (value)
      setSources((prev) =>
        prev.some(
          (p) => JSON.stringify(p.source) === JSON.stringify(value.source),
        )
          ? prev
          : [...prev, value],
      );
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!sources.length) return;
    setBusy(true);
    const payload = {
      target_capture_id: record.id,
      expected_revision_id: record.revision_id,
      expected_state_version: record.state_version,
      sources: sources.map((s) => s.source),
      merged_body_markdown: body,
    };
    try {
      onSaved(
        await post<MutationResult>(`/captures/${record.id}/merge`, {
          ...payload,
          request_id: requestId(payload),
        }),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <div className="panel-heading">
        <Dialog.Title data-initial-focus tabIndex={-1}>
          기록 병합
        </Dialog.Title>
        <IconButton
          type="button"
          aria-label="병합 닫기"
          variant="ghost"
          onClick={onClose}
        >
          <X />
        </IconButton>
      </div>
      <p className="muted">
        <strong>{record.title || "제목 없는 기록"}</strong>에 내용을 합칩니다.
        선택한 원본 기록은 그대로 남습니다.
      </p>
      <ErrorText error={error} />
      <ReferencePicker
        label="병합할 출처"
        value={null}
        onChange={add}
        excludeId={record.id}
      />
      {sources.length > 0 && (
        <section className="merge-selections">
          <h3>선택한 출처 {sources.length}개</h3>
          {sources.map((source, i) => (
            <div className="merge-source" key={JSON.stringify(source.source)}>
              <div className="section-heading">
                <strong>{source.capture.title || "제목 없는 기록"}</strong>
                <IconButton
                  type="button"
                  variant="ghost"
                  aria-label={`병합 출처 ${i + 1} 제외`}
                  onClick={() =>
                    setSources((prev) => prev.filter((_, index) => index !== i))
                  }
                >
                  <X />
                </IconButton>
              </div>
              <Markdown>{source.text}</Markdown>
              <Button
                type="button"
                variant="ghost"
                onClick={() =>
                  setBody(
                    (prev) =>
                      `${prev}\n\n## ${source.capture.title || "추가한 내용"}\n\n${source.text}`,
                  )
                }
              >
                <Plus />
                최종 본문에 추가
              </Button>
            </div>
          ))}
        </section>
      )}
      <label className="field">
        병합할 최종 내용
        <textarea
          className="body-editor"
          aria-label="병합할 최종 내용"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          required
        />
      </label>
      <p className="field-hint">
        선택한 내용이 최종 본문에 정확히 반영되었는지 확인해 주세요.
      </p>
      <div className="dialog-actions">
        <Button
          type="button"
          color="gray"
          variant="soft"
          disabled={busy}
          onClick={onClose}
        >
          취소
        </Button>
        <Button
          type="submit"
          disabled={busy || !sources.length || !body.trim()}
        >
          <Check />
          {busy ? "병합 중…" : "이 기록에 병합"}
        </Button>
      </div>
    </form>
  );
}

function RelationCard({
  relation,
  onSource,
  onRetract,
}: {
  relation: RelationView;
  onSource: (ref: SourceRef) => void;
  onRetract: (relation: RelationView) => void;
}) {
  const [details, setDetails] = useState<{
      source: SourceDetail;
      target: SourceDetail;
      evidence: SourceDetail;
    } | null>(null),
    [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all([
      post<SourceDetail>("/sources/resolve", relation.source),
      post<SourceDetail>("/sources/resolve", relation.target),
      post<SourceDetail>("/sources/resolve", relation.evidence),
    ])
      .then(([source, target, evidence]) => {
        if (active) setDetails({ source, target, evidence });
      })
      .catch(() => {
        if (active) setUnavailable(true);
      });
    return () => {
      active = false;
    };
  }, [relation]);
  if (unavailable)
    return (
      <p className="notice">
        현재 조회할 수 없는 관계입니다. 목록을 새로고침해 주세요.
      </p>
    );
  if (!details)
    return (
      <p className="muted" role="status">
        관계의 근거를 확인하는 중
      </p>
    );
  return (
    <article className="relation-card">
      <span className="part-label">
        {RELATION_LABELS[relation.relation_type]}
      </span>
      <div className="relation-direction">
        <button
          type="button"
          className="text-button"
          onClick={() => onSource(relation.source)}
        >
          {details.source.capture.title || "제목 없는 기록"}
        </button>
        <ArrowRight aria-hidden="true" />
        <button
          type="button"
          className="text-button"
          onClick={() => onSource(relation.target)}
        >
          {details.target.capture.title || "제목 없는 기록"}
        </button>
      </div>
      {relation.scope_note && <p>{relation.scope_note}</p>}
      <button
        type="button"
        className="text-button"
        onClick={() => onSource(relation.evidence)}
      >
        <FileText />
        근거 확인 · {details.evidence.capture.title || "제목 없는 기록"}
      </button>
      {relation.evidence_note && (
        <p className="muted">{relation.evidence_note}</p>
      )}
      <Button type="button" variant="ghost" onClick={() => onRetract(relation)}>
        <Unlink />
        관계 철회
      </Button>
    </article>
  );
}

export function RelationsDialog({
  record,
  onClose,
  onChanged,
}: {
  record: Capture;
  onClose: () => void;
  onChanged: (message: string) => void;
}) {
  const [items, setItems] = useState<RelationView[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [creating, setCreating] = useState(false),
    [type, setType] = useState<RelationType>("related_to"),
    [source, setSource] = useState<PickedReference | null>(whole(record)),
    [target, setTarget] = useState<PickedReference | null>(null),
    [evidence, setEvidence] = useState<PickedReference | null>(null),
    [scope, setScope] = useState(""),
    [note, setNote] = useState(""),
    [busy, setBusy] = useState(false),
    [retracting, setRetracting] = useState<RelationView | null>(null),
    [reason, setReason] = useState(""),
    [preview, setPreview] = useState<SourceDetail | null>(null),
    [notice, setNotice] = useState("");
  const requestId = useRequestId(),
    loadSequence = useRef(0),
    previewSequence = useRef(0);
  const load = useCallback(
    async (next?: string | null) => {
      const version = ++loadSequence.current;
      setLoading(true);
      setError("");
      try {
        const page = await api<Page<RelationView>>(
          `/relations?capture_id=${record.id}&limit=20${next ? "&cursor=" + encodeURIComponent(next) : ""}`,
        );
        if (version !== loadSequence.current) return;
        setItems((prev) => (next ? [...prev, ...page.items] : page.items));
        setCursor(page.next_cursor);
      } catch (e) {
        if (version === loadSequence.current) setError(errorText(e));
      } finally {
        if (version === loadSequence.current) setLoading(false);
      }
    },
    [record.id],
  );
  useEffect(() => {
    void load();
    return () => {
      loadSequence.current++;
      previewSequence.current++;
    };
  }, [load]);
  async function showSource(ref: SourceRef) {
    const version = ++previewSequence.current;
    setPreview(null);
    setError("");
    try {
      const detail = await post<SourceDetail>("/sources/resolve", ref);
      if (version === previewSequence.current) setPreview(detail);
    } catch (e) {
      if (version === previewSequence.current) setError(errorText(e));
    }
  }
  function changeType(value: RelationType) {
    setType(value);
    if (value === "supersedes") {
      if (source && !source.source.node_id && source.source.body_start == null)
        setSource(null);
      if (target && !target.source.node_id && target.source.body_start == null)
        setTarget(null);
      if (
        evidence &&
        !evidence.source.node_id &&
        evidence.source.body_start == null
      )
        setEvidence(null);
    }
  }
  async function create(e: FormEvent) {
    e.preventDefault();
    if (!source || !target || !evidence) return;
    setError("");
    setBusy(true);
    const payload = {
      relation_type: type,
      source: source.source,
      target: target.source,
      evidence: evidence.source,
      scope_note: scope.trim() || null,
      evidence_note: note.trim() || null,
    };
    try {
      await post<RelationView>("/relations", {
        ...payload,
        request_id: requestId(payload),
      });
      setCreating(false);
      setTarget(null);
      setEvidence(null);
      setScope("");
      setNote("");
      setNotice("관계를 저장했습니다.");
      onChanged("관계를 저장했습니다.");
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function retract(e: FormEvent) {
    e.preventDefault();
    if (!retracting || !reason.trim()) return;
    setBusy(true);
    setError("");
    const payload = {
      relation_id: retracting.id,
      withdrawal_reason: reason.trim(),
    };
    try {
      await post<RelationView>(`/relations/${retracting.id}/retraction`, {
        ...payload,
        request_id: requestId(payload),
      });
      setRetracting(null);
      setReason("");
      setPreview(null);
      setNotice("관계를 철회했습니다. 기록은 유지됩니다.");
      onChanged("관계를 철회했습니다.");
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const precise = type === "supersedes";
  return (
    <>
      <div className="panel-heading">
        <Dialog.Title data-initial-focus tabIndex={-1}>
          기록의 관계
        </Dialog.Title>
        <IconButton
          type="button"
          aria-label="관계 관리 닫기"
          variant="ghost"
          onClick={onClose}
        >
          <X />
        </IconButton>
      </div>
      <p className="muted">{record.title || "제목 없는 기록"}</p>
      <ErrorText error={error} />
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {creating ? (
        <form onSubmit={create}>
          <label className="field">
            관계의 의미
            <select
              aria-label="관계의 의미"
              value={type}
              onChange={(e) => changeType(e.target.value as RelationType)}
            >
              {Object.entries(RELATION_LABELS).map(([key, label]) => (
                <option value={key} key={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {precise ? (
            <p className="notice">
              새 조건 → 이전 조건 순서입니다. 양쪽 내용과 근거의 정확한 구간을
              선택하세요.
            </p>
          ) : (
            <p className="field-hint">
              시작 기록 → 대상 기록 방향으로 저장합니다.
            </p>
          )}
          <ReferencePicker
            label={precise ? "새 조건" : "시작"}
            value={source}
            onChange={setSource}
            initial={record}
            precise={precise}
          />
          <ReferencePicker
            label={precise ? "이전 조건" : "대상"}
            value={target}
            onChange={setTarget}
            precise={precise}
          />
          <ReferencePicker
            label="근거"
            value={evidence}
            onChange={setEvidence}
            initial={record}
            precise={precise}
          />
          <label className="field">
            적용 범위{precise ? " · 필수" : ""}
            <textarea
              className="reason-input"
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              placeholder="누구의 어떤 상황과 시점에 해당하나요?"
              required={precise}
            />
          </label>
          <label className="field">
            근거 설명{precise ? " · 필수" : ""}
            <textarea
              className="reason-input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="선택한 내용이 이 관계를 어떻게 뒷받침하나요?"
              required={precise}
            />
          </label>
          <div className="dialog-actions">
            <Button
              type="button"
              variant="soft"
              color="gray"
              disabled={busy}
              onClick={() => {
                setCreating(false);
                setError("");
              }}
            >
              작성 취소
            </Button>
            <Button
              type="submit"
              disabled={
                busy ||
                !source ||
                !target ||
                !evidence ||
                (precise && (!scope.trim() || !note.trim()))
              }
            >
              <Check />
              {busy ? "저장 중…" : "관계 저장"}
            </Button>
          </div>
        </form>
      ) : retracting ? (
        <form onSubmit={retract}>
          <h3>{RELATION_LABELS[retracting.relation_type]} 관계 철회</h3>
          <p className="muted">
            기록을 삭제하지 않고 이 관계의 사용을 중단합니다.
          </p>
          <label className="field">
            철회 이유
            <textarea
              className="reason-input"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          </label>
          <div className="dialog-actions">
            <Button
              type="button"
              variant="soft"
              color="gray"
              disabled={busy}
              onClick={() => {
                setRetracting(null);
                setError("");
              }}
            >
              취소
            </Button>
            <Button type="submit" disabled={busy || !reason.trim()}>
              <Unlink />
              {busy ? "철회 중…" : "이유를 남기고 철회"}
            </Button>
          </div>
        </form>
      ) : (
        <>
          <div className="section-heading">
            <Button
              variant="soft"
              onClick={() => {
                setCreating(true);
                setNotice("");
                setPreview(null);
              }}
            >
              <Plus />
              관계 추가
            </Button>
            <Button
              variant="ghost"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw />
              새로고침
            </Button>
          </div>
          {preview && (
            <section className="reference-preview">
              <div className="section-heading">
                <h4>{preview.capture.title || "제목 없는 기록"}</h4>
                <IconButton
                  type="button"
                  variant="ghost"
                  aria-label="관계 근거 닫기"
                  onClick={() => setPreview(null)}
                >
                  <X />
                </IconButton>
              </div>
              <span className="part-label">
                {preview.is_current ? "현재 저장본" : "당시 저장본"}
              </span>
              <Markdown>{preview.text}</Markdown>
            </section>
          )}
          {items.map((relation) => (
            <RelationCard
              key={relation.id}
              relation={relation}
              onSource={(ref) => void showSource(ref)}
              onRetract={(value) => {
                setRetracting(value);
                setReason("");
                setNotice("");
                setPreview(null);
              }}
            />
          ))}
          {loading && (
            <p className="muted" role="status">
              관계를 불러오는 중
            </p>
          )}
          {!loading && !items.length && (
            <p className="muted">아직 연결한 관계가 없습니다.</p>
          )}
          {cursor && !loading && (
            <Button variant="ghost" onClick={() => void load(cursor)}>
              더 보기
            </Button>
          )}
        </>
      )}
    </>
  );
}
