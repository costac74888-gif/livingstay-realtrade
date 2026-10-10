const assert=require("node:assert/strict");
const Controller=require("../hs2_supermap/web/controller.js");
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
let results=[],details=[],errors=[],searches=[],lookups=[];
const c=new Controller({
 fetchSearch:(params,signal)=>{const d=deferred();searches.push({params,signal,...d});return d.promise;},
 fetchDetail:(layer,id,params,signal)=>{const d=deferred();lookups.push({layer,id,params,signal,...d});return d.promise;},
 onResults:r=>results.push(r),onDetail:r=>details.push(r),onError:e=>errors.push(e.message)
});
const data=layers=>({ok:true,items:layers.flatMap(layer=>[{layer,public_id:"42"},{layer,public_id:"43"}]),markers:layers.map(layer=>({layer,ids:["42","43"]})),counts:{}});
async function main(){
 let count=0;const ok=(v)=>{assert.ok(v);count++;};
 ok(c.query().layers==="stay");
 const first=c.search({q:"old"}),second=c.search({q:"new"});
 searches[1].resolve(data(["stay"]));await second;
 searches[0].resolve(data(["stay"]));await first;
 ok(c.params.q==="new"&&results.at(-1).items.length===2);
 ok(searches[0].signal.aborted);
 for(const layer of ["sale","business","auction"]){
  const p=c.toggle(layer,true);searches.at(-1).resolve(data([...c.layers]));await p;
 }
 ok(c.layers.size===4&&c.result.markers.length===4);
 const sale=c.select("sale","42"),auction=c.select("auction","42");
 lookups.at(-1).resolve({ok:true,item:{layer:"auction",public_id:"42"}});await auction;
 lookups.at(-2).resolve({ok:true,item:{layer:"sale",public_id:"42"}});await sale;
 ok(details.at(-1).layer==="auction");
 ok(c.layers.size===4&&c.result.markers.length===4);
 const late=c.select("business","43");const off=c.toggle("business",false);
 searches.at(-1).resolve(data(["stay","sale","auction"]));await off;
 lookups.at(-1).resolve({ok:true,item:{layer:"business",public_id:"43"}});await late;
 ok(!c.layers.has("business")&&c.layers.size===3&&details.at(-1)===null);
 const b1=c.bounds([33,124,38,130]),b2=c.bounds([34,125,39,131]);
 searches.at(-1).resolve(data([...c.layers]));await b2;
 searches.at(-2).resolve(data(["stay","sale","business","auction"]));await b1;
 ok(c.params.bounds==="34,125,39,131"&&c.result.markers.length===3);
 const mismatch=c.select("sale","42");lookups.at(-1).resolve({ok:true,item:{layer:"auction",public_id:"42"}});await mismatch;
 ok(c.selection===null&&errors.at(-1)==="DETAIL_IDENTITY_MISMATCH");
 const restored=c.restore({params:{q:"restore"},layers:["stay","auction"],selection:{layer:"auction",id:"43"}});
 searches.at(-1).resolve(data(["stay","auction"]));
 await new Promise(r=>setImmediate(r));
 lookups.at(-1).resolve({ok:true,item:{layer:"auction",public_id:"43"}});await restored;
 ok(c.layers.size===2&&c.selection.id==="43"&&details.at(-1).layer==="auction");
 const pending=c.search({q:"clear"});searches.at(-1).resolve(data(["stay","auction"]));await pending;
 ok(c.selection===null&&details.at(-1)===null);
 const failure=c.search({q:"failure"});searches.at(-1).resolve({ok:false,code:"SOURCE_FAIL"});await failure;
 ok(c.result===null&&errors.at(-1)==="SOURCE_FAIL");
 console.log(`HS2_CONTROLLER_PASS ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
