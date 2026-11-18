import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { transform } from "lightningcss";
import { parseHTML } from "linkedom";

const [htmlPath, outputPath] = process.argv.slice(2);
const { document } = parseHTML(await readFile(htmlPath, "utf8"));
const usedClasses = new Set();
for (const node of document.querySelectorAll("[class]")) {
  for (const name of node.classList) usedClasses.add(name);
}

const stylesheets = [
  "@astryxdesign/core/reset.css",
  "@astryxdesign/core/astryx.css",
  "@astryxdesign/theme-neutral/theme.css",
];
const styles = await Promise.all(
  stylesheets.map((name) =>
    readFile(fileURLToPath(import.meta.resolve(name)), "utf8"),
  ),
);
const css = styles.join("\n");
// StyleX generates atomic class names only at build time. Include all states
// and media queries for the classes the SSR markup actually uses.
const unusedSymbols = new Set();
for (const match of css.matchAll(/\.(x[a-z0-9]+)\b/g)) {
  if (!usedClasses.has(match[1])) unusedSymbols.add(match[1]);
}
const result = transform({
  filename: "astryx.css",
  code: Buffer.from(css),
  minify: true,
  unusedSymbols: [...unusedSymbols],
  analyzeDependencies: true,
});
if (result.dependencies.length) {
  throw new Error(
    "Astryx styles must work without additional network requests.",
  );
}
const license = await readFile(
  new URL("../../docs/showcase/licenses/astryx.txt", import.meta.url),
  "utf8",
);
await writeFile(outputPath, `/*!\n${license.trim()}\n*/\n${result.code}\n`);
