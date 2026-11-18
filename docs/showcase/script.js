// Without JavaScript every scene remains readable and playable at its own anchor.
const tour = document.querySelector("#demo");
const tablist = tour.querySelector(".film-nav");
const tabs = [...tablist.querySelectorAll("a[href^='#']")];
const panels = tabs.map((tab) => document.getElementById(tab.hash.slice(1)));

function showScene(selected) {
  tabs.forEach((tab, index) => {
    const active = index === selected;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    panels[index].hidden = !active;
    if (!active) panels[index].querySelector("video")?.pause();
  });
}

function sceneFromAddress() {
  const selected = tabs.findIndex((tab) => tab.hash === location.hash);
  if (selected !== -1) showScene(selected);
  else if (!location.hash || location.hash === "#demo") showScene(0);
}

function visitScene(index, moveFocus) {
  showScene(index);
  if (location.hash !== tabs[index].hash) {
    const method = moveFocus ? "replaceState" : "pushState";
    history[method](null, "", tabs[index].hash);
  }
  if (moveFocus) tabs[index].focus();
}

if (tabs.length && panels.every(Boolean)) {
  tour.classList.add("enhanced");
  tablist.setAttribute("role", "tablist");
  tabs.forEach((tab, index) => {
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", panels[index].id);
    panels[index].setAttribute("role", "tabpanel");
    panels[index].setAttribute("aria-labelledby", tab.id);
    tab.addEventListener("click", (event) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      event.preventDefault();
      visitScene(index, false);
    });
    tab.addEventListener("keydown", (event) => {
      const next = {
        ArrowLeft: (index + tabs.length - 1) % tabs.length,
        ArrowRight: (index + 1) % tabs.length,
        Home: 0,
        End: tabs.length - 1,
      }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      visitScene(next, true);
    });
  });
  const initial = tabs.findIndex((tab) => tab.hash === location.hash);
  showScene(initial < 0 ? 0 : initial);
  window.addEventListener("hashchange", sceneFromAddress);
  window.addEventListener("popstate", sceneFromAddress);
}

const imageViewer = document.getElementById("image-viewer");
const imageOpen = document.querySelector(".graph-open");
const imageFrame = document.getElementById("viewer-frame");
const imageSize = document.querySelector(".viewer-size");

function setImageSize(original) {
  imageFrame.toggleAttribute("data-original", original);
  imageSize.textContent = original ? "전체 맞춤" : "원본 크기";
  if (original) {
    imageFrame.scrollLeft = (imageFrame.scrollWidth - imageFrame.clientWidth) / 2;
    imageFrame.scrollTop = (imageFrame.scrollHeight - imageFrame.clientHeight) / 2;
  }
}

if (typeof imageViewer.showModal === "function") {
  imageOpen.hidden = false;
  imageOpen.addEventListener("click", () => {
    imageViewer.showModal();
    setImageSize(true);
  });
  imageSize.addEventListener("click", () => setImageSize(!imageFrame.hasAttribute("data-original")));
  imageViewer.addEventListener("close", () => imageOpen.focus({ preventScroll: true }));
}

const filmViewer = document.getElementById("film-viewer");
const filmViewerTitle = document.getElementById("film-viewer-title");

// An inline dialog also works in browsers and embeds that restrict fullscreen.
function showVideoDialog(video, button) {
  const figure = video.closest("figure");
  const heading = figure.closest(".film-panel").querySelector("h3");
  filmViewerTitle.textContent = heading.textContent;
  filmViewer.showModal();
  relocateVideo(video, filmViewer, null);
  filmViewer.addEventListener("close", () => {
    relocateVideo(video, figure, figure.firstElementChild);
    button.focus({ preventScroll: true });
  }, { once: true });
}

function relocateVideo(video, parent, before) {
  if (typeof parent.moveBefore === "function") {
    parent.moveBefore(video, before);
    return;
  }
  const playing = !video.paused;
  parent.insertBefore(video, before);
  if (playing) video.play().catch(() => {});
}

window.addEventListener("hashchange", () => {
  if (filmViewer.open) {
    filmViewer.querySelector("video")?.pause();
    filmViewer.close();
  }
});

for (const button of document.querySelectorAll(".film-expand")) {
  const video = button.closest("figure").querySelector("video");
  const fullscreen = document.fullscreenEnabled && typeof video.requestFullscreen === "function";
  const nativePlayer = typeof video.webkitEnterFullscreen === "function";
  const dialog = typeof filmViewer.showModal === "function";
  button.hidden = !(fullscreen || nativePlayer || dialog);
  button.addEventListener("click", async () => {
    try {
      if (fullscreen) return await video.requestFullscreen();
      if (nativePlayer && video.readyState >= HTMLMediaElement.HAVE_METADATA) {
        return video.webkitEnterFullscreen();
      }
    } catch {
      // Browsers may deny fullscreen in an embedded or restricted tab.
    }
    if (dialog) showVideoDialog(video, button);
  });
}
