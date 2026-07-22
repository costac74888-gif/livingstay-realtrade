// 신청서 서류 첨부 드래그앤드롭 — 각 .doc-input을 드롭존으로 감싸고,
// 드롭/클릭 모두 기존 input의 change 핸들러(즉시 업로드 로직)를 그대로 재사용한다.
(function () {
  "use strict";

  document.querySelectorAll("input.doc-input").forEach(function (input) {
    var zone = document.createElement("div");
    zone.className = "doc-dropzone";
    zone.setAttribute("role", "button");
    zone.setAttribute("tabindex", "0");
    zone.innerHTML =
      '<span class="doc-dropzone-icon" aria-hidden="true">📎</span>' +
      '<span class="doc-dropzone-text">파일을 여기로 끌어다 놓거나 <u>클릭하여 선택</u></span>';

    input.parentElement.insertBefore(zone, input);
    zone.appendChild(input);
    input.classList.add("doc-input-hidden");

    function openPicker() { input.click(); }
    zone.addEventListener("click", function (ev) {
      if (ev.target === input) return; // input 자체 클릭은 그대로
      openPicker();
    });
    zone.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openPicker(); }
    });

    ["dragenter", "dragover"].forEach(function (t) {
      zone.addEventListener(t, function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        zone.classList.add("doc-dropzone-over");
      });
    });
    ["dragleave", "drop"].forEach(function (t) {
      zone.addEventListener(t, function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        zone.classList.remove("doc-dropzone-over");
      });
    });
    zone.addEventListener("drop", function (ev) {
      var files = ev.dataTransfer && ev.dataTransfer.files;
      if (!files || !files.length) return;
      try {
        var dt = new DataTransfer();
        dt.items.add(files[0]); // 항목별 1개 파일
        input.files = dt.files;
      } catch (e) {
        // 일부 구형 브라우저에서 DataTransfer 생성 불가 — 클릭 선택 안내
        alert("이 브라우저에서는 끌어다 놓기가 지원되지 않습니다. 클릭하여 파일을 선택해주세요.");
        return;
      }
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    // 업로드 성공 시(✅ 텍스트) 드롭존 자체도 초록 완료 표시로 전환
    var statusEl = zone.parentElement.querySelector(".doc-status");
    if (statusEl) {
      new MutationObserver(function () {
        var done = statusEl.textContent.indexOf("✅") === 0;
        zone.classList.toggle("doc-dropzone-done", done);
        var txt = zone.querySelector(".doc-dropzone-text");
        if (txt) {
          txt.innerHTML = done
            ? "첨부 완료 — 다른 파일로 바꾸려면 클릭 또는 드롭"
            : '파일을 여기로 끌어다 놓거나 <u>클릭하여 선택</u>';
        }
      }).observe(statusEl, { childList: true, characterData: true, subtree: true });
    }
  });
})();
