/* Responsive navigation and map/list presentation; native page controllers
   continue to own all search, results, layer, and map data interactions. */
(() => {
  const start = () => {
    const header = document.querySelector('.hs-live-header');
    const toggle = header?.querySelector('#hs-mobile-menu-toggle');
    const panel = header?.querySelector('#hs-main-menu');
    if (header && toggle && panel) {
      const closeMenu = (restoreFocus = false) => {
        header.classList.remove('hs-menu-open');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-label', '메뉴 열기');
        if (restoreFocus) toggle.focus();
      };
      toggle.addEventListener('click', () => {
        const open = toggle.getAttribute('aria-expanded') !== 'true';
        toggle.setAttribute('aria-expanded', String(open));
        toggle.setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
        header.classList.toggle('hs-menu-open', open);
      });
      panel.addEventListener('click', event => {
        if (event.target.closest('a')) closeMenu();
      });
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && header.classList.contains('hs-menu-open')) closeMenu(true);
      });
      document.addEventListener('click', event => {
        if (!header.contains(event.target)) closeMenu();
      });
      window.matchMedia('(min-width: 801px)').addEventListener?.('change', () => closeMenu());
    }

    const primary = document.querySelector('.search-primary-row');
    const dateFields = primary ? Array.from(primary.querySelectorAll('.date-field,.guest-field')) : [];
    const filterGroup = document.querySelector('.mobile-filter-group');
    if (primary && filterGroup && dateFields.length) {
      const positions = dateFields.map(field => {
        const marker = document.createComment('native search field position');
        field.before(marker); return {field,marker};
      });
      const dates = document.createElement('div');
      dates.className = 'mobile-period-fields'; filterGroup.append(dates);
      const media = matchMedia('(max-width:800px)');
      const moveFields = () => {
        positions.forEach(({field,marker}) => media.matches ? dates.append(field) : marker.after(field));
        dates.hidden = !media.matches;
      };
      media.addEventListener('change', moveFields); moveFields();
    }

    const workspace = document.querySelector('.map-workspace');
    const results = document.querySelector('#resultsPane');
    const ownerMode = document.body.dataset.mapMode === 'owner' ||
      Boolean(document.querySelector('#ownerModeLink[aria-current="page"]')) ||
      /owner|시설|운영/.test(document.title);
    if (!workspace || !results || ownerMode || workspace.querySelector('.map-mobile-switch')) return;
    const switcher = document.createElement('div');
    switcher.className = 'map-mobile-switch';
    switcher.setAttribute('role', 'group');
    switcher.setAttribute('aria-label', '지도와 목록 보기');
    const makeButton = (view, label) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.mobileView = view;
      button.textContent = label;
      button.setAttribute('aria-pressed', 'false');
      return button;
    };
    const listButton = makeButton('list', '목록');
    const mapButton = makeButton('map', '지도');
    switcher.append(listButton, mapButton);
    workspace.prepend(switcher);

    const setView = view => {
      workspace.dataset.mobileView = view;
      listButton.setAttribute('aria-pressed', String(view === 'list'));
      mapButton.setAttribute('aria-pressed', String(view === 'map'));
      if (view === 'map') {
        window.dispatchEvent(new Event('resize'));
        window.setTimeout(() => window.dispatchEvent(new Event('resize')), 100);
      }
    };
    listButton.addEventListener('click', () => setView('list'));
    mapButton.addEventListener('click', () => setView('map'));
    setView('list');
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
