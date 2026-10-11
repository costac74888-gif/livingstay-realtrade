/* Owned Preview only; public map reads, synthetic registration, no real PG. */
const {chromium}=require("playwright");
const assert=require("node:assert/strict"),fs=require("node:fs");
const origin="https://"+process.env.REPLIT_DEV_DOMAIN;
const out="generated-artifacts/seongsu-preview";
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox"]});
 const page=await browser.newPage({viewport:{width:1440,height:1000},userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36"});
 const errors=[];page.on("pageerror",e=>errors.push(e.message));
 const get=async path=>page.evaluate(async path=>{const r=await fetch(path);if(!r.ok)throw new Error(path+":"+r.status);return r.json()},path);
 try {
  await page.goto(origin+"/hs2/consumer");
  const status=await get("/__development__/status");assert.equal(status.database,"owned_ephemeral");assert.equal(status.actual_toss,false);
  await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready);
  await page.locator("#roadviewTool").click();
  await page.evaluate(()=>kakao.maps.event.trigger(HS2PreviewMap.map(),"click",{latLng:new kakao.maps.LatLng(37.5444,127.056)}));
  await page.waitForTimeout(6000);
  const roadview=await page.evaluate(()=>({open:HS2LegacyMapTools.state().roadviewOpen,
   images:[...document.querySelectorAll("#roadview img")].filter(i=>i.naturalWidth>0).length,
   canvas:document.querySelectorAll("#roadview canvas").length,status:document.querySelector("#statusMessage").textContent}));
  await page.screenshot({path:out+"/roadview-proof.png"});
  const catalog=await get("/__development__/seongsu/catalog"),id=catalog.items[0].public_id;
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:width===390?874:1000});
   await page.goto(origin+"/hs2/details/?public_id="+id);
   await page.waitForFunction(()=>document.querySelector("#detail-content")?.hidden===false);
   await page.waitForFunction(()=>window.HS2DetailMap?.ready);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   assert(await page.locator(".demo-gallery img").count()>0);
   await page.evaluate(()=>document.fonts.ready);
   await page.screenshot({path:out+`/reference-detail-${width}.png`,fullPage:true});
   await page.goto(origin+"/hs2/dashboard/");
   await page.waitForFunction(()=>document.querySelector("#dashboard-feedback")?.dataset.state==="ready");
   assert.equal(await page.locator(".preview-sidebar").count(),1);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:out+`/reference-dashboard-${width}.png`,fullPage:true});
  }
  await page.goto(origin+"/hs2/listings/?new=1");
  await page.goto(origin+"/__development__/seongsu/admin-role");
  assert.equal(await page.locator("#demo-role-start").isDisabled(),true);
  await page.locator("#demo-role-ack").check();
  await Promise.all([page.waitForURL("**/hs2/listings/admin"),page.locator("#demo-role-start").click()]);
  const registration=await page.evaluate(async()=>{
   const req=async(path,method="GET",body,csrf)=>{
    const r=await fetch("/hs2/listings/"+path,{method,
     headers:{"X-HS2-CSRF":csrf||"",...(body instanceof FormData?{}:{"Content-Type":"application/json"})},
     ...(body===undefined?{}:{body:body instanceof FormData?body:JSON.stringify(body)})});
    const data=await r.json();if(!r.ok)throw new Error(path+":"+r.status+":"+data.code);return data;
   };
   const meta=await req("meta"),csrf=meta.csrf;
   const photo=new FormData();
   photo.append("file",await (await fetch("/__development__/seongsu/assets/interior-1.jpg")).blob(),"synthetic-interior.jpg");
   const uploaded=await req("photos","POST",photo,csrf);
   const created=await req("applications","POST",{workflow_id:meta.references[0].workflow_id,
    payload:{title:"[가상] 통합 검증 등록",space_label:"TEST-"+Date.now(),space_scope:"unit",
     stay_kind:"lodging",rooms:1,area_m2:"25",guests:2,options:["wifi"],nightly:80000,weekly:null,monthly:null,min_stay:1,
     instant:false,discount:false,photos:[uploaded.id],responsibility:true,public_summary:false,disclosure:"limited"}},csrf);
   const submitted=await req("applications/"+created.item.id+"/submit","POST",{revision:created.item.revision},csrf);
   const admin=await req("admin/meta");
   const approved=await req("admin/applications/"+created.item.id+"/review","POST",{
    revision:submitted.item.revision,decision:"approve",note:"격리 가상 등록 검증",rights:true,disclosure:true},admin.csrf);
   return {draft:created.item.status,submitted:submitted.item.status,approved:approved.item.status,public_id:approved.item.public_id};
  });
  assert.equal(registration.draft,"draft");assert.equal(registration.submitted,"submitted");assert.equal(registration.approved,"approved");
  const after=await get("/__development__/seongsu/catalog");
  assert(after.items.some(r=>r.public_id===registration.public_id&&r.calendar_setup_required&&r.synthetic));
  const result=await get("/hs2/search/api/results?layers=stay");
  assert(result.items.some(r=>r.public_id===registration.public_id&&r.preview_demo.synthetic));
  await page.goto(origin+"/__development__/legacy-capabilities/");
  const matrix=await get("/__development__/legacy-capabilities.json");
  assert.equal(matrix.overall,"INCOMPLETE");assert(matrix.items.every(r=>r.source_exists));
  assert.equal(matrix.production_accounts_connected,false);
  assert.deepEqual(errors,[]);
  const report={ok:true,registration:{draft:"draft",submitted:"submitted",approved:"approved",new_public_listing_visible:true},
   miniature_map:"real_sdk_fictional_position",desktop_mobile_detail_dashboard:"PASS",roadview,
    matrix:"source_retained_is_not_integration",actual_toss:false,production_writes:false,
    private_production_data:false,public_facility_source:status.public_facility_snapshot.source,errors};
  fs.writeFileSync(out+"/completion-checks.json",JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
