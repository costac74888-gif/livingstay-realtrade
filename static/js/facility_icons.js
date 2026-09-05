(function (window) {
  "use strict";

  /*
   * 숙박 상세 화면 공용 시설 아이콘 계약.
   * 같은 시설명은 캠핑·농어촌민박·한옥 상세에서도 이 사전을 사용한다.
   * 이모지는 작은 화면에서도 뜻이 빠르게 읽히는 기존 UI 언어를 따른다.
   */
  const ICONS = {
    "일반 야영": "🏕️", "오토 캠핑": "🚚", "글램핑": "⛺", "카라반": "🚐",
    "화장실": "🚻", "샤워실": "🚿", "개수대": "🚰", "세면장": "🚿",
    "취사장": "🍳", "매점": "🏪", "주차장": "🅿️", "전기": "🔌",
    "와이파이": "📶", "무선인터넷": "📶", "장작판매": "🪵", "온수": "♨️",
    "놀이터": "🛝", "수영장": "🏊", "트램펄린": "🤸", "물놀이장": "💦",
    "산책로": "🥾", "낚시": "🎣", "반려동물": "🐾", "바비큐": "🍖",
    "편의점": "🏪", "세탁실": "🧺", "개별화장실": "🚻", "공용화장실": "🚻",
    "운동시설": "⚽", "운동장": "⚽", "족구장": "⚽", "체육시설": "⚽",
    "산책": "🥾", "해수욕": "🏖️", "해변": "🏖️", "계곡": "🏞️",
    "수상레저": "🛶", "온수제공": "♨️", "덤프스테이션": "🚐",
    "카라반사이트": "🚐", "캠핑장비대여": "🎒", "화로대": "🔥",
    "공용주방": "🍳", "냉장고": "🧊", "에어컨": "❄️", "난방": "♨️",
    "소화기": "🧯", "응급시설": "🩹", "보안": "🔒"
  };
  const key = value => String(value || "").replace(/\s+/g, "").toLowerCase();
  const normalized = Object.keys(ICONS).reduce((out, name) => {
    out[key(name)] = ICONS[name];
    return out;
  }, {});

  window.FacilityIcons = {
    get(name, fallback = "•") {
      const text = String(name || "").trim();
      const compact = key(text);
      if (!compact) return fallback;
      const match = Object.keys(normalized).find(k => compact.includes(k) || k.includes(compact));
      return match ? normalized[match] : fallback;
    },
    html(name, className = "facility-icon") {
      return `<span class="${className}" role="img" aria-label="${String(name || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;")}">${this.get(name)}</span>`;
    },
    map: Object.freeze({ ...ICONS })
  };
})(window);