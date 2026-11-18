const contents = document.querySelector(".ref-toc details");
if (contents && window.matchMedia("(min-width: 47.01rem)").matches) contents.open = true;

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
      const searchable = heading + " " + body;
      if (!terms.every((term) => searchable.includes(term))) continue;
      const position = Math.max(0, body.indexOf(terms[0]));
      const start = Math.max(0, position - 30);
      const end = Math.min(section.body.length, start + 125);
      const excerpt = (start ? "…" : "") + section.body.slice(start, end) + (end < section.body.length ? "…" : "");
      const score = terms.filter((term) => heading.includes(term)).length + Number(heading === normalize(text));
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
