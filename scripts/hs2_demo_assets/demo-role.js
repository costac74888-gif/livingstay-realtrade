(() => {
 "use strict";
 const ack=document.getElementById("demo-role-ack"),button=document.getElementById("demo-role-start");
 if(!ack||!button)return;
 ack.addEventListener("change",()=>button.disabled=!ack.checked);
 button.addEventListener("click",async()=>{
  if(!ack.checked)return;
  button.disabled=true;
  try{
   const r=await fetch("/__development__/seongsu/admin-role",{method:"POST",
    headers:{"Content-Type":"application/json","X-CSRF-Token":"isolated-consumer-csrf-not-real-session"},
    body:JSON.stringify({acknowledged_mock_admin:true})});
   const data=await r.json();if(!r.ok||!data.ok||data.actual_auth!==false)throw new Error();
   location.assign("/hs2/listings/admin");
  }catch(_){document.getElementById("demo-role-status").textContent="가상 역할 선택 실패. 운영 권한으로 대체하지 않습니다.";button.disabled=!ack.checked;}
 });
})();
