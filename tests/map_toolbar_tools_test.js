const fs = require("fs");
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const html = read("static", "index.html");
const css = read("static", "css", "main.css");
const js = read("static", "js", "main.js");

const requiredHtml = [
  'id="mapToolbar"',
  'id="mapTypeTool"',
  'id="roadviewTool"',
  'id="measureTool"',
  'id="educationTool"',
  'id="convenienceTool"',
  'id="roadviewPanel"',
  'id="measurePanel"',
];
const missingHtml = requiredHtml.filter((token) => !html.includes(token));
if (missingHtml.length) {
  throw new Error(`지도 툴바 HTML 요소 누락: ${missingHtml.join(", ")}`);
}

const requiredCss = [
  ".map-toolbar",
  ".map-tool-btn.active",
  ".roadview-panel.open",
  ".map-measure-panel",
  ".map-poi-marker",
  "@media (max-width: 980px)",
];
const missingCss = requiredCss.filter((token) => !css.includes(token));
if (missingCss.length) {
  throw new Error(`지도 툴바 CSS 요소 누락: ${missingCss.join(", ")}`);
}

const requiredJs = [
  "MAP_TYPE_STEPS",
  "RoadviewClient",
  "new kakao.maps.Polyline",
  "new kakao.maps.CustomOverlay",
  "/api/map/poi?",
  "_roadviewRequestSequence",
  "sequence !== _roadviewRequestSequence",
  "function _deactivateMapTool",
  "function _activateMapTool",
  "function _bindMapToolMapEvents",
  "_initMapToolControls();",
  "_bindMapToolMapEvents();",
];
const missingJs = requiredJs.filter((token) => !js.includes(token));
if (missingJs.length) {
  throw new Error(`지도 툴바 JS 계약 누락: ${missingJs.join(", ")}`);
}

const syntax = spawnSync(process.execPath, ["--check", path.join(root, "static", "js", "main.js")], {
  encoding: "utf8",
});
if (syntax.status !== 0) {
  throw new Error(`main.js 문법 오류:\n${syntax.stderr || syntax.stdout}`);
}

console.log("OK  지도 툴바 마크업·모바일 CSS·SDK 도구 계약");