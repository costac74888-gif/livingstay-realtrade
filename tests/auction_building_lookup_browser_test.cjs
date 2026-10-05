/* Visitor click/poll/navigation tests with intercepted API; no collection or writes. */
const {chromium}=require("playwright");
const {execFileSync}=require("node:child_process");
const assert=require("node:assert/strict");

async function main(){
  const browser=await chromium.launch({
    executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),
    args:["--no-sandbox"]
  });
  const origin=process.env.TEST_BASE_URL||`https://${process.env.REPLIT_DEV_DOMAIN}`;
  try{
    for(const width of [390,1280]){
      const page=await browser.newPage({
        viewport:{width,height:900},ignoreHTTPSErrors:true,locale:"ko-KR",
        userAgent:"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
      });
      const errors=[];page.on("pageerror",error=>errors.push(error.message));
      const item={id:987654321,source:"onbid",source_item_id:"browser-fixture",
        title:"우선 조회 검증숙박 B동 407호",address_jibun:"인천광역시 서구 석남동 511-16",
        address_road:null,master_building_id:null,lodging_category:"생활",usage_name:"생활숙박시설",
        status:"bidding",area_m2:26.12,min_bid_price:50000000,management_no:"검증전용",round_no:1};
      let linked=false,methodCalls=[],mode="running",allowLink=false;
      await page.route("**/api/auctions/987654321",route=>route.fulfill({
        json:{ok:true,item:{...item,master_building_id:linked?77777777:null},
          building:linked?{id:77777777,building_name:"대장 확인 숙박"}:null,
          photos:[],rounds:[]}
      }));
      await page.route("**/api/auctions/987654321/survey-info",route=>route.fulfill({
        json:{ok:true,membership_access:{required:true,info_url:"/membership"}}
      }));
      await page.route("**/api/auctions/987654321/building-lookup",async route=>{
        methodCalls.push(route.request().method());
        const state=mode==="running"?(route.request().method()==="GET"&&allowLink?"done":"running"):mode;
        if(state==="done")linked=true;
        await route.fulfill({json:{ok:true,lookup:{state,building_id:linked?77777777:null,
          message:state==="running"?"건축물대장을 우선 조회 중입니다.":state==="done"?"확인 완료":
            state==="failed"?"건축물대장 조회에 실패했습니다.":"주소 후보가 여러 개입니다."}}});
      });
      const building={building_id:77777777,id:77777777,building_name:"대장 확인 숙박",
        lodging_type:"생활",road_address:"인천광역시 서구 검증로 1",
        jibun_address:item.address_jibun,umd_nm:"석남동",sgg_text:"인천광역시 서구",
        units:50,tot_area:1200,area_m2:26.12,detail_fetched_at:"2026-10-05",
        photos:[],agents:[],operators:[],loan_consultants:[],operating_records:[],
        membership_access:{required:true,info_url:"/membership"}};
      await page.route("**/api/building/77777777",route=>route.fulfill({json:building}));
      await page.route("**/api/building/77777777/**",async route=>{
        const history=route.request().url().split("?")[0].endsWith("/auctions");
        if(history)await new Promise(resolve=>setTimeout(resolve,1500));
        await route.fulfill({
          json:{ok:true,items:history?[]:[{...item,master_building_id:77777777}],photos:[],count:0,records:[]}
        });
      });
      await page.goto(origin+"/?auction=987654321");
      await page.locator("#auctionBuildingLookupStatus").waitFor();
      await page.locator("#bTabProperty").click();
      allowLink=true;
      await page.waitForFunction(()=>window.__openBuildingId===77777777);
      await page.locator("#bTabAuctions").waitFor({state:"visible",timeout:1000});
      await page.locator("#bTabProperty[aria-selected=true]").waitFor();
      await page.waitForFunction(()=>document.getElementById("bPropertyPanel")?.textContent.includes("대장 확인 숙박"));
      assert.equal(methodCalls.filter(m=>m==="POST").length,1);
      assert.ok(methodCalls.some(m=>m==="GET"));
      assert.ok(new URL(page.url()).searchParams.get("building")==="77777777");
      const token=await page.evaluate(()=>_buildingDetailRequestToken);
      await page.evaluate(()=>window.dispatchEvent(new CustomEvent("livingstay:auth",{detail:{loggedIn:false}})));
      await page.waitForFunction(previous=>_buildingDetailRequestToken>previous,token);
      await page.locator("#bTabAuctions").waitFor({state:"visible"});
      await page.locator("#bTabProperty[aria-selected=true]").waitFor();
      await page.waitForTimeout(1800);
      assert.ok(await page.locator("#bTabAuctions").isVisible(),"Empty later history must not hide confirmed selection");
      assert.equal(await page.locator("#bTabProperty").getAttribute("aria-selected"),"true");
      console.log(`PASS ${width}px: POST→poll→linked detail, selected tab and URL preserved`);

      // Terminal failure is not "no records"; explicit retry stays inside current panel.
      linked=false;mode="failed";methodCalls=[];
      await page.evaluate(id=>window.openAuctionDetail(id),item.id);
      await page.locator("#auctionBuildingLookupStatus button").waitFor();
      assert.ok((await page.locator("#auctionBuildingLookupStatus").textContent()).includes("실패"));
      await page.locator("#auctionBuildingLookupStatus button").click();
      await page.waitForFunction(()=>document.querySelector("#auctionBuildingLookupStatus button"));
      assert.deepEqual(methodCalls,["POST","POST"]);

      linked=false;mode="running";methodCalls=[];
      await page.evaluate(id=>window.openAuctionDetail(id),item.id);
      await page.waitForFunction(()=>document.querySelector("#auctionBuildingLookupStatus")?.textContent.includes("조회 중"));
      await page.evaluate(()=>restoreDefaultPanel());
      await page.waitForTimeout(2300);
      assert.deepEqual(methodCalls,["POST"],"Leaving panel must stop status polling");
      assert.equal(await page.evaluate(()=>window.__openBuildingId),null);
      assert.deepEqual(errors,[]);
      console.log(`PASS ${width}px: failure/retry and stale-navigation polling cancellation`);
      await page.close();
    }
  }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
