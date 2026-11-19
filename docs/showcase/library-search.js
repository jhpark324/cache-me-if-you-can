function followLayout(details, container) {
  let wasWide;
  const update = () => {
    const wide = container.clientWidth >= 768;
    if (wide !== wasWide) details.open = wide;
    wasWide = wide;
  };
  update();
  new ResizeObserver(update).observe(container);
}

const contents = document.querySelector(".ref-toc details");
if (contents) {
  const page = document.querySelector(".ref-page");
  const list = contents.querySelector("ol");
  const position = contents.querySelector(".ref-location");
  const toc = Array.from(list.querySelectorAll("a"), (link) => ({
    link, heading: document.getElementById(decodeURIComponent(link.hash.slice(1))),
  }));
  followLayout(contents, page);
  let active;
  let frame;
  function markSection() {
    frame = undefined;
    const narrow = page.clientWidth < 768;
    const line = parseFloat(getComputedStyle(toc[0].heading).scrollMarginTop) + 8;
    let current;
    for (const section of toc) {
      if (section.heading.getBoundingClientRect().top > line) break;
      current = section;
    }
    if (active === current && position.textContent) return;
    active?.link.removeAttribute("aria-current");
    active = current;
    position.textContent = current ? current.link.textContent : toc.length + "개 절";
    if (current) {
      current.link.setAttribute("aria-current", "location");
      if (!narrow && contents.open && !contents.contains(document.activeElement)) {
        const item = current.link.getBoundingClientRect();
        const view = list.getBoundingClientRect();
        if (item.top < view.top) list.scrollTop += item.top - view.top;
        else if (item.bottom > view.bottom) list.scrollTop += item.bottom - view.bottom;
      }
    }
  }
  function schedule() {
    if (!frame) frame = requestAnimationFrame(markSection);
  }
  for (const { link, heading } of toc) {
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (page.clientWidth < 768) contents.open = false;
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    });
  }
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);
  window.addEventListener("pageshow", schedule);
  new ResizeObserver(schedule).observe(page.querySelector(".ref-document"));
  // Make a bookmarked section land below the headers after responsive tables and fonts settle.
  const initial = toc.find(({ link }) => link.hash === location.hash);
  const navigation = performance.getEntriesByType("navigation")[0];
  if (initial && navigation?.type !== "back_forward") {
    window.addEventListener("load", async () => {
      await document.fonts.ready;
      requestAnimationFrame(() => {
        if (location.hash === initial.link.hash) initial.heading.scrollIntoView({ block: "start" });
      });
    }, { once: true });
  }
  contents.addEventListener("toggle", schedule);
  schedule();
}

for (const table of document.querySelectorAll(".ref-document .g-table")) {
  const hint = document.createElement("p");
  hint.className = "ref-table-hint";
  hint.textContent = "표를 좌우로 움직여 나머지 열을 읽을 수 있습니다.";
  table.before(hint);
  const resize = () => {
    const scrolls = table.scrollWidth > table.clientWidth + 1;
    hint.hidden = !scrolls;
    table.tabIndex = scrolls ? 0 : -1;
  };
  resize();
  new ResizeObserver(resize).observe(table);
}

for (const code of document.querySelectorAll(".ref-document pre")) {
  const resize = () => { code.tabIndex = code.scrollWidth > code.clientWidth + 1 ? 0 : -1; };
  resize();
  new ResizeObserver(resize).observe(code);
}

const fields = document.querySelector(".ref-fields");
if (fields) {
  const library = document.querySelector(".ref-library");
  const chooser = fields.querySelector("details");
  const name = chooser.querySelector(".ref-field-name");
  const links = Array.from(fields.querySelectorAll("a"));
  followLayout(chooser, library);
  function showField() {
    const current = links.find((link) => link.hash === location.hash) || links[0];
    for (const link of links) {
      const selected = link === current;
      document.getElementById(link.hash.slice(1)).hidden = !selected;
      if (selected) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    }
    name.textContent = current.firstChild.textContent;
  }
  fields.addEventListener("click", (event) => {
    const link = event.target.closest("a");
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (location.hash !== link.hash) history.pushState(null, "", link.hash);
    showField();
    if (library.clientWidth < 768) chooser.open = false;
    const group = document.getElementById(link.hash.slice(1));
    group.focus({ preventScroll: true });
    group.scrollIntoView({ block: "nearest" });
  });
  window.addEventListener("hashchange", showField);
  window.addEventListener("pageshow", showField);
  showField();
}

const form = document.getElementById("ref-search");
if (form) {
  const query = document.getElementById("ref-query");
  const results = document.getElementById("ref-results");
  const catalog = document.getElementById("ref-catalog");
  const count = document.getElementById("ref-count");
  form.hidden = false;
  let index;
  let matches = [];
  let displayed = 0;
  const normalize = (text) => text.normalize("NFC").toLowerCase();
  const element = (name, text) => {
    const item = document.createElement(name);
    item.textContent = text;
    return item;
  };

  function showMore() {
    const list = results.querySelector("ol");
    const oldButton = results.querySelector("button");
    const previous = displayed;
    for (const { section, excerpt } of matches.slice(previous, previous + 18)) {
      const link = document.createElement("a");
      link.href = section.href;
      link.append(element("small", section.group + " · " + section.title));
      link.append(element("strong", section.heading));
      if (excerpt) {
        const snippet = element("span", excerpt);
        snippet.className = "ref-excerpt";
        link.append(snippet);
      }
      const entry = document.createElement("li");
      entry.append(link);
      list.append(entry);
      displayed++;
    }
    if (oldButton) {
      oldButton.remove();
      list.children[previous].querySelector("a").focus();
    }
    if (displayed < matches.length) {
      const button = element("button", "검색 결과 더 보기");
      button.type = "button";
      button.className = "ref-more";
      button.addEventListener("click", showMore);
      results.append(button);
    }
  }

  function search() {
    const text = query.value.trim();
    const terms = normalize(text).split(/\s+/u);
    const url = new URL(location.href);
    if (text) url.searchParams.set("q", text);
    else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    catalog.hidden = Boolean(text);
    results.hidden = !text;
    results.replaceChildren();
    count.textContent = "";
    if (!text) return;
    index ??= JSON.parse(document.getElementById("ref-index").textContent);
    matches = [];
    for (const section of index) {
      const heading = normalize(section.heading);
      const body = normalize(section.body);
      const title = normalize(section.title);
      const group = normalize(section.group);
      const searchable = group + " " + title + " " + heading + " " + body;
      if (!terms.every((term) => searchable.includes(term))) continue;
      const position = Math.max(0, body.indexOf(terms[0]));
      const start = Math.max(0, position - 30);
      const end = Math.min(section.body.length, start + 125);
      const excerpt = (start ? "…" : "") + section.body.slice(start, end) + (end < section.body.length ? "…" : "");
      const score = terms.filter((term) => heading.includes(term)).length * 2 + Number(heading === normalize(text)) + Number(heading === title && terms.some((term) => title.includes(term) || group.includes(term)));
      matches.push({ section, score, excerpt });
    }
    matches.sort((a, b) => b.score - a.score);
    displayed = 0;
    count.textContent = matches.length ? `검색 결과 ${matches.length}개` : "일치하는 절이 없습니다. 더 짧은 용어나 다른 표현으로 찾아보세요.";
    if (matches.length) {
      results.append(document.createElement("ol"));
      showMore();
    }
  }

  form.addEventListener("submit", (event) => { event.preventDefault(); search(); });
  query.addEventListener("input", search);
  query.value = new URLSearchParams(location.search).get("q") || "";
  if (query.value) search();
}
