import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { ScrollableArea } from "@astryxdesign/core/ScrollableArea";
import { IconButton } from "@astryxdesign/core/IconButton";
import { Tooltip } from "@astryxdesign/core/Tooltip";
import { Token } from "@astryxdesign/core/Token";
import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";
import { Heading } from "@astryxdesign/core/Heading";
import {
  ArrowLeft,
  ArrowUp,
  Clock3,
  Check,
  ChevronRight,
  FileText,
  LoaderCircle,
  Lock,
  Menu,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { api, post, streamQuestion, errorText, uid, ApiError } from "./api";
import { Markdown } from "./Markdown";
import AnswerResponse, { buildAnswerDraft } from "./AnswerResponse";
import SearchLoading from "./SearchLoading";
import { RecordDates } from "./RecordDates";
import { exampleGraph } from "./exampleGraph";
import { sourceGraphNodeId, withRetrievalGraph } from "./retrievalGraph";
import RecordEditor from "./RecordEditor";
import { RecordBrowser, monthBounds } from "./RecordBrowser";
import SettingsPanel from "./SettingsPanel";
import { Tool, ErrorMessage, Loading } from "./ui";
import { useConceptCatalog } from "./useConceptCatalog";
import { useHomeGraph } from "./useHomeGraph";
import { SourceReview, ConceptEditor } from "./ManagementDialogs";
import { MergeDialog, RelationsDialog } from "./RecordConnections";
import {
  KIND_LABELS,
  type Capture,
  type CaptureSummary,
  type RecordKind,
  type Page,
  type SourceRef,
  type SourceDetail,
  type MutationResult,
  type AnswerResult,
  type DeletionPreview,
  type GraphData,
} from "./types";
const Graph = lazy(() => import("./Graph"));
const NODE_LABELS: Record<string, string> = {
  explanation: "설명",
  interpretation: "해석",
  hypothesis: "가설",
  question: "질문",
  event: "사건",
  emotion: "감정",
  proposal: "제안",
  decision: "결정",
  action: "행동",
  result: "결과",
};
const ORIGIN_LABELS: Record<string, string> = {
  user_report: "내가 전한 내용",
  user_interpretation: "내 해석",
  ai_explanation: "AI 설명",
  unspecified: "작성 맥락 미지정",
};
const VERIFICATION_LABELS: Record<string, string> = {
  unknown: "검증 정보 없음",
  unverified: "검증하지 않음",
  verified: "검증됨",
};
const date = (value: string) =>
  new Date(value).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
const indexLabel = (status: string) =>
  ({
    pending: "검색 준비 중",
    ready: "검색 가능",
    failed: "검색 준비 실패",
    excluded: "검색 제외",
  })[status] || status;
const CONCEPT_FAILURE_HELP: Record<string, string> = {
  MODEL_USAGE_LIMIT:
    "ChatGPT의 앱 사용 한도에 도달했습니다. 한도를 확인한 뒤 다시 시도해 주세요.",
  AUTH_REQUIRED:
    "설정에서 ChatGPT 로그인과 답변 모델 선택을 확인한 뒤 다시 시도해 주세요.",
  LOGIN_REQUIRED: "설정에서 ChatGPT에 다시 로그인한 뒤 시도해 주세요.",
  MODEL_AUTH_REJECTED:
    "계정 인증을 확인하지 못했습니다. 설정에서 ChatGPT에 다시 로그인해 주세요.",
  AUTH_REJECTED:
    "계정 인증을 확인하지 못했습니다. 설정에서 ChatGPT에 다시 로그인해 주세요.",
  PLAN_PERMISSION_REQUIRED:
    "ChatGPT에서 이 앱의 모델 사용 권한을 허용한 뒤 다시 시도해 주세요.",
  MODEL_PERMISSION_DENIED:
    "계정 또는 워크스페이스의 모델 사용 권한을 확인한 뒤 다시 시도해 주세요.",
  MODEL_REQUIRED: "설정에서 답변 모델을 선택한 뒤 다시 시도해 주세요.",
  MODEL_UNAVAILABLE:
    "모델에 연결하지 못했습니다. 연결 상태와 AI 설정을 확인한 뒤 다시 시도해 주세요.",
  MODELS_UNAVAILABLE:
    "모델 목록을 확인하지 못했습니다. 설정에서 모델 목록을 다시 불러와 주세요.",
  REASONING_UNAVAILABLE:
    "선택한 추론 수준을 사용할 수 없습니다. 설정에서 답변 모델의 추론 수준을 다시 선택해 주세요.",
  MODEL_REQUEST_INVALID:
    "선택한 모델이 요청을 지원하지 않습니다. 설정에서 다른 모델을 선택한 뒤 다시 시도해 주세요.",
  MODEL_FORMAT_ERROR:
    "모델의 응답을 주제로 정리하지 못했습니다. 다시 시도하거나 주제 정정에서 직접 선택해 주세요.",
  MODEL_TIMEOUT:
    "모델의 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
  MODEL_RATE_LIMIT:
    "모델 요청이 일시적으로 많습니다. 잠시 후 다시 시도해 주세요.",
  MODEL_TEMPORARILY_UNAVAILABLE:
    "모델 서비스에 일시적인 문제가 있습니다. 잠시 후 다시 시도해 주세요.",
  MODEL_CHANGED:
    "처리 중 답변 모델이 변경되었습니다. 현재 모델로 다시 시도해 주세요.",
};
function useMedia(query: string) {
  const [v, setV] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const m = matchMedia(query),
      f = () => setV(m.matches);
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, [query]);
  return v;
}
function KindBadges({ values }: { values: RecordKind[] }) {
  return (
    <>
      {values.map((k) => (
        <Token key={k} color="gray" size="sm" label={KIND_LABELS[k] || k} />
      ))}
    </>
  );
}
export default function App() {
  const [records, setRecords] = useState<CaptureSummary[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [listLoading, setListLoading] = useState(true),
    [listError, setListError] = useState("");
  const {
    concepts,
    error: conceptError,
    loading: conceptsLoading,
    refresh: refreshConcepts,
  } = useConceptCatalog();
  type View = "home" | "library" | "timeline";
  const [view, setView] = useState<View>(() =>
    location.hash === "#timeline"
      ? "timeline"
      : location.hash === "#library"
        ? "library"
        : "home",
  );
  const viewRef = useRef<View>(view);
  const recordOrigin = useRef<View>(view === "home" ? "library" : view);
  const recordTrigger = useRef<string | null>(null);
  const [kind, setKind] = useState(""),
    [concept, setConcept] = useState("");
  const [month, setMonth] = useState("");
  const [sort, setSort] = useState<"created_desc" | "title_asc">(
    "created_desc",
  );
  const activeMonth = view === "timeline" ? month : "";
  const activeSort = view === "timeline" ? "created_desc" : sort;
  const listController = useRef<AbortController | null>(null);
  const [query, setQuery] = useState(""),
    [answer, setAnswer] = useState<AnswerResult | null>(null),
    [searching, setSearching] = useState(false),
    [searched, setSearched] = useState(false),
    [searchError, setSearchError] = useState(""),
    [searchStatus, setSearchStatus] = useState("");
  const [searchAttempt, setSearchAttempt] = useState(0);
  const [source, setSource] = useState<SourceDetail | null>(null),
    [sourceOpen, setSourceOpen] = useState(false),
    [sourceLoading, setSourceLoading] = useState(false),
    [sourceError, setSourceError] = useState("");
  const [selected, setSelected] = useState<Capture | null>(null),
    [detailLoading, setDetailLoading] = useState(false),
    [detailError, setDetailError] = useState("");
  const [requestedRecordId, setRequestedRecordId] = useState<string | null>(
    null,
  );
  const [sourceSelection, setSourceSelection] = useState<SourceRef | null>(
    null,
  );
  const recordHeading = useRef<HTMLHeadingElement>(null);
  const recordErrorHeading = useRef<HTMLHeadingElement>(null);
  const menuToggle = useRef<HTMLSpanElement>(null);
  const menuDestination = useRef<"record" | "editor" | "settings" | null>(null);
  const [editor, setEditor] = useState<{
      record?: Capture;
      body?: string;
      sources?: SourceRef[];
    } | null>(null),
    [settingsOpen, setSettingsOpen] = useState(false),
    [navOpen, setNavOpen] = useState(false);
  const [deletePreview, setDeletePreview] = useState<DeletionPreview | null>(
      null,
    ),
    [deleteBusy, setDeleteBusy] = useState(false),
    [deleteError, setDeleteError] = useState("");
  const [toast, setToast] = useState(""),
    [paused, setPaused] = useState(
      () => localStorage.getItem("cache-me-motion") === "paused",
    );
  const [reviewOpen, setReviewOpen] = useState(false),
    [conceptOpen, setConceptOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false),
    [relationsOpen, setRelationsOpen] = useState(false),
    [conceptRetryBusy, setConceptRetryBusy] = useState(false);
  const conceptRetryReceipt = useRef<{ key: string; id: string } | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null),
    [graphLoading, setGraphLoading] = useState(false);
  const [exampleMode, setExampleMode] = useState(false),
    [exampleSelection, setExampleSelection] = useState("");
  useEffect(() => {
    if (selected || editor) {
      setExampleMode(false);
      setExampleSelection("");
    }
  }, [selected, editor]);
  const {
    data: homeGraph,
    loading: homeGraphLoading,
    error: homeGraphError,
    refresh: loadHomeGraph,
  } = useHomeGraph(
    view === "home" &&
      !selected &&
      !detailLoading &&
      !detailError &&
      !exampleMode &&
      !settingsOpen &&
      !editor,
  );
  const refreshHomeGraph = useCallback(() => {
    setExampleMode(false);
    setExampleSelection("");
    void loadHomeGraph();
  }, [loadHomeGraph]);
  const systemReduced = useMedia("(prefers-reduced-motion: reduce)"),
    reduced = systemReduced || paused,
    mobile = useMedia("(max-width: 1279px)"),
    compactNav = useMedia("(max-width: 800px)");
  const searchArea = useRef<HTMLElement>(null);
  const [searchBottom, setSearchBottom] = useState(96);
  const displayGraph = useMemo(
    () => withRetrievalGraph(homeGraph, answer?.retrieval),
    [homeGraph, answer?.retrieval],
  );
  const hasRetrieval = displayGraph.nodes.some(
    (node) => node.kind === "retrieved_chunk",
  );
  const pendingConnections =
    homeGraph?.nodes.filter(
      (node) =>
        node.kind === "capture" && node.concept_state?.status === "pending",
    ) || [];
  const runningConnections =
    homeGraph?.nodes.filter(
      (node) =>
        node.kind === "capture" && node.concept_state?.status === "running",
    ) || [];
  const failedConnections =
    homeGraph?.nodes.filter(
      (node) =>
        node.kind === "capture" && node.concept_state?.status === "failed",
    ) || [];
  const reviewConnections =
    homeGraph?.nodes.filter(
      (node) =>
        node.kind === "capture" &&
        node.concept_state?.status === "needs_review",
    ) || [];
  useEffect(() => {
    const area = searchArea.current;
    if (!area) return;
    const measure = () => {
      const workspace = area.closest(".workspace");
      if (workspace)
        setSearchBottom(
          Math.ceil(
            area.getBoundingClientRect().bottom -
              workspace.getBoundingClientRect().top +
              12,
          ),
        );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(area);
    return () => observer.disconnect();
  }, [hasRetrieval]);
  const searchInput = useRef<HTMLInputElement>(null),
    searchController = useRef<AbortController | null>(null),
    searchVersion = useRef(0),
    sourceVersion = useRef(0),
    detailVersion = useRef(0),
    listVersion = useRef(0),
    deleteRequest = useRef(uid()),
    sourceTrigger = useRef<HTMLElement | null>(null),
    sourceHeading = useRef<HTMLHeadingElement | null>(null);
  const loadRecords = useCallback(
    async (more = false) => {
      const version = ++listVersion.current;
      listController.current?.abort();
      const controller = new AbortController();
      listController.current = controller;
      if (!more) {
        setRecords([]);
        setCursor(null);
      }
      setListLoading(true);
      setListError("");
      try {
        const p = new URLSearchParams({ limit: "20", sort: activeSort });
        const bounds = monthBounds(activeMonth);
        if (bounds) {
          p.set("created_from", bounds.created_from);
          p.set("created_before", bounds.created_before);
        }
        if (kind) p.set("kinds", kind);
        if (concept) p.set("concept_ids", concept);
        if (more && cursor) p.set("cursor", cursor);
        const result = await api<Page<CaptureSummary>>("/captures?" + p, {
          signal: controller.signal,
        });
        if (version !== listVersion.current) return;
        setRecords((prev) =>
          more
            ? [
                ...new Map(
                  [...prev, ...result.items].map((item) => [item.id, item]),
                ).values(),
              ]
            : result.items,
        );
        setCursor(result.next_cursor);
      } catch (e) {
        if (!controller.signal.aborted && version === listVersion.current)
          setListError(errorText(e));
      } finally {
        if (version === listVersion.current) setListLoading(false);
      }
    },
    [kind, concept, cursor, activeMonth, activeSort],
  );
  useEffect(() => {
    void loadRecords();
    return () => {
      listController.current?.abort();
      listVersion.current++;
    };
  }, [kind, concept, activeMonth, activeSort]);
  useEffect(() => {
    if (new URLSearchParams(location.search).has("login")) {
      setSettingsOpen(true);
      history.replaceState(null, "", location.pathname + location.hash);
    }
    return () => {
      searchController.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(""), 4500);
    return () => clearTimeout(id);
  }, [toast]);
  const closeSource = useCallback(() => {
    sourceVersion.current++;
    setSourceOpen(false);
    setSource(null);
    setSourceSelection(null);
    setSourceError("");
    setSourceLoading(false);
    const trigger = sourceTrigger.current;
    sourceTrigger.current = null;
    requestAnimationFrame(() => {
      if (trigger?.isConnected) trigger.focus();
      else if (trigger) searchInput.current?.focus();
    });
  }, []);
  const openCapture = useCallback(async (id: string, updateHash = true) => {
    const version = ++detailVersion.current;
    if (updateHash) {
      recordOrigin.current =
        viewRef.current === "home" ? "library" : viewRef.current;
      recordTrigger.current = id;
    } else {
      const origin =
        history.state?.recordOrigin === "timeline" ? "timeline" : "library";
      recordOrigin.current = origin;
      recordTrigger.current = id;
      viewRef.current = origin;
      setView(origin);
    }
    menuDestination.current = "record";
    setRequestedRecordId(id);
    searchController.current?.abort();
    searchVersion.current++;
    setSearched(false);
    setSearching(false);
    setAnswer(null);
    sourceVersion.current++;
    setSourceOpen(false);
    setSource(null);
    setSourceSelection(null);
    setDetailLoading(true);
    setDetailError("");
    setSelected(null);
    setGraph(null);
    setGraphLoading(false);
    setNavOpen(false);
    if (updateHash)
      history.pushState(
        { recordOrigin: recordOrigin.current },
        "",
        "#capture/" + encodeURIComponent(id),
      );
    try {
      const r = await api<Capture>("/captures/" + id);
      if (version === detailVersion.current) setSelected(r);
    } catch (e) {
      if (version === detailVersion.current) setDetailError(errorText(e));
    } finally {
      if (version === detailVersion.current) setDetailLoading(false);
    }
  }, []);
  const goHome = useCallback(() => {
    detailVersion.current++;
    setRequestedRecordId(null);
    setSelected(null);
    setDetailLoading(false);
    setDetailError("");
    setGraph(null);
    setGraphLoading(false);
    closeSource();
    viewRef.current = "home";
    setView("home");
    history.pushState(null, "", location.pathname + location.search);
    setNavOpen(false);
  }, [closeSource]);
  const navigateView = useCallback(
    (target: View, push = true) => {
      detailVersion.current++;
      searchController.current?.abort();
      searchVersion.current++;
      setRequestedRecordId(null);
      setSelected(null);
      setDetailLoading(false);
      setDetailError("");
      setGraph(null);
      setGraphLoading(false);
      setSearched(false);
      setSearching(false);
      setAnswer(null);
      setSearchError("");
      setExampleMode(false);
      closeSource();
      viewRef.current = target;
      setView(target);
      setNavOpen(false);
      menuDestination.current = "record";
      if (push)
        history.pushState(
          null,
          "",
          location.pathname +
            location.search +
            (target === "home" ? "" : "#" + target),
        );
      requestAnimationFrame(() =>
        document.getElementById("main")?.focus({ preventScroll: true }),
      );
    },
    [closeSource],
  );
  const returnToRecords = useCallback(() => {
    navigateView(recordOrigin.current);
    requestAnimationFrame(() => {
      const id = recordTrigger.current;
      if (id)
        document
          .querySelector<HTMLElement>(`[data-record-id="${CSS.escape(id)}"]`)
          ?.focus({ preventScroll: true });
    });
  }, [navigateView]);
  useEffect(() => {
    const navigate = () => {
      const m = location.hash.match(/^#capture\/([^/]+)$/);
      if (m) {
        try {
          void openCapture(decodeURIComponent(m[1]), false);
        } catch {
          detailVersion.current++;
          setSelected(null);
          setRequestedRecordId(null);
          setDetailLoading(false);
          setDetailError(
            "기록 주소가 올바르지 않습니다. 지식 공간에서 기록을 다시 선택해 주세요.",
          );
        }
      } else {
        navigateView(
          location.hash === "#timeline"
            ? "timeline"
            : location.hash === "#library"
              ? "library"
              : "home",
          false,
        );
      }
    };
    navigate();
    addEventListener("popstate", navigate);
    return () => removeEventListener("popstate", navigate);
  }, [openCapture, navigateView]);
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if (
        (e.metaKey || e.ctrlKey) &&
        e.key.toLowerCase() === "k" &&
        !document.querySelector(
          'dialog[open], [role="dialog"], [role="alertdialog"]',
        )
      ) {
        e.preventDefault();
        searchInput.current?.focus();
      }
      if (
        e.key === "Escape" &&
        !e.defaultPrevented &&
        !(
          e.target instanceof Element &&
          e.target.closest(
            'dialog[open], [role="dialog"], [role="alertdialog"]',
          )
        )
      ) {
        if (sourceOpen) closeSource();
        else setNavOpen(false);
      }
    };
    addEventListener("keydown", f);
    return () => removeEventListener("keydown", f);
  }, [sourceOpen, closeSource]);
  const openSource = useCallback(async (ref: SourceRef) => {
    if (
      !(document.activeElement instanceof HTMLElement) ||
      !document.activeElement.closest(".source-panel, .source-mobile")
    ) {
      sourceTrigger.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
    }
    const version = ++sourceVersion.current;
    setSourceOpen(true);
    setSourceSelection(ref);
    setSource(null);
    setSourceLoading(true);
    setSourceError("");
    try {
      const result = await post<SourceDetail>("/sources/resolve", ref);
      if (version === sourceVersion.current) setSource(result);
    } catch (e) {
      if (version === sourceVersion.current) setSourceError(errorText(e));
    } finally {
      if (version === sourceVersion.current) setSourceLoading(false);
    }
  }, []);
  async function runSearch(e?: FormEvent) {
    e?.preventDefault();
    if (exampleMode || !query.trim()) return;
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    const version = ++searchVersion.current;
    setSearching(true);
    setSearchAttempt((attempt) => attempt + 1);
    setSearched(true);
    setAnswer(null);
    setSearchError("");
    setSearchStatus("저장된 지식을 찾고 있어요");
    closeSource();
    goHome();
    if (
      Array.from(query).length > 10_000 ||
      new TextEncoder().encode(query).byteLength > 65_536
    ) {
      setSearchError(
        "질문은 최대 10,000자까지 입력할 수 있습니다. 내용을 나누어 검색해 주세요.",
      );
      setSearching(false);
      setSearchStatus("");
      return;
    }
    let answerError = "";
    const requestId = uid();
    let completed = false;
    try {
      await streamQuestion(
        { request_id: requestId, question: query },
        controller.signal,
        (event, data) => {
          if (version !== searchVersion.current) return;
          const value = data as Record<string, unknown>;
          if (value.request_id && value.request_id !== requestId) return;
          if (event === "completed" || event === "answer") {
            const result = (value.result ||
              value.answer ||
              value) as unknown as AnswerResult;
            if (Array.isArray(result.parts)) {
              setAnswer(result);
              completed = true;
            }
          } else if (event === "progress" || event === "status") {
            const payload = (value.payload || value) as Record<string, unknown>;
            const status = String(
              payload.message || payload.stage || payload.status || "",
            );
            setSearchStatus(
              (
                {
                  searching: "저장된 지식을 찾고 있어요",
                  gathering: "출처를 확인하고 있어요",
                  reading: "출처를 확인하고 있어요",
                  answering: "답변을 정리하고 있어요",
                  generating: "답변을 정리하고 있어요",
                } as Record<string, string>
              )[status] || status,
            );
          } else if (event === "invalidated") {
            setAnswer(null);
            throw new ApiError(
              "ANSWER_INVALIDATED",
              "답변의 출처가 변경되었습니다. 다시 검색해 주세요.",
            );
          } else if (event === "error") {
            const payload = (value.error || value.payload || value) as Record<
              string,
              unknown
            >;
            throw new ApiError(
              String(payload.code || "ANSWER_FAILED"),
              String(payload.message || "답변을 생성하지 못했습니다."),
            );
          } else if (event === "cancelled") {
            throw new ApiError("CANCELLED", "검색이 취소되었습니다.");
          }
        },
      );
      if (!completed && !controller.signal.aborted)
        throw new ApiError(
          "INCOMPLETE_RESPONSE",
          "답변 연결이 끝났습니다. 다시 검색해 주세요.",
        );
    } catch (e) {
      if (version === searchVersion.current) {
        completed = false;
        setAnswer(null);
        closeSource();
        if ((e as Error).name !== "AbortError") answerError = errorText(e);
      }
    } finally {
      if (version === searchVersion.current) {
        setSearchError(completed ? "" : answerError);
        setSearching(false);
        setSearchStatus("");
      }
    }
  }
  function dismissSearch() {
    searchController.current?.abort();
    searchVersion.current++;
    setSearched(false);
    setSearching(false);
    setAnswer(null);
    setSearchError("");
    closeSource();
    searchInput.current?.focus();
  }
  async function saved(result: MutationResult) {
    refreshHomeGraph();
    refreshConcepts();
    setEditor(null);
    setReviewOpen(false);
    setConceptOpen(false);
    setMergeOpen(false);
    detailVersion.current++;
    setDetailLoading(false);
    setGraph(null);
    dismissSearch();
    if (!result.capture) {
      setToast("저장은 처리되었지만 현재 기록을 조회할 수 없습니다.");
      void loadRecords();
      return;
    }
    setSelected(result.capture);
    setRequestedRecordId(result.capture.id);
    setDetailError("");
    if (editor && !editor.record)
      history.pushState(
        { recordOrigin: recordOrigin.current },
        "",
        "#capture/" + result.capture.id,
      );
    else
      history.replaceState(
        { recordOrigin: recordOrigin.current },
        "",
        "#capture/" + result.capture.id,
      );
    setToast("저장한 내용을 확인해 주세요.");
    requestAnimationFrame(() =>
      recordHeading.current?.focus({ preventScroll: true }),
    );
    void loadRecords();
  }
  useEffect(() => {
    if (
      !selected ||
      !["pending", "running"].includes(selected.concept_state?.status || "") ||
      editor ||
      reviewOpen ||
      conceptOpen ||
      mergeOpen ||
      relationsOpen ||
      deletePreview
    )
      return;
    let active = true;
    const id = selected.id,
      version = detailVersion.current;
    const timer = setInterval(async () => {
      try {
        const current = await api<Capture>("/captures/" + id);
        if (active && version === detailVersion.current) {
          if (
            current.revision_id !== selected.revision_id ||
            current.state_version !== selected.state_version
          ) {
            setGraph(null);
            refreshHomeGraph();
          }
          if (
            !["pending", "running"].includes(
              current.concept_state?.status || "",
            )
          )
            refreshConcepts();
          setSelected((prev) => (prev?.id === id ? current : prev));
        }
      } catch (e) {
        if (
          active &&
          version === detailVersion.current &&
          e instanceof ApiError &&
          e.code === "NOT_FOUND"
        ) {
          setSelected(null);
          setDetailError(errorText(e));
        }
      }
    }, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [
    selected?.id,
    selected?.concept_state?.status,
    editor,
    reviewOpen,
    conceptOpen,
    mergeOpen,
    relationsOpen,
    deletePreview,
  ]);
  async function retryConcept() {
    if (!selected?.concept_state?.job_id) return;
    const payload = {
      capture_id: selected.id,
      expected_revision_id: selected.revision_id,
      expected_state_version: selected.state_version,
      job_id: selected.concept_state.job_id,
    };
    const key = JSON.stringify(payload);
    if (conceptRetryReceipt.current?.key !== key)
      conceptRetryReceipt.current = { key, id: uid() };
    setConceptRetryBusy(true);
    setDetailError("");
    const version = detailVersion.current;
    try {
      const result = await post<MutationResult>(
        `/captures/${selected.id}/concept-retry`,
        { ...payload, request_id: conceptRetryReceipt.current.id },
      );
      conceptRetryReceipt.current = null;
      if (version !== detailVersion.current) return;
      if (result.capture) {
        setSelected(result.capture);
        setGraph(null);
        setToast("주제 연결을 다시 요청했습니다.");
        void loadRecords();
      } else setDetailError("현재 기록을 조회할 수 없습니다.");
    } catch (e) {
      if (version === detailVersion.current) setDetailError(errorText(e));
    } finally {
      setConceptRetryBusy(false);
    }
  }
  async function prepareDelete() {
    if (!selected) return;
    const version = detailVersion.current;
    setDeleteError("");
    setDeleteBusy(true);
    try {
      const preview = await post<DeletionPreview>(
        `/captures/${selected.id}/deletion-preview`,
        {
          capture_id: selected.id,
          expected_revision_id: selected.revision_id,
          expected_state_version: selected.state_version,
        },
      );
      if (version !== detailVersion.current) return;
      deleteRequest.current = uid();
      setDeletePreview(preview);
    } catch (e) {
      if (version === detailVersion.current) setDetailError(errorText(e));
    } finally {
      setDeleteBusy(false);
    }
  }
  async function confirmDelete() {
    if (!deletePreview) return;
    setDeleteBusy(true);
    setDeleteError("");
    try {
      await api(`/captures/${deletePreview.capture_id}/deletion`, {
        method: "POST",
        body: JSON.stringify({
          request_id: deleteRequest.current,
          capture_id: deletePreview.capture_id,
          expected_revision_id: deletePreview.expected_revision_id,
          expected_state_version: deletePreview.expected_state_version,
          confirmation_token: deletePreview.confirmation_token,
        }),
      });
      setDeletePreview(null);
      refreshHomeGraph();
      goHome();
      dismissSearch();
      void loadRecords();
      setToast("기록을 삭제했습니다.");
    } catch (e) {
      setDeleteError(errorText(e));
    } finally {
      setDeleteBusy(false);
    }
  }
  async function showGraph() {
    if (!selected) return;
    const version = detailVersion.current;
    setGraphLoading(true);
    setDetailError("");
    try {
      const result = await api<GraphData>(`/captures/${selected.id}/neighbors`);
      if (version === detailVersion.current) setGraph(result);
    } catch (e) {
      if (version === detailVersion.current) setDetailError(errorText(e));
    } finally {
      if (version === detailVersion.current) setGraphLoading(false);
    }
  }
  function toggleMotion() {
    setPaused((v) => {
      localStorage.setItem("cache-me-motion", !v ? "paused" : "enabled");
      return !v;
    });
  }
  const sourceIsExcerpt =
    source !== null && source.text !== source.capture.body_markdown;
  const sourceContent = (
    <>
      <HStack className="panel-heading">
        <VStack>
          <Heading
            level={2}
            id="source-title"
            ref={sourceHeading}
            tabIndex={-1}
          >
            {source?.capture.title || "저장된 기록"}
          </Heading>
        </VStack>
        <Tool label="출처 닫기" onClick={closeSource}>
          <X />
        </Tool>
      </HStack>
      {sourceLoading ? (
        <Loading text="출처를 불러오는 중" />
      ) : sourceError ? (
        <VStack>
          <ErrorMessage error={sourceError} />
          {sourceSelection && (
            <Button
              onClick={() => void openSource(sourceSelection)}
              variant="secondary"
              label="출처 다시 불러오기"
              icon={<RefreshCw />}
            />
          )}
        </VStack>
      ) : (
        source && (
          <>
            <RecordDates
              capture={source.capture}
              isCurrent={source.is_current}
            />
            <HStack className="metadata">
              <KindBadges values={source.capture.kinds} />
              <Text type="inherit" color="inherit">
                {source.is_current
                  ? "현재 저장본"
                  : `과거 저장본 · 버전 ${source.capture.revision_no}`}
              </Text>
            </HStack>
            {!source.is_current && (
              <p className="notice">답변이 참조한 당시의 내용입니다.</p>
            )}
            {source.review_state === "needs_review" && (
              <p className="notice">출처가 변경되어 재검토가 필요합니다.</p>
            )}
            <VStack className="source-excerpt">
              {sourceIsExcerpt && <Heading level={3}>참조한 부분</Heading>}
              <Markdown>{source.text}</Markdown>
            </VStack>
            {sourceIsExcerpt && (
              <details>
                <summary>기록 전체 보기</summary>
                <Markdown>{source.capture.body_markdown}</Markdown>
              </details>
            )}
            <Button
              onClick={() => {
                void openCapture(source.capture.id);
                closeSource();
              }}
              variant="secondary"
              label="현재 기록 열기"
              icon={<ChevronRight />}
            />
          </>
        )
      )}
    </>
  );
  useEffect(() => {
    if (detailLoading) return;
    const frame = requestAnimationFrame(() => {
      if (selected) recordHeading.current?.focus({ preventScroll: true });
      else if (detailError)
        recordErrorHeading.current?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [selected?.id, detailLoading, detailError]);
  useEffect(() => {
    if (!compactNav) setNavOpen(false);
  }, [compactNav]);
  const navWasOpen = useRef(false);
  useEffect(() => {
    const restoreMenu =
      navWasOpen.current && !navOpen && compactNav && !menuDestination.current;
    navWasOpen.current = navOpen;
    if (!restoreMenu) return;
    const frame = requestAnimationFrame(() => {
      menuToggle.current
        ?.querySelector("button")
        ?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [navOpen, compactNav]);
  const sidebarContent = (
    <>
      <button
        className="brand"
        onClick={() => navigateView("home")}
        aria-label="Cache Me If You Can 홈"
      >
        <Text type="inherit" color="inherit">
          <Text type="inherit" color="inherit" className="brand-first">
            Cache Me
          </Text>
          <Text type="inherit" color="inherit" className="brand-second">
            If You Can
          </Text>
        </Text>
      </button>
      {compactNav && (
        <Tool label="메뉴 닫기" onClick={() => setNavOpen(false)}>
          <X />
        </Tool>
      )}
      <nav aria-label="공간 탐색">
        {(
          [
            ["home", "지식 공간", Network],
            ["library", "모든 기록", FileText],
            ["timeline", "타임라인", Clock3],
          ] as const
        ).map(([target, label, Icon]) => (
          <button
            key={target}
            className={`nav-button ${view === target ? "active" : ""}`}
            aria-current={view === target ? "page" : undefined}
            onClick={() => navigateView(target)}
          >
            <Icon aria-hidden="true" />
            {label}
          </button>
        ))}
      </nav>
      <VStack className="sidebar-space" />
      <button
        className="nav-button"
        onClick={() => {
          menuDestination.current = "settings";
          setSettingsOpen(true);
          setNavOpen(false);
        }}
      >
        <SettingsIcon />
        설정
      </button>
      <HStack className="local-label">내 기기에 저장</HStack>
    </>
  );
  return (
    <HStack
      className={`app-shell ${sourceOpen ? "has-source" : ""}`}
      data-view={view}
      data-reduced-motion={reduced}
    >
      <a
        href="#main"
        className="skip-link"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus({ preventScroll: true });
        }}
      >
        본문으로 이동
      </a>
      {!compactNav && (
        <aside className="sidebar glass" aria-label="주 메뉴">
          {sidebarContent}
        </aside>
      )}
      <Dialog
        isOpen={navOpen && compactNav}
        onOpenChange={setNavOpen}
        onKeyDownCapture={(event) => {
          if (event.key !== "Escape") return;
          // Close navigation on the first Escape, including a fading tooltip.
          event.preventDefault();
          event.stopPropagation();
          setNavOpen(false);
        }}
        className="sidebar glass nav-drawer"
        aria-describedby={undefined}
        width="var(--sidebar-width)"
        maxHeight="90dvh"
        purpose="info"
      >
        <DialogHeader
          className="nav-heading"
          title="기록과 탐색"
          hasDivider={false}
        />
        {sidebarContent}
      </Dialog>
      <VStack className="workspace" inert={Boolean(sourceOpen && mobile)}>
        <main
          id="main"
          className={`main-content ${view !== "home" ? "is-browsing" : ""} ${selected || detailLoading || detailError ? "has-detail" : ""} ${searched ? "is-searching" : ""} ${hasRetrieval ? "has-retrieval" : ""}`}
          tabIndex={-1}
        >
          <section
            ref={searchArea}
            className="search-area"
            aria-label="지식 검색"
          >
            <Heading level={1} className="sr-only">
              Cache Me If You Can — 지식 공간
            </Heading>
            <VStack className={`search-dock ${searched ? "has-answer" : ""}`}>
              <form className="search-form" onSubmit={runSearch}>
                {compactNav ? (
                  <Text
                    type="inherit"
                    color="inherit"
                    className="nav-toggle"
                    ref={menuToggle}
                  >
                    <Tooltip content="메뉴 열기">
                      <IconButton
                        className="app-icon-button"
                        id="menu-toggle"
                        type="button"
                        onClick={() => {
                          menuDestination.current = null;
                          setNavOpen(true);
                        }}
                        variant="ghost"
                        label="메뉴 열기"
                        icon={<Menu />}
                      />
                    </Tooltip>
                  </Text>
                ) : (
                  <Search aria-hidden="true" />
                )}
                <label htmlFor="search-input" className="sr-only">
                  저장된 지식 검색 또는 질문
                </label>
                <input
                  id="search-input"
                  ref={searchInput}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={
                    exampleMode
                      ? "예시 모드에서는 검색하지 않아요"
                      : "내 지식에서 무엇을 찾고 있나요?"
                  }
                  disabled={exampleMode}
                  autoComplete="off"
                  aria-keyshortcuts="Control+k Meta+k"
                />
                {!query && !exampleMode && (
                  <kbd className="search-shortcut" aria-hidden="true">
                    {navigator.platform.includes("Mac") ? "⌘ K" : "Ctrl K"}
                  </kbd>
                )}
                <IconButton
                  className="app-icon-button"
                  type="submit"
                  isDisabled={exampleMode || !query.trim()}
                  variant="primary"
                  label="검색"
                  icon={
                    searching ? (
                      <LoaderCircle
                        className="search-loading-spinner"
                        aria-hidden="true"
                      />
                    ) : (
                      <ArrowUp aria-hidden="true" />
                    )
                  }
                />
              </form>
              <p className="sr-only" role="status" aria-atomic="true">
                {searching ? searchStatus || "답변을 준비하고 있어요" : ""}
              </p>
              {searched && (
                <section
                  className="answer-area"
                  aria-label="검색 응답"
                  aria-busy={searching}
                >
                  <HStack className="section-heading">
                    <Text
                      type="inherit"
                      color="inherit"
                      className="section-kicker"
                    >
                      <Sparkles /> {searching ? "답변 준비 중" : "검색 응답"}
                    </Text>
                    <Tool label="검색 응답 닫기" onClick={dismissSearch}>
                      <X />
                    </Tool>
                  </HStack>
                  {searching && !answer && (
                    <SearchLoading
                      key={searchAttempt}
                      text={searchStatus || "답변을 준비하고 있어요"}
                    />
                  )}
                  <ErrorMessage error={searchError} />
                  {answer && (
                    <>
                      <AnswerResponse
                        answer={answer}
                        onOpenSource={openSource}
                      />
                      <Button
                        onClick={() => {
                          recordOrigin.current = "library";
                          recordTrigger.current = null;
                          setEditor({
                            body: buildAnswerDraft(answer),
                            sources: answer.sources,
                          });
                        }}
                        variant="ghost"
                        label="답변을 기록으로 저장"
                        icon={<Plus />}
                      />
                    </>
                  )}
                  {!searching && !answer && !searchError && (
                    <p className="muted">
                      관련 지식을 찾지 못했어요. 다른 단어로 검색해 보세요.
                    </p>
                  )}
                </section>
              )}
            </VStack>
          </section>
          {view !== "home" && (
            <VStack
              className="record-browser-host"
              hidden={Boolean(selected || detailLoading || detailError)}
            >
              <RecordBrowser
                view={view}
                records={records}
                loading={listLoading}
                error={listError}
                cursor={cursor}
                kind={kind}
                concept={concept}
                month={month}
                sort={sort}
                concepts={concepts}
                conceptLoading={conceptsLoading}
                conceptError={conceptError}
                onKindChange={setKind}
                onConceptChange={setConcept}
                onMonthChange={setMonth}
                onSortChange={setSort}
                onLoadMore={() => void loadRecords(true)}
                onRetry={() => void loadRecords()}
                onRetryConcepts={refreshConcepts}
                onOpen={(id) => void openCapture(id)}
                onCreate={() => {
                  recordOrigin.current = view;
                  recordTrigger.current = null;
                  setEditor({});
                }}
                onReset={() => {
                  setKind("");
                  setConcept("");
                  setMonth("");
                }}
              />
            </VStack>
          )}
          {detailLoading ? (
            <Loading text="기록을 불러오는 중" />
          ) : selected ? (
            <article className="record-detail glass">
              <HStack className="section-heading">
                <button className="text-button" onClick={returnToRecords}>
                  <ArrowLeft />
                  {recordOrigin.current === "timeline"
                    ? "타임라인"
                    : "모든 기록"}
                </button>
                <HStack className="row">
                  <Tool
                    label="기록 수정"
                    onClick={() => setEditor({ record: selected })}
                  >
                    <Pencil />
                  </Tool>
                  <Tool
                    label="기록 삭제"
                    onClick={() => void prepareDelete()}
                    disabled={deleteBusy}
                  >
                    <Trash2 />
                  </Tool>
                </HStack>
              </HStack>
              <ErrorMessage error={detailError} />
              <Heading
                level={1}
                id="record-title"
                ref={recordHeading}
                tabIndex={-1}
              >
                {selected.title || "제목 없는 기록"}
              </Heading>
              <HStack className="metadata">
                <KindBadges values={selected.kinds} />
                {selected.visibility === "private" && (
                  <Text type="inherit" color="inherit">
                    <Lock />
                    비공개
                  </Text>
                )}
                <Text type="inherit" color="inherit">
                  {date(selected.updated_at)}
                </Text>
                <Text type="inherit" color="inherit">
                  버전 {selected.revision_no}
                </Text>
                <Text type="inherit" color="inherit">
                  {indexLabel(selected.index_state.status)}
                </Text>
                {selected.completion_state && (
                  <Text type="inherit" color="inherit">
                    {selected.completion_state === "completed"
                      ? "완료"
                      : "미완료"}
                  </Text>
                )}
              </HStack>
              {selected.review_state === "needs_review" && (
                <p className="notice">
                  출처가 변경되었습니다. 현재 내용의 근거를 다시 확인해 주세요.
                </p>
              )}
              {selected.concept_state?.status === "failed" && (
                <VStack className="concept-status notice">
                  <VStack className="concept-failure-help">
                    <p>기록은 저장되었지만 주제를 연결하지 못했습니다.</p>
                    <p>
                      {CONCEPT_FAILURE_HELP[
                        selected.concept_state.error_code || ""
                      ] ||
                        "설정에서 AI 연결을 확인한 뒤 다시 시도하거나, 주제 정정에서 직접 선택해 주세요."}
                    </p>
                    {selected.concept_state.error_code ===
                      "MODEL_USAGE_LIMIT" && (
                      <a
                        href="https://chatgpt.com/settings/usage"
                        target="_blank"
                        rel="noreferrer"
                      >
                        ChatGPT 사용량 확인
                      </a>
                    )}
                  </VStack>
                  <Button
                    isDisabled={
                      conceptRetryBusy || !selected.concept_state.job_id
                    }
                    onClick={() => void retryConcept()}
                    variant="secondary"
                    label={
                      conceptRetryBusy ? "다시 요청 중…" : "주제 연결 다시 시도"
                    }
                    icon={<RefreshCw />}
                  />
                </VStack>
              )}
              {["pending", "running"].includes(
                selected.concept_state?.status || "",
              ) && (
                <p className="field-hint" role="status">
                  저장한 기록의 주제를 연결하고 있어요.
                </p>
              )}
              {selected.concept_state?.status === "needs_review" && (
                <p className="notice">
                  확정하기 어려운 주제는 연결을 보류했어요. 주제 정정에서
                  확인하고 직접 선택할 수 있어요.
                </p>
              )}
              <Markdown>{selected.body_markdown}</Markdown>
              <HStack className="management-actions">
                <Button
                  onClick={() => setMergeOpen(true)}
                  variant="ghost"
                  label="기록 병합"
                />
                <Button
                  onClick={() => setRelationsOpen(true)}
                  variant="ghost"
                  label="관계 관리"
                />
                <Button
                  onClick={() => setConceptOpen(true)}
                  variant="ghost"
                  label="주제 정정"
                />
                <Button
                  onClick={() => setReviewOpen(true)}
                  variant="ghost"
                  label="출처 재검토"
                />
              </HStack>
              {selected.concepts?.length > 0 && (
                <HStack className="chips">
                  {selected.concepts.map((c) => (
                    <Text
                      type="inherit"
                      color="inherit"
                      className="chip"
                      key={c.id}
                    >
                      {c.name}
                    </Text>
                  ))}
                </HStack>
              )}
              {selected.nodes?.length > 0 && (
                <details>
                  <summary>
                    세부 항목 {selected.nodes.length}개{" "}
                    {selected.node_status === "stale" ? "· 재구성 필요" : ""}
                  </summary>
                  {selected.nodes.map((n) => (
                    <section className="node-block" key={n.id}>
                      <Text
                        type="inherit"
                        color="inherit"
                        className="part-label"
                      >
                        {n.label || NODE_LABELS[n.kind] || n.kind}
                      </Text>
                      <p>{n.text}</p>
                      <Text type="inherit" color="inherit" className="muted">
                        {ORIGIN_LABELS[n.origin] || n.origin} ·{" "}
                        {VERIFICATION_LABELS[n.verification_state] ||
                          n.verification_state}
                      </Text>
                    </section>
                  ))}
                </details>
              )}
              {selected.sources?.length > 0 && (
                <VStack className="detail-sources">
                  <Heading level={3}>이 기록의 출처</Heading>
                  {selected.sources.map((s, i) => (
                    <button
                      className="chip"
                      key={i}
                      disabled={s.availability !== "available"}
                      onClick={() => void openSource(s.source)}
                    >
                      <FileText />
                      출처 {i + 1}
                      {s.availability !== "available"
                        ? " · 조회 불가"
                        : s.review_state === "needs_review"
                          ? " · 검토 필요"
                          : ""}
                    </button>
                  ))}
                </VStack>
              )}
              <Button
                onClick={() => void showGraph()}
                isDisabled={graphLoading}
                variant="secondary"
                label={graphLoading ? "연결을 불러오는 중" : "주변 지식 보기"}
                icon={<Network />}
              />
              {graph && (
                <Suspense fallback={<Loading text="그래프를 여는 중" />}>
                  <Graph data={graph} onSource={openSource} reduced={reduced} />
                </Suspense>
              )}
            </article>
          ) : detailError ? (
            <article className="detail-error glass">
              <Heading level={2} ref={recordErrorHeading} tabIndex={-1}>
                기록을 열 수 없어요
              </Heading>
              <ErrorMessage error={detailError} />
              <HStack className="detail-error-actions">
                {requestedRecordId && (
                  <Button
                    onClick={() => void openCapture(requestedRecordId, false)}
                    variant="secondary"
                    label="기록 다시 불러오기"
                    icon={<RefreshCw />}
                  />
                )}
                <Button
                  onClick={goHome}
                  variant="secondary"
                  label="지식 공간으로"
                  icon={<ArrowLeft />}
                />
              </HStack>
            </article>
          ) : (
            <VStack className="home-view-marker" />
          )}
        </main>
        <VStack
          className={`graph-stage ${searched || selected ? "is-reading" : ""} ${hasRetrieval ? "has-retrieval" : ""}`}
          style={hasRetrieval ? { top: searchBottom } : undefined}
          aria-label="내 지식 그래프"
          hidden={
            view !== "home" || Boolean(selected || detailLoading || detailError)
          }
        >
          {(exampleMode ||
            displayGraph.nodes.length > 0 ||
            displayGraph.retrieval_truncated) && (
            <Suspense fallback={<Loading text="그래프를 여는 중" />}>
              <Graph
                data={exampleMode ? exampleGraph : displayGraph}
                selectedId={
                  exampleMode
                    ? undefined
                    : (sourceOpen && sourceSelection
                        ? sourceGraphNodeId(displayGraph, sourceSelection)
                        : selected?.id) || null
                }
                onSource={openSource}
                onConcept={
                  exampleMode
                    ? undefined
                    : (id) => {
                        setConcept(id);
                        navigateView("library");
                      }
                }
                onPreview={
                  exampleMode
                    ? (node) =>
                        setExampleSelection(
                          node.label || node.name || "예시 항목",
                        )
                    : undefined
                }
                reduced={reduced}
                onToggleMotion={toggleMotion}
                motionDisabled={systemReduced}
                active={
                  view === "home" && !selected && !detailLoading && !detailError
                }
                fullStage
              />
            </Suspense>
          )}
          {exampleMode && (
            <HStack className="example-banner">
              <Token color="gray" size="sm" label="예시 · 읽기 전용" />
              <button
                className="text-button"
                onClick={() => {
                  setExampleMode(false);
                  setExampleSelection("");
                }}
              >
                내 지식으로 돌아가기 <X />
              </button>
            </HStack>
          )}
          {exampleMode && exampleSelection && (
            <VStack className="example-selection glass">
              <Text type="inherit" color="inherit" className="eyebrow">
                예시 항목
              </Text>
              <p>{exampleSelection}</p>
              <small>
                화면을 살펴보기 위한 예시입니다. 내 기록에 저장되지 않아요.
              </small>
            </VStack>
          )}
          {homeGraphLoading && !homeGraph && (
            <VStack className="graph-state">
              <Loading text="지식을 연결하는 중" />
            </VStack>
          )}
          {homeGraphError && !homeGraph && (
            <VStack className="graph-state graph-error glass">
              <ErrorMessage error={homeGraphError} />
              <Button
                onClick={refreshHomeGraph}
                variant="secondary"
                label="다시 불러오기"
              />
            </VStack>
          )}
          {homeGraph &&
            !displayGraph.nodes.length &&
            !homeGraphLoading &&
            !exampleMode && (
              <VStack
                className={`graph-empty ${searched || selected ? "is-behind" : ""}`}
              >
                <Heading level={2}>첫 번째 생각을 남겨보세요</Heading>
                <p>기록한 생각이 연결되고, 나만의 지식이 됩니다.</p>
                <Button
                  onClick={() => {
                    recordOrigin.current = "library";
                    recordTrigger.current = null;
                    setEditor({});
                  }}
                  variant="primary"
                  label="기록 시작하기"
                  icon={<Plus />}
                />
                {
                  <button
                    className="example-start text-button"
                    onClick={() => {
                      setExampleMode(true);
                      setExampleSelection("");
                    }}
                  >
                    예시 보기 <ChevronRight />
                  </button>
                }
              </VStack>
            )}
          {!exampleMode &&
            homeGraph &&
            homeGraph.nodes.length > 0 &&
            !hasRetrieval &&
            (pendingConnections.length > 0 ||
              runningConnections.length > 0 ||
              failedConnections.length > 0 ||
              reviewConnections.length > 0 ||
              !homeGraph.edges.length ||
              Boolean(homeGraphError)) && (
              <HStack
                className="graph-connection-status"
                role="status"
                aria-label="주제 연결 상태"
              >
                {(pendingConnections.length > 0 ||
                  runningConnections.length > 0) && (
                  <p>
                    표시 중인 기록의 주제 연결: 처리 중{" "}
                    {runningConnections.length}개 · 대기{" "}
                    {pendingConnections.length}개.
                  </p>
                )}
                {failedConnections.length > 0 && (
                  <>
                    <p>
                      표시 중인 기록 {failedConnections.length}개의 주제 연결에
                      실패했습니다. 기록을 열어 원인을 확인하고 다시 시도해
                      주세요.
                    </p>
                    <button
                      className="text-button"
                      onClick={() =>
                        void openCapture(
                          failedConnections[0].source?.capture_id ||
                            failedConnections[0].id,
                        )
                      }
                    >
                      연결 실패 기록 확인 <ChevronRight />
                    </button>
                  </>
                )}
                {reviewConnections.length > 0 && (
                  <>
                    <p>
                      표시 중인 기록 {reviewConnections.length}개에 확인이
                      필요한 주제가 있어요.
                    </p>
                    <button
                      className="text-button"
                      onClick={() =>
                        void openCapture(
                          reviewConnections[0].source?.capture_id ||
                            reviewConnections[0].id,
                        )
                      }
                    >
                      주제 검토가 필요한 기록 확인 <ChevronRight />
                    </button>
                  </>
                )}
                {!pendingConnections.length &&
                  !runningConnections.length &&
                  !failedConnections.length &&
                  !reviewConnections.length &&
                  !homeGraph.edges.length && (
                    <p>
                      아직 표시할 연결이 없습니다. 기록에 주제를 지정하거나
                      관계를 추가하면 연결선이 나타납니다.
                    </p>
                  )}
                {homeGraphError && (
                  <p>
                    그래프를 갱신하지 못했습니다. 아래 새로고침으로 다시 확인해
                    주세요.
                  </p>
                )}
              </HStack>
            )}
          <HStack className="stage-footer">
            <Text type="inherit" color="inherit">
              {exampleMode
                ? "예시 공간 · 내 기록과 별개"
                : `내 지식 공간${homeGraph ? ` · ${homeGraph.nodes.length}개 항목` : ""}`}
            </Text>
            <Tool
              label="그래프 새로고침"
              onClick={() => {
                refreshHomeGraph();
                void loadRecords();
              }}
              disabled={homeGraphLoading}
            >
              <RefreshCw />
            </Tool>
          </HStack>
        </VStack>
      </VStack>
      {sourceOpen && !mobile && (
        <aside
          className="source-panel glass"
          role="region"
          aria-labelledby="source-title"
        >
          {sourceContent}
        </aside>
      )}
      <Dialog
        isOpen={sourceOpen && mobile}
        onOpenChange={(open) => {
          if (!open) closeSource();
        }}
        className="source-mobile"
        aria-describedby={undefined}
        width="min(36rem, 94vw)"
        maxHeight="90dvh"
        purpose="info"
      >
        <DialogHeader
          className="dialog-heading"
          title="출처 상세"
          hasDivider={false}
        />
        {sourceOpen && mobile && (
          <VStack className="source-scroll" isScrollable minHeight={0}>
            {sourceContent}
          </VStack>
        )}
      </Dialog>
      {editor && (
        <RecordEditor
          key={editor.record?.id || "new"}
          {...editor}
          onSaved={saved}
          onClose={() => setEditor(null)}
        />
      )}
      <Dialog
        isOpen={Boolean(deletePreview)}
        onOpenChange={(open) => {
          if (!open && !deleteBusy) setDeletePreview(null);
        }}
        className="confirm-dialog"
        width="min(36rem, 94vw)"
        maxHeight="90dvh"
        purpose="info"
      >
        <DialogHeader
          className="dialog-heading"
          title="이 기록을 삭제할까요?"
        />
        <Text as="p">
          <strong>{deletePreview?.title || "선택한 기록"}</strong>은 삭제 후
          검색하거나 다시 열 수 없습니다. 복원 기능은 제공하지 않습니다.
        </Text>
        <ErrorMessage error={deleteError} />
        <HStack className="dialog-actions">
          <Button
            isDisabled={deleteBusy}
            onClick={() => setDeletePreview(null)}
            variant="secondary"
            label="취소"
          />
          <Button
            isDisabled={deleteBusy}
            onClick={() => void confirmDelete()}
            variant="destructive"
            label={deleteBusy ? "삭제 중…" : "삭제하기"}
          />
        </HStack>
      </Dialog>
      <Dialog
        isOpen={reviewOpen && Boolean(selected)}
        aria-label="출처 재검토"
        onOpenChange={setReviewOpen}
        className="editor-dialog"
        aria-describedby={undefined}
        width="min(60rem, 94vw)"
        maxHeight="90dvh"
        purpose="info"
      >
        {reviewOpen && selected && (
          <SourceReview
            record={selected}
            onSaved={saved}
            onClose={() => setReviewOpen(false)}
          />
        )}
      </Dialog>
      <Dialog
        isOpen={conceptOpen && Boolean(selected)}
        aria-label="기록의 주제 정정"
        onOpenChange={setConceptOpen}
        className="settings-dialog"
        aria-describedby={undefined}
        width="min(48rem, 94vw)"
        maxHeight="90dvh"
        purpose="info"
      >
        {conceptOpen && selected && (
          <ConceptEditor
            record={selected}
            onSaved={saved}
            onClose={() => setConceptOpen(false)}
          />
        )}
      </Dialog>
      <Dialog
        isOpen={mergeOpen && Boolean(selected)}
        aria-label="기록 병합"
        onOpenChange={setMergeOpen}
        className="editor-dialog"
        aria-describedby={undefined}
        width="min(60rem, 94vw)"
        maxHeight="90dvh"
        purpose="info"
      >
        {mergeOpen && selected && (
          <MergeDialog
            record={selected}
            onSaved={saved}
            onClose={() => setMergeOpen(false)}
          />
        )}
      </Dialog>
      <Dialog
        isOpen={relationsOpen && Boolean(selected)}
        aria-label="기록의 관계"
        onOpenChange={setRelationsOpen}
        className="editor-dialog"
        aria-describedby={undefined}
        width="min(60rem, 94vw)"
        maxHeight="90dvh"
        purpose="info"
      >
        {relationsOpen && selected && (
          <RelationsDialog
            record={selected}
            onClose={() => setRelationsOpen(false)}
            onChanged={(message) => {
              setGraph(null);
              refreshHomeGraph();
              searchController.current?.abort();
              searchVersion.current++;
              setSearched(false);
              setSearching(false);
              setAnswer(null);
              setSearchError("");
              sourceVersion.current++;
              setSourceOpen(false);
              setSource(null);
              setToast(message);
            }}
          />
        )}
      </Dialog>
      <Dialog
        isOpen={settingsOpen}
        onOpenChange={setSettingsOpen}
        className="settings-dialog settings-content-dialog"
        aria-describedby={undefined}
        width="min(48rem, 94vw)"
        maxHeight="90dvh"
        purpose="info"
      >
        {settingsOpen && (
          <ScrollableArea
            className="settings-scroll"
            label="설정 내용"
            minHeight={0}
            overscroll="contain"
          >
            <SettingsPanel
              onClose={() => setSettingsOpen(false)}
              onToast={setToast}
            />
          </ScrollableArea>
        )}
      </Dialog>
      <VStack className={`toast ${toast ? "is-visible" : ""}`} role="status">
        {toast && (
          <>
            <Check />
            {toast}
          </>
        )}
      </VStack>
    </HStack>
  );
}
