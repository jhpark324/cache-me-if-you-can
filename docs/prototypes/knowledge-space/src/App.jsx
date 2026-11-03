import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Theme, Badge, Button, Dialog, IconButton, Kbd, ScrollArea, SegmentedControl, Separator, Skeleton, TextField, Tooltip } from '@radix-ui/themes';
import { ArrowRight, ArrowUp, Check, ChevronDown, ChevronRight, Copy, FileText, Layers3, List, Maximize, Menu, Minus, Network, Pause, Play, Plus, Search, Sparkles, X } from 'lucide-react';
import '@radix-ui/themes/styles.css';
import { createGraph } from '../graph.js';
import { records, kinds, graphNodes } from '../mock-data.js';

const samples = ['배운 내용을 오래 기억하려면 어떻게 해야 할까?', '내가 기록을 남기는 이유는?'];
const byId = id => records.find(record => record.id === id);
const info = record => kinds[record.kind];
function useMedia(query) {
  const [matches, setMatches] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const media = matchMedia(query), change = () => setMatches(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, [query]);
  return matches;
}
// Retain an outgoing surface only for its exit animation. A new value cancels the exit.
function usePresence(value, duration, reduced) {
  const [retained, setRetained] = useState(value);
  useEffect(() => {
    if (value) { setRetained(value); return; }
    if (!retained) return;
    const timer = setTimeout(() => setRetained(null), reduced ? 0 : duration);
    return () => clearTimeout(timer);
  }, [value, retained, duration, reduced]);
  return { shown: value || retained, exiting: !value && Boolean(retained) };
}
function findRecords(question) {
  const q = question.trim().toLowerCase();
  if (/배운.*기억|오래.*기억/.test(q)) return ['learning', 'zettelkasten', 'retrieval'].map(byId);
  if (/기록.*이유|남기는 이유/.test(q)) return ['capture', 'weekly', 'walk'].map(byId);
  const tokens = q.split(/[\s?.,!]+/).filter(word => word.length > 1);
  return records.map(record => ({ record, score: tokens.reduce((sum, word) => sum + (`${record.title} ${record.topic} ${record.paragraphs.join(' ')}`.toLowerCase().includes(word) ? 1 : 0), 0) }))
    .filter(item => item.score > 0).sort((a, b) => b.score - a.score).slice(0, 3).map(item => item.record);
}
function ToolButton({ label, children, ...props }) {
  return <Tooltip content={label}><IconButton type="button" size="2" color="gray" variant="ghost" aria-label={label} {...props}>{children}</IconButton></Tooltip>;
}
function Dot({ color }) { return <span className="type-dot" style={{ background: color }} aria-hidden="true"/>; }

function SourcePanel({ source, onClose, onSelect, buttonRef, exiting }) {
  const record = byId(source.id);
  return <aside className={`source-panel ${exiting ? 'is-closing' : ''}`} aria-labelledby="source-title" aria-hidden={exiting || undefined} inert={exiting}>
    <div className="panel-light" aria-hidden="true"/>
    <header className="source-toolbar"><span><FileText size={16}/>출처</span><IconButton ref={buttonRef} type="button" size="2" color="gray" variant="ghost" aria-label="출처 패널 닫기" onClick={onClose}><X size={18}/></IconButton></header>
    <ScrollArea type="auto" scrollbars="vertical" className="source-scroll" key={record.id}>
      <div className="source-inner">
        <div className="source-meta"><span><Dot color={info(record).color}/>{info(record).label}</span><time className="source-date">{record.date}</time></div>
        <h2 className="source-title" id="source-title">{record.title}</h2>
        <div className="source-topic"><Badge color="gray" variant="soft" size="2">{record.topic}</Badge></div>
        {source.citation && <div className="citation-notice">인용 구간</div>}
        <article className="source-body" id="source-body">{record.paragraphs.map((paragraph, index) => <p key={index}>{source.citation && index === record.highlightIndex ? <mark>{paragraph}</mark> : paragraph}</p>)}</article>
        <Separator size="4"/>
        <section className="related-section"><h3>연결된 기록</h3>{record.related.map(byId).filter(Boolean).map(item => <Button key={item.id} variant="ghost" color="gray" className="related-button" onClick={() => onSelect(item.id)}><Network size={15}/><span>{item.title}</span><ChevronRight size={15}/></Button>)}</section>
      </div>
    </ScrollArea>
  </aside>;
}

function App() {
  const mobile = useMedia('(max-width: 760px)'), systemReduced = useMedia('(prefers-reduced-motion: reduce)');
  const [pauseMotion, setPauseMotion] = useState(false), reduced = systemReduced || pauseMotion;
  const [view, setView] = useState('graph'), [filter, setFilter] = useState('all'), [more, setMore] = useState(false), [menu, setMenu] = useState(false);
  const [query, setQuery] = useState(''), [answer, setAnswer] = useState(null), [source, setSource] = useState(null), [hover, setHover] = useState(null);
  const [renderer, setRenderer] = useState('loading'), [toast, setToast] = useState('');
  const { shown: shownAnswer, exiting: answerExiting } = usePresence(answer, 180, reduced);
  const { shown: shownSource, exiting: sourceExiting } = usePresence(source, 220, reduced);
  const graphHost = useRef(null), graph = useRef(null), input = useRef(null), returnFocus = useRef(null), requestId = useRef(0), callbacks = useRef({}), closeButton = useRef(null);
  const searchDock = useRef(null), dockPosition = useRef(null), dockAnimation = useRef(null);
  const closeSource = useCallback(() => {
    setSource(null);
    requestAnimationFrame(() => { if (returnFocus.current?.isConnected) returnFocus.current.focus({ preventScroll: true }); else input.current?.focus({ preventScroll: true }); });
  }, []);
  const openSource = useCallback((id, citation = false) => {
    if (!byId(id)) return;
    const active = document.activeElement;
    if (!active?.closest('.source-panel')) returnFocus.current = active;
    setMenu(false); setSource({ id, citation });
  }, []);
  callbacks.current.openSource = openSource;
  useEffect(() => { document.documentElement.dataset.motion = reduced ? 'reduced' : 'full'; }, [reduced]);
  useEffect(() => {
    let cancelled = false;
    document.fonts.ready.then(() => {
      if (cancelled) return;
      try {
        graph.current = createGraph(graphHost.current, { onSelect: node => callbacks.current.openSource(node.recordId), onHover: node => setHover(node?.title || null) });
        graph.current.setMotion(false); setRenderer(graphHost.current.dataset.graphRenderer);
      } catch { setRenderer('failed'); setView('list'); }
    });
    return () => { cancelled = true; graph.current?.destroy(); };
  }, []);
  useEffect(() => {
    graph.current?.select(source?.id || null);
    if (source && !mobile) requestAnimationFrame(() => closeButton.current?.focus({ preventScroll: true }));
  }, [source?.id, mobile]);
  useLayoutEffect(() => {
    const element = searchDock.current;
    if (!element) return;
    dockAnimation.current?.cancel();
    const next = element.getBoundingClientRect(), previous = dockPosition.current;
    if (previous && !reduced && !mobile && Math.abs(previous.left - next.left) > 1) {
      dockAnimation.current = element.animate([{ translate: `${previous.left - next.left}px 0` }, { translate: '0px 0px' }], { duration: 360, easing: 'cubic-bezier(.16,1,.3,1)' });
    }
    dockPosition.current = { left: next.left };
    graph.current?.resize();
  }, [Boolean(shownSource), mobile, reduced]);
  useEffect(() => {
    const keydown = event => {
      if (event.defaultPrevented || (event.key === 'Escape' && event.target instanceof Element && event.target.closest('[role="dialog"]'))) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSource(null); setMenu(false); requestAnimationFrame(() => input.current?.focus()); }
      if (event.key === 'Escape') {
        if (source && !mobile) { event.preventDefault(); closeSource(); }
        else if (!source && menu) setMenu(false);
        else if (!source && answer) { requestId.current++; setAnswer(null); requestAnimationFrame(() => input.current?.focus()); }
      }
    };
    document.addEventListener('keydown', keydown);
    return () => document.removeEventListener('keydown', keydown);
  }, [source, answer, menu, mobile, closeSource]);
  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(''), 2800); return () => clearTimeout(timer); } }, [toast]);
  useEffect(() => { if (!mobile) setMenu(false); }, [mobile]);
  function navigate(next) { requestId.current++; setAnswer(null); setSource(null); setView(next); setMenu(false); requestAnimationFrame(() => graph.current?.resize()); }
  function changeFilter(kind) { const next = filter === kind ? 'all' : kind; setFilter(next); setMenu(false); setSource(null); graph.current?.setFilter(next); }
  async function search(question) {
    if (!question.trim()) { input.current?.focus(); return; }
    const current = ++requestId.current;
    setQuery(question); setView('graph'); setSource(null); setMenu(false); setAnswer({ question, status: 'searching', records: [] });
    await new Promise(resolve => setTimeout(resolve, 420));
    if (current !== requestId.current) return;
    setAnswer({ question, status: 'reading', records: [] });
    await new Promise(resolve => setTimeout(resolve, 330));
    if (current !== requestId.current) return;
    setAnswer({ question, status: 'ready', records: findRecords(question) });
  }
  function dismissAnswer() { requestId.current++; setAnswer(null); setSource(null); input.current?.focus(); }
  async function copyAnswer() {
    try {
      const body = document.getElementById('answer-content')?.innerText || '';
      await navigator.clipboard.writeText(`${shownAnswer.question}\n\n${body}\n\n출처\n${shownAnswer.records.map((record, index) => `${index + 1}. ${record.title}`).join('\n')}`);
      setToast('답변을 복사했어요.');
    } catch { setToast('복사하지 못했어요. 본문을 선택해서 복사해 주세요.'); }
  }
  const selected = records.filter(record => filter === 'all' || record.kind === filter), primary = ['knowledge', 'reflection', 'idea', 'decision'], ready = shownAnswer?.status === 'ready';
  const responseIntro = shownAnswer && /배운.*기억|오래.*기억/.test(shownAnswer.question)
    ? <>배운 내용을 오래 남기는 방법은 <strong>내 말로 설명하고, 작은 단위로 연결하고, 다시 꺼내 읽는 것</strong>으로 이어져요.</>
    : shownAnswer && /기록.*이유|남기는 이유/.test(shownAnswer.question)
    ? <>그날의 생각을 붙잡아 두고, 시간이 지난 뒤 <strong>내가 어떻게 달라졌는지 알아보기 위해</strong> 기록하고 있어요.</>
    : <>질문과 관련된 기록에서 다음 내용을 찾았어요.</>;
  const shortTitles = { learning: '내 말로 설명하기', zettelkasten: '하나의 생각을 하나의 메모로', retrieval: '다시 찾는 경로 만들기', capture: '작게라도 남기기', weekly: '변화 발견하기', walk: '떠오른 맥락 남기기' };
  return <Theme appearance="dark" grayColor="gray" accentColor="orange" radius="medium" scaling="100%">
    <div className={`app-shell ${shownSource && !mobile ? 'has-source' : ''} ${shownAnswer ? 'has-answer' : ''} ${view === 'list' ? 'is-list' : ''} ${menu ? 'menu-open' : ''}`}>
      <div className="ambient-light" aria-hidden="true"/>
      <a className="skip-link" href="#search-input">검색으로 바로 이동</a>
      {menu && <button className="sidebar-scrim" aria-label="탐색 메뉴 닫기" onClick={() => setMenu(false)}/>}
      <aside className="sidebar" aria-label="지식 공간 탐색" inert={mobile && !menu}>
        <div className="panel-light" aria-hidden="true"/>
        <a className="brand" href="./"><span className="brand-mark"><Network size={23}/></span><span className="brand-copy">Second Brain</span></a>
        <nav className="main-nav" aria-label="화면 선택">
          <Button className="nav-button" variant={view === 'graph' ? 'soft' : 'ghost'} color="gray" data-active={view === 'graph'} onClick={() => navigate('graph')}><Network size={18}/><span>지식 지도</span></Button>
          <Button className="nav-button" variant={view === 'list' ? 'soft' : 'ghost'} color="gray" data-active={view === 'list'} onClick={() => navigate('list')}><Layers3 size={18}/><span>모든 기록</span><span className="nav-count">{records.length}</span></Button>
        </nav>
        <section className="sidebar-section"><div className="section-title">기록 유형</div>
          {[...primary, ...(more ? Object.keys(kinds).filter(kind => !primary.includes(kind)) : [])].map(kind => <Button key={kind} variant="ghost" color="gray" className="type-filter" data-kind={kind} data-active={filter === kind} aria-pressed={filter === kind} onClick={() => changeFilter(kind)}><Dot color={kinds[kind].color}/><span>{kinds[kind].label}</span><span className="type-count">{records.filter(record => record.kind === kind).length}</span></Button>)}
          <Button variant="ghost" color="gray" className="more-types" onClick={() => setMore(!more)} aria-expanded={more}>{more ? '간략히 보기' : '모든 유형 보기'}<ChevronDown size={14} style={{ transform: more ? 'rotate(180deg)' : undefined }}/></Button>
        </section>
        <section className="sidebar-section recent-section"><div className="section-title">최근 기록</div>{['search', 'connections', 'weekly'].map(byId).map(record => <Button key={record.id} variant="ghost" color="gray" className="recent-record" onClick={() => openSource(record.id)}><FileText size={16}/><span>{record.title}</span></Button>)}</section>
      </aside>
      <main className="workspace" id="workspace" inert={Boolean(source && mobile)}>
        <header className="workspace-toolbar"><div className="breadcrumb"><ToolButton label="탐색 메뉴 열기" className="mobile-menu" aria-expanded={menu} onClick={() => setMenu(!menu)}><Menu size={20}/></ToolButton><span>{view === 'graph' ? '지식 지도' : '모든 기록'}</span></div><div className="toolbar-actions"><Badge className="demo-badge" color="gray" variant="outline" size="1">목데이터</Badge><ToolButton label={reduced ? '모션 켜기' : '모션 끄기'} className="motion-toggle" aria-pressed={reduced} disabled={systemReduced} onClick={() => setPauseMotion(!pauseMotion)}>{reduced ? <Play size={15}/> : <Pause size={15}/>}</ToolButton><SegmentedControl.Root className="view-toggle" size="1" value={view} onValueChange={navigate} aria-label="표시 방식"><SegmentedControl.Item value="graph" aria-label="그래프로 보기"><Network size={16}/></SegmentedControl.Item><SegmentedControl.Item value="list" aria-label="목록으로 보기"><List size={16}/></SegmentedControl.Item></SegmentedControl.Root></div></header>
        <section className="graph-stage" aria-label="지식 그래프"><div id="graph" ref={graphHost}/>{hover && <div className="graph-tooltip">{hover}</div>}{filter !== 'all' && <div className="graph-caption"><Dot color={kinds[filter].color}/><span>{kinds[filter].label}</span><ToolButton label="유형 필터 해제" onClick={() => changeFilter(filter)}><X size={14}/></ToolButton></div>}{renderer === 'webgl' && <div className="graph-controls"><div className="zoom-group"><ToolButton label="축소" onClick={() => graph.current?.zoom(-1)}><Minus size={17}/></ToolButton><ToolButton label="확대" onClick={() => graph.current?.zoom(1)}><Plus size={17}/></ToolButton><Separator orientation="vertical" size="1"/><ToolButton label="전체 보기" onClick={() => graph.current?.reset()}><Maximize size={17}/></ToolButton></div></div>}</section>
        <div className="search-dock" ref={searchDock}><div className={`search-panel ${shownAnswer ? 'is-expanded' : ''} ${answerExiting ? 'answer-closing' : ''}`} data-status={shownAnswer?.status || 'idle'}>
          <form className="search-form" onSubmit={event => { event.preventDefault(); search(query); }}><TextField.Root id="search-input" className="search-field" size="3" variant="soft" value={query} onChange={event => setQuery(event.target.value)} ref={input} autoComplete="off" maxLength={10000} aria-label="내 기록에 질문하기" placeholder="내 기록에 질문하기"><TextField.Slot className="search-leading"><Sparkles size={20}/></TextField.Slot><TextField.Slot side="right" className="search-actions">{!shownAnswer && <Kbd className="search-key" size="1">Ctrl K</Kbd>}<Tooltip content="검색 실행"><IconButton className="search-submit" type="submit" size="1" color="gray" variant="soft" aria-label="검색 실행"><ArrowUp size={19}/></IconButton></Tooltip>{shownAnswer && <ToolButton label="답변 닫기" className="dismiss-answer" onClick={dismissAnswer}><X size={18}/></ToolButton>}</TextField.Slot></TextField.Root></form>
          {shownAnswer && <ScrollArea type="auto" scrollbars="vertical" className="answer-scroll" key={shownAnswer.question} inert={answerExiting} aria-hidden={answerExiting || undefined}><section className="answer-inner" aria-labelledby="answer-question" id="answer-view"><h1 className="sr-only" id="answer-question">{shownAnswer.question}</h1><div className="answer-meta"><span className="answer-label"><Sparkles size={16}/>{shownAnswer.status === 'searching' ? '기록 찾는 중' : shownAnswer.status === 'reading' ? '답변 정리 중' : '답변'}</span>{ready && shownAnswer.records.length > 0 && <ToolButton label="답변 복사" className="answer-copy" onClick={copyAnswer}><Copy size={16}/></ToolButton>}</div><div aria-live="polite" aria-busy={!ready}>
            {!ready ? <div className="answer-state loading"><Skeleton height="14px" width="95%"/><Skeleton height="14px" width="85%"/><Skeleton height="14px" width="60%"/></div> : shownAnswer.records.length ? <>
              <div className="answer-prose" id="answer-content"><p className="answer-intro">{responseIntro}</p>{shownAnswer.records.map((record, index) => <section className="answer-section" key={record.id} style={{ '--reveal-order': index }}><h2>{shortTitles[record.id] || record.title}</h2><p>{record.paragraphs[record.highlightIndex]}<button className="inline-citation" aria-label={`출처 ${index + 1}: ${record.title}`} onClick={() => openSource(record.id, true)}>{index + 1}</button></p></section>)}</div>
              <div className="sources-heading"><h2>출처 <span>{shownAnswer.records.length}</span></h2></div><div className="source-list">{shownAnswer.records.map((record, index) => <Button key={record.id} className="source-row" data-source={record.id} variant="ghost" color="gray" aria-pressed={source?.id === record.id} onClick={() => openSource(record.id, true)}><span className="source-number">{index + 1}</span><span className="source-row-copy"><strong>{record.title}</strong><small><Dot color={info(record).color}/>{info(record).label}<span>·</span>{record.date}</small></span><ChevronRight size={16}/></Button>)}</div>
            </> : <div className="answer-state empty"><Search size={23}/><h2>일치하는 기록이 없어요</h2><p>아래 예시 질문으로 다시 검색해 보세요.</p><Button size="2" variant="soft" color="gray" onClick={() => search(samples[0])}>학습에 관한 질문 살펴보기<ArrowRight size={14}/></Button></div>}
          </div></section></ScrollArea>}
        </div>{!shownAnswer && view === 'graph' && <div className="suggestions"><Button variant="outline" color="gray" size="2" onClick={() => search(samples[0])}>배운 내용을 오래 기억하려면?<ArrowRight size={13}/></Button><Button variant="outline" color="gray" size="2" onClick={() => search(samples[1])}>내가 기록을 남기는 이유는?<ArrowRight size={13}/></Button></div>}</div>
        {view === 'list' && !shownAnswer && <ScrollArea className="record-list-view" type="auto" scrollbars="vertical"><div className="list-heading"><h1>{filter === 'all' ? '모든 기록' : kinds[filter].label}</h1><Badge color="gray">{selected.length}</Badge></div>{selected.map(record => <Button key={record.id} variant="ghost" color="gray" className="record-row" onClick={() => openSource(record.id)}><span className="record-row-icon"><FileText size={18}/></span><span className="record-row-copy"><strong>{record.title}</strong><span>{record.excerpt}</span></span><span className="record-row-meta"><span><Dot color={info(record).color}/>{info(record).label}</span><time>{record.date}</time></span><ChevronRight size={15}/></Button>)}</ScrollArea>}
      </main>
      {shownSource && !mobile && <SourcePanel source={shownSource} onClose={closeSource} onSelect={openSource} buttonRef={closeButton} exiting={sourceExiting}/>}
      <Dialog.Root open={Boolean(source && mobile)} onOpenChange={open => { if (!open) closeSource(); }}><Dialog.Content className="mobile-source-dialog" onCloseAutoFocus={event => { event.preventDefault(); requestAnimationFrame(() => { if (returnFocus.current?.isConnected) returnFocus.current.focus({ preventScroll: true }); else input.current?.focus({ preventScroll: true }); }); }}><Dialog.Title className="sr-only">출처 기록</Dialog.Title><Dialog.Description className="sr-only">저장된 본문과 인용 구간</Dialog.Description>{shownSource && mobile && <SourcePanel source={shownSource} onClose={closeSource} onSelect={openSource} exiting={sourceExiting}/>}</Dialog.Content></Dialog.Root>
      {toast && <div className="toast" role="status"><Check size={16}/>{toast}</div>}
    </div>
  </Theme>;
}
createRoot(document.getElementById('root')).render(<App/>);
