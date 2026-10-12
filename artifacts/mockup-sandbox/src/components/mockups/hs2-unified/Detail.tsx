import { useState, type FormEvent } from 'react';
import { ArrowLeft, BedDouble, CalendarDays, Heart, MapPin, Maximize2, Users, Wifi } from 'lucide-react';
import './_group.css';
import { Header, LocalDialog, imageUrl, placeById, previewHref, priceText } from './_shared';

export function Detail() {
  const params = new URLSearchParams(window.location.search);
  const place = placeById(params.get('id'));
  const [favorite, setFavorite] = useState(false);
  const [checkIn, setCheckIn] = useState('');
  const [checkOut, setCheckOut] = useState('');
  const [guests, setGuests] = useState(String(Math.min(2, place.guests)));
  const [activePhoto, setActivePhoto] = useState<number | null>(null);
  const [dialog, setDialog] = useState(false);
  const [dateError, setDateError] = useState(false);
  const photoSet = [place.image, (place.image % 4) + 1, ((place.image + 1) % 4) + 1, ((place.image + 2) % 4) + 1];
  const requestStay = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!checkIn || !checkOut || new Date(checkOut).getTime() <= new Date(checkIn).getTime()) {
      setDateError(true);
      setDialog(true);
      return;
    }
    setDateError(false);
    setDialog(true);
  };
  const stepPhoto = (direction: number) => setActivePhoto((current) => current === null ? 0 : (current + direction + photoSet.length) % photoSet.length);
  return <div className="hs2 hs2-shell">
    <Header current="Detail"/>
    <main className="hs2-wrap hs2-detail-wrap">
      <a className="hs2-back" href={previewHref('Consumer')}><ArrowLeft size={18}/> 검색 결과로 돌아가기</a>
      <div className="hs2-detail-topline"><span className={`hs2-chip ${place.kind === 'lodging' ? 'lodging' : ''}`}>{place.kind === 'lodging' ? '숙박시설' : '주거형 단기임대'}</span><span className="hs2-muted"> 합성 성수 데이터 · 정확한 위치 보호</span></div>
      <div className="hs2-gallery" aria-label="숙소 사진 갤러리">
        {photoSet.map((number, index) => <button key={`${number}-${index}`} onClick={() => setActivePhoto(index)} aria-label={`사진 ${index + 1} 크게 보기`}><img src={imageUrl(number)} alt={`${place.title} 내부 사진 ${index + 1}`}/></button>)}
        <button className="hs2-gallery-count" onClick={() => setActivePhoto(0)}><Maximize2 size={17}/> 사진 모두 보기</button>
      </div>
      <div className="hs2-detail-layout">
        <article className="hs2-detail-content">
          <div className="hs2-detail-title">
            <div><p className="hs2-eyebrow">{place.neighborhood} · {place.walk}</p><h1>{place.title}</h1><p>{place.neighborhood}, 서울 · {place.walk}</p></div>
            <button className={`hs2-icon-btn ${favorite ? 'hs2-loved' : ''}`} onClick={() => setFavorite(!favorite)} aria-pressed={favorite} aria-label={favorite ? '관심 숙소 해제' : '관심 숙소 저장'}><Heart size={20} fill={favorite ? 'currentColor' : 'none'}/></button>
          </div>
          <div className="hs2-detail-facts">
            <span><Users size={19}/> 최대 {place.guests}명</span><span><BedDouble size={19}/> 침실 {place.rooms}개</span><span><Maximize2 size={18}/> {place.area}㎡</span><span><MapPin size={19}/> {place.walk}</span>
          </div>
          <section className="hs2-detail-section"><h2>이 공간에 대하여</h2><p>{place.description}</p></section>
          <section className="hs2-detail-section"><h2>편의시설</h2><div className="hs2-amenities">{place.amenities.map((item) => <span key={item}><Wifi size={17}/>{item}</span>)}</div></section>
          <section className="hs2-detail-section"><h2>동네 둘러보기</h2><div className="hs2-neighborhood-note"><MapPin size={20}/><p><strong>{place.neighborhood}</strong><br/>성수의 오래된 골목과 새로 문을 연 가게가 만나는 동네입니다. 지도에는 대략적인 위치만 표시됩니다.</p></div></section>
          <div className="hs2-notice">이 페이지는 합성 데이터로 구성된 디자인 시안입니다. 숙소의 실제 존재, 위치, 재고 및 조건을 확인하지 않습니다.</div>
        </article>
        <aside className="hs2-booking" aria-label="날짜와 인원 입력">
          <div className={`hs2-booking-price ${place.kind === 'lodging' ? 'lodging' : ''}`}>{priceText(place)} <small>표시 기준</small></div>
          <p className="hs2-booking-sub">희망 일정을 입력해 보세요</p>
          <form onSubmit={requestStay}>
            <label className="hs2-label"><CalendarDays size={16}/> 체크인<input className="hs2-input" type="date" required value={checkIn} onChange={(e)=>setCheckIn(e.target.value)}/></label>
            <label className="hs2-label"><CalendarDays size={16}/> 체크아웃<input className="hs2-input" type="date" required value={checkOut} onChange={(e)=>setCheckOut(e.target.value)}/></label>
            <label className="hs2-label"><Users size={16}/> 인원<select className="hs2-select" value={guests} onChange={(e)=>setGuests(e.target.value)}>{Array.from({length:place.guests},(_,i)=>i+1).map((n)=><option key={n} value={n}>{n}명</option>)}</select></label>
            <button type="submit" className={`hs2-btn hs2-booking-submit ${place.kind === 'lodging' ? 'mustard' : ''}`}>이 일정 확인하기</button>
          </form>
          <p className="hs2-booking-disclaimer">이용 가능 여부와 총액은 실제 조회되지 않습니다. 이 시안에서는 예약·결제가 진행되지 않습니다.</p>
          <div className="hs2-booking-policy"><span>요금 단위</span><strong>{place.basis === 'week' ? '주 기준' : place.basis === 'day' ? '1일 기준' : '월 기준'}</strong></div>
          {place.basis === 'month' && <p className="hs2-month-note">등록된 실제 합성 요금은 월 단위입니다. 주·일 금액으로 환산하지 않았습니다.</p>}
        </aside>
      </div>
    </main>
    <footer className="hs2-footer">HOME &amp; STAY · 성수 디자인 미리보기 · 실제 예약 기능 없음</footer>
    <LocalDialog open={dialog} title={dateError ? '날짜를 다시 확인해 주세요' : '일정 확인 미리보기'} onClose={() => setDialog(false)}>
      <div className="hs2-preview-receipt">{dateError ? <p>체크아웃은 체크인보다 뒤 날짜로 선택해 주세요. 이 시안에는 예약 가능한 날짜 정보가 연결되어 있지 않습니다.</p> : <><p><strong>{place.title}</strong></p><p>{checkIn} — {checkOut} · {guests}명</p><p>이 작업은 이 화면 안에서만 보여주는 예시입니다. 실제 예약 요청이나 결제, 재고 확인은 발생하지 않습니다.</p></>}</div>
    </LocalDialog>
    <LocalDialog open={activePhoto !== null} title={`${place.title} · 사진`} onClose={() => setActivePhoto(null)}>
      {activePhoto !== null && <div className="hs2-lightbox"><button className="hs2-btn secondary" onClick={() => stepPhoto(-1)}>이전 사진</button><img src={imageUrl(photoSet[activePhoto])} alt={`${place.title} 내부 사진 ${activePhoto+1}`}/><button className="hs2-btn secondary" onClick={() => stepPhoto(1)}>다음 사진</button><span>{activePhoto + 1} / {photoSet.length}</span></div>}
    </LocalDialog>
  </div>;
}
export default Detail;
