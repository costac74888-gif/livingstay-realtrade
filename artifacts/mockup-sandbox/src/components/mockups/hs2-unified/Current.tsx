import snapshot from "./_baseline/current-rendered.html?raw";
export function Current() {
  return <div style={{height:"100vh",background:"white"}}>
    <div style={{height:40,display:"flex",alignItems:"center",padding:"0 16px",fontSize:16,color:"black",background:"#eff0e8"}}>
      기존 개발화면 · 원본 DOM 추출 · 비교용 / 조작 불가
    </div>
    <iframe title="기존 개발화면 원본 추출" srcDoc={snapshot} sandbox="" style={{border:0,width:"100%",height:"calc(100% - 40px)",pointerEvents:"none"}} />
  </div>;
}
