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
import { Badge, Button, Dialog, IconButton, Tooltip } from "@radix-ui/themes";
import {
  ArrowLeft,
  ArrowUp,
  Clock3,
  Check,
  ChevronRight,
  FileText,
  Layers3,
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
        <Badge key={k} variant="soft" color="gray">
          {KIND_LABELS[k] || k}
        </Badge>
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
      () => localStorage.getItem("second-brain-motion") === "paused",
    );
  const [reviewOpen, setReviewOpen] = useState(false),
    [conceptOpen, setConceptOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false),
    [relationsOpen, setRelationsOpen] = useState(false),
    [conceptRetryBusy, setConceptRetryBusy] = useState(false);
  const conceptRetryReceipt = useRef<{ key: string; id: string } | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null),
    [graphLoading, setGraphLoading] = useState(false);
  const [homeGraph, setHomeGraph] = useState<GraphData | null>(null),
    [homeGraphLoading, setHomeGraphLoading] = useState(true),
    [homeGraphError, setHomeGraphError] = useState(""),
    [graphRefresh, setGraphRefresh] = useState(0);
  const [exampleMode, setExampleMode] = useState(false),
    [exampleSelection, setExampleSelection] = useState("");
  useEffect(() => {
    if (selected || editor) {
      setExampleMode(false);
      setExampleSelection("");
    }
  }, [selected, editor]);
  const homeGraphVersion = useRef(0);
  const refreshHomeGraph = useCallback(() => {
    setHomeGraph(null);
    setExampleMode(false);
    setExampleSelection("");
    setGraphRefresh((value) => value + 1);
  }, []);
  useEffect(() => {
    const version = ++homeGraphVersion.current;
    const controller = new AbortController();
    setHomeGraph(null);
    setHomeGraphLoading(true);
    setHomeGraphError("");
    const params = new URLSearchParams();
    api<GraphData>("/graph?" + params, { signal: controller.signal })
      .then((data) => {
        if (version === homeGraphVersion.current) setHomeGraph(data);
      })
      .catch((error) => {
        if (!controller.signal.aborted && version === homeGraphVersion.current)
          setHomeGraphError(errorText(error));
      })
      .finally(() => {
        if (version === homeGraphVersion.current) setHomeGraphLoading(false);
      });
    return () => controller.abort();
  }, [graphRefresh]);
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
        !document.querySelector('[role="dialog"], [role="alertdialog"]')
      ) {
        e.preventDefault();
        searchInput.current?.focus();
      }
      if (
        e.key === "Escape" &&
        !e.defaultPrevented &&
        !(e.target instanceof Element && e.target.closest('[role="dialog"]'))
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
      localStorage.setItem("second-brain-motion", !v ? "paused" : "enabled");
      return !v;
    });
  }
  const sourceContent = (
    <>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">출처</span>
          <h2 id="source-title" ref={sourceHeading} tabIndex={-1}>
            {source?.capture.title || "저장된 기록"}
          </h2>
        </div>
        <Tool label="출처 닫기" onClick={closeSource}>
          <X />
        </Tool>
      </div>
      {sourceLoading ? (
        <Loading text="출처를 불러오는 중" />
      ) : sourceError ? (
        <div>
          <ErrorMessage error={sourceError} />
          {sourceSelection && (
            <Button
              variant="soft"
              onClick={() => void openSource(sourceSelection)}
            >
              <RefreshCw />
              출처 다시 불러오기
            </Button>
          )}
        </div>
      ) : (
        source && (
          <>
            <RecordDates
              capture={source.capture}
              isCurrent={source.is_current}
            />
            <div className="metadata">
              <KindBadges values={source.capture.kinds} />
              <span>
                {source.is_current
                  ? "현재 저장본"
                  : `과거 저장본 · 버전 ${source.capture.revision_no}`}
              </span>
            </div>
            {!source.is_current && (
              <p className="notice">답변이 참조한 당시의 내용입니다.</p>
            )}
            {source.review_state === "needs_review" && (
              <p className="notice">출처가 변경되어 재검토가 필요합니다.</p>
            )}
            <div className="source-excerpt">
              <Markdown>{source.text}</Markdown>
            </div>
            <details>
              <summary>기록 전체 보기</summary>
              <Markdown>{source.capture.body_markdown}</Markdown>
            </details>
            <Button
              variant="soft"
              onClick={() => {
                void openCapture(source.capture.id);
                closeSource();
              }}
            >
              현재 기록 열기 <ChevronRight />
            </Button>
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
  const sidebarContent = (
    <>
      <button
        className="brand"
        onClick={() => navigateView("home")}
        aria-label="Cache Me If You Can 홈"
      >
        <span>
          <span className="brand-first">Cache Me</span>
          <span className="brand-second">If You Can</span>
        </span>
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
      <div className="sidebar-space" />
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
      <div className="local-label">내 기기에 저장</div>
    </>
  );
  return (
    <div
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
      <Dialog.Root open={navOpen && compactNav} onOpenChange={setNavOpen}>
        <Dialog.Content
          className="sidebar glass nav-drawer"
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (menuDestination.current === "record") {
              (
                recordHeading.current ||
                recordErrorHeading.current ||
                document.getElementById("main")
              )?.focus({ preventScroll: true });
            } else if (!menuDestination.current)
              menuToggle.current?.querySelector("button")?.focus();
          }}
        >
          <Dialog.Title className="sr-only">기록과 탐색</Dialog.Title>
          {sidebarContent}
        </Dialog.Content>
      </Dialog.Root>
      <div className="workspace" inert={Boolean(sourceOpen && mobile)}>
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
            <h1 className="sr-only">Cache Me If You Can — 지식 공간</h1>
            <div className={`search-dock ${searched ? "has-answer" : ""}`}>
              <form className="search-form" onSubmit={runSearch}>
                {compactNav ? (
                  <span className="nav-toggle" ref={menuToggle}>
                    <Tooltip content="메뉴 열기">
                      <IconButton
                        id="menu-toggle"
                        type="button"
                        variant="ghost"
                        aria-label="메뉴 열기"
                        onClick={() => {
                          menuDestination.current = null;
                          setNavOpen(true);
                        }}
                      >
                        <Menu />
                      </IconButton>
                    </Tooltip>
                  </span>
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
                <Button
                  type="submit"
                  aria-label="검색"
                  disabled={exampleMode || !query.trim()}
                >
                  {searching ? (
                    <LoaderCircle
                      className="search-loading-spinner"
                      aria-hidden="true"
                    />
                  ) : (
                    <ArrowUp aria-hidden="true" />
                  )}
                </Button>
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
                  <div className="section-heading">
                    <span className="section-kicker">
                      <Sparkles /> {searching ? "답변 준비 중" : "검색 응답"}
                    </span>
                    <Tool label="검색 응답 닫기" onClick={dismissSearch}>
                      <X />
                    </Tool>
                  </div>
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
                        variant="ghost"
                        onClick={() => {
                          recordOrigin.current = "library";
                          recordTrigger.current = null;
                          setEditor({
                            body: buildAnswerDraft(answer),
                            sources: answer.sources,
                          });
                        }}
                      >
                        <Plus />
                        답변을 기록으로 저장
                      </Button>
                    </>
                  )}
                  {!searching && !answer && !searchError && (
                    <p className="muted">
                      관련 지식을 찾지 못했어요. 다른 단어로 검색해 보세요.
                    </p>
                  )}
                </section>
              )}
            </div>
          </section>
          {view !== "home" && (
            <div
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
            </div>
          )}
          {detailLoading ? (
            <Loading text="기록을 불러오는 중" />
          ) : selected ? (
            <article className="record-detail glass">
              <div className="section-heading">
                <button className="text-button" onClick={returnToRecords}>
                  <ArrowLeft />
                  {recordOrigin.current === "timeline"
                    ? "타임라인"
                    : "모든 기록"}
                </button>
                <div className="row">
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
                </div>
              </div>
              <ErrorMessage error={detailError} />
              <h1 id="record-title" ref={recordHeading} tabIndex={-1}>
                {selected.title || "제목 없는 기록"}
              </h1>
              <div className="metadata">
                <KindBadges values={selected.kinds} />
                {selected.visibility === "private" && (
                  <span>
                    <Lock />
                    비공개
                  </span>
                )}
                <span>{date(selected.updated_at)}</span>
                <span>버전 {selected.revision_no}</span>
                <span>{indexLabel(selected.index_state.status)}</span>
                {selected.completion_state && (
                  <span>
                    {selected.completion_state === "completed"
                      ? "완료"
                      : "미완료"}
                  </span>
                )}
              </div>
              {selected.review_state === "needs_review" && (
                <p className="notice">
                  출처가 변경되었습니다. 현재 내용의 근거를 다시 확인해 주세요.
                </p>
              )}
              {selected.concept_state?.status === "failed" && (
                <div className="concept-status notice">
                  <span>기록은 저장되었지만 주제를 연결하지 못했습니다.</span>
                  <Button
                    variant="soft"
                    disabled={
                      conceptRetryBusy || !selected.concept_state.job_id
                    }
                    onClick={() => void retryConcept()}
                  >
                    <RefreshCw />
                    {conceptRetryBusy ? "다시 요청 중…" : "주제 연결 다시 시도"}
                  </Button>
                </div>
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
                  주제를 확정하지 못했습니다. 주제 정정에서 직접 선택할 수
                  있어요.
                </p>
              )}
              <Markdown>{selected.body_markdown}</Markdown>
              <div className="management-actions">
                <Button variant="ghost" onClick={() => setMergeOpen(true)}>
                  기록 병합
                </Button>
                <Button variant="ghost" onClick={() => setRelationsOpen(true)}>
                  관계 관리
                </Button>
                <Button variant="ghost" onClick={() => setConceptOpen(true)}>
                  주제 정정
                </Button>
                <Button variant="ghost" onClick={() => setReviewOpen(true)}>
                  출처 재검토
                </Button>
              </div>
              {selected.concepts?.length > 0 && (
                <div className="chips">
                  {selected.concepts.map((c) => (
                    <span className="chip" key={c.id}>
                      {c.name}
                    </span>
                  ))}
                </div>
              )}
              {selected.nodes?.length > 0 && (
                <details>
                  <summary>
                    세부 항목 {selected.nodes.length}개{" "}
                    {selected.node_status === "stale" ? "· 재구성 필요" : ""}
                  </summary>
                  {selected.nodes.map((n) => (
                    <section className="node-block" key={n.id}>
                      <span className="part-label">
                        {n.label || NODE_LABELS[n.kind] || n.kind}
                      </span>
                      <p>{n.text}</p>
                      <span className="muted">
                        {ORIGIN_LABELS[n.origin] || n.origin} ·{" "}
                        {VERIFICATION_LABELS[n.verification_state] ||
                          n.verification_state}
                      </span>
                    </section>
                  ))}
                </details>
              )}
              {selected.sources?.length > 0 && (
                <div className="detail-sources">
                  <h3>이 기록의 출처</h3>
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
                </div>
              )}
              <Button
                variant="soft"
                onClick={() => void showGraph()}
                disabled={graphLoading}
              >
                <Network />
                {graphLoading ? "연결을 불러오는 중" : "주변 지식 보기"}
              </Button>
              {graph && (
                <Suspense fallback={<Loading text="그래프를 여는 중" />}>
                  <Graph data={graph} onSource={openSource} reduced={reduced} />
                </Suspense>
              )}
            </article>
          ) : detailError ? (
            <article className="detail-error glass">
              <h2 ref={recordErrorHeading} tabIndex={-1}>
                기록을 열 수 없어요
              </h2>
              <ErrorMessage error={detailError} />
              <div className="detail-error-actions">
                {requestedRecordId && (
                  <Button
                    onClick={() => void openCapture(requestedRecordId, false)}
                  >
                    <RefreshCw />
                    기록 다시 불러오기
                  </Button>
                )}
                <Button variant="soft" color="gray" onClick={goHome}>
                  <ArrowLeft />
                  지식 공간으로
                </Button>
              </div>
            </article>
          ) : (
            <div className="home-view-marker" />
          )}
        </main>
        <div
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
            <div className="example-banner">
              <Badge color="gray">예시 · 읽기 전용</Badge>
              <button
                className="text-button"
                onClick={() => {
                  setExampleMode(false);
                  setExampleSelection("");
                }}
              >
                내 지식으로 돌아가기 <X />
              </button>
            </div>
          )}
          {exampleMode && exampleSelection && (
            <div className="example-selection glass">
              <span className="eyebrow">예시 항목</span>
              <p>{exampleSelection}</p>
              <small>
                화면을 살펴보기 위한 예시입니다. 내 기록에 저장되지 않아요.
              </small>
            </div>
          )}
          {homeGraphLoading && (
            <div className="graph-state">
              <Loading text="지식을 연결하는 중" />
            </div>
          )}
          {homeGraphError && (
            <div className="graph-state graph-error glass">
              <ErrorMessage error={homeGraphError} />
              <Button variant="soft" onClick={refreshHomeGraph}>
                다시 불러오기
              </Button>
            </div>
          )}
          {homeGraph &&
            !displayGraph.nodes.length &&
            !homeGraphLoading &&
            !exampleMode && (
              <div
                className={`graph-empty ${searched || selected ? "is-behind" : ""}`}
              >
                <div className="empty-orbits" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                  <span>
                    <Layers3 />
                  </span>
                </div>
                <h2>첫 번째 생각을 남겨보세요</h2>
                <p>기록한 생각이 연결되고, 나만의 지식이 됩니다.</p>
                <Button
                  variant="soft"
                  onClick={() => {
                    recordOrigin.current = "library";
                    recordTrigger.current = null;
                    setEditor({});
                  }}
                >
                  <Plus />
                  기록 시작하기
                </Button>
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
              </div>
            )}
          <div className="stage-footer">
            <span>
              {exampleMode
                ? "예시 공간 · 내 기록과 별개"
                : `내 지식 공간${homeGraph ? ` · ${homeGraph.nodes.length}개 항목` : ""}`}
            </span>
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
          </div>
        </div>
      </div>
      {sourceOpen && !mobile && (
        <aside
          className="source-panel glass"
          role="region"
          aria-labelledby="source-title"
        >
          {sourceContent}
        </aside>
      )}
      <Dialog.Root
        open={sourceOpen && mobile}
        onOpenChange={(open) => {
          if (!open) closeSource();
        }}
      >
        <Dialog.Content
          className="source-mobile"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            sourceHeading.current?.focus();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            requestAnimationFrame(() => sourceTrigger.current?.focus());
          }}
          aria-describedby={undefined}
        >
          <Dialog.Title className="sr-only">출처 상세</Dialog.Title>
          {sourceContent}
        </Dialog.Content>
      </Dialog.Root>
      {editor && (
        <RecordEditor
          key={editor.record?.id || "new"}
          {...editor}
          onSaved={saved}
          onClose={() => setEditor(null)}
        />
      )}
      <Dialog.Root
        open={Boolean(deletePreview)}
        onOpenChange={(open) => {
          if (!open && !deleteBusy) setDeletePreview(null);
        }}
      >
        <Dialog.Content className="confirm-dialog">
          <Dialog.Title>이 기록을 삭제할까요?</Dialog.Title>
          <Dialog.Description>
            <strong>{deletePreview?.title || "선택한 기록"}</strong>은 삭제 후
            검색하거나 다시 열 수 없습니다. 복원 기능은 제공하지 않습니다.
          </Dialog.Description>
          <ErrorMessage error={deleteError} />
          <div className="dialog-actions">
            <Button
              variant="soft"
              color="gray"
              disabled={deleteBusy}
              onClick={() => setDeletePreview(null)}
            >
              취소
            </Button>
            <Button
              color="red"
              disabled={deleteBusy}
              onClick={() => void confirmDelete()}
            >
              {deleteBusy ? "삭제 중…" : "삭제하기"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Root>
      <Dialog.Root
        open={reviewOpen && Boolean(selected)}
        onOpenChange={setReviewOpen}
      >
        <Dialog.Content
          className="editor-dialog"
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            document
              .querySelector<HTMLElement>("[data-initial-focus]")
              ?.focus();
          }}
        >
          {selected && (
            <SourceReview
              record={selected}
              onSaved={saved}
              onClose={() => setReviewOpen(false)}
            />
          )}
        </Dialog.Content>
      </Dialog.Root>
      <Dialog.Root
        open={conceptOpen && Boolean(selected)}
        onOpenChange={setConceptOpen}
      >
        <Dialog.Content
          className="settings-dialog"
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            document
              .querySelector<HTMLElement>("[data-initial-focus]")
              ?.focus();
          }}
        >
          {selected && (
            <ConceptEditor
              record={selected}
              onSaved={saved}
              onClose={() => setConceptOpen(false)}
            />
          )}
        </Dialog.Content>
      </Dialog.Root>
      <Dialog.Root
        open={mergeOpen && Boolean(selected)}
        onOpenChange={setMergeOpen}
      >
        <Dialog.Content
          className="editor-dialog"
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            document
              .querySelector<HTMLElement>("[data-initial-focus]")
              ?.focus();
          }}
        >
          {selected && (
            <MergeDialog
              record={selected}
              onSaved={saved}
              onClose={() => setMergeOpen(false)}
            />
          )}
        </Dialog.Content>
      </Dialog.Root>
      <Dialog.Root
        open={relationsOpen && Boolean(selected)}
        onOpenChange={setRelationsOpen}
      >
        <Dialog.Content
          className="editor-dialog"
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            document
              .querySelector<HTMLElement>("[data-initial-focus]")
              ?.focus();
          }}
        >
          {selected && (
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
        </Dialog.Content>
      </Dialog.Root>
      <Dialog.Root open={settingsOpen} onOpenChange={setSettingsOpen}>
        <Dialog.Content
          className="settings-dialog"
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            document
              .querySelector<HTMLElement>("[data-settings-heading]")
              ?.focus();
          }}
        >
          {settingsOpen && (
            <SettingsPanel
              onClose={() => setSettingsOpen(false)}
              onToast={setToast}
            />
          )}
        </Dialog.Content>
      </Dialog.Root>
      <div className={`toast ${toast ? "is-visible" : ""}`} role="status">
        {toast && (
          <>
            <Check />
            {toast}
          </>
        )}
      </div>
    </div>
  );
}
