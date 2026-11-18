export const KIND_LABELS = {
  knowledge: "지식",
  episode: "경험·회고",
  context: "맥락",
  idea: "아이디어·계획",
  decision: "결정",
  artifact: "자료",
} as const;
export type RecordKind = keyof typeof KIND_LABELS;
export interface SourceRef {
  capture_id: string;
  revision_id: string;
  node_id?: string | null;
  body_start?: number | null;
  body_end?: number | null;
}
export function sourceKey(source: SourceRef): string {
  return JSON.stringify([
    source.capture_id,
    source.revision_id,
    source.node_id ?? null,
    source.body_start ?? null,
    source.body_end ?? null,
  ]);
}
export type ArticleCitation =
  | { kind: "record"; source: SourceRef }
  | { kind: "external"; title: string; url: string; note: string };
export interface ArticleSummary {
  id: string;
  title: string;
  summary: string;
  topics: string[];
  created_at: string;
  updated_at: string;
}
export interface ArticleDocument extends ArticleSummary {
  revision_id: string;
  revision_no: number;
  body_markdown: string;
  citations: ArticleCitation[];
  sources: SourceView[];
  review_state: string;
}
export interface Concept {
  id: string;
  name: string;
  description?: string;
  aliases?: string[];
}
export interface SourceView {
  source: SourceRef;
  resolved_source?: SourceRef | null;
  availability: string;
  review_state: string;
  reason?: string;
}
export interface NodeView {
  id: string;
  kind: string;
  text: string;
  label?: string;
  source: SourceRef;
  origin: string;
  verification_state: string;
  concepts: Concept[];
}
export interface Capture {
  id: string;
  revision_id: string;
  revision_no: number;
  state_version: number;
  title?: string | null;
  body_markdown: string;
  kinds: RecordKind[];
  visibility: "public" | "private";
  completion_state?: "incomplete" | "completed" | null;
  created_at: string;
  updated_at: string;
  revision_created_at?: string;
  is_current: boolean;
  node_status: string;
  index_state: { status: string; error_code?: string };
  concept_state?: {
    status: string;
    job_id?: string | null;
    error_code?: string | null;
    unresolved_hints?: string[];
  };
  concepts: Concept[];
  concept_hints: string[];
  nodes: NodeView[];
  sources: SourceView[];
  review_state: string;
  review_reason?: string;
  event_time?: {
    expression?: string;
    precision: string;
    value?: string;
    timezone?: string;
  } | null;
}
export type CaptureSummary = Pick<
  Capture,
  | "id"
  | "revision_id"
  | "state_version"
  | "title"
  | "kinds"
  | "visibility"
  | "updated_at"
  | "created_at"
  | "index_state"
  | "review_state"
> & {
  excerpt?: string;
  body_excerpt?: string;
  preview?: string;
};
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}
export interface MutationResult {
  capture: Capture | null;
  committed_ref: SourceRef | null;
  request_id: string;
  replayed: boolean;
  result_state: string;
  warnings: string[];
}
export interface SourceDetail {
  source: SourceRef;
  is_current: boolean;
  current_revision_id?: string;
  text: string;
  capture: Capture;
  node?: NodeView;
  review_state: string;
}
export interface SearchHit {
  source: SourceRef;
  excerpt: string;
  matched_spans?: unknown[];
  matched_node_ids?: string[];
  score: number;
  score_kind: string;
  title?: string;
}
export interface AnswerResult {
  answer_id: string;
  limitations: string[];
  parts: {
    part_id: string;
    kind: "stored_knowledge" | "general_explanation";
    text: string;
    sources: SourceRef[];
  }[];
  evidence_status: string;
  sources: SourceRef[];
  retrieval?: {
    items: {
      source: SourceRef;
      label: string;
      capture_label: string;
      cited: boolean;
    }[];
    truncated: boolean;
  };
}
export interface DeletionPreview {
  confirmation_token: string;
  capture_id: string;
  expected_revision_id: string;
  expected_state_version: number;
  title?: string;
  preview?: string;
  expires_at: string;
}
export interface GraphData {
  nodes: {
    id: string;
    kind: string;
    label?: string;
    name?: string;
    kinds?: RecordKind[];
    concept_id?: string;
    source?: SourceRef;
    cited?: boolean;
    capture_label?: string;
    concept_state?: { status: string; error_code?: string | null };
  }[];
  edges: {
    id?: string;
    source: string;
    target: string;
    kind?: string;
    relation_type?: string;
  }[];
  truncated: boolean;
  retrieval_truncated?: boolean;
}
export interface Settings {
  auth?: {
    connected: boolean;
    pending_login?: boolean;
    request_blocked?: {
      code: string;
      message: string;
      retryable: boolean;
    } | null;
    plan_enabled?: boolean;
    email?: string;
    active_account_id?: string;
    selected_model?: string | null;
    selected_reasoning_effort?: string | null;
    models?: {
      slug: string;
      display_name: string;
      supported_reasoning_efforts?: { effort: string; description: string }[];
      default_reasoning_effort?: string | null;
    }[];
    error?: string;
  };
  index?: {
    status: string;
    ready: boolean;
    index_counts: {
      pending: number;
      failed: number;
      ready: number;
      excluded: number;
    };
    error_code?: string | null;
  };
  data_dir?: string;
  [key: string]: unknown;
}
export const RELATION_LABELS = {
  related_to: "관련 있음",
  clarifies: "명확히 설명함",
  corrects: "정정함",
  supports: "뒷받침함",
  contradicts: "상충함",
  merged_from: "병합해 옴",
  supersedes: "이전 조건을 대체함",
} as const;
export type RelationType = keyof typeof RELATION_LABELS;
export interface RelationView {
  id: string;
  relation_type: RelationType;
  source: SourceRef;
  target: SourceRef;
  evidence: SourceRef;
  scope_note?: string | null;
  evidence_note?: string | null;
  created_at: string;
  withdrawn_at?: string | null;
  withdrawal_reason?: string | null;
}
