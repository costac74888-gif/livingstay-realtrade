const test=require("node:test"),assert=require("node:assert/strict");
const ui=require("../scripts/hs2_demo_assets/preview-rate-date.js");
test("strict base display, missing versus real zero",()=>{
 assert.equal(ui.basePresentation("lodging",{night:0}).headline,"1박 0원");
 assert.equal(ui.basePresentation("lodging",null).headline,"기준 요금 비공개");
 for(const v of [true,"123",1.5,-1,1e9+1]){
  assert.equal(ui.basePresentation("lodging",{night:v}).headline,"기준 요금 비공개");
  assert.equal(ui.basePresentation("non_lodging",{week:1,month:v}).headline,"기준 요금 비공개");
 }
 assert.equal(ui.basePresentation("lodging",{night:1,week:2}).headline,"기준 요금 비공개");
 assert.equal(ui.basePresentation("non_lodging",{month:1000,week:null}).headline,"1개월 1,000원");
});
test("chosen period total is not a multiplied base or fake N weeks",()=>{
 const quote={total_krw:123456,check_in:"2027-01-01",check_out:"2027-01-11"};
 assert.equal(ui.basePresentation("non_lodging",{week:300000,month:1000000},quote,
  quote.check_in,quote.check_out).quote.text,"선택 10일 총 123,456원");
 assert.equal(ui.basePresentation("non_lodging",null,quote,
  quote.check_in,quote.check_out).headline,"기준 요금 비공개");
 assert.equal(ui.basePresentation("lodging",{night:178000},null).quote,null);
});
test("anniversary clamp, leap years, no 30 day conversion",()=>{
 assert.equal(ui.addMonthsClamped("2027-01-31",1),"2027-02-28");
 assert.equal(ui.addMonthsClamped("2028-01-31",1),"2028-02-29");
 assert.equal(ui.addMonthsClamped("2027-01-31",3),"2027-04-30");
 assert.equal(ui.addMonthsClamped("2027-01-31",2),"2027-03-31");
 assert.equal(ui.checkoutFor("2027-01-31",{days:28}),"2027-02-28");
 assert.equal(ui.checkoutFor("2027-01-31",{months:1}),"2027-02-28");
 assert.equal(ui.quickPeriods("lodging").map(x=>x.label).join("/"),"1박/2박/7박");
 assert.equal(ui.quickPeriods("non_lodging").map(x=>x.label).join("/"),"1주/2주/4주/1개월/3개월");
});
test("warning bounds do not confuse missing, zero division or invalid",()=>{
 assert.equal(ui.rateWarnings("lodging",0,null).length,1);
 assert.equal(ui.rateWarnings("non_lodging",100,200).length,0);
 assert.equal(ui.rateWarnings("non_lodging",100,500).length,0);
 assert.equal(ui.rateWarnings("non_lodging",100,199).length,1);
 assert.equal(ui.rateWarnings("non_lodging",100,501).length,1);
 assert.equal(ui.rateWarnings("non_lodging",0,500).length,1);
 for(const v of [null,true,"0",1.5,-1,1e9+1]){
  assert.equal(ui.rateWarnings("non_lodging",v,500).length,0);
  assert.equal(ui.rateWarnings("non_lodging",100,v).length,0);
 }
});
