import { useMemo, useState, type ReactNode } from 'react';
import { ArrowRight, MapPin } from 'lucide-react';
import type { Screen } from './_shared';
import { Field, LocalForm, LocalSubmit, PopoverScreen, SuiteFrame, screenHref } from './_shared';

type LegacyCategory = 'building' | 'application' | 'directory' | 'admin' | 'workspace';

const clean = (value: string) => value.replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '').replace(/\s+/g, ' ').trim();
const titleOf = (screen: Screen) => clean(screen.title.replace(/&amp;/g, '&').replace(/\{\{[^}]*\}\}/g, '')) || '업무 정보';
const actionOnly = /^(?:검색|저장|제출|등록|추가|전환|신청|요청|확인|변경|로그인|새로고침|다시 시도|초안|취소|편집|선택|닫기|미리보기|전송|재검증|보기|조회|초기화|확정|검토|비밀번호|목록 새로고침|패널 닫기|지도전환|확인 요청|재검증 요청|용도 라벨 정정 요청|내 건물 수정 요청|검색 결과|메뉴 열기|로그아웃|삭제|등록하기|저장하기|다음|이전|바로가기|전체 보기|화면 전환|openModal)$/i;
const fieldTerms = /주소|검색|기간|일자|입실|퇴실|요금|가격|수|면적|인원|유형|계정|이메일|전화|비밀번호|메모|제목|이름|소개|내용|지역|건물|사진|상태|용도|사업자|연락처|정렬|분류|예약|비용|날짜|이용|신고|거래|통계|금융|증빙|권한/;
const actionSuffix = /(?:새로고침|다시 시도|수정 요청|정정 요청|재검증|로그아웃|로그인|제출|등록하기|저장하기|전환|닫기|열기|조회|확정|바로가기|목록으로|돌아가기|신청하기|추가하기|삭제하기|편집하기)$/;
const rawCode = /^(?:on[A-Z]|handle[A-Z]|set[A-Z]|openModal|closeModal)|[{}<>();]|=>/;
const isSourceAction = (label: string) => actionOnly.test(label) || rawCode.test(label) || (actionSuffix.test(label) && !fieldTerms.test(label));

function siblingsFor(screen: Screen, allScreens: Screen[]) {
  if (!screen.parent) return [];
  return allScreens.filter((item) => item.parent === screen.parent && item.id !== screen.id);
}

function classify(screen: Screen, outline: string[]): LegacyCategory {
  const text = `${screen.title} ${screen.view} ${outline.join(' ')}`;
  if (screen.role === '관리자' || /관리자|권한|정책 관리|운영 설정|회원관리|관리 메뉴|감사 기록|로그 관리/.test(text)) return 'admin';
  if (/대시보드|운영 현황|운영 요약|통계 대시보드/.test(text)) return 'workspace';
  if (/지도|건축|실거래|데이터랩|데이터 원본|분석|관광 데이터|거래량|건물|용도 라벨|인근 지역/.test(text)) return 'building';
  if (/로그인|가입|비밀번호|신청|제출|등록|예약|약관|수신거부|인증|파트너 제안/.test(text)) return 'application';
  if (/목록|검색|매물|시설|회원|알림|대화|후기|찾기|디렉토리/.test(text)) return 'directory';
  return 'workspace';
}

function SourceFields({ fields, compact = false }: { fields: string[]; compact?: boolean }) {
  return <div className={`hs-form-grid ${compact ? 'hs-legacy-compact' : ''}`}>{fields.map((label, index) => <Field key={`${label}-${index}`} label={label} type={/내용|소개글|요약|설명|메모|사유/.test(label) ? 'textarea' : /날짜|일자|입실|퇴실/.test(label) ? 'date' : /수|면적|가격|요금|기간|금액/.test(label) ? 'number' : 'text'} wide={/내용|소개글|요약|설명|메모|사유/.test(label)}/>)}</div>;
}

function BuildingPanel({ screen, fields, headings, selected, onSelect }: { screen: Screen; fields: string[]; headings: string[]; selected: number; onSelect: (index: number) => void }) {
  const metrics = headings.slice(0, 4);
  return <div className="hs-legacy-analysis">
    <section className="hs-panel hs-legacy-filters">
      <p className="hs-kicker">조건과 기준</p>
      <h2>지역 분석 범위</h2>
      {fields.length > 0 ? <SourceFields fields={fields.slice(0, 8)} compact/> : <Field label="지역 검색" placeholder="동네, 건물명 또는 주소"/>}
      <div className="hs-pills" style={{marginTop:16}}>{['지역','기간','건물 유형'].map((label, index)=><button key={label} className={`hs-btn secondary ${selected === index ? 'active' : ''}`} onClick={()=>onSelect(index)}>{label}</button>)}</div>
    </section>
    <section className="hs-stack">
      <div className="hs-legacy-map">
        <div className="hs-map-label"><MapPin size={18}/>{titleOf(screen)} · 구역 단위 표시</div>
        <span className="hs-map-marker marker-a"/><span className="hs-map-marker marker-b"/><span className="hs-map-marker marker-c"/>
        <div className="hs-map-scale">성수동 인근 · 정확한 주소 비공개</div>
      </div>
      <div className="hs-metric-grid hs-legacy-analysis-metrics">
        {(metrics.length ? metrics : ['거래 흐름','건축 정보','지역 지표']).map((heading, index)=><button type="button" key={`${heading}-${index}`} className={`hs-metric hs-legacy-metric ${selected === index ? 'active' : ''}`} onClick={()=>onSelect(index)}><span>{heading}</span><strong>—</strong><p>{index === selected ? '선택한 분석 항목' : '기준을 선택해 확인'}</p></button>)}
      </div>
    </section>
  </div>;
}

function DirectoryPanel({ screen, fields, headings, siblings, selected, onSelect }: { screen: Screen; fields: string[]; headings: string[]; siblings: Screen[]; selected: number; onSelect: (index: number) => void }) {
  return <section className="hs-stack">
    <div className="hs-panel">
      <div className="hs-title-row"><div><p className="hs-kicker">검색과 탐색</p><h2>{titleOf(screen)}</h2></div></div>
      <LocalForm className="hs-stack"><Field label="검색어" placeholder="이름이나 지역으로 찾기"/>{fields.length > 0 && <SourceFields fields={fields.slice(0, 5)} compact/>}<div className="hs-pills">{['전체','최근 등록','상태 확인'].map((label,index)=> <button className={`hs-btn secondary ${selected === index ? 'active' : ''}`} type="button" key={label} onClick={()=>onSelect(index)}>{label}</button>)}</div><LocalSubmit text="조건 적용"/></LocalForm>
    </div>
    <div className="hs-panel">
      <div className="hs-title-row"><div><p className="hs-kicker">항목 구성</p><h2>분류와 확인 기준</h2></div><span className="hs-status">검색 기준</span></div>
      <div className="hs-source-chips">{(headings.length ? headings : ['이름','지역','상태']).map((heading,index)=><span key={`${heading}-${index}`}>{heading}</span>)}</div>
    </div>
    {siblings.length > 0 && <nav className="hs-legacy-link-grid" aria-label="관련 목록">{siblings.map((item)=><a className="hs-panel" key={item.id} href={screenHref(item.id)}><span className="hs-kicker">{item.kind}</span><strong>{titleOf(item)}</strong><span>열어보기 <ArrowRight size={16}/></span></a>)}</nav>}
  </section>;
}

function AdminPanel({ screen, fields, headings, siblings, selected, onSelect }: { screen: Screen; fields: string[]; headings: string[]; siblings: Screen[]; selected: number; onSelect: (index: number) => void }) {
  const menu = headings.length ? headings : siblings.map(titleOf);
  return <div className="hs-legacy-admin">
    <aside className="hs-panel hs-legacy-admin-menu"><p className="hs-kicker">관리 메뉴</p><div className="hs-stack">{menu.slice(0, 14).map((label,index)=><button type="button" key={`${label}-${index}`} className={`hs-pill ${selected === index ? 'active' : ''}`} onClick={()=>onSelect(index)}>{label}</button>)}</div></aside>
    <section className="hs-stack">
      <div className="hs-panel"><p className="hs-kicker">선택한 메뉴</p><h2>{menu[selected] || titleOf(screen)}</h2><p>관련 항목을 확인하고 필요한 내용을 정리합니다.</p>{siblings.length > 0 && <div className="hs-legacy-link-grid">{siblings.slice(0, 6).map((item)=><a className="hs-btn secondary" key={item.id} href={screenHref(item.id)}>{titleOf(item)}<ArrowRight size={16}/></a>)}</div>}</div>
      {fields.length > 0 && <section className="hs-panel"><h2>항목 관리</h2><LocalForm className="hs-stack"><SourceFields fields={fields.slice(0, 8)} compact/><LocalSubmit text="입력 내용 확인"/></LocalForm></section>}
    </section>
  </div>;
}

export function LegacyView({ screen, allScreens }: { screen: Screen; allScreens: Screen[] }) {
  const [selected, setSelected] = useState(0);
  const outline = useMemo(() => (screen.source_outline ?? []).map(clean).filter((label) => Boolean(label) && !/체험|공동호스트|서비스 링크/.test(label) && !isSourceAction(label)), [screen.source_outline]);
  const fields = outline.filter((label) => fieldTerms.test(label)).slice(0, 16);
  const headings = outline.filter((label) => !fieldTerms.test(label)).slice(0, 18);
  const siblings = siblingsFor(screen, allScreens);
  const category = classify(screen, outline);
  const title = titleOf(screen);
  const heroLines = headings.filter((label) => label.length > 7).slice(0, 2);
  const isPopup = screen.kind === 'legacy-popup' || screen.kind === 'popup';
  const panel: ReactNode = category === 'building'
    ? <BuildingPanel screen={screen} fields={fields} headings={headings} selected={selected} onSelect={setSelected}/>
    : category === 'application'
            ? <section className="hs-panel hs-legacy-application"><p className="hs-kicker">진행 단계</p><h2>{title}</h2>{heroLines[0] && <p>{heroLines[0]}</p>}<LocalForm className="hs-stack"><SourceFields fields={fields.length ? fields : ['이름','연락처','이메일']} compact/><LocalSubmit text="입력 내용 확인"/></LocalForm>{siblings.length > 0 && <nav className="hs-legacy-steps">{siblings.slice(0, 6).map((item,index)=><a href={screenHref(item.id)} key={item.id}><span>{String(index+1).padStart(2,'0')}</span>{titleOf(item)}</a>)}</nav>}</section>
      : category === 'directory'
        ? <DirectoryPanel screen={screen} fields={fields} headings={headings} siblings={siblings} selected={selected} onSelect={setSelected}/>
        : category === 'admin'
          ? <AdminPanel screen={screen} fields={fields} headings={headings} siblings={siblings} selected={selected} onSelect={setSelected}/>
          : <div className="hs-legacy-workspace">
            <section className="hs-panel hs-legacy-intro"><p className="hs-kicker">{screen.role} · 운영 현황</p><h2>{heroLines[0] || screen.title}</h2><p>{heroLines[1] || '업무 현황과 다음 작업을 한눈에 살펴봅니다.'}</p></section>
            <section className="hs-legacy-dashboard-grid">{(headings.length ? headings.slice(0, 6) : ['운영 현황','최근 기록','확인할 항목']).map((label,index)=><button type="button" className={`hs-metric hs-legacy-metric ${selected === index ? 'active' : ''}`} key={`${label}-${index}`} onClick={()=>setSelected(index)}><span>{label}</span><strong>{['—','—','—'][index % 3]}</strong><p>{selected === index ? '선택한 항목' : '자세히 확인'}</p></button>)}</section>
            {fields.length > 0 && <section className="hs-panel"><h2>확인할 정보</h2><SourceFields fields={fields.slice(0, 8)} compact/></section>}
            {siblings.length > 0 && <nav className="hs-legacy-link-grid">{siblings.slice(0, 12).map((item)=><a className="hs-panel" href={screenHref(item.id)} key={item.id}><span className="hs-kicker">{item.kind}</span><strong>{titleOf(item)}</strong><span>열어보기 <ArrowRight size={16}/></span></a>)}</nav>}
          </div>;

  if (isPopup) {
    return <PopoverScreen screen={screen} wide><div className={`hs-legacy-popup hs-legacy-${category}`}><p>{heroLines[0] || screen.title}</p>{panel}</div></PopoverScreen>;
  }

  return <SuiteFrame screen={screen}><main className="hs-main">
    <div className="hs-title-row"><div><p className="hs-kicker">{screen.role} · {category === 'building' ? '지역 분석' : category === 'application' ? '정보 입력' : category === 'directory' ? '목록 탐색' : category === 'admin' ? '관리 설정' : '운영 현황'}</p><h1>{title}</h1>{heroLines[1] && <p>{heroLines[1]}</p>}</div>{screen.parent && <a className="hs-btn secondary" href={screenHref(screen.parent)}><ArrowRight size={17}/>이전 화면</a>}</div>
    {siblings.length > 0 && <nav className="hs-tabs" aria-label="관련 화면">{siblings.slice(0, 10).map((item)=><a key={item.id} href={screenHref(item.id)}>{titleOf(item)}</a>)}</nav>}
    {panel}
    {siblings.length > 10 && <nav className="hs-legacy-link-grid hs-legacy-more" aria-label="더 많은 관련 화면">{siblings.slice(10).map((item)=><a className="hs-btn secondary" key={item.id} href={screenHref(item.id)}>{titleOf(item)}</a>)}</nav>}
  </main></SuiteFrame>;
}
