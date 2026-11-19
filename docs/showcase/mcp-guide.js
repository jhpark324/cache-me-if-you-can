const search = document.querySelector(".mcp-search");
const field = document.querySelector("#mcp-query");
const groups = Array.from(document.querySelectorAll(".mcp-group"));
const statusText = document.querySelector(".mcp-count");
if (search && field) {
  search.hidden = false;
  search.addEventListener("submit", (event) => event.preventDefault());
  field.addEventListener("input", () => {
    const words = field.value.trim().normalize("NFC").toLowerCase().split(/\s+/);
    let count = 0;
    for (const group of groups) {
      const title = group.querySelector("h3").textContent;
      const entries = [...group.querySelectorAll(".mcp-tool")];
      for (const entry of entries) {
        const text = (title + " " + entry.querySelector("summary").textContent).toLowerCase();
        entry.hidden = !words.every((word) => text.includes(word));
        if (!entry.hidden) count++;
      }
      group.hidden = entries.every((entry) => entry.hidden);
    }
    statusText.textContent = field.value.trim() ? (count ? `도구 ${count}개` : "일치하는 도구가 없습니다.") : "";
  });
}
function openLinkedTool() {
  const target = document.getElementById(location.hash.slice(1));
  if (target?.matches("details.mcp-tool")) {
    if (target.hidden) {
      field.value = "";
      field.dispatchEvent(new Event("input"));
    }
    target.open = true;
  }
}
openLinkedTool();
window.addEventListener("hashchange", openLinkedTool);
