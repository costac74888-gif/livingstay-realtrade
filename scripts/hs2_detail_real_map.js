/* Real Kakao mini-map for server-authorized fictional Preview coordinates. */
(() => {
  "use strict";
  if (document.body.dataset.hs2Demo !== "seongsu") return;
  const section = document.querySelector(".location-section");
  const id = new URLSearchParams(location.search).get("public_id");
  if (!section || !id) return;
  const title = document.createElement("p");
  title.textContent = "실제 지도 위 테스트용 가상 위치 · 실재 주소·운영 확인 아님";
  const canvas = document.createElement("div");
  canvas.id = "preview-detail-map"; canvas.style.cssText = "height:300px;width:100%;margin:12px 0";
  canvas.setAttribute("aria-label", "실제 지도 위 가상 매물 위치");
  const status = document.createElement("p"); status.id = "preview-detail-map-status";
  section.append(title, canvas, status);
  async function mount() {
    try {
      const response = await fetch("/__development__/seongsu/catalog");
      const data = await response.json(), row = data.items.find(r => r.public_id === id);
      // Catalog records use canonical application/public IDs supplied below.
      const current = row || (await (await fetch("/hs2/details/api/items/" + encodeURIComponent(id))).json()).item?.preview_demo;
      if (!current?.synthetic || !window.kakao?.maps?.load) throw new Error("실제 SDK/가상 좌표를 확인하지 못했습니다.");
      kakao.maps.load(() => queueMicrotask(() => {
        const point = new kakao.maps.LatLng(current.point.lat, current.point.lng);
        const map = new kakao.maps.Map(canvas, {center:point,level:4});
        const label = document.createElement("button");
        label.textContent = "이 가상 매물"; label.type = "button";
        label.style.cssText = "padding:8px 12px;background:#075bff;color:white;border:0;border-radius:6px;font-size:14px";
        label.addEventListener("click", () => location.assign("/hs2/consumer?q=" + encodeURIComponent("성수")));
        new kakao.maps.CustomOverlay({map,position:point,content:label,yAnchor:1.2});
        window.HS2DetailMap = {ready:true,provider:"existing_kakao_maps",synthetic:true};
        status.textContent = "기존 카카오 지도 · 가상 좌표입니다. 실제 주소 검증 결과가 아닙니다.";
        window.addEventListener("resize",()=>map.relayout());
      }));
    } catch (_) {
      status.textContent = "실제 지도 연결을 확인하지 못했습니다. 가상 배치도로 대체하지 않습니다.";
    }
  }
  mount();
})();
