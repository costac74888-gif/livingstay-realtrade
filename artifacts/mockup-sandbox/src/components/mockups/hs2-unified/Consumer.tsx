import { useMemo, useState, type FormEvent } from 'react';
import { Heart, MapPin, Search, Users } from 'lucide-react';
import './_group.css';
import { Header, KakaoMap, LocalDialog, imageUrl, places, previewHref, priceText, sampleAvailability, type Place } from './_shared';

export function Consumer() {
  const [query, setQuery] = useState('성수동');
  const [checkIn, setCheckIn] = useState('');
  const [checkOut, setCheckOut] = useState('');
  const [guests, setGuests] = useState('');
  const [submitted, setSubmitted] = useState({ query: '성수동', checkIn: '', checkOut: '', guests: '' });
  const [favorites, setFavorites] = useState<string[]>([]);
  const [activeId, setActiveId] = useState('');
  const [sort, setSort] = useState('recommended');
  const [dialog, setDialog] = useState<Place | null>(null);
  const filtered = useMemo(() => {
    const q = submitted.query.trim().toLowerCase();
    const rows = places.filter((place) => {
      const matchesArea = !q || `${place.title} ${place.neighborhood} ${place.walk}`.toLowerCase().includes(q);
      const matchesGuests = !submitted.guests || place.guests >= Number(submitted.guests);
      const window = sampleAvailability[place.id];
      const matchesDates = !submitted.checkIn || !submitted.checkOut || (!!window && window[0] <= submitted.checkIn && window[1] >= submitted.checkOut);
      return matchesArea && matchesGuests && matchesDates;
    });
    if (sort === 'low') rows.sort((a,b) => a.price - b.price);
    if (sort === 'high') rows.sort((a,b) => b.price - a.price);
    return rows;
  }, [submitted, sort]);
  const doSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (checkIn && checkOut && new Date(checkOut).getTime() <= new Date(checkIn).getTime()) {
      setDialog({ ...places[0], title: '날짜를 다시 확인해 주세요', description: '퇴실일은 입실일보다 뒤 날짜로 선택해 주세요.' });
      return;
    }
    setSubmitted({ query, checkIn, checkOut, guests });
    setActiveId('');
  };
  const toggleFavorite = (id: string) => setFavorites((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const formatDate = (date: string) => date ? new Date(`${date}T00:00:00`).toLocaleDateString('ko-KR',{month:'short',day:'numeric'}) : '';
  return <div className="hs2 hs2-shell">
    <Header current="Consumer"/>
    <main className="hs2-wrap">
      <div className="hs2-search-head">
        <div><p className="hs2-eyebrow">HOME &amp; STAY / SEONGSU</p><h1>동네를 고르고, 머물 곳을 찾다</h1><p>성수의 집과 숙소를 한눈에 비교해 보세요.</p></div>
      </div>
      <form className="hs2-search-form" onSubmit={doSearch}>
        <label className="hs2-label">지역 또는 숙소<input className="hs2-input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="동네, 역, 숙소 이름"/></label>
        <label className="hs2-label">체크인<input className="hs2-input" type="date" value={checkIn} onChange={(e) => setCheckIn(e.target.value)}/></label>
        <label className="hs2-label">체크아웃<input className="hs2-input" type="date" value={checkOut} onChange={(e) => setCheckOut(e.target.value)}/></label>
        <label className="hs2-label">인원<select className="hs2-select" value={guests} onChange={(e) => setGuests(e.target.value)}><option value="">전체</option>{[1,2,3,4,5].map((n)=><option key={n} value={n}>{n}{n === 5 ? '명 이상' : '명'}</option>)}</select></label>
        <button className="hs2-btn" type="submit"><Search size={18}/>검색</button>
      </form>
      <div className="hs2-search-workspace">
        <section className="hs2-result-column" aria-label="단기 숙소 검색 결과">
          <div className="hs2-results-bar">
            <strong>{filtered.length}곳의 단기 숙소</strong>
            <select className="hs2-select hs2-sort" aria-label="정렬" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="recommended">추천순</option><option value="low">표시 금액 낮은 순</option><option value="high">표시 금액 높은 순</option>
            </select>
          </div>
          {submitted.checkIn && <div className="hs2-date-summary">{formatDate(submitted.checkIn)} — {formatDate(submitted.checkOut)} · {submitted.guests || '전체'}명 기준으로 둘러보고 있어요</div>}
          <div className="hs2-listings">
            {filtered.map((place) => <article className={`hs2-card ${activeId === place.id ? 'selected' : ''}`} key={place.id} onClick={() => setActiveId(place.id)} aria-label={`${place.title} 선택`}>
              <button className={`hs2-card-photo ${activeId === place.id ? 'active' : ''}`} onClick={() => { setActiveId(place.id); window.location.href = `${previewHref('Detail')}?id=${place.id}`; }} aria-label={`${place.title} 상세 보기`}>
                <img src={imageUrl(place.image)} alt={`${place.title}의 거실`} loading="lazy"/>
                <span className={`hs2-chip ${place.kind === 'lodging' ? 'lodging' : ''}`}>{place.kind === 'lodging' ? '숙박시설' : '주거형 단기임대'}</span>
              </button>
              <button className={`hs2-icon-btn hs2-favorite ${favorites.includes(place.id) ? 'active' : ''}`} aria-label={favorites.includes(place.id) ? '관심 숙소 해제' : '관심 숙소 저장'} aria-pressed={favorites.includes(place.id)} onClick={(event) => { event.stopPropagation(); toggleFavorite(place.id); }}>
                <Heart size={19} fill={favorites.includes(place.id) ? 'currentColor' : 'none'}/>
              </button>
              <div className="hs2-card-copy" onClick={() => setActiveId(place.id)}>
                <p className="hs2-card-title">{place.title}</p>
                <p className="hs2-card-meta"><MapPin size={14}/> {place.neighborhood} · {place.walk} · <Users size={14}/> 최대 {place.guests}명</p>
                <p className={`hs2-card-price ${place.kind === 'lodging' ? 'lodging' : ''}`}>{priceText(place)} <small>기준 요금</small></p>
                <a className="hs2-card-open" href={`${previewHref('Detail')}?id=${place.id}`} onClick={(event) => event.stopPropagation()}>숙소 자세히 보기</a>
              </div>
            </article>)}
            {!filtered.length && <div className="hs2-empty"><p className="hs2-eyebrow">NO MATCHES</p><strong>조건에 맞는 숙소가 아직 없습니다.</strong><p>지역이나 인원을 바꿔 다시 검색해 보세요.</p></div>}
          </div>
          <p className="hs2-list-note">금액과 예시 날짜 범위는 모두 합성 데이터입니다. 입력 날짜는 시안 범위에만 적용되며 실제 예약 가능 여부를 뜻하지 않습니다.</p>
        </section>
        <section className="hs2-map-panel" aria-label="성수동 숙소 지도">
          <KakaoMap entries={filtered} activeId={activeId} onSelect={setActiveId}/>
          <div className="hs2-map-overlay"><strong>성수동</strong><span>{filtered.length}개 숙소 위치</span></div>
          {activeId && <div className="hs2-map-selected">{places.find((p)=>p.id===activeId)?.title}<button onClick={()=>{ window.location.href = `${previewHref('Detail')}?id=${activeId}`; }}>상세 보기</button></div>}
        </section>
      </div>
    </main>
    <LocalDialog open={!!dialog} title={dialog?.title ?? ''} onClose={() => setDialog(null)}>
      <p className="hs2-dialog-copy">{dialog?.description}</p>
    </LocalDialog>
  </div>;
}
export default Consumer;
