const assert = require("node:assert/strict");
const fs = require("node:fs");
const {execFileSync} = require("node:child_process");
const {chromium} = require("playwright");
const source=fs.readFileSync("static/js/main.js","utf8");
const start=source.indexOf("function _renderDetailCards(b, buildingId){");
const end=source.indexOf("\nfunction _removeDetailTourismAttractions",start);
assert.ok(start>=0 && end>start);
(async()=>{
  const browser=await chromium.launch({executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),args:["--no-sandbox"]});
  try {
    const page=await browser.newPage();
    await page.setContent('<section id="bBldgInfoCard"></section>');
    await page.evaluate(code=>{
      window.escapeHtml=String;
      window.trackRecentBuilding=()=>{};
      window._loadDetailTourismStats=()=>{};
      window.eval(code);
    },source.slice(start,end));
    await page.evaluate(()=>{
      _renderDetailCards({
        building_name:"test", arch_area:430.38, indr_auto_utcnt:0, oudr_auto_utcnt:0,
        detail_status:{running:false,stages:{title:{status:"ok"},zoning:{status:"empty"},inspection:{status:"failed"}},
          fields:{arch_area:"ok",jiyuk_nm:"empty",last_inspection_submit_day:"failed"}},
      },24841);
    });
    const text=await page.locator("#bBldgInfoCard").innerText();
    assert.match(text,/430\.38/);
    assert.match(text,/0대/);
    assert.match(text,/원본 미제공/);
    assert.match(text,/조회 실패/);
    assert.doesNotMatch(text,/조회 중/);
    await page.evaluate(()=>_renderDetailCards({
      building_name:"completed",detail_status:{running:false,
        stages:{title:{status:"ok"},zoning:{status:"empty"},inspection:{status:"ok"}}},
    },3128));
    assert.match(await page.locator("[data-detail-status]").innerText(),/조회 완료/);
    console.log("PASS per-field empty/failure states, completed hint and genuine zero parking");
  } finally {await browser.close();}
})().catch(err=>{console.error(err);process.exit(1)});
