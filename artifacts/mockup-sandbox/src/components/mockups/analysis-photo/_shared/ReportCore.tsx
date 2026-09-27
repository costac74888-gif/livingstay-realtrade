import React from 'react';

const examplePhoto = '/__mockup/images/analysis-photo-concept.jpg';

export function ReportCore({ withPhoto }: { withPhoto: boolean }) {
  return (
    <div className="photo-concept report-stage">
      <div className="report-caption"><span>{withPhoto ? '제안 목업 · 현장사진 추가' : '현재 구성 · 비교 기준'}</span><span>A4 세로 · 1페이지 레이아웃</span></div>
      <article className="print-page" aria-label={withPhoto ? '사진 포함 숙박자산 분석보고서 목업' : '현재 숙박자산 분석보고서 목업'}>
        <header className="print-report-header">
          <div className="report-logo">HOME &amp;<br/>STAY</div>
          <div>
            <div className="print-report-types"><span className="report-type active">부동산투자분석</span><span className="report-type">임대수익분석</span><span className="report-type">숙박운영분석</span></div>
            <h1>숙박자산 분석보고서</h1>
          </div>
          <div className="print-report-trust"><b>보고서 번호 HS-EXAMPLE-001</b><br/>예시 자료 · 실제 분석 결과가 아닙니다</div>
        </header>
        <section className="print-zone print-overview">
          <h2>2.1 건물개요</h2>
          <div className="print-overview-body">
            <div className="print-overview-main">
              <div className="print-building"><div><b>바다온 호텔 · 예시 건물</b><span>강원특별자치도 속초시 · 예시 주소</span></div><em>유형: 관광호텔</em></div>
              <p>관광수요 지수 79.4 · 유사자산 대비 가격 −18.2% · 최근 12개월 기준</p>
              <div className="print-metrics">
                <article><small>관광수요 지수</small><strong>79.4점</strong></article>
                <article><small>㎡당 중앙가격</small><strong>270만원</strong></article>
                <article><small>유사자산 가격</small><strong>330만원</strong></article>
                <article><small>상대가격</small><strong>−18.2%</strong></article>
              </div>
            </div>
            <div className="print-result-line"><small>사분위 평가</small><strong>수요 대비 저평가 후보</strong><span>관광수요 지수 79.4 · 유사자산 대비 −18.2%</span><span>표본 범위와 개별 건물 상태를 함께 확인하세요.</span></div>
          </div>
        </section>
        <section className="print-zone print-graph">
          <h2>3.1 관광수요 × 상대가격 포지셔닝</h2>
          <div className="quadrant-label"><span>MARKET POSITION</span><span>선택 건물</span></div>
          <div className="quadrant-chart">
            <div className="quad-cell q-tl">② 가격 부담<small>관광수요 낮음 · 가격 높음</small></div>
            <div className="quad-cell q-tr">① 프리미엄 수요<small>관광수요 높음 · 가격 높음</small></div>
            <div className="quad-cell q-bl">③ 운영 개선 필요<small>관광수요 낮음 · 가격 낮음</small></div>
            <div className="quad-cell q-br">④ 저평가 후보<small>관광수요 높음 · 가격 낮음</small></div>
            <div className="vline"/><div className="chart-point"/>
          </div>
          <p className="graph-note">• 분석 그래프는 예시 위치입니다. 보고서 사진 추가 시 차트와 4. 계산근거의 기존 위치는 유지합니다.</p>
        </section>
        <aside className="print-side">
          <section className="print-zone print-tx-zone">
            <h2>3.2 근거 거래</h2>
            <div className="print-side-metrics">
              <article><small>분석 거래</small><strong>12건</strong></article>
              <article><small>㎡당 중앙값</small><strong>270만원</strong></article>
              <article><small>비교 자산</small><strong>18개</strong></article>
              <article><small>기준 기간</small><strong>최근 12개월</strong></article>
            </div>
            <p className="print-side-note">실거래 표본이 적을 때에는 시도·전국 기준을 함께 확인합니다.</p>
          </section>
          <section className="print-zone print-map-zone">
            <h2>{withPhoto ? '3.3 현장사진 · 지도위치' : '3.3 지도위치'}</h2>
            {withPhoto ? (
              <div className="photo-panel">
                <div className="photo-frame"><img className="site-photo" src={examplePhoto} alt="목업용 호텔 외관 예시"/></div>
                <p className="photo-credit">목업용 예시 이미지 · 실제 건물이나 공공데이터 사진이 아닙니다</p>
                <div className="map-preview"><span>위치 지도 (기존 영역 유지)</span></div>
              </div>
            ) : (
              <><div className="map-preview"><span>선택 건물 지도위치</span></div><p>선택 건물 주소 · 위치 기준</p></>
            )}
          </section>
        </aside>
        <section className="print-zone print-basis">
          <h2>4. 계산근거</h2>
          <p>선택 건물 유형과 최근 12개월 실거래, 관광수요 자료를 결합하여 위치를 설명합니다. 이 수치는 가격 또는 수익을 예측하지 않습니다.</p>
          <div className="formula">관광수요 지수 = 시군구 방문자 수의 전국 백분위 × 100<br/>건물 가격 = 최근 12개월 호실 실거래의 ㎡당 가격 중앙값<br/>유사자산 대비 가격 = (건물 가격 − 유사자산 가격) ÷ 유사자산 가격 × 100<br/>사분면 기준선 = 관광수요 지수 50 · 유사자산 대비 가격 0%</div>
          <div className="print-caution"><b>주의사항</b><span>본 보고서는 참고자료이며 감정평가, 투자 권유, 수익 보장 또는 법률·세무 자문을 대신하지 않습니다. 원문과 실제 건물 상태를 별도로 확인하세요.</span></div>
          <div className="report-legend"><span className="active">부동산투자분석<br/>관광수요와 유사자산 가격 비교</span><span>임대수익분석<br/>임대·대출 조건 분석</span><span>숙박운영분석<br/>객실가격과 객실 이용률 비교</span></div>
        </section>
      </article>
    </div>
  );
}