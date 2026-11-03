(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const data = window.SECOND_BRAIN_MOCK;
  const captures = data.captures.filter(c => !c.trashed);
  const all = [...data.concepts, ...captures, ...data.details];
  const byId = new Map(all.map(n => [n.id, n]));
  const colors = { concept:'#839c69', learning:'#729bbb', daily:'#c58b68', memo:'#a28fba', detail:'#acb69f' };
  const typeLabels = { learning:'학습', daily:'일상·감정', memo:'메모' };
  const state = { query:'',type:'all',visibility:'all',selected:'t-brain',near:false,depth:1,details:false,labels:true,view:'graph',tab:'content',rotating:false };
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const duration = reducedMotion ? 0 : 650;
  const objects = new Map();
  const positions = new Map(all.map(n => [n.id,{x:n.x,y:n.y,z:n.z}]));
  let graph, THREE, visibleNodes=[],visibleLinks=[],filteredCaptures=[],lastOpener=null,toastTimer;
  const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const kindType = n => n.kind === 'capture' ? n.types[0] : n.kind;
  const colorFor = n => colors[kindType(n)];
  const badge = n => `<span class="privacy-badge ${n.visibility==='private'?'private':''}">${icon(n.visibility==='private'?'lock':'check')}${n.visibility==='private'?'비공개':'공개 가능'}</span>`;
  const paragraphs = body => body.split('\n\n').map(p=>`<p>${esc(p)}</p>`).join('');
  function notify(message) { $('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,2400); }
  function currentBase() {
    const q=state.query.trim().toLocaleLowerCase();
    return captures.filter(c => (state.type==='all'||c.types.includes(state.type)) && (state.visibility==='all'||c.visibility===state.visibility) && (!q||[c.title,c.body,...c.tags,...c.topics.map(id=>byId.get(id).title)].join(' ').toLocaleLowerCase().includes(q)));
  }
  function makeGraphData() {
    const eligible=currentBase();
    const captureIds=new Set(eligible.map(c=>c.id));
    const topicIds=new Set(eligible.flatMap(c=>c.topics));
    let nodes=[...data.concepts.filter(t=>topicIds.has(t.id)),...eligible];
    let links=eligible.flatMap(c=>c.topics.map(t=>({id:`${c.id}-${t}`,source:t,target:c.id,type:'topic',label:'주제에 연결',directed:false,reason:'이 기록에 지정된 주제입니다.'})));
    links.push(...data.relations.filter(r=>captureIds.has(r.source)&&captureIds.has(r.target)).map(r=>({...r})));
    if(state.details) {
      const details=data.details.filter(n=>captureIds.has(n.captureId)&&byId.get(n.captureId).revision===n.revision);
      nodes.push(...details);
      links.push(...details.map(n=>({id:`part-${n.id}`,source:n.captureId,target:n.id,type:'part',label:'기록의 일부',directed:true,reason:`현재 저장본 v${n.revision}에 포함된 내용입니다.`})));
    }
    if(state.near) {
      const ids=new Set(nodes.map(n=>n.id));
      if(!ids.has(state.selected)) { state.near=false; }
      else {
        let keep=new Set([state.selected]);
        for(let i=0;i<state.depth;i++) {
          const next=new Set(keep);
          links.forEach(l=>{if(keep.has(l.source))next.add(l.target);if(keep.has(l.target))next.add(l.source);});
          keep=next;
        }
        nodes=nodes.filter(n=>keep.has(n.id));links=links.filter(l=>keep.has(l.source)&&keep.has(l.target));
      }
    }
    filteredCaptures=nodes.filter(n=>n.kind==='capture');
    visibleNodes=nodes;visibleLinks=links;
    return {nodes:nodes.map(n=>({...n,...positions.get(n.id)})),links:links.map(l=>({...l}))};
  }
  function selectedLinks(l) {return endId(l.source)===state.selected||endId(l.target)===state.selected;}
  function endId(value){return typeof value==='object'?value.id:value;}
  function wrapLabel(title) {
    if(title.length<=14)return title;
    const mid=Math.floor(title.length/2);let cut=title.indexOf(' ',mid-3);
    if(cut<0||cut>mid+6)cut=14;
    return title.slice(0,cut).trim()+'\n'+title.slice(cut).trim();
  }
  function createNode(n) {
    const {SpriteText}=window.GraphPreviewLib;
    const group=new THREE.Group();
    const isConcept=n.kind==='concept';
    const radius=isConcept?14:n.kind==='detail'?5:7;
    const geometry=n.kind==='detail'?new THREE.OctahedronGeometry(radius):new THREE.SphereGeometry(radius,24,20);
    const sphere=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:colorFor(n),roughness:.38,metalness:.05}));
    sphere.userData.previewNodeId=n.id;
    group.add(sphere);
    let ring;
    if(isConcept) {
      ring=new THREE.Mesh(new THREE.TorusGeometry(radius+4,.32,8,64),new THREE.MeshBasicMaterial({color:colorFor(n),transparent:true,opacity:.6}));
      group.add(ring);
    }
    const label=new SpriteText(wrapLabel(n.title),isConcept?18:14,'#42543b');
    label.fontFace='"Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif';
    label.fontSize=80;label.fontWeight=isConcept?'600':'400';
    label.backgroundColor='#f8faf3ee';label.padding=[4,2];label.borderRadius=2;
    label.position.y=-radius-(isConcept?21:20);
    label.material.depthTest=false;label.material.depthWrite=false;label.renderOrder=10;
    // 제목 스프라이트가 앞뒤에 있는 실제 노드의 선택을 가로채지 않도록 한다.
    label.raycast=()=>{};
    group.add(label);
    objects.set(n.id,{sphere,ring,label,group,labelScale:label.scale.clone(),radius});
    return group;
  }
  function updateLabelSizes(){
    if(!graph)return;
    const camera=graph.camera();camera.updateMatrixWorld();
    const h=graph.height(),w=graph.width();if(!h||!w)return;
    const used=[];
    const ids=[...objects.keys()].filter(id=>visibleNodes.some(n=>n.id===id)).sort((a,b)=>{
      const score=id=>id===state.selected?0:byId.get(id).kind==='concept'?1:2;
      return score(a)-score(b);
    });
    for(const id of ids){
      const obj=objects.get(id),n=byId.get(id);
      const world=obj.group.position.clone();
      const depth=-world.clone().applyMatrix4(camera.matrixWorldInverse).z;
      if(depth<=0){obj.label.visible=false;continue;}
      const unit=h/(2*Math.tan(camera.fov*Math.PI/360)*depth);
      const textHeight=n.kind==='concept'?18:14;
      const factor=(n.kind==='concept'?13:11.5)/(textHeight*unit);
      obj.label.scale.copy(obj.labelScale).multiplyScalar(factor);
      obj.label.position.y=-obj.radius-19*factor;
      const projected=world.add(obj.label.position).project(camera);
      const cx=(projected.x+1)*w/2,cy=(1-projected.y)*h/2;
      const width=obj.label.scale.x*unit,height=obj.label.scale.y*unit;
      const rect={x:cx-width/2-3,y:cy-height/2-3,r:cx+width/2+3,b:cy+height/2+3};
      const allowed=(n.kind!=='concept'||state.labels)&&rect.x>6&&rect.r<w-6&&rect.y>6&&rect.b<h-6&&!used.some(a=>rect.x<a.r&&rect.r>a.x&&rect.y<a.b&&rect.b>a.y);
      obj.label.visible=allowed;
      if(allowed)used.push(rect);
    }
  }
  function updateHighlights() {
    if(!graph)return;
    const neighbours=new Set([state.selected]);
    visibleLinks.forEach(l=>{if(l.source===state.selected)neighbours.add(l.target);if(l.target===state.selected)neighbours.add(l.source);});
    objects.forEach((obj,id)=>{
      const n=byId.get(id);const selected=id===state.selected;
      obj.sphere.scale.setScalar(selected?1.3:1);
      obj.sphere.material.emissive.set(selected?'#35452a':'#000000');obj.sphere.material.emissiveIntensity=.14;
      obj.label.color=selected?'#253c2a':n.kind==='concept'?'#465e37':'#52604b';
      obj.label.fontWeight=selected||n.kind==='concept'?'600':'400';
      obj.labelScale.copy(obj.label.scale);
      obj.label.visible=n.kind==='concept'?state.labels:true;
      if(obj.ring){obj.ring.material.opacity=selected?.95:.45;obj.ring.scale.setScalar(selected?1.2:1);}
    });
    graph.linkColor(l=>selectedLinks(l)?'#7a9863':l.type==='topic'?'#cad7bd':l.type==='derived'?'#b4a2c8':'#bec8b4')
      .linkWidth(l=>selectedLinks(l)?1.1:l.type==='topic'?.65:.75)
      .linkDirectionalArrowLength(l=>l.directed?4:0)
      .linkDirectionalArrowColor(l=>l.type==='derived'?'#a18bb6':'#8c9f7a');
    updateLabelSizes();
  }
  function initializeGraph(){
    try {
      const lib=window.GraphPreviewLib;
      if(!lib)throw new Error('Graph library unavailable');
      THREE=lib.THREE;
      const holder=$('#graph');
      graph=new lib.ForceGraph3D(holder,{controlType:'orbit',rendererConfig:{antialias:true,alpha:true,preserveDrawingBuffer:true}})
        .width(holder.clientWidth).height(holder.clientHeight).backgroundColor('#f8faf3').showNavInfo(false)
        .nodeThreeObject(createNode).nodeLabel(n=>`${esc(n.title)}<br><small>${n.kind==='concept'?'주제':n.kind==='detail'?'저장본의 일부':typeLabels[n.types[0]]} · 눌러서 읽기</small>`)
        .linkLabel(l=>`${esc(l.label)}<br><small>${esc(l.reason)}</small>`)
        .linkOpacity(.85).linkResolution(6).linkDirectionalArrowRelPos(.75)
        .cooldownTicks(0).enableNodeDrag(true).onEngineStop(()=>requestAnimationFrame(updateLabelSizes))
        .onNodeHover(n=>{holder.style.cursor=n?'pointer':'grab';})
        .onNodeDrag(()=>{stopRotation();updateLabelSizes();})
        .onNodeDragEnd(n=>{n.fx=n.x;n.fy=n.y;n.fz=n.z;positions.set(n.id,{x:n.x,y:n.y,z:n.z});});
      const controls=graph.controls();
      controls.enableDamping=true;controls.dampingFactor=.08;controls.rotateSpeed=.55;controls.zoomSpeed=.8;controls.panSpeed=.65;controls.autoRotate=false;controls.autoRotateSpeed=.35;controls.minDistance=80;controls.maxDistance=4500;
      controls.addEventListener('start',()=>stopRotation());
      controls.addEventListener('change',updateLabelSizes);
      graph.renderer().setPixelRatio(Math.min(devicePixelRatio,2));
      const ambient=new THREE.HemisphereLight('#ffffff','#cbd5bc',1.4);
      const light=new THREE.DirectionalLight('#ffffff',1.5);light.position.set(-150,400,550);graph.lights([ambient,light]);
      // 호버 갱신 프레임을 기다리지 않고 탭 위치에서 실제 노드를 판별한다.
      // 드래그·멀티터치 회전/확대와 단순 선택은 분리한다.
      const canvas=graph.renderer().domElement,pointers=new Map(),raycaster=new THREE.Raycaster();
      let multiTouch=false;
      canvas.addEventListener('pointerdown',event=>{
        pointers.set(event.pointerId,{x:event.clientX,y:event.clientY,moved:false});
        if(pointers.size>1)multiTouch=true;
      });
      canvas.addEventListener('pointermove',event=>{const start=pointers.get(event.pointerId);if(start&&Math.hypot(event.clientX-start.x,event.clientY-start.y)>7)start.moved=true;});
      canvas.addEventListener('pointercancel',event=>{pointers.delete(event.pointerId);if(!pointers.size)multiTouch=false;});
      canvas.addEventListener('pointerup',event=>{
        const start=pointers.get(event.pointerId),skip=multiTouch||!start||start.moved||event.button!==0;
        pointers.delete(event.pointerId);if(!pointers.size)multiTouch=false;if(skip)return;
        const rect=canvas.getBoundingClientRect();
        const point=new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2);
        graph.scene().updateMatrixWorld(true);graph.camera().updateMatrixWorld(true);
        raycaster.setFromCamera(point,graph.camera());
        const hit=raycaster.intersectObjects([...objects.values()].map(obj=>obj.sphere),false)[0];
        if(hit)selectNode(hit.object.userData.previewNodeId);
        else if(innerWidth<=1050)closeDetail();
      });
      let previousWidth=holder.clientWidth;
      const resize=new ResizeObserver(()=>{if(holder.clientWidth>0&&holder.clientHeight>0){graph.width(holder.clientWidth).height(holder.clientHeight);if(Math.abs(previousWidth-holder.clientWidth)>80)fitGraph();previousWidth=holder.clientWidth;updateLabelSizes();}});resize.observe(holder);
    } catch(error) {
      console.warn('3D 미리보기를 열 수 없습니다.',error.message);
      $('#graph-error').hidden=false;
      $('#auto-rotate').disabled=true;
      ['#zoom-in','#zoom-out','#fit'].forEach(id=>$(id).disabled=true);
    }
  }
  function disposeObjects(){objects.forEach(o=>o.group.traverse(obj=>{obj.geometry?.dispose();if(obj.material){obj.material.map?.dispose();obj.material.dispose();}}));objects.clear();}
  function fitGraph(resetAngle=false){
    if(!graph||!visibleNodes.length)return;
    stopRotation();
    if(resetAngle){graph.cameraPosition({x:0,y:80,z:1150},{x:0,y:0,z:0},0);}
    graph.zoomToFit(duration,35);
  }
  function renderGraph(fit=false){
    const graphData=makeGraphData();
    if(graph){disposeObjects();graph.graphData(graphData);updateHighlights();}
    $('#empty-state').hidden=visibleNodes.length>0;
    $('#graph-count').textContent=`${filteredCaptures.length}개 기록 · ${visibleNodes.filter(n=>n.kind==='concept').length}개 주제`;
    $('#graph-caption').hidden=state.near||!!state.query||state.type!=='all'||state.visibility!=='all';
    $('#depth-wrap').hidden=!state.near;
    $('#view-all').classList.toggle('active',!state.near);$('#view-all').setAttribute('aria-pressed',String(!state.near));
    $('#view-near').classList.toggle('active',state.near);$('#view-near').setAttribute('aria-pressed',String(state.near));
    $('#view-near').disabled=!state.selected||!visibleNodes.some(n=>n.id===state.selected);
    renderSidebar();renderList();renderDetail();
    if(fit&&graph&&visibleNodes.length)requestAnimationFrame(()=>fitGraph());
  }
  function renderSidebar(){
    $('#type-filters').innerHTML=Object.entries(typeLabels).map(([type,label])=>`<button class="type-item ${state.type===type?'active':''}" data-type="${type}" aria-pressed="${state.type===type}"><i class="dot ${type}"></i><span>${label}</span><span>${captures.filter(c=>c.types.includes(type)).length}</span></button>`).join('');
    const base=currentBase();const topics=data.concepts.filter(t=>base.some(c=>c.topics.includes(t.id)));
    $('#topic-count').textContent=topics.length;
    $('#topic-list').innerHTML=topics.map(t=>`<button class="topic-item ${state.selected===t.id?'active':''}" data-node="${t.id}"><i class="dot"></i><span>${esc(t.title)}</span><span>${base.filter(c=>c.topics.includes(t.id)).length}</span></button>`).join('')||'<p class="side-hint">일치하는 주제가 없어요.</p>';
    $('#all-count').textContent=captures.length;
  }
  function renderList(){
    $('#list-count').textContent=`${filteredCaptures.length}개 기록`;
    $('#record-list').innerHTML=filteredCaptures.slice().sort((a,b)=>b.date.localeCompare(a.date)).map(c=>`<button class="record-row ${state.selected===c.id?'active':''}" data-node="${c.id}"><i class="dot ${c.types[0]}"></i><div><strong>${esc(c.title)}</strong><p>${esc(c.body.replaceAll('\n',' '))}</p><small>${esc(c.date)} · ${typeLabels[c.types[0]]} · ${c.visibility==='private'?'비공개':'공개 가능'}</small></div>${icon('arrow')}</button>`).join('')||'<div class="list-empty">조건에 맞는 기록이 없어요.<br><button class="text-button" data-action="reset">필터 초기화</button></div>';
  }
  function relatedButton(n,note=''){
    return `<button class="related-item" data-node="${n.id}"><i class="dot ${kindType(n)}"></i><div><span class="related-title">${esc(n.title)}</span><span class="related-note">${esc(note)}</span></div>${icon('arrow')}</button>`;
  }
  function closeButton(){return `<button class="icon-button detail-close" data-action="close-detail" aria-label="상세 닫기">${icon('x')}</button>`;}
  function focusButton(){return `<button class="focus-button" data-action="focus">${icon('graph')}이 지식의 주변 연결 보기</button>`;}
  function renderDetail(){
    const n=byId.get(state.selected);
    const accessible=new Set(currentBase().map(c=>c.id));
    const isAvailable=n&&(n.kind==='capture'?accessible.has(n.id):n.kind==='detail'?state.details&&accessible.has(n.captureId):captures.some(c=>accessible.has(c.id)&&c.topics.includes(n.id)));
    if(!isAvailable){$('#detail-content').innerHTML=`<div class="detail-top"><span class="detail-kind">지식 살펴보기</span>${closeButton()}</div><h2 class="detail-title">연결된 생각을<br>만나보세요.</h2><p class="detail-summary">지도에서 점을 선택하면 여기에 저장 내용과 연결이 표시됩니다.</p>`;return;}
    if(n.kind==='concept'){
      const related=captures.filter(c=>accessible.has(c.id)&&c.topics.includes(n.id));
      $('#detail-content').innerHTML=`<div class="detail-top"><span class="detail-kind"><i class="dot concept"></i>주제</span>${closeButton()}</div><h2 class="detail-title">${esc(n.title)}</h2><div class="detail-meta">${related.length}개의 기록이 연결되어 있어요</div><p class="detail-summary">${esc(n.summary)}</p><div class="detail-tabs"><button class="active" aria-current="true">연결된 기록</button></div><div class="detail-body">${related.map(c=>relatedButton(c,`${typeLabels[c.types[0]]} · ${c.date}`)).join('')}${focusButton()}<p class="mini-note" style="margin-top:18px">하나의 기록은 여러 주제와 연결될 수 있어요. 주제는 기록을 담는 폴더와 달라요.</p></div>`;return;
    }
    if(n.kind==='detail'){
      const parent=byId.get(n.captureId);
      $('#detail-content').innerHTML=`<div class="detail-top"><span class="detail-kind"><i class="dot"></i>기록 안의 세부 지식</span>${closeButton()}</div><h2 class="detail-title">${esc(n.title)}</h2><div class="detail-meta">저장본 v${n.revision}의 일부 ${badge(parent)}</div><div class="detail-body"><div class="detail-part">${paragraphs(n.body)}</div><h3>이 내용이 속한 기록</h3>${relatedButton(parent,`현재 저장본 v${n.revision}`)}<p class="mini-note">별도의 원본이 아니라 이 저장본에 포함된 부분이에요. 공개 범위도 부모 기록을 따릅니다.</p>${focusButton()}</div>`;return;
    }
    const relationships=data.relations.filter(r=>(r.source===n.id||r.target===n.id)&&accessible.has(r.source)&&accessible.has(r.target));
    const topics=n.topics.map(id=>byId.get(id));
    const otherRelated=captures.filter(c=>c.id!==n.id&&accessible.has(c.id)&&c.topics.some(t=>n.topics.includes(t))).slice(0,3);
    let content='';
    if(state.tab==='history'){
      content=`<p class="mini-note">수정 전 저장본은 이력에서만 확인해요. 지도에는 현재 버전이 표시됩니다.</p>${n.history.map((h,i)=>`<div class="history-item"><strong>v${h.revision} ${i===0?'· 현재 저장본':''}</strong><time>${h.date}</time><p>${esc(h.note)}</p><details><summary>이 버전의 내용 보기</summary>${paragraphs(h.body)}</details></div>`).join('')}`;
    }else if(state.tab==='connections'){
      content=`<h3>기록 사이의 관계 <span>${relationships.length}</span></h3>${relationships.length?relationships.map(r=>{
        const outward=r.source===n.id;const other=byId.get(outward?r.target:r.source);
        return relatedButton(other,`${r.label}${r.directed?(outward?' · 이 기록에서 연결':' · 이 기록으로 연결'):''} — ${r.reason}`);
      }).join(''):'<p class="mini-note">직접 연결된 기록은 아직 없어요.</p>'}<h3>같은 주제로 만나는 기록</h3>${otherRelated.map(c=>relatedButton(c,'공유하는 주제 · 인과관계를 뜻하지 않아요')).join('')}${focusButton()}`;
    }else{
      content=`${paragraphs(n.body)}<div class="saved-status">${icon('check')}저장된 정리본 · v${n.revision}</div><h3>연결된 주제</h3><div class="topic-tags">${topics.map(t=>`<button class="topic-tag" data-node="${t.id}">${esc(t.title)}</button>`).join('')}</div><h3>함께 살펴볼 기록</h3>${otherRelated.slice(0,2).map(c=>relatedButton(c,'같은 주제로 연결됨')).join('')}${focusButton()}<p class="mini-note" style="margin-top:18px">${n.visibility==='private'?'비공개로 지정한 예시입니다. 이 화면은 소유자 관점이라 비공개 기록도 볼 수 있어요.':'공개 가능한 기록입니다. 공유는 꺼져 있으며 인터넷에 게시되지 않아요.'}</p>`;
    }
    $('#detail-content').innerHTML=`<div class="detail-top"><span class="detail-kind"><i class="dot ${n.types[0]}"></i>${typeLabels[n.types[0]]} 기록</span>${closeButton()}</div><h2 class="detail-title">${esc(n.title)}</h2><div class="detail-meta"><time>${n.date.replaceAll('-','. ')}</time><span>v${n.revision}</span>${badge(n)}</div><div class="detail-tabs" role="tablist" aria-label="기록 상세 보기">${[['content','저장 내용'],['connections','연결'],['history','변경 이력']].map(([id,label])=>`<button role="tab" aria-selected="${state.tab===id}" data-tab="${id}" class="${state.tab===id?'active':''}">${label}</button>`).join('')}</div><div class="detail-body" role="tabpanel">${content}</div>`;
  }
  function selectNode(id,{open=true}={}){
    if(!byId.has(id))return;
    state.selected=id;state.tab='content';
    if(state.near)renderGraph(true);else{updateHighlights();renderSidebar();renderDetail();renderList();}
    closeSidebar();
    if(open&&innerWidth<=1050){lastOpener=document.activeElement;$('#detail-panel').classList.add('open');$('#detail-panel').querySelector('button')?.focus({preventScroll:true});}
    if(graph){stopRotation();}
  }
  function closeDetail(){
    $('#detail-panel').classList.remove('open');
    if(lastOpener?.isConnected)lastOpener.focus({preventScroll:true});
  }
  function closeSidebar(){$('#sidebar').classList.remove('open');$('#panel-scrim').hidden=true;}
  function setView(view){
    state.view=view;
    $('#graph-stage').hidden=view==='list';$('#list-view').hidden=view!=='list';
    $('#nav-graph').classList.toggle('active',view==='graph');$('#nav-list').classList.toggle('active',view==='list');
    $('#nav-graph').setAttribute('aria-pressed',String(view==='graph'));$('#nav-list').setAttribute('aria-pressed',String(view==='list'));
    $('#breadcrumb-view').textContent=view==='graph'?'지식 지도':'모든 기록';
    closeSidebar();
    if(graph){view==='list'?graph.pauseAnimation():graph.resumeAnimation();if(view==='graph')requestAnimationFrame(()=>{graph.width($('#graph').clientWidth).height($('#graph').clientHeight);});}
  }
  function stopRotation(){if(graph)graph.controls().autoRotate=false;state.rotating=false;$('#auto-rotate').setAttribute('aria-pressed','false');$('#auto-rotate span').textContent='자동 회전';}
  function resetFilters(){state.query='';state.type='all';state.visibility='all';state.near=false;$('#search').value='';$('#visibility').value='all';renderGraph(true);}
  function moveZoom(factor){if(!graph)return;const camera=graph.camera();const target=graph.controls().target.clone();const next=camera.position.clone().sub(target).multiplyScalar(factor).add(target);graph.cameraPosition(next,target,duration);}
  document.addEventListener('click',event=>{
    const node=event.target.closest('[data-node]');if(node){selectNode(node.dataset.node);return;}
    const type=event.target.closest('[data-type]');if(type){state.type=state.type===type.dataset.type?'all':type.dataset.type;state.near=false;renderGraph(true);closeDetail();return;}
    const tab=event.target.closest('[data-tab]');if(tab){state.tab=tab.dataset.tab;renderDetail();$('#detail-panel').querySelector(`[data-tab="${state.tab}"]`)?.focus({preventScroll:true});return;}
    const action=event.target.closest('[data-action]')?.dataset.action;
    if(action==='reset')resetFilters();
    if(action==='list')setView('list');
    if(action==='close-detail')closeDetail();
    if(action==='focus'){state.near=true;setView('graph');renderGraph(true);closeDetail();}
  });
  $('#search').addEventListener('input',()=>{state.query=$('#search').value;state.near=false;renderGraph(true);closeDetail();});
  $('#visibility').addEventListener('change',()=>{state.visibility=$('#visibility').value;state.near=false;renderGraph(true);closeDetail();});
  $('#type-reset').addEventListener('click',()=>{state.type='all';state.near=false;renderGraph(true);});
  $('#view-all').addEventListener('click',()=>{state.near=false;renderGraph(true);});
  $('#view-near').addEventListener('click',()=>{state.near=true;renderGraph(true);});
  $('#depth').addEventListener('change',()=>{state.depth=Number($('#depth').value);renderGraph(true);});
  $('#show-labels').addEventListener('change',()=>{state.labels=$('#show-labels').checked;updateHighlights();});
  $('#show-details').addEventListener('change',()=>{state.details=$('#show-details').checked;if(!state.details&&byId.get(state.selected)?.kind==='detail')state.selected=byId.get(state.selected).captureId;renderGraph(true);});
  $('#nav-graph').addEventListener('click',()=>setView('graph'));$('#nav-list').addEventListener('click',()=>setView('list'));
  $('#zoom-in').addEventListener('click',()=>moveZoom(.8));$('#zoom-out').addEventListener('click',()=>moveZoom(1.25));$('#fit').addEventListener('click',()=>fitGraph());
  $('#auto-rotate').addEventListener('click',()=>{if(!graph)return;state.rotating=!state.rotating;graph.controls().autoRotate=state.rotating;$('#auto-rotate').setAttribute('aria-pressed',String(state.rotating));$('#auto-rotate span').textContent=state.rotating?'회전 멈추기':'자동 회전';});
  $('#reset-layout').addEventListener('click',()=>{all.forEach(n=>positions.set(n.id,{x:n.x,y:n.y,z:n.z}));renderGraph();fitGraph(true);notify('처음 위치로 돌아왔어요.');});
  $('#mobile-menu').addEventListener('click',()=>{$('#sidebar').classList.add('open');$('#panel-scrim').hidden=false;$('#sidebar-close').focus();});
  $('#sidebar-close').addEventListener('click',()=>{closeSidebar();$('#mobile-menu').focus();});$('#panel-scrim').addEventListener('click',closeSidebar);
  function closeHelp(){$('#help-panel').hidden=true;$('#help-toggle').setAttribute('aria-expanded','false');}
  $('#help-toggle').addEventListener('click',()=>{$('#help-panel').hidden=!$('#help-panel').hidden;$('#help-toggle').setAttribute('aria-expanded',String(!$('#help-panel').hidden));});$('#help-close').addEventListener('click',()=>{closeHelp();$('#help-toggle').focus();});
  document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('#search').focus();}if(event.key==='Escape'){closeHelp();closeDetail();closeSidebar();}if(event.target.matches('[data-tab]')&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();const tabs=['content','connections','history'];const next=(tabs.indexOf(state.tab)+(event.key==='ArrowRight'?1:2))%3;state.tab=tabs[next];renderDetail();$(`[data-tab="${state.tab}"]`).focus();}});
  if(!navigator.platform.toLowerCase().includes('mac'))$('.search-wrap kbd').textContent='Ctrl K';
  initializeGraph();renderGraph();if(graph){graph.cameraPosition({x:0,y:50,z:1250},{x:0,y:0,z:0},0);requestAnimationFrame(()=>fitGraph(true));}
  // 읽기 전용 검증용 접근점. 실제 데이터/서비스와 연결되지 않는다.
  window.graphPreview={get state(){return {...state};},get graph(){return graph;},get nodes(){return visibleNodes.map(n=>({...n}));},get links(){return visibleLinks.map(l=>({...l}));}};
})();
