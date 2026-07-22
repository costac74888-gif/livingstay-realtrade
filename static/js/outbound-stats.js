// 아웃바운드 랜딩페이지(agents/operators/loan_partners) 공용 — 히어로 통계 실시간 주입.
// #statBuildingCount / #statTxCount 에 /api/building-count, /api/tx-count 값을 넣는다.
// API 실패 시 HTML에 미리 넣어둔 숫자 없는 안전 문구를 그대로 둔다 (틀린 숫자를 보여주지 않기 위함).
(function () {
  var elB = document.getElementById("statBuildingCount");
  var elT = document.getElementById("statTxCount");
  if (!elB && !elT) return;

  function fill(el, url, okFmt) {
    if (!el) return;
    fetch(url)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        if (d && typeof d.count === "number" && d.count > 0) {
          el.textContent = okFmt(d.count);
        }
      })
      .catch(function () { /* 폴백: HTML 기본 문구 유지 */ });
  }

  fill(elB, "/api/building-count", function (n) { return n.toLocaleString("ko-KR") + "개 단지"; });
  fill(elT, "/api/tx-count", function (n) { return "실거래 " + n.toLocaleString("ko-KR") + "건을"; });
})();
