import { useState, type FormEvent, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, Heart, Search, Star, X } from 'lucide-react';
import { KakaoMap, imageUrl, places, priceText, type Place } from '../hs2-unified/_shared';
import './_suite.css';

export type Screen = {
  id: string;
  role: string;
  title: string;
  view: string;
  kind: string;
  parent: string;
  basis?: string;
  design_status?: string;
  function_status?: string;
  source_files?: string[];
  source_outline?: string[];
};

export const screenHref = (id: string) => `?screen=${encodeURIComponent(id)}`;
export const roleRoot = (role: string) => role === '사용자' ? 'C001' : role === '임대인' ? 'O001' : 'A001';
export const screenById = (screens: Screen[], id: string) => screens.find((screen) => screen.id === id) ?? screens[0];
export const syntheticPlaces = places;
export const stayLabel = (place: Place) => place.kind === 'home' ? '주거형 단기임대' : '숙박시설';
export const displayPrice = (place: Place) => priceText(place);

export function Header({ currentRole }: { currentRole: string }) {
  const links = [
    ['사용자', 'C001', '머물 곳 찾기'],
    ['임대인', 'O001', '공간 운영'],
    ['관리자', 'A001', '관리자'],
  ];
  return <header className="hs-header">
    <a className="hs-logo" href={screenHref('C001')} aria-label="HOME & STAY 홈">
      <img src="/__mockup/images/hs2-unified/brand-logo.png" alt="HOME & STAY"/>
    </a>
    <nav className="hs-header-nav" aria-label="역할별 화면">
      {links.map(([role, id, label]) => <a key={id} href={screenHref(id)} aria-current={currentRole === role ? 'page' : undefined}>{label}</a>)}
    </nav>
  </header>;
}

export function SuiteFrame({ screen, children, role, hideFooter = false }: { screen: Screen; children: ReactNode; role?: string; hideFooter?: boolean }) {
  return <div className="hs-suite" data-screen-id={screen.id} data-screen-kind={screen.kind} data-testid={`hs-screen-${screen.id}`}>
    <Header currentRole={role ?? screen.role}/>
    {children}
    {!hideFooter && <footer className="hs-footer">HOME &amp; STAY · 머무는 공간을 살피는 기준</footer>}
  </div>;
}

export function TitleBlock({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="hs-title-row"><div>{eyebrow && <p className="hs-kicker">{eyebrow}</p>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action && <div>{action}</div>}</div>;
}

export function Field({ label, type = 'text', placeholder, value, onChange, options, required = false, wide = false }: {
  label: string; type?: string; placeholder?: string; value?: string; onChange?: (value: string) => void; options?: string[]; required?: boolean; wide?: boolean;
}) {
  const cls = `hs-field ${wide ? 'hs-wide' : ''}`;
  return <label className={cls}>{label}{options
    ? <select value={value} onChange={(e) => onChange?.(e.target.value)}>{options.map((option) => <option key={option}>{option}</option>)}</select>
    : type === 'textarea'
      ? <textarea placeholder={placeholder} value={value} onChange={(e) => onChange?.(e.target.value)} required={required}/>
      : <input type={type} placeholder={placeholder} value={value} onChange={(e) => onChange?.(e.target.value)} readOnly={value !== undefined && !onChange} required={required}/>}
  </label>;
}

export function LocalButton({ children, target, onClick, variant = 'primary', type = 'button' }: {
  children: ReactNode; target?: string; onClick?: () => void; variant?: 'primary' | 'secondary' | 'ghost' | 'mustard'; type?: 'button' | 'submit';
}) {
  const className = `hs-btn ${variant === 'primary' ? '' : variant}`;
  if (target) return <a className={className} href={screenHref(target)}>{children}</a>;
  return <button className={className} type={type} onClick={onClick}>{children}</button>;
}

export function LocalForm({ children, onDone, className = '' }: { children: ReactNode; onDone?: (event: FormEvent<HTMLFormElement>) => void; className?: string }) {
  const [message, setMessage] = useState('');
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onDone?.(event);
    setMessage('입력 내용을 확인했습니다.');
    window.setTimeout(() => setMessage(''), 2500);
  };
  return <form className={className} onSubmit={submit}>
    {children}
    {message && <div role="status" className="hs-toast">{message}</div>}
  </form>;
}

export function ListingCard({ place, onFavorite, favorite }: { place: Place; onFavorite?: () => void; favorite?: boolean }) {
  return <article className="hs-stay-card">
    <span className={`hs-card-tag ${place.kind === 'lodging' ? 'stay' : ''}`}>{stayLabel(place)}</span>
    <button className="hs-icon-button hs-card-heart" aria-label={favorite ? '관심에서 제거' : '관심 저장'} aria-pressed={!!favorite} onClick={onFavorite}><Heart size={19} fill={favorite ? 'currentColor' : 'none'}/></button>
    <a className="hs-card-photo" href={screenHref('C002')} aria-label={`${place.title} 상세 보기`}><img src={imageUrl(place.image)} alt={`${place.title}의 실내`} loading="lazy"/></a>
    <div className="hs-stay-copy">
      <h3>{place.title}</h3>
      <p>{place.neighborhood} · {place.walk}</p>
      <p>최대 {place.guests}명 · 침실 {place.rooms}개 · {place.area}㎡</p>
      <div className={`hs-price ${place.kind === 'lodging' ? 'stay' : ''}`}>{displayPrice(place)}</div>
      <a href={screenHref('C002')}>공간 자세히 보기 <ArrowRight size={15}/></a>
    </div>
  </article>;
}

export function SearchView({ screen }: { screen: Screen }) {
  const [area, setArea] = useState('성수동');
  const [guests, setGuests] = useState('전체');
  const [sort, setSort] = useState('추천순');
  const [likes, setLikes] = useState<string[]>([]);
  const [checkIn, setCheckIn] = useState('');
  const [checkOut, setCheckOut] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [searchMessage, setSearchMessage] = useState('');
  const sampleAvailability: Record<string, [string, string]> = {
    p1:['2026-10-01','2027-05-31'],p2:['2026-10-01','2027-12-31'],p3:['2026-11-01','2027-12-31'],
    p4:['2026-10-15','2027-03-31'],p5:['2026-10-01','2027-12-31'],p6:['2026-12-01','2027-12-31'],
    p7:['2026-10-01','2027-12-31'],p8:['2026-10-01','2027-03-31'],p9:['2026-10-01','2027-10-31'],
    p10:['2026-11-01','2027-12-31'],p11:['2026-10-01','2027-12-31'],p12:['2026-10-01','2027-06-30'],
  };
  const rows = [...syntheticPlaces]
    .filter((place) => !area || `${place.neighborhood}${place.title}`.includes(area) || area === '성수동')
    .filter((place) => guests === '전체' || place.guests >= Number(guests.replace(/\D/g, '')))
    .filter((place) => !checkIn || !checkOut || (!!sampleAvailability[place.id] && sampleAvailability[place.id][0] <= checkIn && sampleAvailability[place.id][1] >= checkOut))
    .sort((a, b) => sort === '낮은 금액순' ? a.price - b.price : sort === '높은 금액순' ? b.price - a.price : a.id.localeCompare(b.id));
  return <SuiteFrame screen={screen}><main className="hs-main">
    <TitleBlock eyebrow="HOME & STAY / SEONGSU" title="머물 곳을, 비교해 보세요." description="생활형 단기 임대와 하루 숙박을 한 화면에서 살펴봅니다."/>
    <form className="hs-search-fields" onSubmit={(e) => e.preventDefault()}>
      <Field label="지역 · 건물 · 지하철" value={area} onChange={setArea} placeholder="동네나 역 이름"/>
      <Field label="입실일" type="date" value={checkIn} onChange={setCheckIn}/>
      <Field label="퇴실일" type="date" value={checkOut} onChange={setCheckOut}/>
      <Field label="인원" value={guests} onChange={setGuests} options={['전체','1명','2명','3명','4명']}/>
      <LocalButton onClick={() => {
        const message = checkIn && checkOut && checkOut <= checkIn ? '퇴실일은 입실일 다음 날짜로 선택해 주세요.' : `${rows.length}곳의 공간을 조건에 맞춰 살펴봅니다.`;
        setSearchMessage(message);
        window.setTimeout(() => setSearchMessage(''),2500);
      }}><Search size={18}/>검색</LocalButton>
    </form>
    {searchMessage && <p role="status" className="hs-notice" style={{marginBottom:16}}>{searchMessage}</p>}
    <div className="hs-search-workspace">
      <section className="hs-result-pane" aria-label="검색 결과 목록">
        <div className="hs-title-row"><div><h2 style={{fontSize:22,margin:0}}>{rows.length}곳의 머물 곳</h2><p>주간 임대와 1일 숙박의 기준 요금을 확인하세요.</p></div><Field label="정렬" value={sort} onChange={setSort} options={['추천순','낮은 금액순','높은 금액순']}/></div>
        <div className="hs-result-grid">{rows.map((place) => <ListingCard key={place.id} place={place} favorite={likes.includes(place.id)} onFavorite={() => setLikes((prev) => prev.includes(place.id) ? prev.filter((id) => id !== place.id) : [...prev, place.id])}/>)}</div>
      </section>
      <section className="hs-map-pane" aria-label="대략적인 숙소 위치"><KakaoMap entries={rows} activeId={selectedId} onSelect={setSelectedId}/><div className="hs-map-label"><strong>서울 성수동</strong><br/>표시 위치는 구역 단위입니다.</div>{selectedId && <div className="hs-map-label" style={{top:'auto',bottom:18}}>{syntheticPlaces.find((place)=>place.id === selectedId)?.title}<br/><a href={screenHref('C002')}>상세 보기</a></div>}</section>
    </div>
  </main></SuiteFrame>;
}

export function DetailView({ screen, month = false, missing = false }: { screen: Screen; month?: boolean; missing?: boolean }) {
  const place = month ? syntheticPlaces[6] : missing ? syntheticPlaces[4] : syntheticPlaces[0];
  const [favorite, setFavorite] = useState(false);
  const [photoIndex, setPhotoIndex] = useState(0);
  const photos = [place.image, place.image % 4 + 1, (place.image + 1) % 4 + 1, (place.image + 2) % 4 + 1];
  return <SuiteFrame screen={screen}><main className="hs-main">
    <p className="hs-kicker">{place.neighborhood} · {place.walk} · 정확한 위치 비공개</p>
    <div className="hs-title-row"><div><h1>{place.title}</h1><p>최대 {place.guests}명 · 침실 {place.rooms}개 · {place.area}㎡</p></div><div className="hs-pills">
      <button className={`hs-icon-button ${favorite ? 'active' : ''}`} aria-label="관심 숙소 저장" onClick={() => setFavorite(!favorite)}><Heart fill={favorite ? 'currentColor' : 'none'}/></button>
      <a className="hs-btn secondary" href={screenHref('C003')}>공유</a>
    </div></div>
    <div className="hs-gallery" aria-label="숙소 사진">
      {photos.map((photo, index) => <button key={`${photo}-${index}`} onClick={() => { setPhotoIndex(index); window.location.href = screenHref('C004'); }} aria-label={`사진 ${index + 1} 전체 보기`}><img src={imageUrl(photo)} alt={`${place.title} 사진 ${index + 1}`}/></button>)}
    </div>
    <div className="hs-detail-columns">
      <article className="hs-detail-content">
        <div className="hs-facts"><span>최대 {place.guests}명</span><span>침실 {place.rooms}개</span><span>전용 {place.area}㎡</span><span>{place.kind === 'home' ? '독립형 주거 공간' : '단독 객실'}</span></div>
        <section><h2>공간 소개</h2><p>{place.description}</p><a className="hs-link-button" href={screenHref('C005')}>소개 더보기</a></section>
        <section><h2>편의시설</h2><div className="hs-pills">{place.amenities.map((amenity) => <span className="hs-pill" key={amenity}>{amenity}</span>)}</div><p><a className="hs-link-button" href={screenHref('C006')}>편의시설 전체 보기</a></p></section>
        <section><h2>대략적인 위치</h2><p>{place.neighborhood} 인근 · 역까지 도보 {place.walk.match(/\d+/)?.[0] ?? '7'}분</p><p>정확한 주소와 건물 위치는 공개되지 않습니다.</p><a className="hs-link-button" href={screenHref('C034')}>지도에서 확인</a></section>
        <section><h2>호스트 · 후기</h2><p>호스트 이수현 · 응답이 빠른 운영자</p><p><Star size={17} fill="currentColor"/> 4.87 · 18개 후기</p><div className="hs-pills"><a className="hs-pill" href={screenHref('C035')}>호스트 정보</a><a className="hs-pill" href={screenHref('C007')}>후기 전체</a></div></section>
        <section><h2>규칙과 취소</h2><p>체크인 오후 3시 이후 · 체크아웃 오전 11시까지</p><a className="hs-link-button" href={screenHref('C008')}>규칙·취소 정책 보기</a></section>
      </article>
      <aside className="hs-panel hs-booking-panel">
        <div className={`hs-price ${place.kind === 'lodging' ? 'stay' : ''}`}>{missing ? '요금 미등록' : displayPrice(place)}</div>
        {month && <p>월 기준 등록 요금이며 주·일 요금으로 환산하지 않습니다.</p>}
        <div className="hs-stack" style={{marginTop:18}}>
          <Field label="체크인" type="date"/><Field label="체크아웃" type="date"/><Field label="인원" options={['1명','2명','3명']}/>
          <a className="hs-btn" href={screenHref('C037')}>날짜와 인원 선택</a>
          {!missing && <a className="hs-btn secondary" href={screenHref('C013')}>예약 조건 확인</a>}
        </div>
        <hr className="hs-rule"/>
        {!missing && <><p><a href={screenHref('C009')}>요금 내역 자세히 보기</a></p><p><a href={screenHref('C008')}>규칙 및 취소 정책</a></p></>}
        {missing && <p>호스트가 아직 요금을 등록하지 않았습니다. 금액을 추정하거나 0원으로 표시하지 않습니다.</p>}
      </aside>
    </div>
    <div className="hs-mobile-booking"><div><strong className={`hs-price ${place.kind === 'lodging' ? 'stay' : ''}`}>{missing ? '요금 미등록' : displayPrice(place)}</strong></div><a className="hs-btn" href={screenHref('C037')}>일정 선택</a></div>
  </main></SuiteFrame>;
}

export function PopoverScreen({ screen, children, wide = false }: { screen: Screen; children: ReactNode; wide?: boolean }) {
  return <SuiteFrame screen={screen}><main className="hs-modal-stage"><section className={`hs-modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true">
    <div className="hs-modal-head"><div><p className="hs-kicker">{screen.role} · {screen.kind === 'popup' ? '자세히 보기' : '안내'}</p><h1>{screen.title}</h1></div><a href={screen.parent && screen.parent !== screen.id ? screenHref(screen.parent) : screenHref(roleRoot(screen.role))} aria-label="닫기"><X size={22}/></a></div>{children}
  </section></main></SuiteFrame>;
}

export function Notice({ children }: { children: ReactNode }) { return <div className="hs-notice">{children}</div>; }
export function Photo({ image, alt }: { image: number; alt: string }) { return <img src={imageUrl(image)} alt={alt}/>; }
export function GalleryViewer({ screen }: { screen: Screen }) {
  const [index, setIndex] = useState(0);
  const photos = [1,2,3,4];
  return <PopoverScreen screen={screen} wide><div className="hs-gallery-viewer"><div className="hero"><Photo image={photos[index]} alt={`공간 전체 사진 ${index + 1}`}/></div><div className="hs-gallery-thumbs">{photos.map((photo, i) => <button key={photo} onClick={() => setIndex(i)} aria-label={`${i + 1}번 사진 보기`}><Photo image={photo} alt={`공간 썸네일 ${i + 1}`}/></button>)}</div></div><div className="hs-title-row" style={{marginTop:15}}><span>{index + 1} / {photos.length} · 숙소 전체 사진</span><div className="hs-pills"><button className="hs-btn secondary" onClick={() => setIndex((index + photos.length - 1) % photos.length)}><ArrowLeft size={16}/>이전</button><button className="hs-btn secondary" onClick={() => setIndex((index + 1) % photos.length)}>다음<ArrowRight size={16}/></button></div></div></PopoverScreen>;
}

export function LocalSubmit({ text = '이 화면에서 확인', target }: { text?: string; target?: string }) {
  return <div style={{display:'flex',gap:10,marginTop:18}}>{target && <a className="hs-btn secondary" href={screenHref(target)}>다음 단계</a>}<button className="hs-btn" type="submit">{text}</button></div>;
}
