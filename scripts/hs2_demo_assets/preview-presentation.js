/* Preview-only presentation adapter. Load after the original page scripts. */
(() => {
  "use strict";

  const start = () => {
    const body = document.body;
    if (!body || body.dataset.hs2Demo !== "seongsu") return;

    // Final Preview decision: all application text black, including async text.
    // Never recolor the provider's map, tiles, logos or attribution.
    if (!window.HS2PreviewInk) {
      const overrides = new Map();
      let queued = false;
      const excluded = "#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap,script,style";
      const normalize = () => {
        queued = false;
        for (const [element, saved] of overrides) {
          if (saved.value) element.style.setProperty("color", saved.value, saved.priority);
          else element.style.removeProperty("color");
        }
        overrides.clear();
        for (const element of body.querySelectorAll("*")) {
          if (!(element instanceof HTMLElement) || element.closest(excluded)) continue;
          const hasText = [...element.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
          if (!hasText && !element.matches("input,select,textarea")) continue;
          const rgb = getComputedStyle(element).color.match(/[\d.]+/g);
          if (!rgb || rgb.slice(0,3).every(v => +v === 0)) continue;
          overrides.set(element, {value:element.style.getPropertyValue("color"),
                                  priority:element.style.getPropertyPriority("color")});
          element.style.setProperty("color", "#000", "important");
        }
      };
      const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(normalize); } };
      new MutationObserver(records => {
        if (records.some(r => !r.target.closest?.(excluded))) schedule();
      }).observe(body, {childList:true, subtree:true, attributes:true,
                        attributeFilter:["class", "data-state"]});
      window.HS2PreviewInk = {normalize};
      normalize();
    }

    const injectBrandLogo = () => {
      let brand = document.querySelector(".site-nav .brand, .topbar .brand, .workspace-brand, .brand");
      if (!brand && location.pathname.startsWith("/__development__/")) {
        const main = document.querySelector("main");
        if (main) {
          brand = document.createElement("a");
          brand.className = "brand";
          brand.href = "/hs2/consumer";
          brand.setAttribute("aria-label", "HOME & STAY 지도 메인");
          main.prepend(brand);
        }
      }
      if (!brand || brand.querySelector(".preview-brand-logo")) return;
      const image = document.createElement("img");
      image.className = "preview-brand-logo";
      image.src = "/__development__/seongsu/map-assets/brand-logo.png";
      image.alt = "HOME & STAY";
      image.setAttribute("decoding", "async");
      brand.prepend(image);
    };
    injectBrandLogo();

    const detail = document.getElementById("detail-content");
    if (detail) {
      body.classList.add("preview-detail");
      return;
    }

    const summary = document.getElementById("dashboard-summary");
    if (!summary || body.classList.contains("preview-dashboard")) return;

    const shell = document.querySelector(".shell");
    const main = shell && shell.querySelector(":scope > main");
    const layout = main && main.querySelector(".layout");
    const aside = layout && layout.querySelector(":scope > .aside");
    if (!shell || !main || !layout || !aside) return;

    body.classList.add("preview-dashboard");

    injectBrandLogo();

    const workPanel = aside.querySelector(".links-panel:not(.legacy)");
    const legacyPanel = aside.querySelector(".links-panel.legacy");
    const truthPanel = aside.querySelector(".aside-card");
    const connectivityNote = document.createElement("p");
    connectivityNote.className = "preview-connectivity-note";
    connectivityNote.setAttribute("aria-label", "외부 서비스 연결 상태");
    connectivityNote.textContent = "카카오 로그인 · 미연결\n카카오톡 발송 · 미연결";
    aside.replaceChildren(
      ...[workPanel, legacyPanel, connectivityNote, truthPanel].filter(Boolean)
    );
    aside.classList.add("preview-sidebar");

    const workflows = aside.querySelector("#dashboard-work-links");
    const markRealRegistrationLink = () => {
      if (!workflows) return;
      workflows.querySelectorAll("a").forEach((link) => {
        try {
          const url = new URL(link.href, window.location.origin);
          if (url.pathname === "/hs2/listings/" && url.searchParams.get("new") === "1") {
            link.classList.add("preview-register-link");
          }
        } catch {
          link.classList.remove("preview-register-link");
        }
      });
    };
    markRealRegistrationLink();
    if (workflows) {
      new MutationObserver(markRealRegistrationLink).observe(workflows, {
        childList: true,
        subtree: true
      });
    }

    const frame = document.createElement("div");
    frame.className = "preview-dashboard-frame";
    shell.insertBefore(frame, main);
    frame.append(aside, main);
    main.classList.add("preview-dashboard-main");
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
