import './_group.css';

const photo = '/__mockup/images/analysis-photo-concept.jpg';

export function DesktopWithPhoto() {
  return (
    <div className="photo-concept desktop-stage">
      <header className="desktop-header"><div className="brand"><span>HOME &amp;<br/>STAY</span>홈앤스테이</div><nav><span>내건물시세</span><span>지도</span><b style={{color:'#17324a'}}>자산분석</b><span>실거래목록</span><span>마이페이지</span></nav></header>
      <div className="desktop-heading"><div><span className="eyebrow">HOME &amp; STAY / ASSET INTELLIGENCE</span><h1>홈앤스테이 숙박자산 분석</h1><p>선택한 건물의 공공데이터 사진과 분석 결과를 함께 확인합니다.</p></div><button className="primary-action">보고서 출력 ↗</button></div>
      <section className="analysis-card building-select" aria-label="선택 건물 및 보고서 사진">
        <div>
          <div className="photo-frame"><img className="site-photo" src={photo} alt="목업용 호텔 외관 예시"/></div>
          <span className="photo-credit">목업용 예시 이미지 · 실제 건물 사진 아님</span>
        </div>
        <div><span className="eyebrow">SELECTED BUILDING</span><h2>바다온 호텔 · 예시 건물</h2><p className="address">강원특별자치도 속초시 · 예시 주소</p><span className="data-source">기존 공공데이터 사진 우선</span><p className="photo-credit" style={{margin:'9px 0 0'}}>기존 호텔·캠핑장 사진 공급 순서는 변경하지 않습니다.</p></div>
        <div className="report-inclusion"><b>인쇄 보고서의 현장사진</b><p>선택 건물에 확인된 사진이 있으면 3.3 지도위치 옆에 함께 배치합니다.</p><p>사진이 없으면 기존 지도 영역만 표시합니다.</p></div>
      </section>
      <div className="mode-tabs"><span className="active">부동산투자분석</span><span>임대수익분석</span><span>숙박운영분석</span></div>
      <div className="desktop-workspace">
        <section className="analysis-card"><h3>관광수요 × 상대가격 포지셔닝</h3><div className="quadrant-chart"><div className="quad-cell q-tl">② 가격 부담</div><div className="quad-cell q-tr">① 프리미엄 수요</div><div className="quad-cell q-bl">③ 운영 개선 필요</div><div className="quad-cell q-br">④ 저평가 후보</div><div className="vline"/><div className="chart-point"/></div><p className="graph-note">관광수요 지수 79.4 · 유사자산 대비 −18.2% · 예시 수치</p></section>
        <section className="analysis-card"><span className="eyebrow">ANALYSIS SUMMARY</span><h3 style={{marginTop:7}}>수요 대비 저평가 후보</h3><div className="side-metric"><span>관광수요 지수</span><b>79.4점</b></div><div className="side-metric"><span>㎡당 중앙가격</span><b>270만원</b></div><div className="side-metric"><span>유사자산 대비</span><b>−18.2%</b></div><p className="photo-credit">사진은 건물 식별 보조 자료이며 판정이나 산식에는 반영하지 않습니다.</p></section>
      </div>
    </div>
  );
}