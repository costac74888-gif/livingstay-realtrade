/* Real dev-only sessions/HTTP/SQL. Synthetic accounts are removed in finally.
   No real money is transferred; only a temporary staff account confirms test rows.
   No external notifications or production connection are used. */
const {chromium}=require("playwright");
const {execFileSync}=require("node:child_process");
const assert=require("node:assert/strict");
const python=code=>execFileSync("python",["-c",code],{encoding:"utf8"}).trim();
const base=`https://${process.env.REPLIT_DEV_DOMAIN}`;
const agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36";
const json=async r=>{assert.equal(r.status(),200);return r.json()};

(async()=>{
  const fixtures=JSON.parse(python(`
import json,secrets,uuid
from db import get_conn
from werkzeug.security import generate_password_hash
c=get_conn()
try:
 with c:
  with c.cursor() as q:
   members=[]
   for i in range(2):
    email='bank-browser-'+uuid.uuid4().hex+'@example.invalid';password=secrets.token_urlsafe(24)
    q.execute("INSERT INTO users(email,name,password_hash) VALUES(%s,'멤버십 자동검증',%s) RETURNING id",[email,generate_password_hash(password)])
    members.append(dict(id=q.fetchone()['id'],email=email,password=password))
   email='bank-staff-'+uuid.uuid4().hex+'@example.invalid';password=secrets.token_urlsafe(24)
   q.execute("INSERT INTO admin_users(email,password_hash,name,role) VALUES(%s,%s,'멤버십 자동검증','admin') RETURNING id",[email,generate_password_hash(password)])
   staff=dict(id=q.fetchone()['id'],email=email,password=password)
   q.execute("SELECT id FROM master_buildings WHERE lodging_type='생활' AND units>0 ORDER BY id LIMIT 1")
   building=q.fetchone()['id']
 print(json.dumps(dict(members=members,staff=staff,building=building)))
finally:c.close()
`));
  const browser=await chromium.launch({executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),args:["--no-sandbox"]});
  const contexts=[];
  try{
    const adminCtx=await browser.newContext({viewport:{width:1280,height:900},ignoreHTTPSErrors:true,userAgent:agent});
    contexts.push(adminCtx);
    const admin=await adminCtx.newPage();
    const adminErrors=[];admin.on("pageerror",e=>adminErrors.push(e.message));
    await admin.goto(base+"/admin/login");
    await admin.fill("#adminEmail",fixtures.staff.email);
    await admin.fill("#adminPassword",fixtures.staff.password);
    await admin.click('button[type="submit"]');
    await admin.waitForURL(/\/admin$/);
    await admin.click('[data-menu="admin-membership"]');
    await admin.locator("#amStatus").waitFor();
    for(const [index,width] of [1280,390].entries()){
      const context=await browser.newContext({viewport:{width,height:900},ignoreHTTPSErrors:true,userAgent:agent});
      contexts.push(context);
      const page=await context.newPage();
      const errors=[];page.on("pageerror",e=>errors.push(e.message));
      page.on("dialog",d=>d.accept());
      await page.goto(base+"/membership");
      await page.click("[data-login]");
      await page.fill("#authEmail",fixtures.members[index].email);
      await page.fill("#authPassword",fixtures.members[index].password);
      await page.click("#authSubmit");
      await page.locator("#memberDepositor").waitFor();
      const me=async()=>json(await page.request.get(base+"/api/membership/me"));
      assert.equal((await me()).status,"inactive");
      await page.fill("#memberDepositor","멤버십 자동검증");
      await page.check('[name="agree_terms"]');
      await page.click("#membershipPayForm button[type=submit]");
      await page.locator("[data-cancel-payment]").waitFor();
      assert.equal((await me()).status,"inactive");
      assert.ok(await page.locator(".bank-box").isVisible());
      // Cancellation has no financial refund side effect and cannot activate.
      await page.click("[data-cancel-payment]");
      await page.locator("#memberDepositor").waitFor();
      await page.fill("#memberDepositor","멤버십 자동검증");
      await page.check('[name="agree_terms"]');
      await page.click("#membershipPayForm button[type=submit]");
      await page.locator("[data-cancel-payment]").waitFor();
      const pending=(await me()).payments.find(p=>p.status==="pending");
      assert.ok(pending);
      await admin.click("#amReload");
      const approve=admin.locator(`[data-payment-action="approved"][data-id="${pending.id}"]`);
      await approve.waitFor();
      admin.once("dialog",d=>d.accept());
      await approve.click();
      await approve.waitFor({state:"detached"});
      await page.reload();
      await page.locator(".member-state").filter({hasText:"이용 중"}).first().waitFor();
      assert.equal((await me()).remaining,1);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.goto(base+`/?building=${fixtures.building}`);
      await page.locator("#bTabOperations").waitFor({state:"visible"});
      await page.click("#bTabOperations");
      const requestButton=page.locator("[data-building-membership-check],[data-membership-building-check]");
      await requestButton.waitFor({state:"visible"});
      const detail=await json(await page.request.get(base+`/api/building/${fixtures.building}`));
      assert.equal(detail.membership_access.required,false);
      if(detail.operating_records.length)assert.ok(await page.locator("#bApprovedRosterOperatingBody dl").count()>0);
      await requestButton.click();
      await page.locator("#memberCheckForm").waitFor();
      await page.locator('#memberCheckForm textarea').fill("서류·전화 확인 요청 / 자동검증");
      await page.locator('#memberCheckForm [name="agree_terms"]').check();
      assert.ok(await page.locator(".membership-dialog").evaluate(n=>getComputedStyle(n).position!=="static"||n.closest(".membership-dialog-backdrop")&&getComputedStyle(n.closest(".membership-dialog-backdrop")).position==="fixed"));
      await page.locator("#memberCheckForm button[type=submit]").click();
      await page.locator(".membership-dialog-backdrop").waitFor({state:"detached"});
      const current=await me();
      assert.equal(current.remaining,0);
      const check=current.checks[0];
      assert.equal(check.building_id,fixtures.building);
      await admin.click("#amReload");
      await admin.locator(`[data-check-id="${check.id}"]`).click();
      await admin.locator('#amCheckForm textarea[name="report"]').fill("자동검증 보고서: 자료 및 응답 부재로 두 항목 미확인");
      await admin.locator('#amCheckForm [name="business_report"]').selectOption("ok");
      await admin.locator('#amCheckForm [name="status"]').selectOption("reported");
      const saved=admin.waitForResponse(r=>r.url().endsWith(`/api/admin/membership/checks/${check.id}/status`)&&r.request().method()==="POST");
      await admin.locator("#amCheckForm button[type=submit]").click();
      assert.equal((await saved).status(),200);
      await page.goto(base+"/membership");
      await page.getByText("자동검증 보고서:",{exact:false}).waitFor();
      assert.equal(await page.locator(".member-result").filter({hasText:"미확인"}).count(),2);
      const auctionList=await json(await page.request.get(base+"/api/auctions?page_size=10"));
      assert.ok(auctionList.items.length,"Live auction is needed to verify the paid information zone");
      await page.goto(base+`/?auction=${auctionList.items[0].id}&tab=auction`);
      await page.locator("#bTabAuctions").waitFor({state:"visible"});
      await page.locator("#bTabAuctions").click();
      const paidZone=page.locator("#bAuctionPanel .auction-membership-zone");
      await paidZone.waitFor({state:"visible"});
      assert.equal(await paidZone.count(),1);
      assert.equal(await paidZone.locator(".b-membership-mask").count(),0);
      assert.ok(await paidZone.locator(".survey-source-facts").isVisible());
      assert.ok(await paidZone.locator("[data-open-auction-survey]").isVisible());
      assert.equal(await page.locator("#bAuctionPanel .survey-membership-notice").count(),0);
      await page.goto(base+"/membership");
      await page.locator("#memberDepositor").waitFor();
      // Early renewal extends a future paid period; it does not reset this one.
      await page.fill("#memberDepositor","멤버십 자동검증");
      await page.check('[name="agree_terms"]');
      await page.click("#membershipPayForm button[type=submit]");
      await page.locator("[data-cancel-payment]").waitFor();
      const renewal=(await me()).payments.find(p=>p.status==="pending");
      await admin.click("#amReload");
      const renewApprove=admin.locator(`[data-payment-action="approved"][data-id="${renewal.id}"]`);
      await renewApprove.waitFor();
      admin.once("dialog",d=>d.accept());
      await renewApprove.click();
      await renewApprove.waitFor({state:"detached"});
      const renewed=await me();
      assert.equal(renewed.remaining,0);
      assert.ok(new Date(renewed.paid_through)>new Date(renewed.period.ends_at));
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      assert.deepEqual(errors,[]);
      console.log(`PASS ${width}px real login, immutable bank receipt, cancel, manual staff approval, official-record gate, bundled check, report with unconfirmed items, early renewal and no overflow`);
    }
    assert.deepEqual(adminErrors,[]);
  }finally{
    for(const context of contexts)await context.close();
    await browser.close();
    const users=fixtures.members.map(m=>m.id);
    python(`
from db import get_conn
c=get_conn()
try:
 with c:
  with c.cursor() as q:
   ids=${JSON.stringify(users)}
   q.execute("DELETE FROM membership_history WHERE payment_id IN (SELECT id FROM membership_payments WHERE user_id=ANY(%s)) OR check_id IN (SELECT id FROM membership_checks WHERE user_id=ANY(%s))",[ids,ids])
   q.execute("DELETE FROM membership_checks WHERE user_id=ANY(%s)",[ids])
   q.execute("DELETE FROM membership_periods WHERE user_id=ANY(%s)",[ids])
   q.execute("DELETE FROM membership_payments WHERE user_id=ANY(%s)",[ids])
   q.execute("DELETE FROM users WHERE id=ANY(%s)",[ids])
   q.execute("DELETE FROM admin_users WHERE id=%s",[${fixtures.staff.id}])
finally:c.close()
`);
  }
})().catch(error=>{console.error(error);process.exitCode=1});