import { useState, type ReactNode } from 'react';
import { ArrowRight, ChevronLeft, ChevronRight, ClipboardList, Plus, Trash2 } from 'lucide-react';
import type { Screen } from './_shared';
import { Field, LocalForm, LocalSubmit, Notice, PopoverScreen, SuiteFrame, screenHref, syntheticPlaces } from './_shared';
import { KakaoMap } from '../hs2-unified/_shared';

const facilities = [
  { id: 'F-024', name: '서울숲 라운지 하우스', area: '서울 성동구 · 성수동', type: '생활숙박시설', status: '운영 중', count: 7 },
  { id: 'F-031', name: '연무장 코너 스테이', area: '서울 성동구 · 성수동', type: '숙박시설', status: '정보 확인', count: 4 },
  { id: 'F-052', name: '성수 리버워크', area: '서울 성동구 · 성수동', type: '주거형 단기임대', status: '등록 검토', count: 3 },
];
const channelData: Record<string, { label: string; category: string; price?: string; status: string; count: number }[]> = {
  'listing-stay': [
    { label: '햇살이 머무는 성수 빌라', category: '주간 단기임대', price: '430,000원/주', status: '공개', count: 2 },
    { label: '매월의 성수 하우스', category: '월 단기임대', price: '1,680,000원/월', status: '초안', count: 1 },
  ],
  'listing-sale': [
    { label: '서울숲 가까운 코너 호실', category: '주거용 매매', price: '가격 미등록', status: '검토 중', count: 1 },
    { label: '성수 리버워크 8층', category: '건물 매매', price: '가격 미등록', status: '비공개', count: 4 },
  ],
  'listing-business': [
    { label: '연무장길 운영권 양도', category: '영업권', price: '조건 확인 필요', status: '초안', count: 2 },
    { label: '서울숲 스테이 운영 양도', category: '영업권', price: '가격 미등록', status: '검토 중', count: 3 },
  ],
  'listing-auction': [
    { label: '성수동 업무·숙박 복합 건물', category: '공매', price: '최저가 미등록', status: '조사 중', count: 1 },
    { label: '성수동 단독형 숙소', category: '공매', price: '조건 확인 필요', status: '공개 전', count: 0 },
  ],
};
const channels = [['O006','단기 임대','listing-stay'],['O007','매매','listing-sale'],['O008','영업권','listing-business'],['O009','공매','listing-auction']];
const facilityPlaces = facilities.map((facility, index) => ({
  ...syntheticPlaces[index],
  id: facility.id,
  title: facility.name,
  mapLabel: facility.name,
  layer: 'facility',
}));

function OpsTitle({ screen, subtitle, action }: { screen: Screen; subtitle?: string; action?: ReactNode }) {
  return <div className="hs-title-row"><div><p className="hs-kicker">{screen.role} · HOME &amp; STAY</p><h1>{screen.title}</h1>{subtitle && <p>{subtitle}</p>}</div>{action}</div>;
}
function OpsPage({ screen, children, subtitle, action }: { screen: Screen; children: ReactNode; subtitle?: string; action?: ReactNode }) {
  return <SuiteFrame screen={screen}><main className="hs-main"><OpsTitle screen={screen} subtitle={subtitle} action={action}/>{children}</main></SuiteFrame>;
}
function StatGrid({ values }: { values: [string,string,string,string][] }) {
  return <div className="hs-metric-grid">{values.map(([label,value,detail,status]) => <div className="hs-metric" key={label}><span>{label}</span><strong>{value}</strong><p>{detail}</p><small>{status}</small></div>)}</div>;
}
function DataTable({ headers, rows, actionId, actionLabel = '상세' }: { headers: string[]; rows: string[][]; actionId?: string; actionLabel?: string }) {
  return <div className="hs-table-wrap"><table className="hs-table"><thead><tr>{headers.map((h)=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={`${row[0]}-${i}`}>{row.map((cell,j)=><td key={`${cell}-${j}`}>{cell}</td>)}{actionId && <td><a href={screenHref(actionId)}>{actionLabel}</a></td>}</tr>)}</tbody></table></div>;
}
function ChannelTabs({ active }: { active: string }) {
  return <nav className="hs-tabs">{channels.map(([id,label])=><a className={active === id ? 'active' : ''} href={screenHref(id)} key={id}>{label}</a>)}</nav>;
}

function OwnerPage({ screen }: { screen: Screen }) {
  const [layer, setLayer] = useState<'facility'|'stay'|'sale'|'business'|'auction'>('facility');
  const [calendarIndex, setCalendarIndex] = useState(0);
  const [notice, setNotice] = useState('');
  const toast = (value: string) => { setNotice(value); window.setTimeout(() => setNotice(''),2300); };
  const formPage = (fields: ReactNode[], desc?: ReactNode, target?: string) => <OpsPage screen={screen} subtitle="필요한 정보를 입력하고 다음 단계를 확인합니다."><section className="hs-panel" style={{maxWidth:850}}>{desc}<LocalForm className="hs-form-grid">{fields}<LocalSubmit text="입력 내용 확인" target={target}/></LocalForm></section></OpsPage>;

  switch (screen.view) {
    case 'owner-guide': return <OpsPage screen={screen} subtitle="공간, 일정, 운영 정보를 한 흐름에서 살펴봅니다.">
      <div className="hs-panel" style={{background:'var(--hs-wash)',padding:36}}><p className="hs-kicker">OWNER WORKSPACE</p><h2 style={{fontSize:34}}>공간의 정보와 운영 일정을<br/>차분히 정리하세요.</h2><p>시설 정보를 확인하고 채널별 매물을 따로 관리할 수 있는 화면 구성입니다.</p><div className="hs-pills" style={{marginTop:24}}><a className="hs-btn" href={screenHref('O003')}>운영 현황 보기</a><a className="hs-btn secondary" href={screenHref('O002')}>시설 지도 보기</a><a className="hs-btn secondary" href={screenHref('O011')}>새 공간 등록</a></div></div>
      <div className="hs-metric-grid" style={{marginTop:20}}>{[['시설 운영','시설 정보 정리','O004'],['단기 임대','주·월 조건','O006'],['매매','독립 채널','O007'],['영업권·공매','별도 운영','O008']].map(([a,b,c])=><a className="hs-panel" href={screenHref(c)} key={a}><h2>{a}</h2><p>{b}</p><ArrowRight/></a>)}</div>
    </OpsPage>;
    case 'owner-map': return <OpsPage screen={screen} subtitle="시설 레이어와 4개 매물 채널은 서로 독립적으로 전환됩니다.">
      <div className="hs-pills" style={{marginBottom:16}}>{[['facility','시설'],['stay','단기 임대'],['sale','매매'],['business','영업권'],['auction','공매']].map(([key,label])=><button className={`hs-btn ${layer === key ? '' : 'secondary'}`} key={key} onClick={()=>setLayer(key as typeof layer)}>{label}</button>)}</div>
      <div style={{height:'min(68vh,690px)',minHeight:470,position:'relative',border:'1px solid var(--hs-line)',borderRadius:18,overflow:'hidden'}}><div style={{position:'absolute',inset:0}}><KakaoOwnerLayer type={layer}/></div><div className="hs-map-label"><strong>{layer === 'facility' ? '시설 위치' : `운영 채널 · ${layer === 'stay' ? '단기 임대' : layer === 'sale' ? '매매' : layer === 'business' ? '영업권' : '공매'}`}</strong><br/>성수동 · {layer === 'facility' ? '시설' : '운영 매물'} 위치</div></div>
      <p className="hs-muted">성수동의 시설과 채널별 운영 항목을 살펴봅니다.</p>
    </OpsPage>;
    case 'dashboard': return <OpsPage screen={screen} subtitle="시설과 예약 업무를 한 화면에서 살펴봅니다.">
      <StatGrid values={ [['운영 시설','3곳','등록·검토 중인 합성 시설','표본'],['공개 단기 임대','2건','주·월 요금별 확인','표본'],['확인할 예약','4건','일정 확인이 필요한 항목','대기'],['이번 달 정산','2,480,000원','정산 내역 예시','가상']] }/>
      <div className="hs-legacy-grid" style={{marginTop:24}}><section className="hs-panel"><h2>최근 확인이 필요한 항목</h2><DataTable headers={['항목','공간','상태']} rows={ [['예약 요청','햇살이 머무는 성수 빌라','호스트 확인'],['등록 신청','성수 리버워크','내용 보완'],['정산 내역','10월 정산','예정']] } actionId="O021"/></section><aside className="hs-panel"><h2>빠른 이동</h2><div className="hs-stack"><a className="hs-btn secondary" href={screenHref('O019')}>요금 캘린더</a><a className="hs-btn secondary" href={screenHref('O025')}>정산·수입</a><a className="hs-btn secondary" href={screenHref('O004')}>시설 목록</a></div></aside></div>
    </OpsPage>;
    case 'facilities': return <OpsPage screen={screen} subtitle="시설 정보를 단기 임대 및 운영 채널과 분리해 관리합니다." action={<a className="hs-btn" href={screenHref('O035')}><Plus size={18}/>시설 추가</a>}>
      <div className="hs-tabs"><a className="active" href={screenHref('O004')}>전체 시설</a><a href={screenHref('O002')}>지도 보기</a></div>
      <div className="hs-result-grid">{facilities.map((item)=><a key={item.id} href={screenHref('O005')} className="hs-panel"><p className="hs-kicker">{item.id} · {item.type}</p><h2>{item.name}</h2><p>{item.area}</p><span className={`hs-status ${item.status === '등록 검토' ? 'wait' : ''}`}>{item.status}</span><p>{item.count}개 운영 항목</p></a>)}</div>
    </OpsPage>;
    case 'facility-detail': return <OpsPage screen={screen}><div className="hs-legacy-grid"><section className="hs-panel"><p className="hs-kicker">시설 F-024 · 운영 중</p><h2>{facilities[0].name}</h2><p>{facilities[0].area} · 대략적인 위치</p><div className="hs-facts"><span>숙박시설</span><span>공개 시설 정보</span><span>최근 확인 2026. 06. 18</span></div><div className="hs-pills"><a className="hs-btn secondary" href={screenHref('O031')}>건축 정보</a><a className="hs-btn secondary" href={screenHref('O029')}>실거래 예시</a></div></section><aside className="hs-panel"><h2>연결된 운영 채널</h2>{channels.map(([id,label])=><p key={id}><a href={screenHref(id)}>{label} 매물 보기 →</a></p>)}</aside></div></OpsPage>;
    case 'listing-stay': case 'listing-sale': case 'listing-business': case 'listing-auction': {
      const active = channels.find((item)=>item[2] === screen.view)?.[0] ?? 'O006';
      const rows = channelData[screen.view];
      return <OpsPage screen={screen} subtitle="채널은 별도 목록으로 관리됩니다. 요금 미등록 항목은 금액을 추정하지 않습니다." action={<a className="hs-btn" href={screenHref('O011')}><Plus size={18}/>매물 등록</a>}>
        <ChannelTabs active={active}/>
        <div className="hs-title-row"><div><h2 style={{fontSize:23}}>이 채널의 매물</h2><p>{screen.view === 'listing-stay' ? '단기 임대 — 주·월 조건을 각각 유지합니다.' : screen.view === 'listing-sale' ? '매매 채널 — 임대 요금과 분리합니다.' : screen.view === 'listing-business' ? '영업권 양도 — 매매 매물과 분리합니다.' : '공매 — 공개 상태와 조사 조건을 분리합니다.'}</p></div><Field label="상태" options={['전체','공개','검토 중','초안']}/></div>
        <div className="hs-result-grid">{rows.map((row,i)=><article className="hs-panel" key={row.label}><div className="hs-title-row"><span className="hs-chip">{row.category}</span><span className={`hs-status ${row.status !== '공개' ? 'wait' : ''}`}>{row.status}</span></div><h2>{row.label}</h2><p>성수동 · {row.count}개 사진 · 최근 수정 2026. 06. {18-i}</p><strong className={row.price.includes('원/') ? `hs-price ${screen.view !== 'listing-stay' ? '' : ''}` : ''}>{row.price}</strong><div className="hs-pills" style={{marginTop:18}}><a className="hs-btn secondary" href={screenHref(screen.view === 'listing-sale' ? 'O032' : screen.view === 'listing-business' ? 'O033' : screen.view === 'listing-auction' ? 'O034' : 'O005')}>매물 상세</a><a className="hs-btn secondary" href={screenHref('O036')}>더 보기</a></div></article>)}</div>
      </OpsPage>;
    }
    case 'address': case 'address-results': return <OpsPage screen={screen} subtitle="건물 확인을 위한 입력 예시입니다. 게스트 화면에는 정확한 주소를 노출하지 않습니다.">
      <section className="hs-panel" style={{maxWidth:850}}><LocalForm className="hs-stack"><Field label="도로명 또는 지번 검색" placeholder="예: 서울 성동구 성수이로"/><LocalSubmit text="주소 후보 보기" target="O037"/></LocalForm>
        <h2 style={{marginTop:28}}>주소 후보</h2><div className="hs-stack">{['서울 성동구 성수이로 인근 · 건물 A','서울 성동구 아차산로 인근 · 건물 B'].map((label,i)=><a className="hs-panel" href={screenHref('O011')} key={label}><strong>{label}</strong><p>건축물 근거 확인 상태: 예시 {i ? '대기' : '확인됨'}</p></a>)}</div>
      </section><Notice>주소 후보와 건물 정보는 화면용 합성 데이터입니다.</Notice>
    </OpsPage>;
    case 'registration-info': case 'registration-photos': case 'registration-options': case 'registration-description': case 'registration-price': case 'registration-preview': case 'registration-policy': {
      const steps = [['O011','기본정보'],['O012','사진'],['O013','옵션'],['O014','설명'],['O015','요금'],['O016','미리보기'],['O017','정책 동의']];
      const active = steps.findIndex(([id])=>id === screen.id);
      const stepFields: Record<string, ReactNode[]> = {
        'registration-info': [<Field key="title" label="등록 제목" placeholder="공간을 알아보기 쉬운 이름"/>,<Field key="name" label="공간 이름" required/>,<Field key="address" label="확인된 건물" value="성수동 예시 건물"/>,<Field key="kind" label="운영 형태" options={['주거형 단기임대','숙박시설']}/>,<Field key="rooms" label="방 수" type="number"/>,<Field key="area" label="전용 면적 (㎡)" type="number"/>,<Field key="guests" label="수용 인원" type="number"/>],
        'registration-photos': [<Field key="upload" label="사진 선택" type="file"/>,<Field key="cover" label="대표 사진 설명" placeholder="사진에 담긴 공간"/>,<Field key="caption" label="공간 사진 메모" type="textarea" wide/>],
        'registration-options': [<Field key="amenities" label="편의시설" options={['와이파이','주방','주차','세탁기']}/>,<Field key="checkin" label="체크인 안내"/>,<Field key="checkout" label="체크아웃 안내"/>],
        'registration-description': [<Field key="desc" label="공간 설명" type="textarea" wide/>,<Field key="location" label="동네 소개" type="textarea" wide/>],
        'registration-price': [<Field key="night" label="1일 요금 (원)" type="number"/>,<Field key="week" label="주 요금 (원)" type="number"/>,<Field key="month" label="월 요금 (원)" type="number"/>,<Field key="minimum" label="최소 이용 기간 (일)" type="number"/>],
        'registration-preview': [<div key="preview" className="hs-panel hs-wide"><p className="hs-kicker">공개 전 미리보기</p><h2>새로 등록하는 공간</h2><p>선택한 공개 정보와 요금 표시 형태를 확인합니다. 주소는 공개되지 않습니다.</p><div className="hs-pills"><span className="hs-price">가격 미등록</span><span className="hs-chip">요금 확인 전</span></div></div>],
        'registration-policy': [<label key="responsibility" className="hs-pill hs-wide"><input type="checkbox"/> 등록 정보의 정확성과 운영 책임을 확인했습니다.</label>,<label key="disclosure" className="hs-pill hs-wide"><input type="checkbox"/> 제한된 공개 요약 정보 게시 안내를 확인했습니다.</label>],
      };
      return <OpsPage screen={screen} subtitle="공간 등록 7단계 · 단계별 정보와 공개 조건을 확인합니다.">
        <div className="hs-progress">{steps.map(([id],i)=><span key={id} className={i <= active ? 'active' : ''}/>)}</div><nav className="hs-tabs" style={{marginTop:15}}>{steps.map(([id,label])=><a className={id === screen.id ? 'active' : ''} href={screenHref(id)} key={id}>{label}</a>)}</nav>
        <section className="hs-panel" style={{maxWidth:920}}><LocalForm className="hs-form-grid">{stepFields[screen.view]}<LocalSubmit text={active === steps.length - 1 ? '제출 내용 확인' : '입력 확인 후 다음'} target={active === steps.length - 1 ? 'O018' : steps[Math.min(active + 1,steps.length - 1)][0]}/></LocalForm></section>
      </OpsPage>;
    }
    case 'registration-status': return <OpsPage screen={screen}><div className="hs-empty-state"><ClipboardList size={40}/><h2>등록 정보를 확인하고 있습니다</h2><p>공개 전 검토가 필요한 항목을 확인해 주세요.</p><span className="hs-status wait">확인 대기</span><a className="hs-btn secondary" href={screenHref('O011')}>등록 내용 다시 보기</a></div></OpsPage>;
    case 'rates-calendar': case 'bookings-calendar': return <OpsPage screen={screen} subtitle={screen.view === 'rates-calendar' ? '요금과 이용 불가 기간을 날짜별로 관리합니다.' : '예약 요청과 확인 일정을 함께 살펴봅니다.'}>
      <div className="hs-title-row"><div><h2 style={{fontSize:24}}>성수동 단기임대 공간</h2><p>주 기준 요금 430,000원/주 · 월 등록 요금은 별도 표시</p></div><div className="hs-pills"><button className="hs-icon-button" onClick={()=>setCalendarIndex(calendarIndex-1)}><ChevronLeft/></button><strong>{new Date(2026,9+calendarIndex,1).toLocaleDateString('ko-KR',{year:'numeric',month:'long'})}</strong><button className="hs-icon-button" onClick={()=>setCalendarIndex(calendarIndex+1)}><ChevronRight/></button></div></div>
      <section className="hs-panel"><div className="hs-calendar">{['일','월','화','수','목','금','토'].map((d)=><strong key={d}>{d}</strong>)}{Array.from({length:35},(_,i)=><button key={i} onClick={(e)=>e.currentTarget.classList.toggle('selected')}><span>{i < 3 ? '' : i - 2}</span>{i % 7 === 2 && i > 4 && <small>{screen.view === 'rates-calendar' ? '가능' : '요청'}</small>}</button>)}</div></section>
      {screen.view === 'rates-calendar' && <section className="hs-panel" style={{marginTop:18}}><h2>기간 요금·상태 편집</h2><div className="hs-form-grid"><Field label="시작일" type="date"/><Field label="종료일" type="date"/><Field label="주 요금 (원)" type="number"/><Field label="월 요금 (원)" type="number"/></div><div className="hs-pills" style={{marginTop:17}}>{['기간 이용 불가로 설정','기간 다시 열기','주 요금 지우기','월 요금 지우기'].map((x)=><button className="hs-btn secondary" key={x} onClick={()=>toast(`${x} 설정을 확인했습니다.`)}>{x}</button>)}</div><p><button className="hs-btn" onClick={()=>toast('입력한 달력 조건을 확인했습니다.')}>변경 저장</button></p></section>}
      {notice && <p role="status">{notice}</p>}
    </OpsPage>;
    case 'owner-bookings': return <OpsPage screen={screen} subtitle="예약 요청과 이용 일정을 확인합니다."><div className="hs-tabs"><a className="active" href={screenHref('O021')}>요청 4</a><a href={screenHref('O020')}>달력</a></div><DataTable headers={['요청일','공간','일정','인원','상태']} rows={ [['6월 18일',syntheticPlaces[0].title,'10.12 — 10.19','2명','확인 필요'],['6월 17일','스테이 모노 성수','10.20 — 10.22','1명','검토 중'],['6월 15일','서울숲 옆 작은 테라스','11.03 — 11.10','2명','확인 필요']] } actionId="O022" actionLabel="요청 검토"/></OpsPage>;
    case 'booking-approval': return <PopoverScreen screen={screen}><p className="hs-kicker">요청 번호 BK-EX-2406</p><h2>햇살이 머무는 성수 빌라</h2><p>2026. 10. 12 — 10. 19 · 2명 · 430,000원/주 기준</p><Notice>이 화면의 수락·거절은 실제 예약이나 재고를 변경하지 않습니다.</Notice><div className="hs-pills" style={{marginTop:20}}><button className="hs-btn" onClick={()=>setNotice('요청 수락을 선택했습니다.')}>요청 수락</button><button className="hs-btn secondary" onClick={()=>setNotice('추가 확인을 선택했습니다.')}>추가 확인</button><button className="hs-btn secondary" onClick={()=>setNotice('요청 거절을 선택했습니다.')}>요청 거절</button></div>{notice && <p role="status">{notice}</p>}</PopoverScreen>;
    case 'owner-chat-list': return <OpsPage screen={screen}><div className="hs-chat-layout"><aside className="hs-chat-list"><a className="hs-panel" href={screenHref('O024')}><strong>김하늘 · 햇살이 머무는 성수 빌라</strong><p>체크인 안내 문의</p></a><a className="hs-panel" href={screenHref('O024')}><strong>박서윤 · 스테이 모노</strong><p>예약 일정 확인</p></a></aside><div className="hs-chat-thread"><h2>대화를 선택하세요</h2><p>대화 내용은 합성된 예시입니다.</p></div></div></OpsPage>;
    case 'owner-chat': return <OpsPage screen={screen}><div className="hs-chat-layout"><aside className="hs-chat-list"><a href={screenHref('O023')}>대화 목록</a></aside><div className="hs-chat-thread"><h2>김하늘 · 일정 문의</h2><div className="hs-bubble">입실 당일 짐을 먼저 맡길 수 있을까요?</div><div className="hs-bubble mine">오후 1시 이후에 안내 데스크에 맡기실 수 있습니다.</div><LocalForm className="hs-form-grid"><Field label="메시지 작성" placeholder="답변 내용을 입력하세요" wide/><LocalSubmit text="메시지 보내기"/></LocalForm></div></div></OpsPage>;
    case 'earnings': return <OpsPage screen={screen} subtitle="계약상 표시 내역과 실제 자금 이동을 구분해 확인합니다."><StatGrid values={ [['예정 정산','2,480,000원','2026년 6월 예시','예정'],['확인 대기','684,000원','정책 검토 전','확인 필요'],['정산 완료','4,130,000원','합성 기록','완료'],['정산 기준','월별','계약별 확인','안내']] }/><div className="hs-chart">{[46,64,52,80,57,90,67].map((v,i)=><i key={i} style={{height:`${v}%`}}/>)}</div><p><a className="hs-btn secondary" href={screenHref('O026')}>정산 내역 상세 보기</a></p><Notice>이 데이터는 화면 예시이며 실제 지급이나 금융 실행을 나타내지 않습니다.</Notice></OpsPage>;
    case 'payout-detail': return <OpsPage screen={screen}><section className="hs-panel" style={{maxWidth:800}}><p className="hs-kicker">정산 예시 · 2026년 6월</p><h2>2,480,000원 · 지급 예정</h2><DataTable headers={['항목','기준','표시 금액']} rows={ [['예약 요금','계약 조건','2,900,000원'],['운영 수수료','예시 기준','-290,000원'],['조정 항목','검토 대기','-130,000원'],['예상 정산','참고용','2,480,000원']] }/><Notice>실제 송금·정산 처리 내역이 아닙니다.</Notice></section></OpsPage>;
    case 'business-settings': case 'owner-settings': return <OpsPage screen={screen}><div className="hs-legacy-grid"><nav className="hs-panel hs-stack"><a href={screenHref('O027')}>사업자 정보</a><a href={screenHref('O028')}>소유자 설정</a><a href={screenHref('O024')}>알림 설정</a></nav><section className="hs-panel"><LocalForm className="hs-form-grid"><Field label={screen.view === 'business-settings' ? '사업자명' : '소유자명'} value="성수 공간 운영팀"/><Field label="이메일" type="email" value="host@example.test"/><Field label="연락처" value="02-0000-0000"/><Field label="운영 지역" value="서울 성동구"/><Field label="알림 수신" options={['이메일','문자','화면 알림']}/><LocalSubmit text="설정 미리보기"/></LocalForm></section></div></OpsPage>;
    case 'transactions': return <OpsPage screen={screen} subtitle="시설 실거래 예시 목록과 출처 확인 항목을 함께 표시합니다."><div className="hs-pills" style={{marginBottom:18}}><Field label="기간" options={['최근 1년','최근 3년','전체 기간']}/><Field label="유형" options={['전체','매매','임대']}/></div><DataTable headers={['기준일','건물 구역','유형','전용 면적','표시 금액','출처 상태']} rows={ [['2026.05','성수동 인근','매매','54㎡','가격 확인 전','예시'],['2026.04','성수동 인근','임대','42㎡','조건 확인 필요','검증 전'],['2026.02','서울숲 인근','매매','63㎡','가격 확인 전','예시']] } actionId="O030" actionLabel="데이터랩"/></OpsPage>;
    case 'datalab': return <OpsPage screen={screen} subtitle="기간별 거래 흐름과 운영 지표를 둘러봅니다."><div className="hs-tabs"><a href={screenHref('O029')}>실거래</a><a className="active" href={screenHref('O030')}>데이터랩</a><a href={screenHref('O031')}>건축 정보</a></div><div className="hs-metric-grid">{[['거래량 흐름','18건','성수동 월별 표본','2026.06'],['가격 변화','확인 필요','가격 기준 확인 중','2026.06'],['신고 현황','10건','월별 표본','2026.06']].map(([a,b,c,d])=><div className="hs-metric" key={a}><span>{a}</span><strong style={{fontSize:20}}>{b}</strong><p>{c}</p><small>{d}</small></div>)}</div><div className="hs-chart" style={{marginTop:20}}>{[25,38,32,50,45,57,44,67,61,72].map((v,i)=><i key={i} style={{height:`${v}%`}}/>)}</div></OpsPage>;
    case 'building-info': return <OpsPage screen={screen}><div className="hs-tabs"><a href={screenHref('O029')}>실거래</a><a href={screenHref('O030')}>데이터랩</a><a className="active" href={screenHref('O031')}>건축 정보</a></div><section className="hs-panel" style={{maxWidth:800}}><p className="hs-kicker">성수동 예시 건물</p><h2>건축 정보 확인 항목</h2><DataTable headers={['항목','상태','표시']} rows={ [['건물 구분','예시','숙박시설'],['연면적','정보 미연결','—'],['준공 시점','정보 미연결','—'],['공개 위치','보호됨','성수동 인근']] }/></section></OpsPage>;
    case 'sale-detail': case 'business-detail': case 'auction-detail': {
      const sale = screen.view === 'sale-detail', business = screen.view === 'business-detail';
      return <OpsPage screen={screen}><div className="hs-legacy-grid"><section className="hs-panel"><span className="hs-chip">{sale ? '매매' : business ? '영업권' : '공매'}</span><h2>{sale ? '서울숲 가까운 코너 호실' : business ? '연무장길 운영권 양도' : '성수동 업무·숙박 복합 건물'}</h2><p>서울 성동구 성수동 인근 · 정확한 위치 보호</p><div className={`hs-price ${sale ? '' : 'stay'}`}>{sale ? '매매가 미등록' : business ? '양도 조건 확인 필요' : '최저가 미등록'}</div><p>상세 조건은 소유자 입력 및 확인 후 공개됩니다.</p><a className="hs-btn secondary" href={screenHref('O006')}>채널 목록으로</a></section><aside className="hs-panel"><h2>조건</h2><p>{sale ? '면적 및 권리 정보' : business ? '운영 범위 및 인수 기준' : '공매 종류 및 진행 상태'}</p><Notice>조건이 등록되지 않은 항목은 금액으로 추정하지 않습니다.</Notice></aside></div></OpsPage>;
    }
    case 'facility-add': return <PopoverScreen screen={screen}><LocalForm className="hs-stack"><Field label="시설명" required/><Field label="운영 유형" options={['숙박시설','생활숙박시설','주거형 단기임대']}/><Field label="동네" value="서울 성동구 성수동 인근"/><Field label="공개 메모" type="textarea"/><LocalSubmit text="시설 정보 확인"/></LocalForm></PopoverScreen>;
    case 'listing-delete': return <PopoverScreen screen={screen}><div className="hs-empty-state"><Trash2 size={36}/><h2>매물을 목록에서 숨길까요?</h2><p>숨김 전에 등록 상태와 공개 범위를 확인하세요.</p><div className="hs-pills"><a className="hs-btn secondary" href={screenHref('O006')}>유지</a><button className="hs-btn" onClick={()=>setNotice('목록에서 숨김 상태로 표시했습니다.')}>매물 숨기기</button></div>{notice && <p role="status">{notice}</p>}</div></PopoverScreen>;
    case 'listing-missing': return <OpsPage screen={screen}><div className="hs-empty-state"><h2>등록된 조건이 없습니다</h2><p>단기 임대·매매 조건이 미등록 상태입니다. 가격을 임의로 표시하지 않습니다.</p><a className="hs-btn" href={screenHref('O011')}>정보 입력 시작</a></div></OpsPage>;
    default: return formPage([<Field key="memo" label="운영 정보" type="textarea" wide/>]);
  }
}

function KakaoOwnerLayer({ type }: { type: 'facility'|'stay'|'sale'|'business'|'auction' }) {
  const entries = type === 'facility' ? facilityPlaces : syntheticPlaces.slice(type === 'stay' ? 0 : type === 'sale' ? 2 : type === 'business' ? 4 : 6, type === 'stay' ? 4 : type === 'sale' ? 6 : type === 'business' ? 8 : 10).map((p) => ({ ...p, kind: type === 'stay' ? p.kind : 'home' as const, mapLabel: type === 'stay' ? p.price.toLocaleString() + (p.basis === 'week' ? '원/주' : p.basis === 'month' ? '원/월' : '원/일') : type === 'sale' ? '매매' : type === 'business' ? '영업권' : '공매', layer: type }));
  return <KakaoMap entries={entries}/>;
}

function AdminPage({ screen }: { screen: Screen }) {
  const [notice, setNotice] = useState('');
  const [filter, setFilter] = useState('전체');
  const table = (headers: string[], rows: string[][], id?: string, action = '열기') => <DataTable headers={headers} rows={rows} actionId={id} actionLabel={action}/>;
  const content = (() => {
    switch (screen.view) {
      case 'admin-login': return <div className="hs-modal-stage"><section className="hs-modal"><p className="hs-kicker">HOME &amp; STAY · 운영 관리</p><h1>관리자 로그인</h1><Notice>관리자 인증은 연결되지 않은 화면 시안입니다.</Notice><LocalForm className="hs-stack"><Field label="관리자 이메일" type="email"/><Field label="비밀번호" type="password"/><LocalSubmit text="로그인" target="A002"/></LocalForm></section></div>;
      case 'admin-home': return <><StatGrid values={ [['등록 심사','12건','확인할 신규 항목','대기'],['예약 원장','248건','기간 기준 예시','기록'],['금융 원장','18건','검토 상태 포함','기록'],['감사 기록','96건','최근 변경 이력','누적']] }/><div className="hs-metric-grid" style={{marginTop:20}}>{[['등록 심사','A003'],['예약 원장','A006'],['금융 원장','A008'],['감사 기록','A016'],['FAQ 관리','A010'],['사업자 관리','A020']].map(([label,id])=><a className="hs-panel" key={id} href={screenHref(id)}><h2>{label}</h2><p>목록 및 세부 검토</p><ArrowRight/></a>)}</div></>;
      case 'review-list': return <><div className="hs-tabs">{['전체','대기','보완 요청','완료'].map((f)=><button className={filter===f?'active':''} key={f} onClick={()=>setFilter(f)}>{f}</button>)}</div>{table(['접수일','등록 이름','운영 유형','위치 정보','심사 상태'],[['6월 18일','햇살이 머무는 성수 빌라','단기 임대','성수동 인근','확인 대기'],['6월 17일','성수 리버워크','시설 등록','성수동 인근','보완 요청'],['6월 15일','연무장길 운영권 양도','영업권','성수동 인근','내용 확인']], 'A004','심사 상세')}</>;
      case 'review-empty': return <div className="hs-empty-state"><ClipboardList size={38}/><h2>검토할 등록 항목이 없습니다</h2><p>선택한 상태에 새로운 항목이 없습니다.</p><a className="hs-btn secondary" href={screenHref('A003')}>전체 심사 목록</a></div>;
      case 'review-detail': return <div className="hs-legacy-grid"><section className="hs-panel"><p className="hs-kicker">등록 검토 · EX-024</p><h2>햇살이 머무는 성수 빌라</h2><DataTable headers={['검토 항목','제출 정보','확인']} rows={ [['기본 정보','운영 형태·면적·수용 인원','미확인'],['공개 사진','대표 사진 4장','검토 필요'],['요금 조건','주 요금 입력','확인 필요'],['위치 보호','성수동 단위 공개','적용']] }/><p><a className="hs-btn secondary" href={screenHref('A005')}>검토 결과 작성</a></p></section><aside className="hs-panel"><h2>검토 메모</h2><Field label="내부 메모" type="textarea"/></aside></div>;
      case 'review-action': return <PopoverScreen screen={screen}><h2>검토 처리</h2><Notice>이 선택은 심사 상태를 실제로 변경하지 않습니다.</Notice><Field label="처리 결과" options={['승인 검토','보완 요청','보류']}/><Field label="검토 메모" type="textarea"/><div className="hs-pills" style={{marginTop:17}}><button className="hs-btn" onClick={()=>setNotice('선택한 처리 결과를 확인했습니다.')}>결과 확인</button><a className="hs-btn secondary" href={screenHref('A004')}>상세로 돌아가기</a></div>{notice && <p role="status">{notice}</p>}</PopoverScreen>;
      case 'booking-ledger': return <><div className="hs-pills" style={{margin:'18px 0'}}><Field label="기간" options={['최근 30일','이번 분기','전체']}/><Field label="상태" options={['전체','요청','확정','취소']}/></div>{table(['예약 번호','공간','예약일','표시 금액','상태'],[['BK-EX-024','햇살이 머무는 성수 빌라','6월 18일','430,000원/주','호스트 확인'],['BK-EX-031','스테이 모노 성수','6월 17일','118,000원/일','확인 완료']], 'A007')}</>;
      case 'ledger-detail': return <section className="hs-panel"><p className="hs-kicker">예약 원장 · BK-EX-024</p><h2>예약 이벤트 기록</h2>{table(['시각','이벤트','이전 상태','기록 상태'],[['6월 18일 09:32','예약 신청','—','요청'],['6월 18일 09:33','호스트 알림','요청','전달']])}<Notice>이 예약 기록은 예시 데이터이며 실제 신청 자료가 없습니다.</Notice></section>;
      case 'finance-ledger': return <><div className="hs-pills" style={{margin:'18px 0'}}><Field label="분류" options={['전체','정산','금융 계약','조정']}/><Field label="상태" options={['전체','검토','예정','완료']}/></div>{table(['기록 번호','분류','참조','금액','처리 상태'],[['FN-EX-113','정산','6월 운영','2,480,000원','예정'],['FN-EX-118','조정','숙소 예약','684,000원','확인 필요']], 'A009')}</>;
      case 'finance-detail': return <section className="hs-panel"><p className="hs-kicker">금융 원장 · FN-EX-113</p><h2>표시 금액과 실행 상태 구분</h2>{table(['항목','기록','금액'],[['운영 계약 표시','검토 전','2,900,000원'],['수수료 기준','참고','290,000원'],['지급 상태','실행되지 않음','—']])}<Notice>계약상 표시와 실제 자금 이동은 별개의 절차입니다.</Notice></section>;
      case 'faq-admin': case 'policy-admin': return <><div className="hs-title-row" style={{marginTop:20}}><Field label="분류" options={screen.view === 'faq-admin' ? ['전체','예약','위치 보호','계정'] : ['전체','이용 정책','취소','운영']}/><a className="hs-btn" href={screenHref(screen.view === 'faq-admin' ? 'A011' : 'A013')}><Plus size={17}/>새 항목 추가</a></div>{table(['표시 순서','항목','최근 수정','공개 상태'],screen.view === 'faq-admin' ? [['01','정확한 위치는 어떻게 보호하나요?','6월 12일','공개'],['02','예약 신청 후 절차는?','6월 10일','공개']] : [['01','예약 취소 기준','6월 18일','공개'],['02','숙소 정보 공개 범위','6월 10일','공개']],screen.view === 'faq-admin' ? 'A011' : 'A013','편집')}</>;
      case 'faq-edit': case 'policy-edit': return <PopoverScreen screen={screen}><LocalForm className="hs-stack"><Field label="제목" value={screen.view === 'faq-edit' ? '정확한 위치 보호 안내' : '예약 취소 기준'}/><Field label="분류" options={['예약','숙소 정보','정책 안내']}/><Field label="내용" type="textarea"/><Field label="노출 순서" type="number"/><LocalSubmit text="편집 내용 확인"/></LocalForm></PopoverScreen>;
      case 'promotion': return <><div className="hs-pills" style={{margin:'18px 0'}}><Field label="노출 상태" options={['전체','예정','노출 중','종료']}/><a className="hs-btn" href={screenHref('A015')}><Plus size={17}/>프로모션 추가</a></div>{table(['프로모션','대상','기간','상태'],[['성수의 한 달 머무름','단기 임대','10.01 — 10.31','예정'],['가을 공간 둘러보기','숙박','09.01 — 09.30','종료']], 'A015','편집')}</>;
      case 'promotion-edit': return <PopoverScreen screen={screen}><LocalForm className="hs-stack"><Field label="프로모션 이름"/><Field label="노출 대상" options={['주거형 단기임대','숙박시설','전체']}/><Field label="시작일" type="date"/><Field label="종료일" type="date"/><Field label="안내 문구" type="textarea"/><LocalSubmit text="저장"/></LocalForm></PopoverScreen>;
      case 'audit': return <><div className="hs-pills" style={{margin:'18px 0'}}><Field label="작업 분류" options={['전체','심사','정책 편집','계정']}/><Field label="기간" options={['최근 7일','최근 30일','전체']}/></div>{table(['기록 시각','작업자','작업','대상','결과'],[['6월 18일 10:21','관리자 03','정책 편집','예약 취소 기준','완료'],['6월 18일 09:44','관리자 01','등록 심사','성수 리버워크','보류']], 'A017')}</>;
      case 'audit-detail': return <section className="hs-panel"><p className="hs-kicker">변경 감사 기록 · AU-EX-112</p><h2>정책 문구 편집</h2>{table(['구분','이전 값','변경 값'],[['정책 이름','취소 기준','취소 기준 안내'],['작업 시각','—','2026. 06. 18 10:21'],['처리 결과','초안','저장 완료']])}<Notice>기록 시각과 작업 흐름을 항목별로 확인합니다.</Notice></section>;
      case 'members': return <><div className="hs-pills" style={{margin:'18px 0'}}><Field label="계정 유형" options={['전체','일반 회원','사업자']}/><Field label="상태" options={['전체','활성','확인 필요']}/></div>{table(['회원 번호','표시 이름','역할','가입 시기','상태'],[['MB-EX-024','김하늘','일반 회원','2026. 03','활성'],['MB-EX-031','성수 공간 운영팀','사업자','2026. 02','확인 필요']], 'A019')}</>;
      case 'member-detail': return <section className="hs-panel"><p className="hs-kicker">회원 · MB-EX-024</p><h2>김하늘</h2>{table(['항목','표시 정보'],[['계정 유형','일반 회원'],['가입 시기','2026년 3월'],['최근 이용','예약 목록'],['개인 식별 정보','노출하지 않음']])}<a className="hs-btn secondary" href={screenHref('A018')}>회원 목록</a></section>;
      case 'businesses': return <>{table(['업체 번호','표시 이름','유형','신청일','확인 상태'],[['BZ-EX-018','성수 공간 운영팀','숙박 운영','6월 18일','검토 대기'],['BZ-EX-021','서울숲 스테이','임대 운영','6월 17일','정보 확인']], 'A021')}</>;
      case 'business-detail': return <section className="hs-panel"><p className="hs-kicker">사업자 · BZ-EX-018</p><h2>성수 공간 운영팀</h2>{table(['확인 항목','상태','메모'],[['사업자 유형','숙박 운영','검토 필요'],['등록 정보','확인 대기','추가 자료 없음'],['공개 공간','2곳','합성 데이터']])}<a className="hs-btn secondary" href={screenHref('A020')}>사업자 목록</a></section>;
      case 'admin-permissions': return <div className="hs-legacy-grid"><section className="hs-panel"><h2>역할별 접근 범위</h2>{['등록 심사','예약 원장 조회','금융 원장 확인','정책 편집','회원 정보 열람'].map((label,i)=><div className="hs-toggle-row" key={label}><span>{label}</span><span className="hs-status">{i < 3 ? '권한별 제한' : '별도 승인'}</span></div>)}</section><aside className="hs-panel"><h2>권한 변경 기준</h2><p>업무 범위와 감사 기록을 확인한 뒤 별도 권한을 부여하는 화면 구조입니다.</p></aside></div>;
      default: return <div className="hs-empty-state"><h2>{screen.title}</h2><p>관리 업무를 확인하고 필요한 정보를 살펴봅니다.</p></div>;
    }
  })();
  if (['review-action','faq-edit','policy-edit','promotion-edit'].includes(screen.view)) return content;
  return <SuiteFrame screen={screen}><main className="hs-main"><OpsTitle screen={screen} subtitle="업무 항목을 확인하고 기록합니다."/>{content}</main>{notice && <div role="status" className="hs-toast">{notice}</div>}</SuiteFrame>;
}

export function OwnerView({ screen }: { screen: Screen }) { return <OwnerPage screen={screen}/>; }
export function AdminView({ screen }: { screen: Screen }) { return <AdminPage screen={screen}/>; }
