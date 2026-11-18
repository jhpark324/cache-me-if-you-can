import { readFile, writeFile } from "node:fs/promises";
import { Button, Grid, Heading, Icon, Stack, Text } from "@astryxdesign/core";
import { parseHTML } from "linkedom";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const [input, output] = process.argv.slice(2);
if (!input || !output) {
  throw new Error("Usage: node frontend/scripts/render-showcase.mjs <input-html> <output-html>");
}

// Author the tour in semantic HTML. Only marked regions need React at build time.
const { document } = parseHTML(await readFile(input, "utf8"));
const components = { Button, Grid, Heading, Stack, Text };

function renderNode(node) {
  if (node.nodeType === 3) return node.textContent;
  if (node.nodeType !== 1) return null;

  const tag = node.localName;
  const name = node.getAttribute("data-ax");
  const props = {};
  for (const { name: attr, value } of node.attributes) {
    if (attr === "data-ax" || attr.startsWith("data-ax-")) continue;
    props[attr === "class" ? "className" : attr] = value;
  }
  const children = Array.from(node.childNodes, renderNode);
  if (!name) return createElement(tag, props, ...children);
  if (!Object.hasOwn(components, name)) throw new Error(`Unknown Astryx component: ${name}`);
  Object.assign(props, JSON.parse(node.getAttribute("data-ax-props") || "{}"));

  if (name === "Heading") {
    props.level = Number(tag.slice(1));
    props.color = "inherit";
  } else if (name === "Text" || name === "Stack") {
    props.as = tag;
    if (name === "Text") {
      props.color = "inherit";
      props.display = tag === "p" ? "block" : "inline";
    }
  } else if (name === "Button") {
    props.label = props["aria-label"] || node.textContent.trim();
    props.endContent = createElement(Icon, { icon: node.getAttribute("data-ax-icon"), size: "sm" });
  }
  return createElement(components[name], props, ...children);
}

const regions = [...document.querySelectorAll("[data-ax]")].filter(
  (node) => !node.parentElement?.closest("[data-ax]"),
);
if (!regions.length) throw new Error("The showcase has no marked Astryx components.");
for (const region of regions) {
  region.outerHTML = renderToStaticMarkup(renderNode(region));
}
await writeFile(output, document.toString());
