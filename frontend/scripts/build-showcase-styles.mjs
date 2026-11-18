import { readFile, readdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { transform } from "lightningcss";
import { parseHTML } from "linkedom";

const [site, outputPath] = process.argv.slice(2);
const usedClasses = new Set();
for (const name of await readdir(site)) {
  if (!name.endsWith(".html")) continue;
  const { document } = parseHTML(await readFile(join(site, name), "utf8"));
  for (const node of document.querySelectorAll("[class]")) {
    for (const className of node.classList) usedClasses.add(className);
  }
}

const stylesheets = [
  import.meta.resolve("@astryxdesign/core/reset.css"),
  import.meta.resolve("@astryxdesign/core/astryx.css"),
  new URL("../src/theme/cache-me.css", import.meta.url),
];
const styles = await Promise.all(
  stylesheets.map((url) => readFile(fileURLToPath(url), "utf8")),
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
