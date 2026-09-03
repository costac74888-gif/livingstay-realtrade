
// 등록된 파트너 섹션 — 승인 + 로고 보유 운영지원업체만 로고 그리드로 노출.
// 0곳이면 빈 그리드 대신 "파트너 모집 중입니다" 문구만 표시.
(async function(){
  const body = document.getElementById("partnerIntroBody");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
  try {
    const res = await fetch("/api/partners/operators");
    const data = await res.json();
    const items = (res.ok && data.ok && Array.isArray(data.items)) ? data.items : [];
    if (!items.length){
      body.innerHTML = '<div style="font-size:13px; color:var(--ink-soft); text-align:center; padding:8px 0;">파트너 모집 중입니다</div>';
      return;
    }
    body.innerHTML = '<div class="partner-logo-grid">' + items.map((p) => {
      const inner = `<img src="${esc(p.logo_src)}" alt="${esc(p.company_name)} 로고" loading="lazy" /><div class="partner-logo-name">${esc(p.company_name)}</div>`;
      return p.subdomain_slug
        ? `<a class="partner-logo-card" href="/operator/${encodeURIComponent(p.subdomain_slug)}">${inner}</a>`
        : `<div class="partner-logo-card">${inner}</div>`;
    }).join("") + '</div>';
  } catch(e){
    body.innerHTML = '<div style="font-size:13px; color:var(--ink-soft); text-align:center; padding:8px 0;">파트너 모집 중입니다</div>';
  }
})();
