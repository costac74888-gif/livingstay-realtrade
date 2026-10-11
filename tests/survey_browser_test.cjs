const { artifactPath } = require("./offline_support/capture_artifacts.cjs");
/* Public pages use real HTTP. UI submissions use intercepted test responses;
   real SQL behaviour is covered by rollback-only test_survey.py. No auth bypass. */
const {chromium} = require("playwright");
const {execFileSync} = require("node:child_process");
const fs = require("node:fs");
const assert = require("node:assert/strict");
const python = code => execFileSync("python", ["-c", code], {encoding:"utf8"}).trim();

(async () => {
  const base = process.env.TEST_BASE_URL || `https://${process.env.REPLIT_DEV_DOMAIN}`;
  const id = Number(python(`from db import get_conn
c=get_conn()
try:
 with c.cursor() as q:
  q.execute("SELECT id FROM auction_items WHERE status IN ('scheduled','bidding') AND bid_end_at>NOW()+INTERVAL '3 days' ORDER BY (master_building_id IS NULL),bid_end_at DESC LIMIT 1")
  print(q.fetchone()['id'])
finally: c.close()`));
  const browser = await chromium.launch({executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),args:["--no-sandbox"]});
  const userAgent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36";
  fs.mkdirSync(artifactPath("attached_assets/auction-phase2"), {recursive:true});
  let temporaryAdmin = null;
  try {
    const viewports=process.argv.includes("--admin-only")?[]:[["desktop",1440],["mobile",390]];
    for (const [label,width] of viewports) {
      const context = await browser.newContext({viewport:{width,height:900},ignoreHTTPSErrors:true,locale:"ko-KR",userAgent});
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", e=>errors.push(e.message));
      await page.goto(`${base}/auctions/${id}`);
      // The public announcement stays public; survey/operating details moved
      // behind membership. Never inject a paid identity or mock this API.
      await page.locator("#bAuctionPanel .auction-membership-zone").waitFor();
      assert.equal(await page.locator(".survey-check-state").count(), 0);
      assert.equal(await page.locator('.survey-analysis-link').count(), 0);
      assert.equal(await page.locator("#bAuctionPanel .b-membership-preview dt").count(), 13);
      const masks=await page.locator("#bAuctionPanel .b-membership-preview dd").allTextContents();
      assert.ok(masks.every(text=>text.trim()==="멤버십 회원 전용"));
      const protectedInfo=await page.evaluate(async auctionId=>{
        const response=await fetch(`/api/auctions/${auctionId}/survey-info`);
        return {status:response.status,body:await response.json()};
      },id);
      assert.equal(protectedInfo.body.membership_access.required,true);
      assert.ok(!protectedInfo.body.analysis_links?.length);
      assert.ok(!protectedInfo.body.checklist?.length);
      assert.equal(await page.locator('.auction-panel-general h4').count(), 1);
      assert.ok((await page.locator("#bAuctionPanel").textContent()).includes("온비드"));
      assert.ok((await page.locator("#bAuctionPanel").textContent()).includes("회차"));
      await page.evaluate(()=>document.fonts.ready);
      const overflow=await page.evaluate(()=>({
        width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
        elements:[...document.querySelectorAll("body *")].map(node=>({node,rect:node.getBoundingClientRect()}))
          .filter(({node,rect})=>rect.width>0&&rect.right>innerWidth+1&&getComputedStyle(node).position!=="absolute")
          .slice(0,12).map(({node,rect})=>({id:node.id,tag:node.tagName,className:node.className,right:rect.right,width:rect.width}))
      }));
      if(overflow.scrollWidth>width+1)await page.screenshot({path:artifactPath(`attached_assets/auction-phase2/overflow-${label}.png`)});
      assert.ok(overflow.scrollWidth<=width+1,JSON.stringify(overflow));
      await page.screenshot({path:artifactPath(`attached_assets/auction-phase2/detail-${label}.png`),fullPage:true});
      const cta=page.locator("#bAuctionPanel .b-membership-cta");
      assert.equal(new URL(await cta.getAttribute("href"),base).pathname,"/membership");
      assert.equal(await page.locator("#surveyRequestForm").count(),0);
      await cta.click();
      await page.waitForURL(url=>url.pathname==="/membership");
      await page.locator("main.membership-page").waitFor();
      assert.deepEqual(errors,[]);
      console.log(`PASS ${width}px public announcement, server-side membership privacy, 13 masked fields and membership navigation; no auth/API bypass`);
      await context.close();
    }
    // Authenticate a temporary staff account via the real login UI, then remove it.
    temporaryAdmin = JSON.parse(python(`import json,secrets,uuid
from db import get_conn
from werkzeug.security import generate_password_hash
email='survey-browser-'+uuid.uuid4().hex+'@example.invalid';password=secrets.token_urlsafe(30)
c=get_conn()
try:
 with c.cursor() as q:
  q.execute("INSERT INTO admin_users(email,password_hash,name,role) VALUES(%s,%s,'자동검증','admin') RETURNING id",[email,generate_password_hash(password)])
  ident=q.fetchone()['id']
 c.commit()
 print(json.dumps({'id':ident,'email':email,'password':password}))
finally:c.close()`));
    const context=await browser.newContext({viewport:{width:1280,height:900},ignoreHTTPSErrors:true,locale:"ko-KR",userAgent});
    const page=await context.newPage();
    const errors=[];page.on("pageerror",e=>errors.push(e.message));
    await page.goto(base+"/admin/login");
    await page.fill("#adminEmail",temporaryAdmin.email);
    await page.fill("#adminPassword",temporaryAdmin.password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/admin$/);
    await page.locator(".action-center-counts").waitFor();
    assert.ok(await page.getByText(/신규 현황조사 신청 [\d,]+건/).count());
    await page.screenshot({path:artifactPath("attached_assets/auction-phase2/admin-summary-desktop.png"),fullPage:true});
    const requestListResponse=page.waitForResponse(response=>response.url().includes("/api/admin/survey/requests?"));
    await page.click('[data-menu="admin-survey"]');
    const requestList=await (await requestListResponse).json();
    assert.equal(requestList.ok,true);
    await page.waitForFunction(()=>!document.getElementById("asRequestResults")?.textContent.includes("불러오는 중"));
    if(requestList.items.length)await page.locator("#asContent .as-table").waitFor();
    else assert.ok((await page.locator("#asRequestResults").textContent()).includes("신청이 없습니다"));
    await page.screenshot({path:artifactPath("attached_assets/auction-phase2/admin-requests-desktop.png"),fullPage:true});
    await page.locator('[data-as-tab="settings"]').waitFor();
    await page.click('[data-as-tab="settings"]');
    await page.locator("#as-base_fee").waitFor();
    assert.equal(await page.locator("#as-base_fee").inputValue(),"79000");
    assert.equal(await page.locator("#as-promo_end_date").getAttribute("type"),"date");
    // Capture-only styling must not request a real CDN. Font asset completeness
    // is handled separately; this check verifies auth, privacy and admin flows.
    await page.addStyleTag({content:"body,input,textarea,button{font-family:'Noto Sans KR',sans-serif!important}"});
    await page.evaluate(()=>document.fonts.ready);
    await page.screenshot({path:artifactPath("attached_assets/auction-phase2/admin-settings-desktop.png"),fullPage:true});
    await page.setViewportSize({width:390,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:artifactPath("attached_assets/auction-phase2/admin-settings-mobile.png"),fullPage:true});
    const put=page.waitForRequest(r=>r.url().endsWith("/api/admin/survey/settings") && r.method()==="PUT");
    await page.route("**/api/admin/survey/settings",async route=>{
      if(route.request().method()==="PUT") await route.fulfill({status:200,contentType:"application/json",body:'{"ok":true}'});
      else await route.continue();
    });
    await page.fill("#as-base_fee","81000");
    await page.click("#asSaveSettings");
    const payload=(await put).postDataJSON();
    assert.equal(payload.base_fee,81000);
    assert.equal(typeof payload.visit_fee,"number");
    assert.equal(payload.promo_enabled,false);
    assert.equal(payload.bank_name,"가상은행"); // Owned fixture; never a real payout account.
    const transitions={received:["paid","canceled"],paid:["investigating","refunded"],investigating:["reported","refunded"],reported:["refunded"],canceled:["refunded"],refunded:[]};
    const fixture={id:999999999,request_no:"SV-BROWSER-TEST",created_at:new Date().toISOString(),
      status:"received",auction_title:"자동검증 공매",applicant_name:"자동검증",phone:"01000000000",
      email:"",memo:"자동검증 요청",depositor_name:"자동검증",survey_type:"visit",
      base_fee:79000,visit_fee:99000,total_fee:178000,payment_deadline:new Date(Date.now()+86400000).toISOString(),
      settings_snapshot:{bank_name:"농협",bank_account:"테스트 계좌",bank_holder:"자동검증"},terms_snapshot:"검증용 약관",admin_memo:""};
    const history=[{to_status:"received",changed_by:"신청자",note:"접수",created_at:fixture.created_at}];
    await page.route("**/api/admin/survey/requests**",async route=>{
      const path=new URL(route.request().url()).pathname;
      let result;
      if(path.endsWith("/status")) {
        const data=route.request().postDataJSON();
        assert.equal(data.status,"paid");
        assert.equal(data.note,"자동검증 입금확인");
        history.push({from_status:fixture.status,to_status:data.status,note:data.note,changed_by:"자동검증",created_at:new Date().toISOString()});
        fixture.status=data.status;fixture.admin_memo=data.note;result={ok:true};
      } else if(path.endsWith("/"+fixture.id)) result={ok:true,item:fixture,history,transitions};
      else result={ok:true,items:[fixture],total:1,page:1,page_size:30,transitions};
      await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(result)});
    });
    await page.click('[data-as-tab="requests"]');
    await page.locator(".as-table button").first().waitFor();
    await page.locator(".as-table button").first().click();
    await page.locator("#asNextStatus").waitFor();
    await page.selectOption("#asNextStatus","paid");
    await page.fill("#asStatusNote","자동검증 입금확인");
    await page.locator('#asStatusForm button[type="submit"]').click();
    await page.waitForFunction(()=>document.querySelector("#asNextStatus")?.value==="investigating");
    assert.ok((await page.locator("#asRequestDetail").textContent()).includes("자동검증 입금확인"));
    await page.click('[data-menu="legal"]');
    await page.getByRole("button",{name:"공매 조사 약관",exact:true}).click();
    await page.locator("#legalTextarea").waitFor();
    await page.waitForFunction(()=>document.querySelector("#legalTextarea")?.value.includes("현황조사"));
    assert.deepEqual(errors,[]);
    console.log("PASS authenticated admin desktop/390px settings, typed save payload, status/memo/history (intercepted writes), real terms CMS and menu switching");
    await context.close();
  } finally {
    await browser.close();
    if(temporaryAdmin) python(`from db import get_conn
c=get_conn()
try:
 with c.cursor() as q:q.execute("DELETE FROM admin_users WHERE id=%s",[${temporaryAdmin.id}])
 c.commit()
finally:c.close()`);
  }
})().catch(error=>{console.error(error.stack);process.exit(1)});