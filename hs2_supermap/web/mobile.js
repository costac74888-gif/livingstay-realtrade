(() => {
  "use strict";

  const body = document.body;
  if (!body || body.dataset.mobileExperience !== "true") return;

  const workspace = document.querySelector(".supermap-workspace");
  const listPane = workspace?.querySelector(".results-pane");
  const mapPane = workspace?.querySelector(".map-pane");
  if (!workspace || !listPane || !mapPane) return;

  const mobileQuery = window.matchMedia("(max-width: 760px)");
  let currentView = body.dataset.mobileView === "map" ? "map" : "list";

  if (!listPane.id) listPane.id = "mobile-results-pane";
  if (!mapPane.id) mapPane.id = "mobile-map-pane";

  const controls = document.createElement("div");
  controls.className = "mobile-panel-switch";
  controls.id = "mobile-panel-switch";
  controls.setAttribute("role", "group");
  controls.setAttribute("aria-label", "검색 결과 보기 방식");
  controls.innerHTML = [
    `<button type="button" id="mobile-list-btn" aria-controls="${listPane.id}" aria-pressed="true">`,
    '<span class="mobile-switch-mark mobile-list-mark" aria-hidden="true"></span><span>목록</span></button>',
    `<button type="button" id="mobile-map-btn" aria-controls="${mapPane.id}" aria-pressed="false">`,
    '<span class="mobile-switch-mark mobile-map-mark" aria-hidden="true"></span><span>지도</span></button>'
  ].join("");

  workspace.before(controls);
  const listButton = controls.querySelector("#mobile-list-btn");
  const mapButton = controls.querySelector("#mobile-map-btn");

  function updateView(nextView, announceResize = true) {
    currentView = nextView === "map" ? "map" : "list";
    body.dataset.mobileView = currentView;
    const narrow = mobileQuery.matches;

    listButton.setAttribute("aria-pressed", String(currentView === "list"));
    mapButton.setAttribute("aria-pressed", String(currentView === "map"));
    listPane.hidden = narrow && currentView !== "list";
    mapPane.hidden = narrow && currentView !== "map";

    if (narrow && currentView === "map" && announceResize) {
      // Let the visible pane establish its final dimensions before Kakao's
      // existing search.js resize listener runs relayoutMap().
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
      });
    }
  }

  listButton.addEventListener("click", () => updateView("list"));
  mapButton.addEventListener("click", () => updateView("map"));
  mobileQuery.addEventListener("change", () => updateView(currentView, mobileQuery.matches && currentView === "map"));
  updateView(currentView, mobileQuery.matches && currentView === "map");
})();
