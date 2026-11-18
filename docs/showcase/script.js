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
    if (!active) panels[index].querySelector("video").pause();
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
