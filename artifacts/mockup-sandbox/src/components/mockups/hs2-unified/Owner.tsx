import { useMemo, useState, type CSSProperties } from 'react';
import { Building2, CirclePlus, Pencil, Trash2 } from 'lucide-react';
import './_group.css';
import { Header, LocalDialog, KakaoMap, imageUrl, places, type Place } from './_shared';

type Layer = 'stay'|'sale'|'business'|'auction';
type OwnerListing = { id: string; title: string; area: string; price: string; layer: Layer; image: number; state: string };
const layerNames: Record<Layer,string> = { stay:'단기 숙박', sale:'매매', business:'영업권', auction:'공매' };
const layerColors: Record<Layer,string> = { stay:'#596044', sale:'#9b7047', business:'#7d7250', auction:'#8c5550' };
const starterListings: OwnerListing[] = [
  {id:'o1',title:'햇살이 머무는 성수 빌라',area:'성수동1가 · 주거형',price:'430,000원/주',layer:'stay',image:1,state:'검토 전'},
  {id:'o2',title:'성수동 골목 상가 1층',area:'성수동2가 · 근린생활시설',price:'6억 8,000만원',layer:'sale',image:2,state:'임시 저장'},
  {id:'o3',title:'서울숲길 카페 운영권',area:'성수동1가 · 카페',price:'권리금 협의',layer:'business',image:3,state:'검토 전'},
  {id:'o4',title:'성수동 다가구 건물',area:'성수동2가 · 주거용',price:'감정가 12억 4,000만원',layer:'auction',image:4,state:'공개 전'},
];
const starterFacilities = [
  {id:'f1',name:'스테이 모노 성수',type:'숙박시설',location:'성수동2가 · 성수역 인근'},
  {id:'f2',name:'서울숲 하우스',type:'주거시설',location:'성수동1가 · 서울숲역 인근'},
  {id:'f3',name:'연무장 코너빌딩',type:'근린생활시설',location:'성수동2가 · 연무장길'},
  {id:'f4',name:'온기 스테이 서울숲',type:'숙박시설',location:'성수동1가 · 뚝섬역 인근'},
];

export function Owner() {
  const [listings, setListings] = useState(starterListings);
  const [facilities, setFacilities] = useState(starterFacilities);
  const [activeLayer, setActiveLayer] = useState<Layer>('stay');
  const [visibleLayers, setVisibleLayers] = useState<Layer[]>(['stay','sale','business','auction']);
  const [showFacilities, setShowFacilities] = useState(true);
  const [dialog, setDialog] = useState<'listing'|'facility'|'edit'|'delete'|'facility-delete'|null>(null);
  const [editingId, setEditingId] = useState('');
  const [deletingFacilityId, setDeletingFacilityId] = useState('');
  const [title, setTitle] = useState('');
  const [area, setArea] = useState('');
  const [price, setPrice] = useState('');
  const [facilityName, setFacilityName] = useState('');
  const [notice, setNotice] = useState('');
  const visibleListings = useMemo(() => listings.filter((row)=>row.layer===activeLayer),[listings,activeLayer]);
  const mapEntries: Place[] = useMemo(() => listings.filter((listing)=>visibleLayers.includes(listing.layer)).map<Place>((listing) => {
    const source = places[listings.findIndex(row=>row.id===listing.id) % places.length];
    return { ...source, id:listing.id, title:listing.title, layer:listing.layer, mapLabel:layerNames[listing.layer] };
  }).concat(showFacilities ? facilities.map((facility,index)=>{
    const source = places[(index+5)%places.length];
    return {...source,id:facility.id,title:facility.name,lat:source.lat+.001,layer:'facility',mapLabel:'시설',kind:'home' as const};
  }) : []), [listings, visibleLayers, facilities, showFacilities]);
  const toggleLayer = (layer: Layer) => setVisibleLayers((old)=>old.includes(layer) ? old.filter((item)=>item!==layer) : [...old,layer]);
  const openNewListing = () => { setEditingId(''); setTitle(''); setArea('성수동'); setPrice(''); setDialog('listing'); };
  const openEdit = (listing: OwnerListing) => { setEditingId(listing.id); setTitle(listing.title); setArea(listing.area); setPrice(listing.price); setDialog('edit'); };
  const saveListing = () => {
    const next: OwnerListing = {id:editingId || `local-${Date.now()}`,title:title.trim() || '새 성수 매물',area:area.trim() || '성수동',price:price.trim() || '조건 입력 전',layer:activeLayer,image:((listings.length)%4)+1,state:'시안 입력'};
    setListings((old)=> editingId ? old.map((row)=>row.id===editingId ? {...row,...next,layer:row.layer} : row) : [...old,next]);
    setDialog(null); setNotice('화면 안에만 보이는 시안 정보가 반영되었습니다.');
  };
  const addFacility = () => {
    if (!facilityName.trim()) return;
    setFacilities((old)=>[{id:`local-${Date.now()}`,name:facilityName.trim(),type:'시설 유형 미리보기',location:'성수동 · 위치 미리보기'},...old]);
    setFacilityName(''); setDialog(null); setNotice('시설 목록의 로컬 시안에 추가했습니다.');
  };
  const deleteListing = () => {
    setListings((old)=>old.filter((row)=>row.id!==editingId));
    setDialog(null); setNotice('선택한 시안 항목을 이 화면에서만 삭제했습니다.');
  };
  const deleteFacility = () => {
    setFacilities((old)=>old.filter((facility)=>facility.id!==deletingFacilityId));
    setDialog(null); setNotice('선택한 시설 시안을 이 화면에서만 삭제했습니다.');
  };
  const startDelete = (id:string) => { setEditingId(id); setDialog('delete'); };
  return <div className="hs2 hs2-shell">
    <Header current="Owner"/>
    <main className="hs2-wrap">
      <div className="hs2-owner-hero"><div><p className="hs2-eyebrow">HOME &amp; STAY / OWNER DESK</p><h1>시설과 매물을 나누어 살펴봅니다</h1><p>이 공간의 시설 목록과 네 가지 매물 유형은 독립적으로 관리됩니다.</p></div><button className="hs2-btn" onClick={openNewListing}><CirclePlus size={18}/> 매물 추가</button></div>
      {notice && <div className="hs2-toast" role="status">{notice}<button onClick={()=>setNotice('')} aria-label="알림 닫기">×</button></div>}
      <div className="hs2-owner-grid">
        <div className="hs2-owner-main">
          <section className="hs2-panel" aria-labelledby="facilities-title">
            <div className="hs2-panel-head"><div><p className="hs2-eyebrow">FACILITIES</p><h2 id="facilities-title">시설 목록</h2></div><button className="hs2-btn secondary" onClick={()=>{setFacilityName('');setDialog('facility');}}><CirclePlus size={17}/> 시설 추가</button></div>
            <div className="hs2-panel-body">
              <p className="hs2-muted">시설은 매물과 별도 목록으로 표시됩니다. 합성 데이터 기반 로컬 미리보기입니다.</p>
              <div className="hs2-facilities">{facilities.map((facility)=><article className="hs2-facility" key={facility.id}><span className="hs2-facility-mark"><Building2 size={20}/></span><div><strong>{facility.name}</strong><small>{facility.type} · {facility.location}</small></div><button className="hs2-icon-btn hs2-facility-remove" aria-label={`${facility.name} 삭제`} onClick={()=>{setDeletingFacilityId(facility.id);setDialog('facility-delete');}}><Trash2 size={17}/></button></article>)}</div>
            </div>
          </section>
          <section className="hs2-panel hs2-owner-list-panel" aria-labelledby="listings-title">
            <div className="hs2-panel-head"><div><p className="hs2-eyebrow">LISTING DESK</p><h2 id="listings-title">매물 관리</h2></div><span className="hs2-muted">레이어별 구분</span></div>
            <div className="hs2-layers"><button className="hs2-layer-toggle" aria-pressed={showFacilities} onClick={()=>setShowFacilities(!showFacilities)}>시설 <span>{facilities.length}</span></button>{(['stay','sale','business','auction'] as Layer[]).map((layer)=><button className="hs2-layer-toggle" key={layer} aria-pressed={visibleLayers.includes(layer)} onClick={()=>{toggleLayer(layer);setActiveLayer(layer);}}><i className="hs2-layer-dot" style={{'--layer':layerColors[layer] } as CSSProperties}/>{layerNames[layer]}<span>{listings.filter((x)=>x.layer===layer).length}</span></button>)}</div>
            <div className="hs2-layer-tabs">{(['stay','sale','business','auction'] as Layer[]).map((layer)=><button key={layer} aria-pressed={activeLayer===layer} onClick={()=>setActiveLayer(layer)}>{layerNames[layer]}</button>)}</div>
            <div className="hs2-panel-body">
              <div className="hs2-layer-heading"><div><span className="hs2-chip">{layerNames[activeLayer]}</span><p>{activeLayer === 'stay' ? '단기 체류를 위한 숙박·주거형 임대' : activeLayer === 'sale' ? '소유권 이전을 위한 부동산 매매' : activeLayer === 'business' ? '운영 중인 사업의 영업권 양도' : '공매 진행 물건의 개별 안내'}</p></div><button className="hs2-btn secondary" onClick={openNewListing}>이 유형 추가</button></div>
              <div className="hs2-owner-list">{visibleListings.map((listing)=><article className="hs2-owner-listing" key={listing.id}>
                <img src={imageUrl(listing.image)} alt="합성 성수 공간 이미지"/>
                <div><h3>{listing.title}</h3><p>{listing.area} · {listing.state}</p><strong>{listing.price}</strong></div>
                <div className="hs2-owner-listing-actions"><button className="hs2-small-action" onClick={()=>openEdit(listing)}><Pencil size={15}/> 편집</button><button className="hs2-small-action" onClick={()=>startDelete(listing.id)}><Trash2 size={15}/> 삭제</button></div>
              </article>)}
              {!visibleListings.length && <div className="hs2-empty">이 레이어에는 아직 시안 매물이 없습니다.<br/><button className="hs2-btn secondary" onClick={openNewListing}>매물 추가</button></div>}</div>
              <p className="hs2-owner-caption">시안 항목은 저장되지 않으며 공개, 거래, 예약 또는 운영 상태를 바꾸지 않습니다.</p>
            </div>
          </section>
        </div>
        <aside className="hs2-owner-aside">
          <section className="hs2-side-note"><p className="hs2-eyebrow">MAP LAYERS</p><h3>지도 표시 유형</h3><p>레이어 칩을 눌러 유형을 켜고 끄거나, 아래에서 해당 목록을 확인하세요.</p><div className="hs2-layer-switches">{(['stay','sale','business','auction'] as Layer[]).map((layer)=><button key={layer} aria-pressed={visibleLayers.includes(layer)} className="hs2-layer-toggle" onClick={()=>toggleLayer(layer)}><i className="hs2-layer-dot" style={{'--layer':layerColors[layer]} as CSSProperties}/>{layerNames[layer]}</button>)}</div></section>
          <div className="hs2-owner-map"><KakaoMap entries={mapEntries}/><div className="hs2-map-caption">성수동 · 지도 위치는 참고용</div></div>
          <div className="hs2-notice">관리 도구의 동작은 디자인 검토용입니다. 실제 계정, 권한, 등록 정보와 연결되지 않습니다.</div>
        </aside>
      </div>
    </main>
    <LocalDialog open={dialog==='listing'||dialog==='edit'} title={dialog==='edit'?'매물 시안 편집':'매물 시안 추가'} onClose={()=>setDialog(null)} onConfirm={saveListing} confirmText="로컬 시안에 반영">
      <p className="hs2-dialog-note">현재 선택 유형: <strong>{layerNames[activeLayer]}</strong>. 이 입력은 현재 미리보기 화면에만 적용됩니다.</p>
      <label className="hs2-label">매물 이름<input className="hs2-input" value={title} onChange={(e)=>setTitle(e.target.value)}/></label>
      <label className="hs2-label">지역 및 유형<input className="hs2-input" value={area} onChange={(e)=>setArea(e.target.value)}/></label>
      <label className="hs2-label">표시 조건 또는 기준가<input className="hs2-input" value={price} onChange={(e)=>setPrice(e.target.value)} placeholder="확인 전이면 확인 전으로 표기"/></label>
    </LocalDialog>
    <LocalDialog open={dialog==='facility'} title="시설 시안 추가" onClose={()=>setDialog(null)} onConfirm={addFacility} confirmText="시설 목록에 추가" confirmDisabled={!facilityName.trim()}>
      <label className="hs2-label">시설 이름<input className="hs2-input" value={facilityName} onChange={(e)=>setFacilityName(e.target.value)} placeholder="예: 성수 코너 스테이"/></label><p className="hs2-dialog-note">시안 시설은 목록에만 추가됩니다. 주소나 실제 등록은 생성되지 않습니다.</p>
    </LocalDialog>
    <LocalDialog open={dialog==='delete'} title="이 시안 항목을 삭제할까요?" onClose={()=>setDialog(null)} onConfirm={deleteListing} confirmText="시안에서 삭제">
      <p className="hs2-dialog-note">삭제는 이 화면의 임시 데이터에만 적용되며 실제 매물에 영향을 주지 않습니다.</p>
    </LocalDialog>
    <LocalDialog open={dialog==='facility-delete'} title="시설 시안을 삭제할까요?" onClose={()=>setDialog(null)} onConfirm={deleteFacility} confirmText="시안에서 삭제">
      <p className="hs2-dialog-note">시설 목록에서만 제거됩니다. 실제 시설 정보에는 영향을 주지 않습니다.</p>
    </LocalDialog>
  </div>;
}
export default Owner;
