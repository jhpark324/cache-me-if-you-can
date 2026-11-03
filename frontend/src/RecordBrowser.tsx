import { useId, useMemo } from "react";
import {
  ChevronRight,
  FileText,
  LoaderCircle,
  Lock,
  Plus,
  RefreshCw,
} from "lucide-react";
import { KIND_LABELS, type CaptureSummary, type Concept } from "./types";
import "./RecordBrowser.css";

export type RecordSort = "created_desc" | "title_asc";

export interface RecordBrowserProps {
  view: "library" | "timeline";
  records: CaptureSummary[];
  loading: boolean;
  error: string;
  cursor: string | null;
  kind: string;
  concept: string;
  month: string;
  sort: RecordSort;
  concepts: Concept[];
  conceptLoading: boolean;
  conceptError: string;
  onKindChange: (value: string) => void;
  onConceptChange: (value: string) => void;
  onMonthChange: (value: string) => void;
  onSortChange: (value: RecordSort) => void;
  onLoadMore: () => void;
  onRetry: () => void;
  onRetryConcepts: () => void;
  onOpen: (id: string) => void;
  onCreate: () => void;
  onReset: () => void;
}

/** Local calendar month, expressed as an inclusive/exclusive UTC API range. */
export function monthBounds(
  month: string,
): { created_from: string; created_before: string } | null {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month);
  if (!match || Number(match[1]) < 1) return null;
  const start = new Date(0);
  // setFullYear preserves years 0001–0099 instead of interpreting them as 1901–1999.
  start.setFullYear(Number(match[1]), Number(match[2]) - 1, 1);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setMonth(end.getMonth() + 1);
  return {
    created_from: start.toISOString(),
    created_before: end.toISOString(),
  };
}

const fullDate = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const monthDay = new Intl.DateTimeFormat("ko-KR", {
  month: "long",
  day: "numeric",
});
const weekday = new Intl.DateTimeFormat("ko-KR", { weekday: "long" });

function parsedDate(value: string): Date | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function localDay(date: Date): string {
  return `${String(date.getFullYear()).padStart(4, "0")}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export interface RecordDateGroup {
  key: string;
  date: Date | null;
  records: CaptureSummary[];
}

export function groupRecordsByDate(
  records: CaptureSummary[],
): RecordDateGroup[] {
  const ordered = [...records].sort((left, right) => {
    const a = parsedDate(left.created_at)?.getTime() ?? -Infinity;
    const b = parsedDate(right.created_at)?.getTime() ?? -Infinity;
    return a === b ? left.id.localeCompare(right.id) : b - a;
  });
  const groups = new Map<string, RecordDateGroup>();
  for (const record of ordered) {
    const date = parsedDate(record.created_at);
    const key = date ? localDay(date) : "unknown";
    const existing = groups.get(key);
    if (existing) existing.records.push(record);
    else groups.set(key, { key, date, records: [record] });
  }
  return [...groups.values()];
}

function indexLabel(status: string): string {
  return (
    {
      pending: "검색 준비 중",
      running: "검색 준비 중",
      ready: "검색 가능",
      failed: "검색 준비 실패",
      excluded: "검색 제외",
    }[status] || status
  );
}

function RecordRow({
  record,
  timeline,
  onOpen,
}: {
  record: CaptureSummary;
  timeline: boolean;
  onOpen: (id: string) => void;
}) {
  const descriptionId = useId();
  const date = parsedDate(record.created_at);
  const title = record.title?.trim() || "제목 없는 기록";
  const preview = record.excerpt || record.body_excerpt || record.preview;
  const hasStatus =
    record.visibility === "private" ||
    record.review_state === "needs_review" ||
    record.index_state.status !== "ready";

  return (
    <li className="rb-item">
      <button
        type="button"
        className={`rb-record${timeline ? " rb-record-timeline" : ""}`}
        data-record-id={record.id}
        onClick={() => onOpen(record.id)}
        aria-label={`${title} — 기록 열기`}
        aria-describedby={descriptionId}
        title={title}
      >
        {!timeline && <FileText className="rb-file" aria-hidden="true" />}
        <span className="rb-record-copy">
          <span className="rb-record-title">{title}</span>
          {preview && <span className="rb-record-preview">{preview}</span>}
          {hasStatus && (
            <span className="rb-record-status" aria-hidden="true">
              {record.visibility === "private" && (
                <span>
                  <Lock aria-hidden="true" />
                  비공개
                </span>
              )}
              {record.review_state === "needs_review" && <span>검토 필요</span>}
              {record.index_state.status !== "ready" && (
                <span>{indexLabel(record.index_state.status)}</span>
              )}
            </span>
          )}
        </span>
        <span className="rb-record-kinds" aria-hidden="true">
          {record.kinds.map((kind) => (
            <span key={kind}>{KIND_LABELS[kind] || kind}</span>
          ))}
        </span>
        {!timeline && (
          <span className="rb-record-date" aria-hidden="true">
            {date ? (
              <time dateTime={record.created_at}>{fullDate.format(date)}</time>
            ) : (
              "저장일 미상"
            )}
          </span>
        )}
        <ChevronRight className="rb-chevron" aria-hidden="true" />
        <span className="sr-only" id={descriptionId}>
          {record.kinds.map((kind) => KIND_LABELS[kind] || kind).join(", ")}
          {record.visibility === "private" ? ", 비공개" : ""}
          {record.review_state === "needs_review" ? ", 검토 필요" : ""}
          {record.index_state.status !== "ready"
            ? `, ${indexLabel(record.index_state.status)}`
            : ""}
          {date ? `, 저장일 ${fullDate.format(date)}` : ", 저장일 미상"}
        </span>
      </button>
    </li>
  );
}

export function RecordBrowser({
  view,
  records,
  loading,
  error,
  cursor,
  kind,
  concept,
  month,
  sort,
  concepts,
  conceptLoading,
  conceptError,
  onKindChange,
  onConceptChange,
  onMonthChange,
  onSortChange,
  onLoadMore,
  onRetry,
  onRetryConcepts,
  onOpen,
  onCreate,
  onReset,
}: RecordBrowserProps) {
  const headingId = useId();
  const groups = useMemo(() => groupRecordsByDate(records), [records]);
  const conceptNames = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of concepts)
      counts.set(item.name, (counts.get(item.name) || 0) + 1);
    return counts;
  }, [concepts]);
  const timeline = view === "timeline";
  const filtered = Boolean(kind || concept || (timeline && month));
  const missingConcept =
    concept && !concepts.some((item) => item.id === concept);

  return (
    <section
      className={`record-browser${timeline ? " rb-timeline" : ""}`}
      aria-labelledby={headingId}
    >
      <header className="rb-toolbar">
        <div className="rb-heading">
          <div className="rb-heading-copy">
            <h1 id={headingId}>{timeline ? "타임라인" : "모든 기록"}</h1>
            <span className="rb-count" aria-live="polite" aria-atomic="true">
              불러온 {records.length.toLocaleString("ko-KR")}개
            </span>
          </div>
          <button className="rb-create" type="button" onClick={onCreate}>
            <Plus aria-hidden="true" />새 기록
          </button>
        </div>
        <div className="rb-filters" role="group" aria-label="기록 필터">
          <label className="rb-filter">
            <span className="sr-only">기록 유형</span>
            <select
              aria-label="기록 유형"
              value={kind}
              onChange={(event) => onKindChange(event.target.value)}
            >
              <option value="">모든 유형</option>
              {Object.entries(KIND_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="rb-filter rb-concept-filter">
            <span className="sr-only">주제</span>
            <select
              aria-label="주제"
              value={concept}
              aria-busy={conceptLoading}
              onChange={(event) => onConceptChange(event.target.value)}
            >
              <option value="">
                {conceptLoading && !concepts.length
                  ? "주제 불러오는 중…"
                  : "모든 주제"}
              </option>
              {missingConcept && <option value={concept}>선택한 주제</option>}
              {concepts.map((item) => (
                <option key={item.id} value={item.id}>
                  {(conceptNames.get(item.name) || 0) > 1 && item.description
                    ? `${item.name} — ${item.description}`
                    : item.name}
                </option>
              ))}
            </select>
          </label>
          {filtered && (
            <button className="rb-reset" type="button" onClick={onReset}>
              필터 초기화
            </button>
          )}
          {timeline ? (
            <label className="rb-filter rb-period">
              <span>저장 월</span>
              <input
                type="month"
                aria-label="저장 월"
                value={month}
                onChange={(event) => onMonthChange(event.target.value)}
              />
            </label>
          ) : (
            <label className="rb-filter rb-sort">
              <span className="sr-only">기록 정렬</span>
              <select
                aria-label="기록 정렬"
                value={sort}
                onChange={(event) =>
                  onSortChange(event.target.value as RecordSort)
                }
              >
                <option value="created_desc">저장일 최신순</option>
                <option value="title_asc">제목순</option>
              </select>
            </label>
          )}
        </div>
        {conceptError && (
          <div className="rb-notice">
            <p role="alert">주제를 불러오지 못했습니다. {conceptError}</p>
            <button
              type="button"
              className="rb-retry"
              onClick={onRetryConcepts}
              disabled={conceptLoading}
            >
              <RefreshCw aria-hidden="true" />
              주제 다시 불러오기
            </button>
          </div>
        )}
      </header>
      <div className="rb-scroll" data-record-scroll>
        {error && (
          <div className="rb-notice rb-list-error">
            <p role="alert">기록을 불러오지 못했습니다. {error}</p>
            <button
              type="button"
              className="rb-retry"
              onClick={onRetry}
              disabled={loading}
            >
              <RefreshCw aria-hidden="true" />
              다시 불러오기
            </button>
          </div>
        )}
        {!loading && !error && !records.length && (
          <div className="rb-empty">
            <h2>
              {filtered
                ? "이 조건의 기록이 없어요"
                : "아직 저장한 기록이 없어요"}
            </h2>
            <p>
              {filtered
                ? "다른 유형이나 주제, 기간으로 살펴보세요."
                : "생각과 경험을 첫 기록으로 남겨 보세요."}
            </p>
            <button
              type="button"
              className="rb-secondary"
              onClick={filtered ? onReset : onCreate}
            >
              {filtered ? "필터 초기화" : "첫 기록 남기기"}
            </button>
          </div>
        )}
        {records.length > 0 &&
          (timeline ? (
            <div
              className="rb-timeline-groups"
              aria-label="저장일별 기록"
              aria-busy={loading}
            >
              {groups.map((group, index) => (
                <section
                  className={`rb-date-group${index === 0 && group.date ? " rb-latest" : ""}`}
                  key={group.key}
                  aria-label={
                    group.date
                      ? `${fullDate.format(group.date)} 저장한 기록`
                      : "저장일 미상 기록"
                  }
                >
                  <div className="rb-date-heading">
                    <h2>
                      {group.date ? (
                        <time dateTime={group.key}>
                          {monthDay.format(group.date)}
                        </time>
                      ) : (
                        "저장일 미상"
                      )}
                    </h2>
                    {group.date && (
                      <span className="rb-weekday">
                        {group.date.getFullYear()} ·{" "}
                        {weekday.format(group.date)}
                      </span>
                    )}
                    {index === 0 && group.date && (
                      <span
                        className="rb-recent"
                        title="현재 목록에서 가장 최근 저장일"
                      >
                        최근
                      </span>
                    )}
                  </div>
                  <ul className="rb-date-records">
                    {group.records.map((record) => (
                      <RecordRow
                        key={record.id}
                        record={record}
                        timeline
                        onOpen={onOpen}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <ul
              className="rb-records"
              aria-label="기록 목록"
              aria-busy={loading}
            >
              {records.map((record) => (
                <RecordRow
                  key={record.id}
                  record={record}
                  timeline={false}
                  onOpen={onOpen}
                />
              ))}
            </ul>
          ))}
        {loading && (
          <div
            className={`rb-loading${records.length ? "" : " rb-loading-initial"}`}
            role="status"
          >
            <LoaderCircle aria-hidden="true" />
            기록을 불러오는 중
          </div>
        )}
        {cursor && !error && (
          <div className="rb-footer">
            <button
              type="button"
              className="rb-secondary"
              onClick={onLoadMore}
              disabled={loading}
            >
              기록 더 보기
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
