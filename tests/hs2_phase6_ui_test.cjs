const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const origin=process.env.HS2_FIXTURE_ORIGIN;
const png=Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=","base64");
async function browserJson(page,path,body){
  return page.evaluate(async({path,body})=>{
    const response=await fetch(path,body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:undefined);
    if(!response.ok)throw Error("Owned browser fixture request "+response.status);
    return response.json();
  },{path,body});
}
async function run(){
  assert(/^http:\/\/127\.0\.0\.1:\d+$/.test(origin));
  const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM,
    args:["--no-sandbox","--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"]});
  let checks=0;
  try{
    for(const width of [1280,390]){
      const context=await browser.newContext({viewport:{width,height:1100}});
      const page=await context.newPage(),errors=[],external=[];
      page.on("pageerror",e=>errors.push(e.message));
      await page.route("**/*",r=>{
        const u=new URL(r.request().url());
        if(u.origin!==origin){external.push(u.origin);return r.abort();}
        if(!u.pathname.startsWith("/hs2/"))return r.abort();
        return r.continue();
      });
      await page.goto(origin+"/hs2/listings/");
      await page.waitForFunction(()=>document.querySelector("#workflowSelect").options.length>1);
      await page.waitForLoadState("networkidle");
      await page.locator("#newApplication").click();
      await page.locator("#workflowSelect").selectOption({index:1});
      await page.locator("#title").fill("<script>PRIVATE_TITLE</script>");
      await page.locator("#space_label").fill("UI-"+width);
      await page.locator("#stay_kind").selectOption("lodging");
      await page.locator("#rooms").fill("0");
      await page.locator("#area_m2").fill("21.5");
      await page.locator("#guests").fill("2");
      await page.locator("#min_stay").fill("1");
      await page.locator("#nightly").fill("120000");
      await page.locator("#responsibility").check();
      await page.locator("#photoFiles").setInputFiles({name:"private.png",mimeType:"image/png",buffer:png});
      await page.waitForFunction(()=>document.querySelectorAll("#photoGrid img").length===1);
      const saved=page.waitForResponse(r=>r.request().method()==="POST"&&r.url().endsWith("/applications")&&r.status()===201);
      await page.locator("#saveButton").click();
      const row=(await(await saved).json()).item;
      await page.waitForFunction(()=>!document.querySelector("#saveButton").disabled);
      assert.equal(row.payload.title,"<script>PRIVATE_TITLE</script>");
      assert.equal(row.status,"draft");checks+=2;
      await page.reload();
      await page.waitForFunction(()=>document.querySelector("#title").value.includes("PRIVATE_TITLE"));
      assert.equal(await page.locator("#space_label").inputValue(),"UI-"+width);checks++;
      const submit=page.waitForResponse(r=>r.url().endsWith("/submit")&&r.status()===200);
      await page.locator("#submitButton").click();
      assert.equal((await(await submit).json()).item.status,"submitted");checks++;
      let pub=await browserJson(page,"/hs2/listings-fixture/public");
      assert(!pub.items.some(i=>i.public_id===row.public_id));checks++;
      await browserJson(page,"/hs2/listings-fixture/identity",{admin:true});
      const admin=await context.newPage();
      admin.on("pageerror",e=>errors.push(e.message));
      await admin.goto(origin+"/hs2/listings/admin");
      await admin.waitForFunction(()=>document.querySelectorAll("#reviewList button").length>0);
      await admin.locator("#reviewList button").filter({hasText:"PRIVATE_TITLE"}).first().click();
      await admin.locator("#reviewNoteInput").fill("등록권한·공개정보 확인 (격리 검증)");
      await admin.locator("#reviewRights").check();
      await admin.locator("#reviewDisclosure").check();
      const approved=admin.waitForResponse(r=>r.url().endsWith("/review")&&r.status()===200);
      await admin.getByRole("button",{name:/승인/}).last().click();
      const published=(await(await approved).json()).item;
      assert.equal(published.status,"approved");checks++;
      pub=await browserJson(page,"/hs2/listings-fixture/public");
      assert(pub.items.some(i=>i.public_id===published.public_id));
      assert(!JSON.stringify(pub).includes("PRIVATE_TITLE"));checks+=2;
      await page.reload();
      await page.waitForFunction(()=>document.querySelector("#title").value.includes("PRIVATE_TITLE"));
      await page.locator("#nightly").fill("130000");
      const edited=page.waitForResponse(r=>r.request().method()==="PUT"&&r.status()===200);
      await page.locator("#saveButton").click();
      const editrow=(await(await edited).json()).item;
      assert.equal(editrow.status,"draft");assert(editrow.revision>row.revision);checks+=2;
      pub=await browserJson(page,"/hs2/listings-fixture/public");
      assert(!pub.items.some(i=>i.public_id===published.public_id));checks++;
      page.once("dialog",d=>d.accept());
      const withdrawn=page.waitForResponse(r=>r.request().method()==="DELETE"&&r.status()===200);
      await page.locator("#withdrawButton").click();
      assert.equal((await(await withdrawn).json()).item.status,"withdrawn");checks++;
      await page.waitForFunction(()=>document.querySelector("#submitButton").disabled);
      assert(await page.locator("#saveButton").isDisabled());
      assert((await page.evaluate(()=>document.documentElement.scrollWidth))<=width);
      assert.deepEqual(errors,[]);assert.deepEqual(external,[]);checks+=4;
      await context.close();
    }
  }finally{await browser.close();}
  console.log(`HS2_UI_PASS phase6 ${checks} assertions; actual owned PostgreSQL HTTP persistence, upload, submission, admin publication, edit unpublish and terminal withdrawal.`);
}
run().catch(e=>{console.error(e.stack);process.exitCode=1;});
