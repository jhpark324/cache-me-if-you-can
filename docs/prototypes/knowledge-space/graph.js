import { graphNodes, graphLinks, records, kinds } from './mock-data.js';

const endId = end => typeof end === 'object' ? end.id : end;
const recordMap = new Map(records.map(record => [record.id, record]));

export function createGraph(container, { onSelect = () => {}, onHover = () => {} } = {}) {
  const lib = window.GraphPreviewLib;
  const objects = new Map();
  const initialPositions = new Map(graphNodes.map(n => [n.id, { x: n.x, y: n.y, z: n.z }]));
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const state = { filter: 'all', selected: null, hover: null, motion: false };
  let graph, observer, destroyed = false, resizeFrame = 0;
  let lastWidth = 0, lastHeight = 0;
  let compactLayout = container.clientWidth > 0 && container.clientWidth < 600;
  let fallback;
  const duration = () => reducedMotion ? 0 : 380;
  const visible = value => {
    const node = typeof value === 'string' ? graphNodes.find(n => n.id === value) : value;
    return !!node && (state.filter === 'all' || node.kind === state.filter);
  };
  const getCounts = () => ({
    nodes: graphNodes.filter(visible).length,
    links: graphLinks.filter(l => visible(graphNodes.find(n => n.id === endId(l.source))) && visible(graphNodes.find(n => n.id === endId(l.target)))).length,
    records: records.filter(r => state.filter === 'all' || r.kind === state.filter).length,
  });

  function layoutPosition(id) {
    const position = initialPositions.get(id);
    return compactLayout
      ? { x: position.x * 0.36, y: position.y * 0.88, z: position.z * 0.5 }
      : { ...position };
  }

  function applyResponsivePositions() {
    if (!graph) return;
    const data = graph.graphData();
    data.nodes.forEach(node => {
      const position = layoutPosition(node.id);
      Object.assign(node, position, { fx: position.x, fy: position.y, fz: position.z });
      objects.get(node.id)?.group.position.set(position.x, position.y, position.z);
    });
    graph.graphData({ nodes: data.nodes, links: data.links });
  }

  function choose(node) {
    if (!node || !visible(node)) return;
    state.selected = node.id;
    updateHighlights();
    onSelect({ ...node, record: recordMap.get(node.recordId) });
  }

  function makeFallback() {
    container.dataset.graphRenderer = 'fallback';
    fallback = document.createElement('div');
    fallback.className = 'graph-fallback';
    fallback.style.cssText = 'position:absolute;inset:100px 28px 95px;overflow:auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;align-content:center;padding:10px;';
    const note = document.createElement('p');
    note.style.cssText = 'grid-column:1/-1;color:#a4a5ad;font:14px/1.7 sans-serif;';
    note.textContent = '이 환경에서는 3D 대신 연결된 기록을 목록으로 보여드립니다.';
    fallback.append(note);
    graphNodes.filter(n => n.prominent).forEach(node => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.nodeId = node.id;
      button.textContent = node.title;
      button.style.cssText = 'padding:18px;text-align:left;background:#111214;color:#e8e9ed;border:1px solid #303136;border-radius:12px;font:14px/1.6 inherit;cursor:pointer;';
      button.addEventListener('click', () => choose(node));
      fallback.append(button);
    });
    container.append(fallback);
  }

  function makeNode(node) {
    const { THREE, SpriteText } = lib;
    const group = new THREE.Group();
    const color = node.prominent ? kinds[node.kind].color : '#81858e';
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(node.size, 22, 16),
      new THREE.MeshStandardMaterial({ color, roughness: 0.5, metalness: 0.08 }),
    );
    sphere.userData.nodeId = node.id;
    group.add(sphere);
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(node.size + 4, 0.48, 8, 56),
      new THREE.MeshBasicMaterial({ color: kinds[node.kind].color, transparent: true, opacity: 0.8 }),
    );
    ring.visible = false;
    ring.raycast = () => {};
    group.add(ring);
    const label = new SpriteText(node.title, 14, node.prominent ? '#ffffff' : '#c7c7c7');
    label.fontFace = '"SUIT Variable", Pretendard, "Malgun Gothic", sans-serif';
    label.fontSize = 88;
    label.fontWeight = node.id === 'brain' ? '600' : '400';
    label.backgroundColor = false;
    label.padding = 0;
    label.material.depthTest = false;
    label.material.depthWrite = false;
    label.renderOrder = node.prominent ? 5 : 4;
    label.raycast = () => {};
    group.add(label);
    objects.set(node.id, { group, sphere, ring, label, baseScale: label.scale.clone() });
    return group;
  }

  function updateLabels() {
    if (!graph || destroyed) return;
    const camera = graph.camera();
    camera.updateMatrixWorld();
    const height = graph.height(), width = graph.width();
    if (!height || !width) return;
    const used = [];
    const ordered = [...graphNodes].sort((a, b) => {
      const priority = n => n.id === state.selected || n.id === state.hover ? 0 : n.id === 'brain' ? 1 : n.prominent ? 2 : 3;
      return priority(a) - priority(b);
    });
    for (const node of ordered) {
      const object = objects.get(node.id);
      if (!object) continue;
      object.label.visible = false;
      if (!visible(node)) continue;
      if (!node.prominent && node.id !== state.selected && node.id !== state.hover) continue;
      const world = object.group.position.clone();
      const depth = -world.clone().applyMatrix4(camera.matrixWorldInverse).z;
      if (depth <= 0) continue;
      const pixelsPerUnit = height / (2 * Math.tan(camera.fov * Math.PI / 360) * depth);
      const textPx = node.id === 'brain' ? 17 : node.prominent ? 14 : 12;
      const factor = textPx / (14 * pixelsPerUnit);
      object.label.scale.copy(object.baseScale).multiplyScalar(factor);
      // Labels sit below the node, retaining the open graph geometry.
      object.label.position.set(0, -node.size - textPx / pixelsPerUnit * 1.1, 0);
      const center = world.clone().add(object.label.position).project(camera);
      const x = (center.x + 1) * width / 2, y = (1 - center.y) * height / 2;
      const labelWidth = object.label.scale.x * pixelsPerUnit;
      const rect = { left: x - labelWidth / 2 - 5, right: x + labelWidth / 2 + 5, top: y - textPx / 2 - 3, bottom: y + textPx / 2 + 3 };
      const collide = used.some(r => rect.left < r.right && rect.right > r.left && rect.top < r.bottom && rect.bottom > r.top);
      object.label.visible = !collide && center.z >= -1 && center.z <= 1 && rect.left > 12 && rect.right < width - 12 && rect.top > 60 && rect.bottom < height - 150;
      if (object.label.visible) used.push(rect);
    }
  }

  function updateHighlights() {
    if (!graph) {
      fallback?.querySelectorAll('button').forEach(button => {
        const node = graphNodes.find(n => n.id === button.dataset.nodeId);
        button.hidden = !visible(node);
        button.setAttribute('aria-pressed', String(state.selected === node.id));
      });
      return;
    }
    const activeId = state.hover || state.selected;
    const adjacent = new Set(activeId ? [activeId] : []);
    graphLinks.forEach(link => {
      if (endId(link.source) === activeId) adjacent.add(endId(link.target));
      if (endId(link.target) === activeId) adjacent.add(endId(link.source));
    });
    objects.forEach((object, id) => {
      const node = graphNodes.find(n => n.id === id);
      object.ring.visible = id === state.selected;
      object.sphere.scale.setScalar(id === activeId ? 1.22 : 1);
      object.sphere.material.emissive.set(id === activeId ? kinds[node.kind].color : '#000000');
      object.sphere.material.emissiveIntensity = id === activeId ? 0.14 : 0;
      const color = id === activeId ? '#ffad66' : adjacent.has(id) ? '#ffffff' : node.prominent ? '#ffffff' : '#c7c7c7';
      if (object.label.color !== color) object.label.color = color;
    });
    graph.linkColor(link => activeId && (endId(link.source) === activeId || endId(link.target) === activeId) ? '#778b86' : '#30343a');
    graph.linkWidth(link => activeId && (endId(link.source) === activeId || endId(link.target) === activeId) ? 0.72 : 0.35);
    updateLabels();
  }

  function resize() {
    if (!graph || destroyed) return;
    const bounds = container.getBoundingClientRect();
    const width = Math.round(bounds.width), height = Math.round(bounds.height);
    if (!width || !height) return;
    const dimensionsChanged = width !== lastWidth || height !== lastHeight;
    if (!dimensionsChanged) return;
    lastWidth = width;
    lastHeight = height;
    graph.width(width).height(height);
    const nextCompactLayout = width < 600;
    if (nextCompactLayout !== compactLayout) {
      compactLayout = nextCompactLayout;
      applyResponsivePositions();
    }
    // Graph's resize hooks can settle on the following render; update projection
    // synchronously before projecting labels or fitting the portrait viewport.
    graph.camera().aspect = width / height;
    graph.camera().updateProjectionMatrix();
    resetCamera(false);
    graph.camera().updateMatrixWorld(true);
    updateLabels();
  }

  function resetCamera(animate = true) {
    if (!graph) return;
    const width = Math.max(container.clientWidth, 1);
    const height = Math.max(container.clientHeight, 1);
    const tanHalfFov = Math.tan(20 * Math.PI / 180);
    const usableWidth = Math.max(120, width - 48);
    const usableHeight = Math.max(120, height - 210);
    const horizontalFit = 560 * (compactLayout ? 0.36 : 1) * height / (tanHalfFov * usableWidth);
    const verticalFit = 375 * (compactLayout ? 0.88 : 1) * height / (tanHalfFov * usableHeight);
    const distance = Math.max(compactLayout ? 1050 : 1260, horizontalFit, verticalFit);
    // Reserve 60px above and 150px below for the search/discovery controls.
    // A lower camera target raises the graph into the available upper space.
    const targetY = -20 - 45 * (2 * tanHalfFov * distance / height);
    graph.cameraPosition({ x: 0, y: targetY, z: distance }, { x: 0, y: targetY, z: 0 }, animate ? duration() : 0);
  }

  try {
    if (!lib?.ForceGraph3D || !lib?.THREE || !lib?.SpriteText) throw new Error('Graph library unavailable');
    graph = new lib.ForceGraph3D(container, { controlType: 'orbit', rendererConfig: { antialias: true, alpha: false, preserveDrawingBuffer: true } })
      .width(container.clientWidth || 1000).height(container.clientHeight || 700)
      .backgroundColor('#000000').showNavInfo(false)
      .nodeThreeObject(makeNode).nodeLabel(() => '')
      .linkColor('#30343a').linkWidth(0.35).linkOpacity(0.62)
      .cooldownTicks(0).enableNodeDrag(true)
      .onNodeHover(node => {
        state.hover = node?.id || null;
        container.style.cursor = node ? 'pointer' : 'grab';
        updateHighlights();
        onHover(node ? { ...node, record: recordMap.get(node.recordId) } : null);
      })
      .onNodeClick(choose)
      .onNodeDrag(() => { state.motion = false; graph.controls().autoRotate = false; updateLabels(); })
      .onNodeDragEnd(node => { node.fx = node.x; node.fy = node.y; node.fz = node.z; updateLabels(); })
      .onEngineStop(() => requestAnimationFrame(updateLabels));
    graph.camera().fov = 40;
    graph.camera().updateProjectionMatrix();
    graph.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    const keyLight = new lib.THREE.DirectionalLight('#ffffff', 2);
    keyLight.position.set(-200, 300, 600);
    graph.lights([new lib.THREE.HemisphereLight('#ffffff', '#26272c', 2.2), keyLight]);
    const controls = graph.controls();
    controls.enableDamping = !reducedMotion;
    controls.dampingFactor = 0.1;
    controls.rotateSpeed = 0.45;
    controls.zoomSpeed = 0.7;
    controls.panSpeed = 0.6;
    controls.autoRotate = false;
    controls.autoRotateSpeed = 0.25;
    controls.minDistance = 250;
    controls.maxDistance = 4500;
    controls.addEventListener('change', updateLabels);
    graph.graphData({ nodes: graphNodes.map(node => {
      const position = layoutPosition(node.id);
      return { ...node, ...position, fx: position.x, fy: position.y, fz: position.z };
    }), links: graphLinks.map(l => ({ ...l })) });
    lastWidth = Math.round(container.getBoundingClientRect().width);
    lastHeight = Math.round(container.getBoundingClientRect().height);
    resetCamera(false);
    container.dataset.graphRenderer = 'webgl';
    const canvas = graph.renderer().domElement;
    canvas.setAttribute('aria-label', '지식 연결 그래프. 기록 목록에서도 모든 내용을 선택할 수 있습니다.');
    canvas.setAttribute('role', 'img');
    observer = new ResizeObserver(() => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(resize);
    });
    observer.observe(container);
    document.fonts?.ready.then(() => {
      if (destroyed) return;
      objects.forEach(({ label }) => { const size = label.fontSize; label.fontSize = size + 1; label.fontSize = size; });
      updateLabels();
    });
    requestAnimationFrame(updateLabels);
  } catch (error) {
    console.warn('지식 그래프를 목록으로 표시합니다.', error.message);
    graph?._destructor?.();
    graph = null;
    container.replaceChildren();
    makeFallback();
  }

  return {
    setFilter(kind = 'all') {
      state.filter = kinds[kind] ? kind : 'all';
      if (graph) {
        graph.nodeVisibility(visible);
        graph.linkVisibility(link => visible(link.source) && visible(link.target));
      }
      updateHighlights();
      return getCounts();
    },
    select(id) {
      const node = graphNodes.find(n => n.id === id) || graphNodes.find(n => n.recordId === id);
      state.selected = node?.id || null;
      updateHighlights();
    },
    reset() {
      state.selected = null;
      state.hover = null;
      state.motion = false;
      if (graph) {
        graph.controls().autoRotate = false;
        applyResponsivePositions();
        resetCamera();
      }
      updateHighlights();
    },
    zoom(delta) {
      if (!graph) return;
      const camera = graph.camera();
      const target = graph.controls().target;
      const offset = camera.position.clone().sub(target).multiplyScalar(delta > 0 ? 0.8 : 1.25);
      offset.clampLength(250, 4500);
      graph.cameraPosition(target.clone().add(offset), target, duration());
    },
    resize,
    setMotion(enabled) {
      state.motion = !!enabled && !reducedMotion;
      if (graph) graph.controls().autoRotate = state.motion;
      return state.motion;
    },
    getCounts,
    destroy() {
      destroyed = true;
      observer?.disconnect();
      cancelAnimationFrame(resizeFrame);
      graph?._destructor?.();
      objects.forEach(({ group }) => group.traverse(object => {
        object.geometry?.dispose();
        object.material?.map?.dispose();
        object.material?.dispose();
      }));
      objects.clear();
      fallback?.remove();
    },
  };
}
