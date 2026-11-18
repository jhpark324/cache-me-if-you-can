// HTML anchors and still images also work without the story player.
const story = document.querySelector(".story");
const demos = document.getElementById("demo");
const chapters = [...story.querySelectorAll(".chapter")];
const films = [...demos.querySelectorAll(".film-panel")];
const rail = [...story.querySelectorAll(".story-rail a")];
const filmTabs = [...demos.querySelectorAll(".film-nav a")];
const sections = [...document.querySelectorAll(".section-nav a")];
const previous = story.querySelector(".prev");
const next = story.querySelector(".next");
const imageViewer = document.getElementById("image-viewer");
const filmViewer = document.getElementById("film-viewer");
const qrViewer = document.getElementById("qr-viewer");
const imageFrame = document.getElementById("viewer-frame");
const imageSize = imageViewer.querySelector(".viewer-size");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const share = document.querySelector(".share-open");

let chapterIndex = -1;
let paused = reducedMotion.matches;
let imageOpener;

function refreshPictures() {
  for (const figure of story.querySelectorAll(".story-media")) {
    const visible = !story.hidden && !figure.closest(".chapter").hidden;
    let image = figure.querySelector(":scope > img");
    if (!visible) {
      image?.remove();
      continue;
    }
    const still = figure.querySelector("template").content.querySelector("img");
    const animate = !paused && !document.hidden && !imageViewer.open && !qrViewer.open;
    const source = animate ? still.dataset.motion : still.getAttribute("src");
    if (!image) {
      image = still.cloneNode();
      image.src = source;
      figure.prepend(image);
    } else if (image.getAttribute("src") !== source) {
      image.src = source;
    }
    figure.querySelector(".motion").textContent = paused ? "움직임 보기" : "정지 화면";
  }
}

function select(chapter, film) {
  const showingStory = film < 0;
  const direction = chapterIndex > chapter ? "arrive-back" : "arrive";
  const transition = !story.hidden && chapterIndex >= 0 && chapterIndex !== chapter;
  story.hidden = !showingStory;
  demos.hidden = showingStory;
  for (const link of sections) {
    const current = link.hash === (showingStory ? "#story" : "#demo");
    if (current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  chapters.forEach((section, index) => {
    const active = index === chapter;
    section.hidden = !active;
    section.classList.remove("arrive", "arrive-back");
    if (active && transition && showingStory) section.classList.add(direction);
    if (active) rail[index].setAttribute("aria-current", "step");
    else rail[index].removeAttribute("aria-current");
  });
  films.forEach((panel, index) => {
    const active = index === film;
    panel.hidden = !active;
    if (!active) panel.querySelector("video")?.pause();
    filmTabs[index].setAttribute("aria-selected", String(active));
    filmTabs[index].tabIndex = active ? 0 : -1;
    if (active) filmTabs[index].setAttribute("aria-current", "true");
    else filmTabs[index].removeAttribute("aria-current");
  });
  chapterIndex = chapter;
  previous.disabled = chapter <= 0;
  next.disabled = chapter >= chapters.length - 1;
  story.querySelector(".position").textContent = (chapter + 1) + " / " + chapters.length;
  refreshPictures();
}

function renderAddress() {
  const hash = location.hash.slice(1);
  const legacy = document.querySelector(".legacy-links");
  const destination = [...legacy.querySelectorAll("a")].find(link => link.id === hash);
  if (destination) {
    location.replace(destination.href);
    return;
  }
  if (hash === "share" && typeof qrViewer.showModal === "function") {
    if (chapterIndex < 0) select(0, -1);
    if (!qrViewer.open) qrViewer.showModal();
    refreshPictures();
    return;
  }
  if (qrViewer.open) qrViewer.close();
  if (imageViewer.open) imageViewer.close();
  if (filmViewer.open) {
    filmViewer.querySelector("video")?.pause();
    filmViewer.close();
  }
  const film = hash === "demo" ? 0 : hash === "recall" ? films.length - 1 : films.findIndex(panel => panel.id === hash);
  const chapter = chapters.findIndex(panel => panel.id === hash);
  select(chapter < 0 ? 0 : chapter, film);
}

function navigate(hash) {
  if (location.hash !== hash) {
    const state = hash === "#share" ? { returnTo: location.hash || "#story" } : null;
    history.pushState(state, "", hash);
  }
  renderAddress();
  if (hash !== "#share") window.scrollTo(0, 0);
}

for (const link of document.querySelectorAll("a[href^='#']")) {
  if (link.classList.contains("skip")) continue;
  link.addEventListener("click", event => {
    if (event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    const advance = link.classList.contains("advance");
    navigate(link.hash);
    if (advance) {
      const target = !story.hidden ? rail[chapterIndex] : filmTabs.find(tab => tab.getAttribute("aria-selected") === "true");
      target?.focus({ preventScroll: true });
    }
  });
}

function turnPage(index, focus) {
  if (index < 0 || index >= chapters.length) return;
  navigate("#" + chapters[index].id);
  if (focus) rail[index].focus({ preventScroll: true });
}
previous.addEventListener("click", () => turnPage(chapterIndex - 1, true));
next.addEventListener("click", () => turnPage(chapterIndex + 1, true));

document.addEventListener("keydown", event => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || document.querySelector("dialog[open]")) return;
  if (story.hidden || !(story.contains(event.target) || event.target === document.body || event.target.id === "main")) return;
  if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    event.preventDefault();
    turnPage(chapterIndex + (event.key === "ArrowRight" ? 1 : -1), true);
  } else if (event.target.closest(".story-rail") && ["Home","End"].includes(event.key)) {
    event.preventDefault();
    turnPage(event.key === "Home" ? 0 : chapters.length - 1, true);
  }
});

let touchStart;
const book = story.querySelector(".book-pages");
book.addEventListener("touchstart", event => {
  touchStart = event.touches.length === 1 && !event.target.closest("button,a")
    ? { x:event.touches[0].clientX, y:event.touches[0].clientY } : null;
}, { passive:true });
book.addEventListener("touchcancel", () => { touchStart = null; }, { passive:true });
book.addEventListener("touchend", event => {
  if (!touchStart) return;
  const touch = event.changedTouches[0];
  const dx = touch.clientX - touchStart.x;
  const dy = touch.clientY - touchStart.y;
  touchStart = null;
  if (Math.abs(dx) > 60 && Math.abs(dx) > 1.6 * Math.abs(dy)) turnPage(chapterIndex + (dx < 0 ? 1 : -1), false);
}, { passive:true });

demos.querySelector(".film-nav").setAttribute("role","tablist");
filmTabs.forEach((tab, index) => {
  tab.setAttribute("role","tab");
  tab.setAttribute("aria-controls",films[index].id);
  films[index].setAttribute("role","tabpanel");
  films[index].setAttribute("aria-labelledby",tab.id);
  tab.addEventListener("keydown", event => {
    const count = filmTabs.length;
    const to = { ArrowRight:(index+1)%count, ArrowLeft:(index+count-1)%count, Home:0, End:count-1 }[event.key];
    if (to === undefined) return;
    event.preventDefault();
    navigate(filmTabs[to].hash);
    filmTabs[to].focus({ preventScroll:true });
  });
});

function setImageSize(original) {
  imageFrame.toggleAttribute("data-original",original);
  imageSize.textContent = original ? "전체 맞춤" : "원본 크기";
  if (original) {
    imageFrame.scrollLeft = (imageFrame.scrollWidth - imageFrame.clientWidth) / 2;
    imageFrame.scrollTop = (imageFrame.scrollHeight - imageFrame.clientHeight) / 2;
  }
}

for (const figure of story.querySelectorAll(".story-media")) {
  figure.querySelector(".motion").addEventListener("click", () => { paused = !paused; refreshPictures(); });
  const zoom = figure.querySelector(".zoom");
  zoom.hidden = typeof imageViewer.showModal !== "function";
  zoom.addEventListener("click", () => {
    imageOpener = zoom;
    const image = figure.querySelector("template").content.querySelector("img").cloneNode();
    imageFrame.replaceChildren(image);
    imageFrame.style.setProperty("--native-width", image.width + "px");
    imageViewer.querySelector("h2").textContent = figure.querySelector("figcaption > span").textContent;
    imageViewer.showModal();
    refreshPictures();
    setImageSize(true);
  });
  figure.addEventListener("click", event => {
    if (event.target === figure.querySelector(":scope > img") && !zoom.hidden) zoom.click();
  });
}
imageSize.addEventListener("click", () => setImageSize(!imageFrame.hasAttribute("data-original")));
imageViewer.addEventListener("close", () => { refreshPictures(); imageOpener?.focus({ preventScroll:true }); });
reducedMotion.addEventListener("change", event => { paused = event.matches; refreshPictures(); });
document.addEventListener("visibilitychange",refreshPictures);

function relocateVideo(video,parent,before) {
  if (typeof parent.moveBefore === "function") { parent.moveBefore(video,before); return; }
  const playing = !video.paused;
  parent.insertBefore(video,before);
  if (playing) video.play().catch(() => {});
}

for (const button of demos.querySelectorAll(".film-expand")) {
  const figure = button.closest("figure");
  const video = figure.querySelector("video");
  button.addEventListener("click",async () => {
    try {
      if (document.fullscreenEnabled && video.requestFullscreen) return await video.requestFullscreen();
      if (video.webkitEnterFullscreen && video.readyState >= HTMLMediaElement.HAVE_METADATA) return video.webkitEnterFullscreen();
    } catch { /* Fullscreen may be restricted in an embedded browser. */ }
    if (typeof filmViewer.showModal !== "function") return;
    filmViewer.querySelector("h2").textContent = figure.closest(".film-panel").querySelector("h3").textContent;
    filmViewer.showModal();
    relocateVideo(video,filmViewer,null);
    filmViewer.addEventListener("close",() => {
      relocateVideo(video,figure,figure.firstElementChild);
      if (!figure.closest("[hidden]")) button.focus({ preventScroll:true });
    }, {once:true});
  });
}

qrViewer.addEventListener("close", () => {
  if (location.hash === "#share") {
    history.replaceState(null,"",history.state?.returnTo || "#story");
    renderAddress();
    share.focus({preventScroll:true});
  }
});
window.addEventListener("hashchange",renderAddress);
document.body.classList.add("enhanced");
renderAddress();
