import { mountGuideNavigation } from "./showcase-navigation.mjs";
import { copyFile, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { Heading } from "@astryxdesign/core";
import { parseHTML } from "linkedom";
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

const [source, site] = process.argv.slice(2);
if (!source || !site) throw new Error("Usage: render-showcase-reference.mjs <docs/showcase> <output-site>");
const docs = path.resolve(source, "..");
const template = await readFile(path.join(source, "guide-library.html"), "utf8");
const diagramDir = path.join(docs, "architecture/diagrams");
const diagrams = new Set(await readdir(diagramDir));
const html = renderToStaticMarkup;
const markdown = (text) => html(h(Markdown, { remarkPlugins: [remarkGfm], skipHtml: true }, text));
function page(filename) {
  const { document } = parseHTML(template);
  mountGuideNavigation(document, filename);
  return document;
}

async function chapters(dir) {
  return (await readdir(path.join(docs, dir))).filter((name) => name.endsWith(".md") && name !== "index.md").sort();
}

// Publishing is opt-in by directory or document. Build from the canonical Markdown,
// including the distinction each source makes between current behavior and proposals.
const groups = [
  { id: "architecture", label: "시스템 설계", role: "구성요소, 데이터 구조와 실행 흐름", files: await chapters("architecture") },
  { id: "specs", label: "기능 명세", role: "기능별 동작과 수용 기준", files: ["records.md", "runtime.md", "workspace.md", "articles.md", "cache-me.md"] },
  { id: "decisions", label: "기술 결정 기록 (ADR)", role: "선택한 기술과 대안, 채택 이유", files: await chapters("decisions") },
  { id: "skills", label: "Codex 스킬", role: "호출 조건과 작성 절차", files: ["cache-me/SKILL.md", "cache-me-article/SKILL.md"] },
  { id: "guides", label: "설치와 검증", role: "로컬 실행과 검사 방법", files: ["local-development.md", "testing.md"] },
  { id: "project", label: "제품 범위와 용어", role: "지원 범위와 핵심 개념", files: ["product-brief.md", "mvp-scope.md", "domain-language.md", "record-types.md", "record-and-visibility.md"] },
];
const entries = new Map();
const searchIndex = [];
const headingSelector = "h1, h2, h3, h4, h5, h6";

function slug(text) {
  return text.normalize("NFC").toLowerCase().trim().replace(/[^\p{L}\p{N}\p{M}\s_-]/gu, "").replace(/\s/g, "-");
}

for (const group of groups) {
  const indexMarkdown = await readFile(path.join(docs, group.id, "index.md"), "utf8");
  const descriptions = new Map();
  const index = parseHTML("<html><body>" + markdown(indexMarkdown) + "</body></html>").document;
  for (const row of index.querySelectorAll("tr")) {
    const cells = row.querySelectorAll("td");
    for (const link of row.querySelectorAll("a")) {
      const description = group.id === "decisions" ? cells[1]?.textContent : cells[cells.length - 1]?.textContent;
      if (description) descriptions.set(link.getAttribute("href"), description);
    }
  }
  const files = group.id === "architecture"
    ? [...new Set([...descriptions.keys(), ...group.files])].filter((file) => group.files.includes(file))
    : group.files;
  for (const file of files) {
    const canonical = path.posix.join(group.id, file);
    const sourceText = await readFile(path.join(docs, canonical), "utf8");
    const front = sourceText.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
    const body = parseHTML("<html><body><article>" + markdown(sourceText.slice(front?.[0].length || 0)) + "</article></body></html>").document.querySelector("article");
    const anchors = new Set();
    const headings = [];
    let section;
    for (const block of body.children) {
      if (block.matches(headingSelector)) {
        const label = block.textContent.trim();
        const base = slug(label) || "section";
        let anchor = base;
        for (let suffix = 1; anchors.has(anchor); suffix++) anchor = base + "-" + suffix;
        anchors.add(anchor);
        block.id = anchor;
        section = { id: anchor, label, level: Number(block.localName[1]), text: [] };
        headings.push(section);
      } else if (section) {
        section.text.push(block.textContent.trim().replace(/\s+/gu, " "));
      }
    }
    if (headings[0]?.level !== 1) throw new Error("Missing document title: " + canonical);
    const stem = path.parse(file).name;
    const name = stem === "SKILL" ? "skill-" + path.basename(path.dirname(file)) : stem.toLowerCase();
    const title = headings[0].label;
    entries.set(canonical, {
      group, canonical, body, headings, anchors, title, stem, frontMatter: front?.[1],
      filename: "ref-" + name + ".html", description: descriptions.get(file) || headings.slice(1, 4).map((item) => item.label).join(" · "),
    });
  }
}

if (new Set([...entries.values()].map((entry) => entry.filename)).size !== entries.size) throw new Error("Duplicate reference filenames.");
await mkdir(path.join(site, "diagrams"), { recursive: true });

function destination(from, href) {
  // An unlisted file or an external link stays readable as the original label.
  if (!href || /^[a-z][a-z\d+.-]*:|^\/|^\?/i.test(href)) return null;
  const [rawPath, fragment] = href.split("#", 2).map(decodeURIComponent);
  const canonical = rawPath ? path.posix.join(path.posix.dirname(from.canonical), rawPath) : from.canonical;
  const target = entries.get(canonical);
  if (target) {
    const id = fragment?.normalize("NFC");
    if (id && !target.anchors.has(id)) throw new Error(`Unknown Markdown heading in ${from.canonical}: ${href}`);
    return (canonical === from.canonical && id ? "" : target.filename) + (id ? "#" + encodeURIComponent(id) : "");
  }
  const index = groups.find((group) => canonical === group.id + "/index.md");
  return index ? "guide-library.html#" + index.id : null;
}

function sectionTitle(block, fallback) {
  for (let node = block; node; node = node.previousElementSibling) {
    if (node.matches(headingSelector)) return node.textContent.trim();
  }
  return fallback;
}

async function prepareBody(entry) {
  const { body, stem } = entry;
  for (const link of body.querySelectorAll("a[href]")) {
    const target = destination(entry, link.getAttribute("href"));
    if (target) link.setAttribute("href", target);
    else link.replaceWith(...Array.from(link.childNodes));
  }
  for (const table of body.querySelectorAll("table")) {
    const wrapper = body.ownerDocument.createElement("div");
    wrapper.className = "g-table";
    wrapper.tabIndex = 0;
    wrapper.setAttribute("role", "region");
    wrapper.setAttribute("aria-label", sectionTitle(table, entry.title) + " 표");
    for (const cell of table.querySelectorAll("thead th")) cell.setAttribute("scope", "col");
    table.replaceWith(wrapper);
    wrapper.append(table);
  }
  for (const [number, code] of [...body.querySelectorAll("pre > code.language-mermaid")].entries()) {
    const original = code.parentElement;
    const filename = stem + "-rendered-" + (number + 1) + ".svg";
    if (!diagrams.has(filename)) continue; // The Markdown source remains visible as preformatted text.
    await copyFile(path.join(diagramDir, filename), path.join(site, "diagrams", filename));
    const svg = await readFile(path.join(diagramDir, filename), "utf8");
    const viewBox = svg.match(/\bviewBox="([^"]+)"/)?.[1].trim().split(/[\s,]+/).map(Number);
    if (!viewBox || !(viewBox[2] > 0 && viewBox[3] > 0)) throw new Error("Missing diagram dimensions: " + filename);
    const topic = sectionTitle(original, entry.title);
    const url = "diagrams/" + filename;
    const figure = body.ownerDocument.createElement("figure");
    original.replaceWith(figure);
    figure.innerHTML = html(h("details", { className: "ref-zoom" },
        h("summary", null,
          h("span", { className: "ref-zoom-label" },
            h("span", { className: "ref-to-zoom" }, "도식 원본 크기로 보기"), h("span", { className: "ref-to-fit" }, "도식 전체 보기")),
          h("span", { className: "ref-diagram" }, h("img", { src: url, width: Math.ceil(viewBox[2]), height: Math.ceil(viewBox[3]), loading: "lazy", alt: topic + " 도식" }))),
        h("div", { tabIndex: 0, role: "region", "aria-label": topic + " 확대 도식 스크롤" },
          h("img", { src: url, loading: "lazy", alt: topic + " 확대 도식", width: Math.ceil(viewBox[2]) })))) +
      html(h("details", null, h("summary", null, "도식 텍스트로 읽기")));
    figure.lastElementChild.append(original);
  }
  for (const code of body.querySelectorAll("pre")) code.tabIndex = 0;
  // Markdown headings preserve their actual levels and fragment targets in the rendered theme.
  for (const node of body.querySelectorAll(headingSelector)) {
    const level = Number(node.localName[1]);
    node.outerHTML = html(h(Heading, { level, color: "inherit", id: node.id }, node.textContent));
  }
}

function members(group) {
  return [...entries.values()].filter((doc) => doc.group === group);
}

function catalog(group) {
  return h("section", { className: "ref-group", id: group.id, key: group.id, tabIndex: -1 },
    h("header", { className: "ref-group-title" },
      h(Heading, { level: 2, color: "inherit" }, group.label),
      h("p", null, group.role)),
    h("ul", { className: "ref-list" }, members(group).map((doc) => h("li", { key: doc.filename },
      h("a", { href: doc.filename }, h("strong", null, doc.title), h("span", null, doc.description))))));
}

function groupReader(entry) {
  const docs = members(entry.group);
  const index = docs.indexOf(entry);
  const jump = (doc, label, direction) => doc && h("a", { href: doc.filename, className: direction },
    h("small", null, label), h("strong", null, doc.title));
  return h("footer", { className: "ref-footer" },
    h("nav", { className: "ref-neighbors", "aria-label": entry.group.label + " 안에서 이어 읽기" },
      jump(docs[index - 1], "← 이전 문서", "ref-prev"), jump(docs[index + 1], "다음 문서 →", "ref-next")),
    h("div", { className: "ref-credit" },
      h("a", { href: "guide-library.html#" + entry.group.id }, entry.group.label + " 전체 문서"),
      h("code", null, "docs/" + entry.canonical)));
}

for (const entry of entries.values()) {
  await prepareBody(entry);
  const document = page(entry.filename);
  document.title = entry.title + " · 기술 자료집";
  document.querySelector('meta[name="description"]').setAttribute("content", entry.description);
  const main = document.querySelector("main");
  main.className = "g-wrap g-main ref-page";
  const sections = entry.headings.slice(1);
  const crumb = h("nav", { className: "ref-crumb", "aria-label": "현재 위치" },
    h("a", { href: "guide-library.html" }, "기술 자료집"), h("span", { "aria-hidden": true }, "/"),
    h("a", { href: "guide-library.html#" + entry.group.id }, entry.group.label));
  const toc = sections.length ? h("nav", { className: "ref-toc", "aria-label": "이 문서의 목차" },
    h("details", null, h("summary", null, "이 문서의 목차", h("small", { className: "ref-location", "aria-hidden": true })),
      h("ol", null, sections.map((section) => h("li", { key: section.id, className: section.level > 2 ? "ref-sub" : undefined },
        h("a", { href: "#" + encodeURIComponent(section.id) }, section.label)))))) : null;
  const title = entry.body.querySelector("h1");
  const intro = title.nextElementSibling;
  const lead = intro?.matches("p") && intro.textContent.length <= 280 ? intro : null;
  const heading = title.outerHTML + (lead?.outerHTML || "");
  title.remove();
  lead?.remove();
  main.innerHTML = html(crumb) + html(h("header", { className: "ref-dochead" })) +
    html(h("div", { className: "ref-layout" }, toc, h("article", { className: "ref-document", "aria-labelledby": title.id })));
  main.querySelector(".ref-dochead").innerHTML = heading;
  const article = main.querySelector("article");
  article.innerHTML = entry.body.innerHTML;
  if (entry.frontMatter) article.insertAdjacentHTML("beforeend", html(h("details", null,
    h("summary", null, "스킬 호출 정보"), h("pre", { tabIndex: 0 }, h("code", null, entry.frontMatter)))));
  article.insertAdjacentHTML("beforeend", html(groupReader(entry)));
  for (const section of entry.headings) {
    searchIndex.push({
      title: entry.title, group: entry.group.label, heading: section.label,
      body: section.text.join(" "), href: entry.filename + "#" + encodeURIComponent(section.id),
    });
  }
  await writeFile(path.join(site, entry.filename), document.toString());
}

const library = page("guide-library.html");
const title = library.querySelector("h1");
title.outerHTML = html(h(Heading, { level: 1, color: "inherit" }, title.textContent));
library.querySelector("#ref-catalog").innerHTML = html(h("nav", { className: "ref-fields", "aria-label": "자료 분야" },
  h("details", { open: true },
    h("summary", null, "문서 분야", h("span", { className: "ref-field-name" })),
    h("ul", null, groups.map((group) => h("li", { key: group.id },
      h("a", { href: "#" + group.id }, group.label, h("small", null, members(group).length + "편")))))))) +
  html(h("div", { className: "ref-volumes" }, groups.map(catalog)));

const data = library.createElement("script");
data.type = "application/json";
data.id = "ref-index";
data.textContent = JSON.stringify(searchIndex).replace(/</g, "\\u003c");
library.body.append(data);
await writeFile(path.join(site, "guide-library.html"), library.toString());
console.log(`Rendered ${entries.size} reference documents and ${searchIndex.length} searchable sections.`);
