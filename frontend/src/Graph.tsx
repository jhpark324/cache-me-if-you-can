import { useEffect, useId, useRef, useState } from "react";
import "./Graph.css";
import { IconButton, Tooltip } from "@radix-ui/themes";
import { Crosshair, List, Minus, Pause, Play, Plus, X } from "lucide-react";
import type {
  ForceGraph3DInstance,
  LinkObject,
  NodeObject,
} from "3d-force-graph";
import {
  KIND_LABELS,
  type GraphData,
  type RecordKind,
  type SourceRef,
} from "./types";
type GraphNode = NodeObject & GraphData["nodes"][number];
type GraphLink = LinkObject<GraphNode> &
  Omit<GraphData["edges"][number], "source" | "target">;
const colors: Record<RecordKind, string> = {
  knowledge: "#83e5be",
  idea: "#e7bb72",
  decision: "#8cbbf7",
  artifact: "#b3c5cd",
  episode: "#f1a7ab",
  context: "#d9b8f4",
};
const recordColor = (kinds?: RecordKind[]) =>
  (kinds?.[0] && colors[kinds[0]]) || "#ffad66";
const typeName = (n: GraphData["nodes"][number]) =>
  n.kind === "retrieved_chunk"
    ? n.cited
      ? "답변 출처"
      : "검색한 내용"
    : n.kind === "concept"
      ? "주제"
      : n.kind === "node"
        ? "내용의 맥락"
        : n.kinds?.length
          ? n.kinds.map((k) => KIND_LABELS[k]).join(" · ")
          : "기록";
export default function Graph({
  data,
  onSource,
  onConcept,
  onPreview,
  selectedId,
  reduced,
  fullStage = false,
  onToggleMotion,
  motionDisabled = false,
}: {
  data: GraphData;
  onSource: (source: SourceRef) => void;
  onConcept?: (id: string) => void;
  onPreview?: (node: GraphData["nodes"][number]) => void;
  selectedId?: string | null;
  reduced: boolean;
  fullStage?: boolean;
  onToggleMotion?: () => void;
  motionDisabled?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null),
    instance = useRef<ForceGraph3DInstance<GraphNode, GraphLink> | null>(null);
  const dataRef = useRef(data);
  dataRef.current = data;
  const updateData = useRef<((next: GraphData) => void) | null>(null);
  const hasRetrieval = data.nodes.some(
    (node) => node.kind === "retrieved_chunk",
  );
  const listId = useId();
  const listTrigger = useRef<HTMLButtonElement>(null),
    listSearch = useRef<HTMLInputElement>(null);
  const [localSelected, setLocalSelected] = useState<string | null>(null),
    [listQuery, setListQuery] = useState("");
  const activeId = selectedId === undefined ? localSelected : selectedId;
  const selection = useRef<string | null>(null);
  selection.current = data.nodes.some((node) => node.id === activeId)
    ? (activeId ?? null)
    : null;
  const labelElements = useRef(new Map<string, HTMLSpanElement>());
  const hovered = useRef<string | null>(null);
  const actions = useRef({ onSource, onConcept, onPreview });
  actions.current = { onSource, onConcept, onPreview };
  const reducedRef = useRef(reduced);
  reducedRef.current = reduced;
  const [failed, setFailed] = useState(false),
    [listOpen, setListOpen] = useState(false),
    [ready, setReady] = useState(false);
  const activate = (node: GraphData["nodes"][number]) => {
    setLocalSelected(node.id);
    if (actions.current.onPreview) actions.current.onPreview(node);
    else if (node.source) actions.current.onSource(node.source);
    else if (node.kind === "concept")
      actions.current.onConcept?.(
        node.concept_id || node.id.replace(/^concept:/, ""),
      );
  };
  const activeLinks = (link: { source?: unknown; target?: unknown }) => {
    const id = (value: unknown) =>
      typeof value === "object" && value !== null
        ? (value as { id?: string }).id
        : value;
    return (
      selection.current !== null &&
      [id(link.source), id(link.target)].includes(selection.current)
    );
  };
  function closeList() {
    setListOpen(false);
    requestAnimationFrame(() => listTrigger.current?.focus());
  }
  useEffect(() => {
    if (failed && fullStage) setListOpen(true);
  }, [failed, fullStage]);
  useEffect(() => {
    if (!listOpen || failed) return;
    const frame = requestAnimationFrame(() => listSearch.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [listOpen, failed]);
  const normalizedQuery = listQuery
    .normalize("NFKC")
    .toLocaleLowerCase()
    .trim();
  const listedNodes = [...data.nodes]
    .sort(
      (a, b) =>
        Number(b.kind === "retrieved_chunk") -
          Number(a.kind === "retrieved_chunk") ||
        Number(Boolean(b.cited)) - Number(Boolean(a.cited)),
    )
    .filter((node) =>
      `${node.label || node.name || ""} ${node.capture_label || ""} ${typeName(node)}`
        .normalize("NFKC")
        .toLocaleLowerCase()
        .includes(normalizedQuery),
    );
  const activateRef = useRef(activate);
  activateRef.current = activate;
  useEffect(() => {
    let active = true,
      destroy: (() => void) | undefined;
    setFailed(false);
    setReady(false);
    (async () => {
      try {
        const { default: ForceGraph } = await import("3d-force-graph");
        if (!active || !host.current) return;
        const el = host.current;
        let previousView = "",
          layoutVersion = 0;
        const measurements = new Map<
          string,
          { width: number; height: number }
        >();
        const graph = new ForceGraph(el, {
          controlType: "orbit",
          rendererConfig: { antialias: true, alpha: true },
        }) as unknown as ForceGraph3DInstance<GraphNode, GraphLink>;
        instance.current = graph;
        graph
          .backgroundColor("#000000")
          .width(el.clientWidth)
          .height(el.clientHeight || 340)
          .nodeLabel(() => "")
          .nodeColor((n) =>
            n.kind === "concept"
              ? "#c4b5fd"
              : n.kind === "node"
                ? "#7dd3fc"
                : recordColor(n.kinds),
          )
          .nodeVal((n) =>
            n.kind === "concept"
              ? 3
              : n.kind === "capture"
                ? 2.2
                : n.kind === "retrieved_chunk"
                  ? 1.5
                  : 0.8,
          )
          .nodeRelSize(2.3)
          .nodeOpacity(0.95)
          .linkColor(() => "rgba(193,207,228,.28)")
          .linkWidth(0.65)
          .linkOpacity(0.55)
          .enableNodeDrag(!reducedRef.current)
          .warmupTicks(120)
          .cooldownTicks(reducedRef.current ? 0 : 30)
          .showNavInfo(false)
          .onEngineTick(() => {
            layoutVersion++;
          })
          .onNodeDrag(() => {
            layoutVersion++;
          })
          .onNodeClick((n) => activateRef.current(n))
          .onNodeHover((n) => {
            el.style.cursor = n ? "pointer" : "grab";
            hovered.current = n?.id || null;
          });
        // A gentle centering force keeps disconnected, real clusters in the same workspace.
        graph.d3Force("workspace", (alpha: number) => {
          for (const node of graph.graphData().nodes) {
            node.vx = (node.vx || 0) - (node.x || 0) * 0.025 * alpha;
            node.vy = (node.vy || 0) - (node.y || 0) * 0.025 * alpha;
            node.vz = (node.vz || 0) - (node.z || 0) * 0.08 * alpha;
          }
        });
        (
          graph.d3Force("charge") as unknown as {
            strength: (value: number) => void;
          }
        )?.strength(-100);
        (
          graph.d3Force("link") as unknown as {
            distance: (value: number) => void;
          }
        )?.distance(65);
        let fitted = false,
          frame = 0,
          readyFrame = 0;
        updateData.current = (next) => {
          const previous = new Map(
            graph.graphData().nodes.map((node) => [node.id, node]),
          );
          measurements.clear();
          previousView = "";
          layoutVersion++;
          fitted = false;
          // Keep positions and the Canvas when request-local evidence changes.
          graph.graphData({
            nodes: next.nodes.map((node, i) => {
              const existing = previous.get(node.id);
              if (existing) return Object.assign(existing, node);
              const angle = i * 2.39996,
                radius = 32 + Math.sqrt(i + 1) * 18;
              return {
                ...node,
                x: Math.cos(angle) * radius,
                y: Math.sin(angle) * radius * 0.7,
                z: Math.sin(i * 1.7) * 24,
              };
            }),
            links: next.edges.map((edge) => ({ ...edge })),
          });
        };
        updateData.current(dataRef.current);
        const controls = graph.controls() as {
          enableDamping?: boolean;
          enablePan?: boolean;
          minDistance?: number;
          maxDistance?: number;
          target?: { x: number; y: number; z: number };
        };
        controls.enableDamping = !reducedRef.current;
        controls.minDistance = 30;
        controls.maxDistance = 2000;
        graph.cameraPosition({
          x: 0,
          y: 0,
          z: dataRef.current.nodes.length < 3 ? 170 : 300,
        });
        function fitView() {
          const chunks = dataRef.current.nodes.filter(
            (node) => node.kind === "retrieved_chunk",
          );
          const parents = new Set(
            chunks.map((node) => node.source?.capture_id),
          );
          graph.zoomToFit(
            0,
            fullStage ? Math.min(el.clientWidth, el.clientHeight) * 0.2 : 55,
            (node) =>
              !chunks.length ||
              node.kind === "retrieved_chunk" ||
              (node.kind === "capture" &&
                parents.has(node.source?.capture_id || node.id)),
          );
        }
        graph.onEngineStop(() => {
          if (!active || fitted) return;
          fitted = true;
          // The library fires onEngineStop before copying layout positions to scene objects.
          // Wait for that render before reading bounds, including reduced-motion's first frame.
          frame = requestAnimationFrame(() => {
            if (!active) return;
            graph.scene().updateMatrixWorld(true);
            if (dataRef.current.nodes.length > 1) fitView();
            readyFrame = requestAnimationFrame(() => {
              if (active) setReady(true);
            });
          });
        });
        const resize = new ResizeObserver(() => {
          measurements.clear();
          previousView = "";
          if (el.clientWidth > 0 && el.clientHeight > 0) {
            graph.width(el.clientWidth).height(el.clientHeight);
            if (fitted) fitView();
          }
        });
        resize.observe(el);
        let labelFrame = 0,
          measuredSelection: string | null = null;
        void document.fonts.ready.then(() => {
          if (active) {
            measurements.clear();
            previousView = "";
          }
        });
        function positionLabels() {
          if (!active) return;
          const camera = graph.camera();
          const view =
            camera.matrixWorld.elements.join(",") +
            ":" +
            camera.projectionMatrix.elements.join(",") +
            ":" +
            layoutVersion +
            ":" +
            selection.current +
            ":" +
            el.clientWidth +
            ":" +
            el.clientHeight +
            ":" +
            hovered.current;
          if (!fitted || view !== previousView) {
            previousView = view;
            if (measuredSelection !== selection.current) {
              measurements.clear();
              measuredSelection = selection.current;
            }
            const boxes: { x: number; y: number; w: number; h: number }[] = [];
            const nodes = [...graph.graphData().nodes].sort((a, b) =>
              a.id === selection.current
                ? -1
                : b.id === selection.current
                  ? 1
                  : a.id === hovered.current
                    ? -1
                    : b.id === hovered.current
                      ? 1
                      : a.kind === "retrieved_chunk" &&
                          b.kind !== "retrieved_chunk"
                        ? -1
                        : b.kind === "retrieved_chunk" &&
                            a.kind !== "retrieved_chunk"
                          ? 1
                          : a.cited && !b.cited
                            ? -1
                            : b.cited && !a.cited
                              ? 1
                              : a.kind === "concept"
                                ? -1
                                : b.kind === "concept"
                                  ? 1
                                  : 0,
            );
            for (const node of nodes) {
              const label = labelElements.current.get(node.id);
              if (!label) continue;
              const point = graph.graph2ScreenCoords(
                node.x || 0,
                node.y || 0,
                node.z || 0,
              );
              label.dataset.selected = String(node.id === selection.current);
              const size = measurements.get(node.id) || {
                width: label.offsetWidth,
                height: label.offsetHeight,
              };
              measurements.set(node.id, size);
              const { width, height } = size;
              const x = point.x - width / 2,
                y = point.y - height - 8;
              label.dataset.screenX = String(point.x);
              label.dataset.screenY = String(point.y);
              const inverse = camera.matrixWorldInverse.elements;
              const cameraDepth =
                inverse[2] * (node.x || 0) +
                inverse[6] * (node.y || 0) +
                inverse[10] * (node.z || 0) +
                inverse[14];
              const visible =
                cameraDepth < 0 &&
                Number.isFinite(x) &&
                Number.isFinite(y) &&
                x >= 6 &&
                x + width <= el.clientWidth - 6 &&
                y >= 10 &&
                y + height < el.clientHeight - 80 &&
                !boxes.some(
                  (box) =>
                    y < box.y + box.h + 6 &&
                    y + height + 6 > box.y &&
                    x < box.x + box.w + 10 &&
                    x + width + 10 > box.x,
                );
              label.style.opacity = visible ? "1" : "0";
              label.style.transform = `translate3d(${x}px,${y}px,0)`;
              label.dataset.highlighted = String(node.id === hovered.current);
              label.dataset.selected = String(node.id === selection.current);
              if (visible) boxes.push({ x, y, w: width, h: height });
            }
          }
          labelFrame = requestAnimationFrame(positionLabels);
        }
        labelFrame = requestAnimationFrame(positionLabels);

        const contextLost = (event: Event) => {
          event.preventDefault();
          if (active) setFailed(true);
        };
        const canvas = el.querySelector("canvas");
        canvas?.addEventListener("webglcontextlost", contextLost);
        destroy = () => {
          cancelAnimationFrame(frame);
          cancelAnimationFrame(readyFrame);
          cancelAnimationFrame(labelFrame);
          resize.disconnect();
          canvas?.removeEventListener("webglcontextlost", contextLost);
          graph._destructor();
          if (instance.current === graph) {
            instance.current = null;
            updateData.current = null;
          }
        };
      } catch {
        if (active) setFailed(true);
      }
    })();
    return () => {
      active = false;
      destroy?.();
    };
  }, [fullStage]);
  useEffect(() => {
    updateData.current?.(data);
  }, [data]);
  useEffect(() => {
    const graph = instance.current;
    if (!graph) return;
    graph.enableNodeDrag(!reduced).cooldownTicks(reduced ? 0 : 60);
    (graph.controls() as { enableDamping: boolean }).enableDamping = !reduced;
  }, [reduced]);
  useEffect(() => {
    const graph = instance.current;
    if (!graph) return;
    graph
      .nodeColor((node) =>
        node.id === selection.current
          ? "#ffad66"
          : node.kind === "retrieved_chunk"
            ? node.cited
              ? "#ffad66"
              : "#80dce9"
            : hasRetrieval
              ? "#68727e"
              : node.kind === "concept"
                ? "#c4b5fd"
                : node.kind === "node"
                  ? "#7dd3fc"
                  : recordColor(node.kinds),
      )
      .linkColor((link) =>
        activeLinks(link)
          ? "rgba(255,173,102,.85)"
          : link.kind === "retrieval"
            ? "rgba(128,220,233,.6)"
            : selection.current || hasRetrieval
              ? "rgba(193,207,228,.12)"
              : "rgba(193,207,228,.28)",
      )
      .linkWidth((link) =>
        activeLinks(link) ? 1.5 : link.kind === "retrieval" ? 1 : 0.65,
      );
  }, [activeId, ready, data, hasRetrieval]);
  function zoom(factor: number) {
    const graph = instance.current;
    if (!graph) return;
    const pos = graph.cameraPosition(),
      target = (
        graph.controls() as { target?: { x: number; y: number; z: number } }
      ).target || { x: 0, y: 0, z: 0 };
    const distance = Math.hypot(
      pos.x - target.x,
      pos.y - target.y,
      pos.z - target.z,
    );
    if (!distance) return;
    const ratio = Math.min(2000, Math.max(30, distance * factor)) / distance;
    graph.cameraPosition(
      {
        x: target.x + (pos.x - target.x) * ratio,
        y: target.y + (pos.y - target.y) * ratio,
        z: target.z + (pos.z - target.z) * ratio,
      },
      target,
      reduced ? 0 : 220,
    );
  }
  return (
    <section
      className={`graph-section ${fullStage ? "graph-world" : "graph-neighborhood"} ${hasRetrieval ? "has-retrieval" : ""}`}
      data-render-state={failed ? "fallback" : ready ? "ready" : "loading"}
      aria-label={fullStage ? "지식 연결 지도" : "선택 기록의 연결"}
    >
      <div ref={host} className="graph-canvas" aria-hidden="true" />
      {!failed && (
        <div className="graph-label-layer" aria-hidden="true">
          {data.nodes.map((node) => (
            <span
              key={node.id}
              className="graph-label"
              data-node-id={node.id}
              data-kind={node.kind}
              data-cited={
                node.cited === undefined ? undefined : String(node.cited)
              }
              ref={(el) => {
                if (el) labelElements.current.set(node.id, el);
                else labelElements.current.delete(node.id);
              }}
            >
              {node.kind === "retrieved_chunk" ? (
                <>
                  <small className="graph-label-context">
                    <span>{node.capture_label}</span>
                    {node.source?.body_start != null &&
                      node.source.body_end != null && (
                        <span className="graph-label-range">
                          {node.source.body_start}–{node.source.body_end}자
                        </span>
                      )}
                  </small>
                  <span className="graph-label-excerpt">
                    {node.label || "검색한 내용"}
                  </span>
                </>
              ) : (
                node.label || node.name || typeName(node)
              )}
            </span>
          ))}
        </div>
      )}
      {failed && (
        <p className="graph-fallback notice" role="status">
          3D 보기를 열 수 없어 연결 목록으로 표시합니다.
        </p>
      )}
      {fullStage && (
        <>
          <div className="graph-legend" aria-label="그래프 범례">
            {hasRetrieval ? (
              <>
                <span>
                  <i className="legend-retrieved" />
                  검색한 내용
                </span>
                <span>
                  <i className="legend-cited" />
                  답변 출처
                </span>
              </>
            ) : (
              <>
                <span>
                  <i className="legend-capture" />
                  기록
                </span>
                <span>
                  <i className="legend-concept" />
                  주제
                </span>
                <span>
                  <i className="legend-node" />
                  내용의 맥락
                </span>
              </>
            )}
          </div>
          <div className="graph-controls glass" aria-label="그래프 보기 조절">
            {onToggleMotion && (
              <Tooltip content={reduced ? "모션 켜기" : "모션 일시정지"}>
                <IconButton
                  variant="ghost"
                  aria-label={reduced ? "모션 켜기" : "모션 일시정지"}
                  onClick={onToggleMotion}
                  disabled={motionDisabled}
                >
                  {reduced ? <Play /> : <Pause />}
                </IconButton>
              </Tooltip>
            )}
            <Tooltip content="확대">
              <IconButton
                variant="ghost"
                aria-label="그래프 확대"
                disabled={!ready || failed}
                onClick={() => zoom(0.8)}
              >
                <Plus />
              </IconButton>
            </Tooltip>
            <Tooltip content="축소">
              <IconButton
                variant="ghost"
                aria-label="그래프 축소"
                disabled={!ready || failed}
                onClick={() => zoom(1.25)}
              >
                <Minus />
              </IconButton>
            </Tooltip>
            <Tooltip content="전체 보기">
              <IconButton
                variant="ghost"
                aria-label="그래프 화면 맞추기"
                disabled={!ready || failed}
                onClick={() =>
                  instance.current?.zoomToFit(
                    reduced ? 0 : 300,
                    host.current
                      ? Math.min(
                          host.current.clientWidth,
                          host.current.clientHeight,
                        ) * 0.2
                      : 80,
                  )
                }
              >
                <Crosshair />
              </IconButton>
            </Tooltip>
            <Tooltip content="연결 목록">
              <IconButton
                variant="ghost"
                aria-label="연결 목록 보기"
                ref={listTrigger}
                aria-controls={listId}
                aria-expanded={listOpen}
                onClick={() => (listOpen ? closeList() : setListOpen(true))}
              >
                {listOpen ? <X /> : <List />}
              </IconButton>
            </Tooltip>
          </div>
        </>
      )}
      {(!fullStage || listOpen) && (
        <div
          className={`graph-list ${fullStage ? "glass" : ""}`}
          aria-label="연결된 지식"
          id={listId}
          role="region"
          onKeyDownCapture={(event) => {
            if (fullStage && event.key === "Escape") {
              event.preventDefault();
              event.stopPropagation();
              closeList();
            }
          }}
        >
          {fullStage && (
            <div className="graph-list-heading">
              <span>연결된 지식</span>
              <IconButton
                variant="ghost"
                aria-label="연결 목록 닫기"
                onClick={closeList}
              >
                <X />
              </IconButton>
            </div>
          )}
          {fullStage && (
            <div className="graph-list-search">
              <label>
                <span className="sr-only">연결 목록에서 찾기</span>
                <input
                  ref={listSearch}
                  type="search"
                  value={listQuery}
                  onChange={(event) => setListQuery(event.target.value)}
                  placeholder="제목·주제 찾기"
                  autoComplete="off"
                />
              </label>
              <span className="graph-result-count" aria-live="polite">
                {normalizedQuery
                  ? `${data.nodes.length}개 중 ${listedNodes.length}개`
                  : `${data.nodes.length}개 항목`}
              </span>
            </div>
          )}
          {listedNodes.length === 0 && (
            <p className="graph-list-empty">일치하는 항목이 없어요.</p>
          )}
          {listedNodes.map((n) =>
            n.source || onPreview || (n.kind === "concept" && onConcept) ? (
              <button
                className="chip"
                key={n.id}
                data-node-id={n.id}
                data-kind={n.kind}
                data-cited={n.cited === undefined ? undefined : String(n.cited)}
                aria-pressed={activeId === n.id}
                onClick={() => activate(n)}
                onFocus={() => {
                  hovered.current = n.id;
                }}
                onBlur={() => {
                  if (hovered.current === n.id) hovered.current = null;
                }}
              >
                <span>{n.label || n.name || "연결 기록"}</span>
                {fullStage && (
                  <small>
                    {typeName(n)}
                    {n.kind === "retrieved_chunk" && (
                      <>
                        {" "}
                        · {n.capture_label}
                        {n.source?.body_start != null &&
                        n.source.body_end != null
                          ? ` · ${n.source.body_start}–${n.source.body_end}자`
                          : ""}
                      </>
                    )}
                  </small>
                )}
              </button>
            ) : (
              <span className="chip" key={n.id}>
                {n.label || n.name || "주제"}
              </span>
            ),
          )}
        </div>
      )}
      {data.retrieval_truncated && (
        <p className="graph-retrieval-note" role="status">
          유효한 검색 근거의 일부를 표시합니다.
        </p>
      )}
      {data.truncated && (
        <p className="graph-truncated">
          최근 연결의 일부를 표시하고 있어요. 기록을 열어 주변 지식을 더
          살펴보세요.
        </p>
      )}
    </section>
  );
}
