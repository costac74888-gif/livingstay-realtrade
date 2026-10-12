import { useState, type FormEvent } from 'react';
import { ClipboardCheck, FilePlus2, ShieldCheck } from 'lucide-react';
import './_group.css';
import { Header, LocalDialog } from './_shared';

type QueueTab = '등록 신청'|'매물 검토'|'콘텐츠';
type QueueRow = { id: string; title: string; kind: string; detail: string; received: string; status: string };
const initialQueue: Record<QueueTab, QueueRow[]> = {
  '등록 신청': [
    {id:'q1',title:'스테이 모노 성수',kind:'숙박시설 등록',detail:'공개 범위와 시설 안내 문구 검토 요청',received:'2026. 10. 11.',status:'검토 대기'},
    {id:'q2',title:'햇살이 머무는 성수 빌라',kind:'주거형 단기임대',detail:'이용 조건과 사진 사용 범위 확인',received:'2026. 10. 10.',status:'검토 대기'},
    {id:'q3',title:'온기 스테이 서울숲',kind:'숙박시설 등록',detail:'시설 정보 보완 요청이 반영된 시안 항목',received:'2026. 10. 9.',status:'보완 검토'},
  ],
  '매물 검토': [
    {id:'q4',title:'성수동 골목 상가 1층',kind:'매매',detail:'가격 표현 및 위치 공개 기준 확인',received:'2026. 10. 11.',status:'검토 대기'},
    {id:'q5',title:'서울숲길 카페 운영권',kind:'영업권',detail:'영업권 안내와 포함 항목 확인',received:'2026. 10. 8.',status:'검토 대기'},
  ],
  '콘텐츠': [
    {id:'q6',title:'가을 성수 산책 가이드',kind:'지역 콘텐츠',detail:'출처와 장소 표기 내용을 확인해 주세요.',received:'2026. 10. 10.',status:'검토 대기'},
    {id:'q7',title:'숙박 이용 안내 문구',kind:'안내 콘텐츠',detail:'고객에게 오해를 줄 수 있는 표현 검토',received:'2026. 10. 7.',status:'검토 대기'},
  ],
};
const queueTabs: QueueTab[] = ['등록 신청','매물 검토','콘텐츠'];

export function Admin() {
  const [tab, setTab] = useState<QueueTab>('등록 신청');
  const [queue, setQueue] = useState(initialQueue);
  const [memo, setMemo] = useState('');
  const [action, setAction] = useState<{id:string; title:string; kind:string}|null>(null);
  const [nextStatus, setNextStatus] = useState('');
  const [recordTitle, setRecordTitle] = useState('');
  const [recordText, setRecordText] = useState('');
  const [records, setRecords] = useState<{title:string;text:string}[]>([]);
  const [notice, setNotice] = useState('');
  const rows = queue[tab];
  const askAction = (row: QueueRow, status: string) => {
    setAction({id:row.id,title:row.title,kind:row.kind});
    setNextStatus(status);
  };
  const applyAction = () => {
    if (!action) return;
    setQueue((old)=>({...old,[tab]:old[tab].map((row)=>row.id===action.id ? {...row,status:nextStatus} : row)}));
    setAction(null); setMemo('');
    setNotice('로컬 미리보기 큐에서만 상태가 바뀌었습니다. 실제 공개·승인 처리는 없습니다.');
  };
  const saveRecord = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!recordTitle.trim() || !recordText.trim()) return;
    setRecords((old)=>[{title:recordTitle.trim(),text:recordText.trim()},...old]);
    setRecordTitle(''); setRecordText('');
    setNotice('이 화면 안의 임시 기록 목록에 추가했습니다.');
  };
  return <div className="hs2 hs2-shell">
    <Header current="Admin"/>
    <main className="hs2-wrap hs2-admin-wrap">
      <div className="hs2-owner-hero"><div><p className="hs2-eyebrow">HOME &amp; STAY / REVIEW DESK</p><h1>살펴보고, 근거를 남깁니다</h1><p>검토 대기 항목을 구분하고, 시안 안에서만 상태를 바꿔볼 수 있습니다.</p></div><span className="hs2-admin-badge"><ShieldCheck size={19}/> 디자인 전용 화면</span></div>
      <div className="hs2-notice hs2-admin-note">합성 데이터·로컬 동작만 사용합니다. 여기서의 검토는 실제 승인, 공개, 고객 안내, 결제 또는 운영 조치를 하지 않습니다.</div>
      {notice && <div className="hs2-toast" role="status">{notice}<button onClick={()=>setNotice('')} aria-label="알림 닫기">×</button></div>}
      <div className="hs2-admin-columns">
        <div className="hs2-admin-main">
          <section className="hs2-panel">
            <div className="hs2-panel-head"><div><p className="hs2-eyebrow">REVIEW QUEUE / SAMPLE</p><h2>검토 대기함</h2></div><span className="hs2-chip">합성 항목 {rows.length}건</span></div>
            <div className="hs2-admin-tabs" role="tablist" aria-label="검토함 종류">{queueTabs.map((name)=><button key={name} role="tab" aria-selected={tab===name} onClick={()=>setTab(name)}>{name}<span>{queue[name].length}</span></button>)}</div>
            <div className="hs2-panel-body">
              {rows.map((row)=><article className="hs2-queue-item" key={row.id}>
                <div className="hs2-queue-copy"><div className="hs2-queue-kicker"><span className="hs2-chip">{row.kind}</span><span>{row.received}</span></div><h3>{row.title}</h3><p>{row.detail}</p><p className="hs2-queue-status">현재 상태 <strong>{row.status}</strong></p></div>
                <div className="hs2-queue-actions"><button className="hs2-small-action" onClick={()=>askAction(row,'보완 요청 시안')}>보완 요청</button><button className="hs2-small-action" onClick={()=>askAction(row,'검토 완료 시안')}>검토 완료</button></div>
              </article>)}
              {!rows.length && <div className="hs2-empty">현재 탭에는 합성 검토 항목이 없습니다.</div>}
            </div>
          </section>
          <section className="hs2-panel hs2-admin-record-panel">
            <div className="hs2-panel-head"><div><p className="hs2-eyebrow">REVIEW NOTES / LOCAL</p><h2>검토 기록 초안</h2></div><FilePlus2 size={20}/></div>
            <div className="hs2-panel-body">
              <form className="hs2-admin-record-form" onSubmit={saveRecord}>
                <label className="hs2-label">기록 제목<input className="hs2-input" required value={recordTitle} onChange={(e)=>setRecordTitle(e.target.value)} placeholder="예: 시설 소개 문구 검토"/></label>
                <label className="hs2-label">메모<textarea className="hs2-textarea" required value={recordText} onChange={(e)=>setRecordText(e.target.value)} placeholder="검토 기준과 확인할 사항을 기록합니다."/></label>
                <button className="hs2-btn" type="submit">시안 기록 추가</button>
              </form>
              <p className="hs2-record-label">현재 브라우저 화면에만 표시되는 기록</p>
              {records.map((record,index)=><article className="hs2-local-record" key={`${record.title}-${index}`}><ClipboardCheck size={18}/><div><strong>{record.title}</strong><p>{record.text}</p></div><button className="hs2-small-action" onClick={()=>setRecords((old)=>old.filter((_,i)=>i!==index))}>삭제</button></article>)}
              {!records.length && <div className="hs2-admin-empty">아직 추가한 시안 기록이 없습니다.</div>}
            </div>
          </section>
        </div>
        <aside className="hs2-admin-aside">
          <section className="hs2-side-note"><p className="hs2-eyebrow">SCOPE / SAMPLE ONLY</p><h3>기록과 실행은 다릅니다.</h3><p>이 화면에는 실제 고객, 신청 원장, 예약·금융 데이터가 없습니다. 표시된 항목은 검토 흐름을 살펴보기 위한 허구의 샘플입니다.</p></section>
          <section className="hs2-panel hs2-admin-boundaries"><div className="hs2-panel-head"><h2>시안의 경계</h2></div><div className="hs2-panel-body"><ul><li>큐 상태는 이 브라우저 화면 안에서만 바뀝니다.</li><li>콘텐츠 등록이나 공개로 이어지지 않습니다.</li><li>결제, 정산, 환불 및 송금 기능은 없습니다.</li><li>실제 계정 권한 또는 관리자 권한을 제공하지 않습니다.</li></ul></div></section>
          <div className="hs2-admin-mini"><span>전환한 화면</span><strong>검토 공간 미리보기</strong><span>검토 대상</span><strong>가상의 성수 지역 항목</strong></div>
        </aside>
      </div>
    </main>
    <footer className="hs2-footer">HOME &amp; STAY · 관리자 화면 디자인 미리보기 · 실제 운영 조치 없음</footer>
    <LocalDialog open={!!action} title={`${nextStatus} — 로컬 미리보기`} onClose={()=>setAction(null)} onConfirm={applyAction} confirmText="시안에만 반영" confirmDisabled={!memo.trim()}>
      <div className="hs2-dialog-note"><strong>{action?.title}</strong><p>{action?.kind} 항목의 로컬 상태만 바뀝니다. 실제 신청 승인, 공개, 보완 요청 전달은 일어나지 않습니다.</p>
        <label className="hs2-label">검토 근거 메모<textarea className="hs2-textarea" value={memo} onChange={(e)=>setMemo(e.target.value)} placeholder="시안 동작 확인용 메모"/></label></div>
    </LocalDialog>
  </div>;
}
export default Admin;
