import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseHTML } from "linkedom";
import mediaInfoFactory from "mediainfo.js";

const index = pathToFileURL(resolve(process.argv[2], "index.html"));
const { document } = parseHTML(await readFile(index, "utf8"));

async function inspect(mediaInfo, reference) {
  if (!reference) throw new Error("Expected a local media reference.");
  const bytes = await readFile(new URL(reference, index));
  const result = await mediaInfo.analyzeData(bytes.length, (size, offset) =>
    bytes.subarray(offset, offset + size),
  );
  const tracks = result.media?.track ?? [];
  const stream = tracks.find((track) =>
    ["Video", "Image"].includes(track["@type"]),
  );
  if (!stream) throw new Error(`${reference} has no image or video stream.`);
  const rotated = Math.abs(Number(stream.Rotation ?? 0)) % 180 === 90;
  const width = Number(rotated ? stream.Height : stream.Width);
  const height = Number(rotated ? stream.Width : stream.Height);
  if (!(width > height && height > 0)) {
    throw new Error(
      `${reference} must be landscape (found ${width}×${height}).`,
    );
  }
  return {
    width,
    height,
    codec: stream.Format,
    container: tracks.find((track) => track["@type"] === "General")?.Format,
    frames: Number(stream.FrameCount ?? 0),
  };
}

async function checkStory(mediaInfo) {
  // An inactive slide keeps its GIF and still image inside a template.
  let loops = 0;
  for (const slide of document.querySelectorAll("template")) {
    for (const image of slide.content.querySelectorAll("img[data-motion]")) {
      const stillPath = image.getAttribute("src");
      const gifPath = image.getAttribute("data-motion");
      const poster = await inspect(mediaInfo, stillPath);
      const animation = await inspect(mediaInfo, gifPath);
      if (poster.codec !== "JPEG")
        throw new Error(`${stillPath} must be a JPEG still.`);
      if (animation.codec !== "GIF" || animation.frames < 2) {
        throw new Error(`${gifPath} must be a GIF with at least two frames.`);
      }
      if (
        Math.min(poster.width, animation.width) < 960 ||
        poster.width * animation.height !== animation.width * poster.height
      ) {
        throw new Error(
          `${stillPath} and ${gifPath} must share a desktop frame at least 960px wide.`,
        );
      }
      loops++;
    }
  }
  if (!loops)
    throw new Error(
      "The guided story needs desktop animations and still images.",
    );
  return loops;
}

async function checkFilms(mediaInfo) {
  const films = document.querySelectorAll("video");
  if (!films.length) throw new Error("The showcase needs a product film.");
  for (const film of films) {
    const posterPath = film.getAttribute("poster");
    const poster = await inspect(mediaInfo, posterPath);
    if (poster.codec !== "JPEG")
      throw new Error(`${posterPath} must be a JPEG poster.`);
    const sources = film.hasAttribute("src")
      ? [film]
      : film.querySelectorAll("source[src]");
    if (!sources.length)
      throw new Error(`Missing film source for ${posterPath}.`);
    for (const source of sources) {
      const path = source.getAttribute("src");
      const frame = await inspect(mediaInfo, path);
      if (
        frame.codec !== "AVC" ||
        frame.container !== "MPEG-4" ||
        frame.width < 1280
      ) {
        throw new Error(
          `${path} must be a desktop H.264 MP4 at least 1280px wide.`,
        );
      }
      if (poster.width * frame.height !== frame.width * poster.height) {
        throw new Error(
          `${posterPath} must have the same aspect ratio as ${path}.`,
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
  return films.length;
}

const mediaInfo = await mediaInfoFactory({ format: "object" });
try {
  const loops = await checkStory(mediaInfo);
  const films = await checkFilms(mediaInfo);
  console.log(
    `Verified desktop framing for ${loops} story loops and ${films} films with posters.`,
  );
} finally {
  mediaInfo.close();
}
