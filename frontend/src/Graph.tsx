import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { IconButton } from "@astryxdesign/core/IconButton";
import { Tooltip } from "@astryxdesign/core/Tooltip";
import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";
import { Crosshair, List, Minus, Pause, Play, Plus, X } from "lucide-react";
import type {
  ForceGraph3DInstance,
  LinkObject,
  NodeObject,
} from "3d-force-graph";
import { KIND_LABELS, type GraphData, type SourceRef } from "./types";
import TopicExplorer from "./TopicExplorer";
import {
  graphEdgeKey,
  graphNodeId,
  topicGroups,
  type GraphTopicGroup,
} from "./graphTopics";
type GraphNode = NodeObject & GraphData["nodes"][number];
type GraphLink = LinkObject<GraphNode> &
  Omit<GraphData["edges"][number], "source" | "target">;
type GraphPalette = ReturnType<typeof readGraphPalette>;

const clickSlop = 4;
type PointerPosition = Pick<PointerEvent, "clientX" | "clientY">;

function movedForDrag(start: PointerPosition, current: PointerPosition) {
  return (
    Math.hypot(
      current.clientX - start.clientX,
      current.clientY - start.clientY,
    ) > clickSlop
  );
}

function preserveCanvasClicks(host: HTMLElement, canvas: HTMLCanvasElement) {
  let press: PointerEvent | null = null;
  function start(event: PointerEvent) {
    if (
      event.target === canvas &&
      event.isPrimary &&
      event.pointerType === "mouse" &&
      event.button === 0
    )
      press = event;
  }
  function move(event: PointerEvent) {
    if (!press || event.pointerId !== press.pointerId) return;
    // The graph treats the first held mouse move as a drag, even on a click.
    if (event.buttons === 1 && !movedForDrag(press, event))
      event.stopPropagation();
    else press = null;
  }
  function end(event: PointerEvent) {
    if (event.pointerId === press?.pointerId) press = null;
  }
  host.addEventListener("pointerdown", start, true);
  host.addEventListener("pointermove", move, true);
  host.addEventListener("pointerup", end, true);
  host.addEventListener("pointercancel", end, true);
  return () => {
    host.removeEventListener("pointerdown", start, true);
    host.removeEventListener("pointermove", move, true);
    host.removeEventListener("pointerup", end, true);
    host.removeEventListener("pointercancel", end, true);
  };
}

function readGraphPalette(element: HTMLElement) {
  const probe = document.createElement("span");
  element.append(probe);
  const color = (token: string) => {
    probe.style.color = `var(${token})`;
    return getComputedStyle(probe).color;
  };
  const palette = {
    primary: color("--color-text-primary"),
    secondary: color("--color-text-secondary"),
    muted: color("--color-icon-secondary"),
    dimmed: color("--color-text-disabled"),
    accent: color("--color-accent"),
    background: color("--color-background-body"),
  };
  probe.remove();
  return palette;
}
const translucent = (color: string, alpha: number) =>
  color.startsWith("rgb(")
    ? color.replace("rgb(", "rgba(").replace(")", `, ${alpha})`)
    : color;
const nodeColor = (
  node: GraphData["nodes"][number],
  selected: string | null,
  hasRetrieval: boolean,
  palette: GraphPalette,
  topic: GraphTopicGroup | null,
) =>
  node.id === selected
    ? topic
      ? palette.accent
      : palette.primary
    : topic && !topic.nodeIds.has(node.id)
      ? palette.dimmed
      : node.kind === "retrieved_chunk"
        ? node.cited
          ? palette.primary
          : palette.secondary
        : hasRetrieval
          ? palette.dimmed
          : node.kind === "concept"
            ? palette.primary
            : node.kind === "node"
              ? palette.muted
              : palette.secondary;
const typeName = (n: GraphData["nodes"][number]) =>
  n.kind === "retrieved_chunk"
    ? n.cited
      ? "답변 출처"
      : "검색한 내용"
    : n.kind === "concept"
      ? "주제"
      : n.kind === "node"
        ? "세부 항목"
        : n.kinds?.length
          ? n.kinds.map((k) => KIND_LABELS[k]).join(" · ")
          : "기록";
export default function Graph({
  data,
  onSource,
  onConcept,
  onPreview,
  onTopicSelectionChange,
  allowTopicExploration = true,
  selectedId,
  reduced,
  active: isActive = true,
  fullStage = false,
  onToggleMotion,
  motionDisabled = false,
}: {
  data: GraphData;
  onSource: (source: SourceRef) => void;
  onConcept?: (id: string) => void;
  onPreview?: (node: GraphData["nodes"][number]) => void;
  onTopicSelectionChange?: () => void;
  allowTopicExploration?: boolean;
  selectedId?: string | null;
  reduced: boolean;
  active?: boolean;
  fullStage?: boolean;
  onToggleMotion?: () => void;
  motionDisabled?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null),
    instance = useRef<ForceGraph3DInstance<GraphNode, GraphLink> | null>(null);
  const dataRef = useRef(data);
  dataRef.current = data;
  const updateData = useRef<((next: GraphData) => void) | null>(null);
  const fitGraph = useRef<((duration: number) => void) | null>(null);
  const hasRetrieval = data.nodes.some(
    (node) => node.kind === "retrieved_chunk",
  );
  const canExploreTopics = Boolean(
    allowTopicExploration && fullStage && onConcept && !onPreview,
  );
  const groups = useMemo(() => topicGroups(data), [data]);
  const listId = useId();
  const listTrigger = useRef<HTMLButtonElement>(null),
    listSearch = useRef<HTMLInputElement>(null);
  const [localSelected, setLocalSelected] = useState<string | null>(null),
    [listQuery, setListQuery] = useState("");
  const [focusedTopicId, setFocusedTopicId] = useState<string | null>(null);
  const focusedTopic =
    canExploreTopics && !hasRetrieval
      ? (groups.find((group) => group.node.id === focusedTopicId) ?? null)
      : null;
  const activeId =
    selectedId ??
    focusedTopic?.node.id ??
    (selectedId === undefined ? localSelected : null);
  const selection = useRef<string | null>(null);
  selection.current = data.nodes.some((node) => node.id === activeId)
    ? (activeId ?? null)
    : null;
  const topicSelection = useRef<GraphTopicGroup | null>(null);
  topicSelection.current =
    focusedTopic?.node.id === selection.current ? focusedTopic : null;
  const palette = useRef<GraphPalette | null>(null);
  const labelElements = useRef(new Map<string, HTMLSpanElement>());
  const labelPress = useRef<
    (PointerPosition & { id: string; pointerId: number }) | null
  >(null);
  function cancelLabelPress(event: { pointerId: number }) {
    if (labelPress.current?.pointerId === event.pointerId)
      labelPress.current = null;
  }
  const hovered = useRef<string | null>(null);
  const actions = useRef({ onSource, onConcept, onPreview });
  actions.current = { onSource, onConcept, onPreview };
  const reducedRef = useRef(reduced);
  reducedRef.current = reduced;
  const isActiveRef = useRef(isActive);
  isActiveRef.current = isActive;
  const syncActivity = useRef<(() => void) | null>(null);
  const [failed, setFailed] = useState(false),
    [listOpen, setListOpen] = useState(false),
    [ready, setReady] = useState(false);
  const activate = (node: GraphData["nodes"][number]) => {
    if (node.kind === "concept" && canExploreTopics && !hasRetrieval) {
      selectTopic(node.id);
      return;
    }
    setLocalSelected(node.id);
    if (actions.current.onPreview) actions.current.onPreview(node);
    else if (node.source) actions.current.onSource(node.source);
    else if (node.kind === "concept")
      actions.current.onConcept?.(
        node.concept_id || node.id.replace(/^concept:/, ""),
      );
  };
  const activeLinks = (link: GraphLink) => {
    if (topicSelection.current)
      return topicSelection.current.edgeIds.has(graphEdgeKey(link));
    return (
      selection.current !== null &&
      [graphNodeId(link.source), graphNodeId(link.target)].includes(
        selection.current,
      )
    );
  };
  function selectTopic(id: string | null) {
    if (id !== null || focusedTopicId !== null) onTopicSelectionChange?.();
    setFocusedTopicId(id);
    setLocalSelected(null);
    if (id) setListOpen(false);
  }
  const preserveViewOnCommit = useRef(false);
  const clearTopicFromBackground = useRef<(event: MouseEvent) => void>(
    () => {},
  );
  clearTopicFromBackground.current = (event) => {
    if (!focusedTopic || !ready || failed) return;
    // A visible label can cover the canvas without receiving pointer events.
    for (const label of labelElements.current.values()) {
      if (label.style.opacity !== "1") continue;
      const bounds = label.getBoundingClientRect();
      if (
        event.clientX >= bounds.left &&
        event.clientX < bounds.right &&
        event.clientY >= bounds.top &&
        event.clientY < bounds.bottom
      )
        return;
    }
    preserveViewOnCommit.current = true;
    selectTopic(null);
  };
  useLayoutEffect(() => {
    if (!preserveViewOnCommit.current) return;
    preserveViewOnCommit.current = false;
    const graph = instance.current;
    const el = host.current;
    // Closing the source panel may resize the canvas. Apply that size before auto-fit.
    if (graph && el && el.clientWidth > 0 && el.clientHeight > 0) {
      graph.width(el.clientWidth).height(el.clientHeight);
    }
  });
  useEffect(() => {
    if (
      !canExploreTopics ||
      hasRetrieval ||
      (focusedTopicId &&
        !groups.some((group) => group.node.id === focusedTopicId))
    )
      setFocusedTopicId(null);
  }, [canExploreTopics, hasRetrieval, groups, focusedTopicId]);
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
        palette.current = readGraphPalette(el);
        let previousView = "",
          layoutVersion = 0;
        const degree = new Map<string, number>();
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
          .backgroundColor(palette.current.background)
          .width(el.clientWidth)
          .height(el.clientHeight || 340)
          .nodeLabel(() => "")
          .nodeColor((node) =>
            nodeColor(
              node,
              selection.current,
              dataRef.current.nodes.some((n) => n.kind === "retrieved_chunk"),
              palette.current!,
              topicSelection.current,
            ),
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
          .nodeRelSize(3.4)
          .nodeOpacity(0.95)
          .linkColor(() => translucent(palette.current!.secondary, 0.5))
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
          .onBackgroundClick((event) => {
            if (event.target === graph.renderer().domElement)
              clearTopicFromBackground.current(event);
          })
          .showPointerCursor((object) => Boolean(object))
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
          degree.clear();
          for (const edge of next.edges) {
            degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
            degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
          }
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
        function fitView(focusEvidence = true, duration = 0) {
          if (!el.clientWidth || !el.clientHeight) return;
          const before = { ...graph.cameraPosition() };
          const beforeTarget = { ...(controls.target || { x: 0, y: 0, z: 0 }) };
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
              !focusEvidence ||
              !chunks.length ||
              node.kind === "retrieved_chunk" ||
              (node.kind === "capture" &&
                parents.has(node.source?.capture_id || node.id)),
          );
          const position = { ...graph.cameraPosition() };
          const target = { ...(controls.target || { x: 0, y: 0, z: 0 }) };
          const distance = Math.hypot(
            position.x - target.x,
            position.y - target.y,
            position.z - target.z,
          );
          // Sparse evidence should stay legible without filling the stage with spheres.
          const minimum = Math.max(170, el.clientHeight * 0.8);
          if (distance > 0 && distance < minimum) {
            const scale = minimum / distance;
            position.x = target.x + (position.x - target.x) * scale;
            position.y = target.y + (position.y - target.y) * scale;
            position.z = target.z + (position.z - target.z) * scale;
          }
          if (duration) graph.cameraPosition(before, beforeTarget, 0);
          graph.cameraPosition(position, target, duration);
        }
        fitGraph.current = (duration) => fitView(false, duration);
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
          const { clientWidth: width, clientHeight: height } = el;
          if (
            width > 0 &&
            height > 0 &&
            (width !== graph.width() || height !== graph.height())
          ) {
            graph.width(width).height(height);
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
          labelFrame = 0;
          if (!active || !isActiveRef.current || document.hidden) return;
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
            const priority = (node: GraphNode) =>
              node.id === selection.current
                ? 0
                : node.id === hovered.current
                  ? 1
                  : node.kind === "retrieved_chunk"
                    ? node.cited
                      ? 2
                      : 3
                    : topicSelection.current?.nodeIds.has(node.id)
                      ? 2
                      : node.kind === "concept"
                        ? 4
                        : 5;
            const nodes = [...graph.graphData().nodes].sort(
              (a, b) =>
                priority(a) - priority(b) ||
                (degree.get(b.id) || 0) - (degree.get(a.id) || 0) ||
                a.id.localeCompare(b.id),
            );
            // Keep the map quiet without limiting selected, hovered or search evidence.
            const ordinaryLimit = el.clientWidth < 600 ? 3 : 6;
            let ordinaryCount = 0;
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
              const important = priority(node) < 4;
              const centeredX = Math.max(
                6,
                Math.min(el.clientWidth - width - 6, point.x - width / 2),
              );
              const positions = [
                { x: centeredX, y: point.y - height - 10 },
                { x: centeredX, y: point.y + 10 },
                ...(important
                  ? [
                      { x: point.x + 12, y: point.y - height / 2 },
                      { x: point.x - width - 12, y: point.y - height / 2 },
                    ]
                  : []),
              ];
              label.dataset.screenX = String(point.x);
              label.dataset.screenY = String(point.y);
              const inverse = camera.matrixWorldInverse.elements;
              const cameraDepth =
                inverse[2] * (node.x || 0) +
                inverse[6] * (node.y || 0) +
                inverse[10] * (node.z || 0) +
                inverse[14];
              const eligible =
                (important || ordinaryCount < ordinaryLimit) &&
                (!topicSelection.current ||
                  topicSelection.current.nodeIds.has(node.id)) &&
                cameraDepth < 0 &&
                point.x >= 0 &&
                point.x <= el.clientWidth &&
                point.y >= 0 &&
                point.y <= el.clientHeight;
              const placement = eligible
                ? positions.find(
                    ({ x, y }) =>
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
                      ),
                  )
                : undefined;
              const { x, y } = placement || positions[0];
              const related =
                topicSelection.current?.nodeIds.has(node.id) ?? false;
              const dimmed = Boolean(topicSelection.current && !related);
              label.dataset.positioned = String(Boolean(placement));
              label.style.opacity = placement ? (dimmed ? "0.22" : "1") : "0";
              label.style.transform = `translate3d(${x}px,${y}px,0)`;
              label.dataset.highlighted = String(node.id === hovered.current);
              label.dataset.selected = String(node.id === selection.current);
              label.dataset.topicRelated = String(related);
              label.dataset.topicDimmed = String(dimmed);
              if (placement) {
                boxes.push({ x, y, w: width, h: height });
                if (!important) ordinaryCount++;
              }
            }
          }
          labelFrame = requestAnimationFrame(positionLabels);
        }
        let animationRunning = true;
        const updateActivity = () => {
          if (!active) return;
          if (isActiveRef.current && !document.hidden) {
            if (!animationRunning) {
              graph.resumeAnimation();
              animationRunning = true;
            }
            previousView = "";
            if (!labelFrame) labelFrame = requestAnimationFrame(positionLabels);
          } else {
            if (animationRunning) {
              graph.pauseAnimation();
              animationRunning = false;
            }
            cancelAnimationFrame(labelFrame);
            labelFrame = 0;
          }
        };
        syncActivity.current = updateActivity;
        document.addEventListener("visibilitychange", updateActivity);
        updateActivity();

        const contextLost = (event: Event) => {
          event.preventDefault();
          if (active) setFailed(true);
        };
        const canvas = el.querySelector("canvas");
        const detachCanvasClickSlop =
          canvas && preserveCanvasClicks(el, canvas);
        canvas?.addEventListener("webglcontextlost", contextLost);
        destroy = () => {
          cancelAnimationFrame(frame);
          cancelAnimationFrame(readyFrame);
          cancelAnimationFrame(labelFrame);
          resize.disconnect();
          document.removeEventListener("visibilitychange", updateActivity);
          if (syncActivity.current === updateActivity)
            syncActivity.current = null;
          canvas?.removeEventListener("webglcontextlost", contextLost);
          detachCanvasClickSlop?.();
          graph._destructor();
          if (instance.current === graph) {
            instance.current = null;
            updateData.current = null;
            fitGraph.current = null;
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
    syncActivity.current?.();
  }, [isActive]);
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
    if (!graph || !palette.current) return;
    const colors = palette.current;
    graph
      .nodeColor((node) =>
        nodeColor(
          node,
          selection.current,
          hasRetrieval,
          colors,
          topicSelection.current,
        ),
      )
      .linkColor((link) =>
        activeLinks(link)
          ? translucent(
              topicSelection.current ? colors.accent : colors.primary,
              0.9,
            )
          : link.kind === "retrieval"
            ? translucent(colors.secondary, 0.7)
            : selection.current || hasRetrieval
              ? translucent(colors.muted, 0.2)
              : translucent(colors.secondary, 0.5),
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
      data-topic-focus={focusedTopic?.node.id}
      aria-label={fullStage ? "지식 연결 지도" : "선택 기록의 연결"}
    >
      <VStack ref={host} className="graph-canvas" aria-hidden="true" />
      {!failed && (
        // The connected list provides the same actions without depending on
        // the current visibility of the labels or the use of a pointer.
        <VStack className="graph-label-layer" aria-hidden="true">
          {data.nodes.map((node) => (
            <Text
              type="inherit"
              color="inherit"
              key={node.id}
              className="graph-label"
              data-node-id={node.id}
              data-kind={node.kind}
              data-cited={
                node.cited === undefined ? undefined : String(node.cited)
              }
              onPointerDown={(event) => {
                if (!event.isPrimary || event.button !== 0) return;
                labelPress.current = {
                  id: node.id,
                  pointerId: event.pointerId,
                  clientX: event.clientX,
                  clientY: event.clientY,
                };
              }}
              onPointerMove={(event) => {
                const press = labelPress.current;
                if (press && movedForDrag(press, event))
                  cancelLabelPress(event);
              }}
              onPointerUp={(event) => {
                const press = labelPress.current;
                if (press?.pointerId !== event.pointerId) return;
                labelPress.current = null;
                if (
                  press.id === node.id &&
                  event.currentTarget.dataset.positioned === "true" &&
                  !movedForDrag(press, event)
                )
                  activate(node);
              }}
              onPointerCancel={cancelLabelPress}
              onPointerLeave={cancelLabelPress}
              ref={(el) => {
                if (el) labelElements.current.set(node.id, el);
                else labelElements.current.delete(node.id);
              }}
            >
              {node.kind === "retrieved_chunk" ? (
                <>
                  <small className="graph-label-context">
                    <Text
                      type="inherit"
                      color="inherit"
                      className="graph-label-state"
                    >
                      {typeName(node)}
                    </Text>
                    <Text
                      type="inherit"
                      color="inherit"
                      className="graph-label-capture"
                    >
                      {node.capture_label}
                    </Text>
                    {node.source?.body_start != null &&
                      node.source.body_end != null && (
                        <Text
                          type="inherit"
                          color="inherit"
                          className="graph-label-range"
                        >
                          {node.source.body_start}–{node.source.body_end}자
                        </Text>
                      )}
                  </small>
                  <Text
                    type="inherit"
                    color="inherit"
                    className="graph-label-excerpt"
                  >
                    {node.label || "검색한 내용"}
                  </Text>
                </>
              ) : (
                node.label || node.name || typeName(node)
              )}
            </Text>
          ))}
        </VStack>
      )}
      {failed && (
        <p className="graph-fallback notice" role="status">
          3D 보기를 열 수 없어 연결 목록으로 표시합니다.
        </p>
      )}
      {canExploreTopics && !hasRetrieval && !listOpen && onConcept && (
        <TopicExplorer
          data={data}
          selectedId={focusedTopic?.node.id ?? null}
          onSelect={selectTopic}
          onSource={onSource}
          onBrowse={onConcept}
        />
      )}
      {fullStage && (
        <>
          <HStack className="graph-legend" aria-label="그래프 범례">
            {hasRetrieval ? (
              <>
                <Text type="inherit" color="inherit">
                  <i className="legend-retrieved" />
                  검색한 내용
                </Text>
                <Text type="inherit" color="inherit">
                  <i className="legend-cited" />
                  답변 출처
                </Text>
              </>
            ) : (
              <>
                <Text type="inherit" color="inherit">
                  <i className="legend-capture" />
                  기록
                </Text>
                <Text type="inherit" color="inherit">
                  <i className="legend-concept" />
                  주제
                </Text>
                <Text type="inherit" color="inherit">
                  <i className="legend-node" />
                  세부 항목
                </Text>
              </>
            )}
          </HStack>
          <HStack className="graph-controls" aria-label="그래프 보기 조절">
            {onToggleMotion && (
              <Tooltip content={reduced ? "모션 켜기" : "모션 일시정지"}>
                <IconButton
                  className="app-icon-button"
                  onClick={onToggleMotion}
                  isDisabled={motionDisabled}
                  variant="ghost"
                  label={reduced ? "모션 켜기" : "모션 일시정지"}
                  icon={reduced ? <Play /> : <Pause />}
                />
              </Tooltip>
            )}
            <Tooltip content="확대">
              <IconButton
                className="app-icon-button"
                isDisabled={!ready || failed}
                onClick={() => zoom(0.8)}
                variant="ghost"
                label="그래프 확대"
                icon={<Plus />}
              />
            </Tooltip>
            <Tooltip content="축소">
              <IconButton
                className="app-icon-button"
                isDisabled={!ready || failed}
                onClick={() => zoom(1.25)}
                variant="ghost"
                label="그래프 축소"
                icon={<Minus />}
              />
            </Tooltip>
            <Tooltip content="전체 보기">
              <IconButton
                className="app-icon-button"
                isDisabled={!ready || failed}
                onClick={() => {
                  selectTopic(null);
                  fitGraph.current?.(reduced ? 0 : 300);
                }}
                variant="ghost"
                label="그래프 화면 맞추기"
                icon={<Crosshair />}
              />
            </Tooltip>
            <Tooltip content="연결 목록">
              <IconButton
                className="app-icon-button"
                ref={listTrigger}
                aria-controls={listId}
                aria-expanded={listOpen}
                onClick={() => (listOpen ? closeList() : setListOpen(true))}
                variant="ghost"
                label="연결 목록 보기"
                icon={listOpen ? <X /> : <List />}
              />
            </Tooltip>
          </HStack>
        </>
      )}
      {(!fullStage || listOpen) && (
        <VStack
          className="graph-list"
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
            <HStack className="graph-list-heading">
              <Text type="inherit" color="inherit">
                연결된 지식
              </Text>
              <IconButton
                className="app-icon-button"
                onClick={closeList}
                variant="ghost"
                label="연결 목록 닫기"
                icon={<X />}
              />
            </HStack>
          )}
          {fullStage && (
            <HStack className="graph-list-search">
              <label>
                <Text type="inherit" color="inherit" className="sr-only">
                  연결 목록에서 찾기
                </Text>
                <input
                  ref={listSearch}
                  type="search"
                  value={listQuery}
                  onChange={(event) => setListQuery(event.target.value)}
                  placeholder="제목·주제 찾기"
                  autoComplete="off"
                />
              </label>
              <Text
                type="inherit"
                color="inherit"
                className="graph-result-count"
                aria-live="polite"
              >
                {normalizedQuery
                  ? `${data.nodes.length}개 중 ${listedNodes.length}개`
                  : `${data.nodes.length}개 항목`}
              </Text>
            </HStack>
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
                <Text type="inherit" color="inherit">
                  {n.label || n.name || "연결 기록"}
                </Text>
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
              <Text type="inherit" color="inherit" className="chip" key={n.id}>
                {n.label || n.name || "주제"}
              </Text>
            ),
          )}
        </VStack>
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
