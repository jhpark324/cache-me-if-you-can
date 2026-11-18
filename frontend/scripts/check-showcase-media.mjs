import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseHTML } from "linkedom";

const index = pathToFileURL(resolve(process.argv[2], "index.html"));
const { document } = parseHTML(await readFile(index, "utf8"));

function inspect(reference) {
  const file = fileURLToPath(new URL(reference, index));
  const result = execFileSync(
    "ffprobe",
    [
      "-v",
      "error",
      "-select_streams",
      "v:0",
      "-show_streams",
      "-show_format",
      "-of",
      "json",
      file,
    ],
    { encoding: "utf8" },
  );
  const { streams, format } = JSON.parse(result);
  if (!streams?.[0])
    throw new Error(`${reference} has no image or video stream.`);
  const stream = streams[0];
  const rotation =
    stream.side_data_list?.find((item) => item.rotation)?.rotation ??
    stream.tags?.rotate ??
    0;
  const rotated = Math.abs(rotation) % 180 === 90;
  const width = rotated ? stream.height : stream.width;
  const height = rotated ? stream.width : stream.height;
  if (!(width > height && height > 0))
    throw new Error(
      `${reference} must be landscape (found ${width}×${height}).`,
    );
  return {
    width,
    height,
    codec: stream.codec_name,
    formats: format.format_name.split(","),
  };
}

const hero = document.querySelector(".hero-figure");
const heroImages = hero?.querySelectorAll("img");
const heroSource = heroImages?.[0]?.getAttribute("src");
if (
  !heroSource ||
  heroImages.length !== 1 ||
  hero.querySelector("source, img[srcset]")
) {
  throw new Error("Use the same full desktop hero image at every viewport.");
}
if (inspect(heroSource).width < 1280)
  throw new Error(`${heroSource} must be at least 1280px wide.`);

const films = document.querySelectorAll("video");
if (!films.length) throw new Error("The showcase needs a product film.");
for (const film of films) {
  const posterSource = film.getAttribute("poster");
  const poster = inspect(posterSource);
  if (poster.codec !== "mjpeg")
    throw new Error(`${posterSource} must be a JPEG poster.`);
  const sources = film.hasAttribute("src")
    ? [film]
    : film.querySelectorAll("source[src]");
  for (const source of sources) {
    const path = source.getAttribute("src");
    const frame = inspect(path);
    if (
      frame.codec !== "h264" ||
      !frame.formats.includes("mp4") ||
      frame.width < 1280
    ) {
      throw new Error(
        `${path} must be a desktop H.264 MP4 at least 1280px wide.`,
      );
    }
    if (poster.width * frame.height !== frame.width * poster.height) {
      throw new Error(
        `${posterSource} must have the same aspect ratio as ${path}.`,
      );
    }
    const width = film.getAttribute("width");
    const height = film.getAttribute("height");
    if (
      (width !== null || height !== null) &&
      Number(width) / Number(height) !== frame.width / frame.height
    ) {
      throw new Error(
        `The HTML dimensions for ${path} must match its aspect ratio.`,
      );
    }
  }
}
console.log(
  `Verified desktop framing for the hero and ${films.length} films with posters.`,
);
