const sections = [
  ["시스템", [
    ["guide.html", "아키텍처 개요"],
    ["guide-system.html", "구성 요소와 운영"],
    ["guide-engine.html", "저장·검색 엔진"],
  ]],
  ["인터페이스 명세", [
    ["guide-skills.html", "Codex 스킬"],
    ["guide-mcp.html", "MCP 도구"],
  ]],
  ["제품과 자료", [
    ["guide-features.html", "지식 공간과 아티클"],
    ["guide-library.html", "원문 자료집"],
  ]],
];

// The built site has complete, ordinary links even with JavaScript disabled.
export function mountGuideNavigation(document, filename) {
  const header = document.querySelector(".g-header");
  if (!header) return;
  const reference = filename.startsWith("ref-");
  const current = reference ? "guide-library.html" : filename;
  const paths = sections.flatMap(([, links]) => links);
  const currentLabel = paths.find(([href]) => href === current)?.[1];
  if (!currentLabel) throw new Error("Missing guide navigation entry: " + filename);

  const groups = sections.map(([title, links]) => {
    const items = links.map(([href, label]) => {
      const state = href === current ? ' aria-current="' + (reference ? "location" : "page") + '"' : "";
      return '<li><a href="' + href + '"' + state + '>' + label + '</a></li>';
    }).join("");
    return '<li class="g-nav-group"><span>' + title + '</span><ul>' + items + '</ul></li>';
  }).join("");
  const list = '<ul class="g-doc-links">' + groups + '</ul>';
  header.innerHTML =
    '<div class="g-wrap g-bar"><div class="g-brand-row">' +
    '<a class="g-brand" href="index.html" aria-label="Cache Me If You Can 프로젝트 소개">Cache Me <small>If You Can</small></a>' +
    '<a href="guide.html" class="g-doc-home">설계 문서</a></div>' +
    '<details class="g-mobile-menu"><summary><span>' + currentLabel + '</span> 목차</summary>' +
    '<nav aria-label="설계 문서 목차">' + list + '</nav></details></div>';

  const main = document.querySelector("main");
  const shell = document.createElement("div");
  shell.className = "g-shell";
  main.replaceWith(shell);
  const sidebar = document.createElement("nav");
  sidebar.className = "g-sidebar";
  sidebar.setAttribute("aria-label", "설계 문서 목차");
  sidebar.innerHTML = list;
  shell.append(sidebar, main);

  const script = document.createElement("script");
  script.setAttribute("src", "guide-nav.js");
  script.setAttribute("defer", "");
  document.head.append(script);
}
