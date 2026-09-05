const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("static/js/main.js", "utf8");
const start = source.indexOf("let _favOverflowPopover = null;");
const end = source.indexOf("\ndocument.addEventListener", start);

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(start >= 0 && end > start, "관심단지 렌더링 함수 영역을 찾지 못했습니다.");

const nodes = [];
const wrap = {
  innerHTML: "",
  appendChild(node) { nodes.push(node); },
  scrollIntoViewOptions: null,
  scrollIntoView(options) { this.scrollIntoViewOptions = options; },
};
const context = {
  window: {
    matchMedia: () => ({ matches: true }),
  },
  document: {
    createElement(tag) {
      return {
        tag,
        children: [],
        dataset: {},
        className: "",
        appendChild(child) { this.children.push(child); },
        addEventListener(type, listener) { this[`on${type}`] = listener; },
        setAttribute() {},
      };
    },
    getElementById(id) { return id === "favChips" ? wrap : null; },
    body: { appendChild() {} },
  },
  state: { favKey: null },
  getFavorites: () => Array.from({ length: 10 }, (_, i) => `관심단지${i + 1}|주소${i + 1}`),
  serverFavBuildingIds: new Map(),
  requestAnimationFrame: (callback) => callback(),
  closeFavOverflowPopover: undefined,
  console,
};

vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
vm.runInContext("createFavChip = key => ({ key }); renderFavChips();", context);

expect(nodes.length === 4, "모바일 기본 상태는 관심단지 3개와 더보기 버튼이어야 합니다.");
const more = nodes[3];
expect(more.textContent === "+더보기(7)", "숨겨진 관심단지 개수를 표시해야 합니다.");

nodes.length = 0;
more.onclick();

expect(nodes.length === 11, "더보기를 누르면 관심단지 10개와 접기 버튼을 모두 표시해야 합니다.");
expect(nodes[10].textContent === "접기", "펼친 상태에서 접기 버튼을 표시해야 합니다.");
expect(
  wrap.scrollIntoViewOptions && wrap.scrollIntoViewOptions.block === "center",
  "펼친 관심단지 영역이 화면 가운데로 스크롤되어야 합니다."
);

console.log("OK  모바일 관심단지 전체 펼침·자동 스크롤");