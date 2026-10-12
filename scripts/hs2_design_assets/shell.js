/* Shared design only: never replace native functional controllers or APIs. */
(() => {
  const start = () => {
    const map = JSON.parse(document.getElementById('hs-live-routes')?.textContent || '{}');
    document.body.classList.add('hs-live');
    const provider = '#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap,.hs2-map-canvas';
    const apply = () => {
      document.querySelectorAll('.hs-header,.site-nav,.topbar,.workspace-header,body>header:not(.hs-live-header)')
        .forEach(el => { if (!el.closest('.hs-live-header')) el.hidden = true; });
      document.querySelectorAll('a[href]').forEach(a => {
        const href = a.getAttribute('href');
        if (!href) return;
        const id = new URL(href, location.href).searchParams.get('screen');
        if (id && map[id]) a.setAttribute('href', map[id]);
        if (href.includes('/__development__/') && !a.closest('.hs-live-brand')) {
          // Keep source controls intact, remove only reviewer/guide navigation.
          if (!href.includes('map-assets/')) a.hidden = true;
        }
      });
      document.querySelectorAll('.private-label,.private-banner,.preview-demo-notice,.preview-connectivity-note').forEach(e => e.hidden = true);
      document.querySelectorAll('.hs-footer,.site-footer,body>footer').forEach(e => {
        if (!e.closest(provider)) e.style.color = '#000';
      });
      for (const e of document.querySelectorAll('.hs-suite *,.hs-live main *,.map-app *')) {
        if (!(e instanceof HTMLElement) || e.closest(provider)) continue;
        const direct = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
        if ((direct || e.matches('input,select,textarea')) &&
            !e.closest('[data-price],.hs-price,.listing-price,.detail-price,.preview-basis-price')) {
          e.style.setProperty('color', '#000', 'important');
          e.style.setProperty('transition-property', 'background-color,border-color,box-shadow,opacity,transform', 'important');
        }
        if ((direct || e.matches('input,select,textarea')) && parseFloat(getComputedStyle(e).fontSize) < 16)
          e.style.setProperty('font-size', '16px', 'important');
        if (e.matches('.hs-price,.listing-price,.detail-price,.preview-basis-price')) {
          e.dataset.price = 'true';
          e.style.setProperty('color', e.classList.contains('stay') || /원\s*\/\s*(일|박)/.test(e.textContent) ? '#9b7618' : '#596044', 'important');
        }
      }
    };
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; apply(); });
    }).observe(document.body, {childList:true, subtree:true});
    apply();
    const params = new URLSearchParams(location.search);
    if (params.get('facilities') === '1') {
      const directory = document.querySelector('#facilityDirectory');
      if (directory) { directory.open = true; directory.scrollIntoView({block:'start'}); }
    }
    if (params.has('layer')) {
      const layer = params.get('layer');
      document.querySelectorAll('button.layer-button[data-layer]').forEach(button => {
        const selected = button.dataset.layer === layer;
        if ((button.getAttribute('aria-pressed') === 'true') !== selected) button.click();
      });
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
