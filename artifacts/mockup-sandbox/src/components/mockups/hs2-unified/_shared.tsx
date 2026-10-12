import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowUpRight, Building2, ChevronDown, X } from 'lucide-react';

export type Place = {
  id: string; title: string; neighborhood: string; walk: string; guests: number;
  rooms: number; area: number; image: number; kind: 'home' | 'lodging';
  price: number; basis: 'week' | 'day' | 'month'; description: string; lat: number; lng: number;
  layer?: string; mapLabel?: string;
  amenities: string[];
};

export const places: Place[] = [
  { id:'p1', title:'햇살이 머무는 성수 빌라', neighborhood:'성수동1가', walk:'서울숲역 7분', guests:3, rooms:2, area:43, image:1, kind:'home', price:430000, basis:'week', description:'낮은 창으로 오전 빛이 길게 들어오는 조용한 집입니다. 서울숲 산책과 동네의 작은 가게들을 가까이 누릴 수 있습니다.', lat:37.5442, lng:127.0452, amenities:['주방','세탁기','와이파이'] },
  { id:'p2', title:'스테이 모노 성수', neighborhood:'성수동2가', walk:'성수역 5분', guests:2, rooms:1, area:28, image:2, kind:'lodging', price:118000, basis:'day', description:'차분한 회벽과 오크 가구가 어우러진 작은 숙박 공간. 늦은 오후 골목 산책을 즐겨보세요.', lat:37.5449, lng:127.0556, amenities:['와이파이','욕조','짐 보관'] },
  { id:'p3', title:'서울숲 옆 작은 테라스', neighborhood:'성수동1가', walk:'서울숲역 4분', guests:2, rooms:1, area:36, image:3, kind:'home', price:510000, basis:'week', description:'초록이 보이는 테라스와 단정한 주방이 있는 집. 1주 이상 천천히 머물기에 알맞습니다.', lat:37.5472, lng:127.0448, amenities:['테라스','주방','세탁기'] },
  { id:'p4', title:'온기 스테이 서울숲', neighborhood:'성수동1가', walk:'뚝섬역 8분', guests:4, rooms:2, area:52, image:4, kind:'lodging', price:164000, basis:'day', description:'나무의 결을 살린 넉넉한 객실. 친구나 가족과 함께 서울숲 주변을 둘러보기 좋습니다.', lat:37.5476, lng:127.0511, amenities:['주방','와이파이','엘리베이터'] },
  { id:'p5', title:'성수 골목의 조용한 집', neighborhood:'성수동2가', walk:'성수역 9분', guests:2, rooms:1, area:31, image:1, kind:'home', price:385000, basis:'week', description:'생활감 있는 골목 안쪽, 필요한 것을 정갈하게 갖춘 독립형 단기 임대입니다.', lat:37.5413, lng:127.0588, amenities:['주방','세탁기'] },
  { id:'p6', title:'레이어드 룸 성수', neighborhood:'성수동2가', walk:'성수역 6분', guests:2, rooms:1, area:24, image:2, kind:'lodging', price:105000, basis:'day', description:'매일 머물기 편안한 침구와 작업 테이블을 갖춘 소형 숙박 공간입니다.', lat:37.5429, lng:127.0617, amenities:['작업 테이블','와이파이','짐 보관'] },
  { id:'p7', title:'매월의 성수 하우스', neighborhood:'성수동1가', walk:'뚝섬역 6분', guests:2, rooms:1, area:39, image:3, kind:'home', price:1680000, basis:'month', description:'월 단위 체류를 위한 실제 월 요금이 등록된 집입니다. 주 단위 요금은 제공되지 않습니다.', lat:37.5484, lng:127.0463, amenities:['주방','세탁기','책상'] },
  { id:'p8', title:'작업실 같은 하루', neighborhood:'성수동2가', walk:'성수역 7분', guests:1, rooms:1, area:22, image:4, kind:'lodging', price:97000, basis:'day', description:'볕 드는 책상과 넉넉한 수납이 있는 아담한 객실입니다.', lat:37.5437, lng:127.0522, amenities:['작업 테이블','와이파이'] },
  { id:'p9', title:'골목 끝의 한옥 결', neighborhood:'성수동1가', walk:'서울숲역 9분', guests:3, rooms:2, area:47, image:1, kind:'home', price:560000, basis:'week', description:'한국적인 소재와 현대적인 편안함을 담은 단독형 체류 공간입니다.', lat:37.5502, lng:127.0488, amenities:['주방','마당','세탁기'] },
  { id:'p10', title:'코너 스테이 연무장', neighborhood:'성수동2가', walk:'성수역 4분', guests:2, rooms:1, area:26, image:2, kind:'lodging', price:132000, basis:'day', description:'연무장길의 작은 상점과 식당을 천천히 만나는 데 좋은 위치입니다.', lat:37.5431, lng:127.0572, amenities:['와이파이','짐 보관','엘리베이터'] },
  { id:'p11', title:'숲 가까이 머무는 집', neighborhood:'성수동1가', walk:'서울숲역 5분', guests:4, rooms:2, area:58, image:3, kind:'home', price:720000, basis:'week', description:'가족 단위로 머물 수 있는 넓은 집. 서울숲과 한강변 산책로가 가깝습니다.', lat:37.5497, lng:127.0429, amenities:['주방','세탁기','주차'] },
  { id:'p12', title:'담백한 하루 성수', neighborhood:'성수동2가', walk:'성수역 8분', guests:2, rooms:1, area:25, image:4, kind:'lodging', price:112000, basis:'day', description:'차분한 톤과 편안한 침구에 집중한 숙박 공간입니다.', lat:37.5409, lng:127.0543, amenities:['와이파이','욕조'] },
];
export const sampleAvailability: Record<string, [string, string]> = {
  p1:['2026-10-01','2027-05-31'], p2:['2026-10-01','2027-12-31'], p3:['2026-11-01','2027-12-31'],
  p4:['2026-10-15','2027-03-31'], p5:['2026-10-01','2027-12-31'], p6:['2026-12-01','2027-12-31'],
  p7:['2026-10-01','2027-12-31'], p8:['2026-10-01','2027-03-31'], p9:['2026-10-01','2027-10-31'],
  p10:['2026-11-01','2027-12-31'], p11:['2026-10-01','2027-12-31'], p12:['2026-10-01','2027-06-30'],
};

export const previewHref = (name: string) => `/__mockup/preview/hs2-unified/${name}`;
export const imageUrl = (num: number) => `/__mockup/images/hs2-unified/interior-${num}.jpg`;
export const priceText = (place: Place) =>
  `${place.price.toLocaleString('ko-KR')}원/${place.basis === 'week' ? '주' : place.basis === 'day' ? '일' : '월'}`;
export const placeById = (id: string | null) => places.find((place) => place.id === id) ?? places[0];

export function Header({ current }: { current: string }) {
  const options = [['Consumer','숙소 찾기'],['Detail','숙소 상세'],['Owner','임대인'],['Admin','관리자']];
  return <><header className="hs2-header">
    <a className="hs2-brand" href={previewHref('Consumer')} aria-label="HOME & STAY 숙소 찾기">
      <img src="/__mockup/images/hs2-unified/brand-logo.png" alt="HOME & STAY" />
    </a>
    <nav className="hs2-nav" aria-label="미리보기 화면">
      {options.map(([name,label]) => <a href={previewHref(name)} key={name} aria-current={current === name ? 'page' : undefined}>{label}</a>)}
    </nav>
    <details className="hs2-preview-menu">
      <summary><span>DESIGN PREVIEW</span><ChevronDown size={16}/></summary>
      <div className="hs2-preview-pop">
        {options.map(([name,label]) => <a href={previewHref(name)} key={name}>{label}<ArrowUpRight size={14} style={{float:'right',marginTop:3}}/></a>)}
        <p>화면 보기 전환 전용입니다. 실제 계정이나 권한을 부여하지 않습니다.</p>
      </div>
    </details>
  </header><div className="hs2-preview-strip">디자인 시안 · 가상 데이터 · 실제 예약·운영 권한 없음</div></>;
}

export function LocalDialog({ open, title, children, onClose, onConfirm, confirmText = '확인', confirmDisabled = false }: {
  open: boolean; title: string; children: ReactNode; onClose: () => void; onConfirm?: () => void; confirmText?: string; confirmDisabled?: boolean;
}) {
  if (!open) return null;
  return <div className="hs2-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="hs2-modal" role="dialog" aria-modal="true" aria-labelledby="hs2-dialog-title">
      <div className="hs2-modal-head"><div><p className="hs2-eyebrow">LOCAL PREVIEW ONLY</p><h2 id="hs2-dialog-title">{title}</h2></div>
        <button className="hs2-modal-close" aria-label="닫기" onClick={onClose}><X size={22}/></button>
      </div>
      <div>{children}</div>
      <div className="hs2-modal-actions"><button className="hs2-btn secondary" onClick={onClose}>닫기</button>{onConfirm && <button className="hs2-btn" disabled={confirmDisabled} onClick={onConfirm}>{confirmText}</button>}</div>
    </section>
  </div>;
}

declare global { interface Window { kakao?: any; __hs2KakaoPromise?: Promise<any>; } }
export function KakaoMap({ entries = places, activeId, onSelect }: { entries?: Place[]; activeId?: string; onSelect?: (id: string) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]);
  const boundsSignature = useRef('');
  const selectRef = useRef(onSelect);
  const [status, setStatus] = useState<'loading'|'ready'|'error'>('loading');
  const [retryCount, setRetryCount] = useState(0);
  selectRef.current = onSelect;
  useEffect(() => {
    let live = true;
    const boot = async () => {
      try {
        if (!window.__hs2KakaoPromise) {
          window.__hs2KakaoPromise = (async () => {
            const response = await fetch('/hs2/owner-map/', { credentials: 'same-origin' });
            if (!response.ok) throw new Error('map source unavailable');
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const source = Array.from(doc.querySelectorAll('script[src]')).map((script) => script.getAttribute('src') || '').find((src) => src.includes('dapi.kakao.com/v2/maps/sdk.js'));
            if (!source) throw new Error('map SDK unavailable');
            if (!window.kakao?.maps) await new Promise<void>((resolve, reject) => {
              const script = document.createElement('script');
              const secureSource = source.startsWith('//') ? `https:${source}` : source.replace(/^http:/, 'https:');
              script.src = new URL(secureSource, window.location.origin).toString();
              script.async = true;
              script.onload = () => resolve();
              script.onerror = () => reject(new Error('map SDK failed'));
              document.head.appendChild(script);
            });
            if (!window.kakao?.maps) throw new Error('map SDK unavailable');
            return window.kakao;
          })();
        }
        const kakao = await window.__hs2KakaoPromise;
        if (!kakao.maps.Map && typeof kakao.maps.load === 'function') {
          await new Promise<void>((resolve) => kakao.maps.load(resolve));
        }
        if (!live || !host.current) return;
        if (!mapRef.current) {
          mapRef.current = new kakao.maps.Map(host.current, {
            center: new kakao.maps.LatLng(37.545,127.052), level: 5,
          });
           mapRef.current.addControl(new kakao.maps.MapTypeControl(), kakao.maps.ControlPosition.TOPRIGHT);
           mapRef.current.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);
        }
        overlaysRef.current.forEach((overlay) => overlay.setMap(null));
        overlaysRef.current = entries.map((item) => {
          const marker = document.createElement('button');
          marker.type = 'button';
          marker.className = `hs2-map-marker ${item.id === activeId ? 'selected' : ''} ${item.kind === 'lodging' ? 'lodging' : ''}`;
          if (item.layer) marker.dataset.layer = item.layer;
           marker.textContent = item.mapLabel || priceText(item);
          marker.setAttribute('aria-label', item.mapLabel ? `${item.title}, ${item.mapLabel}` : `${item.title}, ${priceText(item)}`);
          marker.addEventListener('click', () => selectRef.current?.(item.id));
          const overlay = new kakao.maps.CustomOverlay({
            position: new kakao.maps.LatLng(item.lat,item.lng), content: marker, yAnchor: 1.18, zIndex: item.id === activeId ? 10 : 1,
          });
          overlay.setMap(mapRef.current);
          return overlay;
        });
         const signature = entries.map(item=>item.id).join('|');
         if(entries.length && boundsSignature.current!==signature) {
           mapRef.current.relayout();
           const bounds=new kakao.maps.LatLngBounds();
           entries.forEach(item=>bounds.extend(new kakao.maps.LatLng(item.lat,item.lng)));
           mapRef.current.setBounds(bounds,50,75,50,75);
           boundsSignature.current=signature;
         }
        setStatus('ready');
      } catch {
        if (live) { window.__hs2KakaoPromise = undefined; setStatus('error'); }
      }
    };
    void boot();
    return () => { live = false; overlaysRef.current.forEach((overlay) => overlay.setMap(null)); overlaysRef.current = []; };
  }, [entries, activeId, retryCount]);
  return <div className="hs2-map-canvas" data-map-status={status} aria-label="카카오 지도">
    <div ref={host} style={{position:'absolute',inset:0}} />
    {status === 'loading' && <div className="hs2-map-message"><div className="hs2-skeleton" aria-hidden="true"/><span>성수동 지도를 불러오고 있습니다</span></div>}
    {status === 'error' && <div className="hs2-map-message error"><Building2 size={23}/><strong>지도 연결을 사용할 수 없습니다</strong><span>지도를 불러오지 못했습니다. 숙소 목록은 계속 확인할 수 있습니다.</span><button className="hs2-small-action" onClick={()=>{setStatus('loading');setRetryCount((count)=>count+1);}}>다시 시도</button></div>}
  </div>;
}

export function useLocalNotice() {
  const [notice, setNotice] = useState('');
  useEffect(() => { if (!notice) return; const timeout = window.setTimeout(() => setNotice(''), 2800); return () => window.clearTimeout(timeout); }, [notice]);
  return { notice, setNotice };
}
