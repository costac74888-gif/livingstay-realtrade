const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("static/admin.html","utf8");
const start = source.indexOf("async function loadPublicApiRelayStatus() {");
const end = source.indexOf("async function loadDataSyncBanner()",start);
assert.ok(start>=0 && end>start);
assert.equal((source.match(/id="publicApiRelayStatus"/g)||[]).length,1);
let target={textContent:""};
let url;
let body={ok:true,services:{
  bldg_hub:{enabled:false,last_success_at:null,last_error_code:null},
  rtms:{enabled:true,last_success_at:"2026-10-05T00:00:00+00:00",last_error_code:"RELAY_QUOTA"}
}};
let ok=true;
const context = vm.createContext({document:{getElementById:()=>target},Date,
  fetch:async value=>{url=value;return {ok,json:async()=>body};}});
vm.runInContext(source.slice(start,end),context);
(async()=>{
  await context.loadPublicApiRelayStatus();
  assert.equal(url,"/api/admin/public-api-relay/status");
  assert.match(target.textContent,/건축HUB 중계: 꺼짐 · 마지막 성공: 없음 · 최근 오류: 없음/);
  assert.match(target.textContent,/실거래 중계: 켜짐.*최근 오류: RELAY_QUOTA/);
  assert.ok(!/token|serviceKey|https:/.test(target.textContent));
  ok=false;
  await context.loadPublicApiRelayStatus();
  assert.equal(target.textContent,"중계 상태를 불러오지 못했습니다.");
  target=null;
  await context.loadPublicApiRelayStatus();
  console.log("PASS existing admin menu relay status: flags, success, error, safe text and absent panel");
})().catch(error=>{console.error(error);process.exit(1);});
