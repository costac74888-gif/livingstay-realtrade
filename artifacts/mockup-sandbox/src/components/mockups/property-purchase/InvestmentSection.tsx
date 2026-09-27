import { useState } from 'react';
import './_group.css';

// Extracted from the purchase comparison and workspace in static/analysis.html.
// Network-backed analysis data is replaced with clearly labeled illustrative values.
const area = 17.6;
const median = 227.4;
const peer = 372.6;
const tourism = 79.4;
const marketGap = (median / peer - 1) * 100;
const examplePoints: [number, number][] = [
  [13,67],[22,71],[34,39],[27,68],[41,54],[54,72],[68,63],[73,47],[84,26],[92,36],
  [18,46],[31,23],[44,37],[58,42],[66,29],[77,64],[88,51],[12,34],[34,81],[47,77],
  [59,88],[71,74],[82,81],[24,54],[37,61],[49,19],[61,24],[74,16],[90,68],[95,78],
];
const money = (value: number, decimals = 0) =>
  value.toLocaleString('ko-KR', { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
const percentage = (value: number) => `${value >= 0 ? '+' : ''}${money(value, 1)}%`;
const chartY = (value: number) => Math.max(9, Math.min(91, 50 - value * .35));

export function InvestmentSection({ proposed }: { proposed: boolean }) {
  const [raw, setRaw] = useState('12000');
  const value = Number(raw);
  const valid = raw !== '' && /^\d+$/.test(raw) && value > 0 && value <= 500000;
  const gap = valid ? (value / area / peer - 1) * 100 : null;
  const assumedVerdict = gap == null ? '매수가를 입력하면 비교합니다.' :
    gap >= 0 ? '수요 프리미엄 (가정 판정)' : '수요 대비 저평가 후보 (가정 판정)';
  const input = (
    <label htmlFor="propertyPurchasePrice">제시 매수가 (만원)
      <input id="propertyPurchasePrice" type="number" inputMode="numeric" min="1" max="500000" step="1"
        placeholder="매수가 입력" value={raw} onChange={event => setRaw(event.target.value)}
        aria-invalid={raw !== '' && !valid} aria-describedby="propertyPurchaseHint"/>
    </label>
  );
  const reset = <button className="am-btn" type="button" onClick={() => setRaw('')}>시장 기준값으로 복귀</button>;

  return <div className={`purchase-preview ${proposed ? 'proposed' : 'current'}`}>
    <p className="selected-building">부동산투자분석 <small>· 예시 건물 · 전용면적 {area}㎡ · 목업용 예시 수치</small></p>
    <section className="analysis-mode-bar" aria-label="자산분석 그래프 종류">
      <div className="analysis-tabs">
        <button type="button" aria-current="page">부동산투자분석</button>
        <button type="button">임대수익분석</button>
        <button type="button">숙박운영분석</button>
      </div>
    </section>
    <div id="propertyAnalysis">
      <section className="analysis-card property-purchase-bar" aria-label="매수조건">
        <div className="purchase-copy"><span className="eyebrow">PURCHASE SCENARIO</span>
          <h2>매수조건 비교</h2>
          <p>시장 기준은 최근 12개월 호실 실거래 중앙값입니다. 내 매수가는 별도의 가정이며 원본 분석·후보 순위에 반영되지 않습니다.</p>
        </div>
        {!proposed && input}
        {!proposed && reset}
        {!proposed && <p id="propertyPurchaseHint" className="property-purchase-hint" role="status">
          {valid ? '입력한 매수가는 선택 면적의 ㎡당 가격으로 환산한 가정입니다.' : '시장 실거래 기준입니다.'}
        </p>}
        <div className="property-price-comparison" id="propertyPriceComparison" aria-live="polite">
          <div><small>시장가격 점 · 최근 12개월 실거래 중앙값</small>
            <strong>{money(median,1)}만원/㎡ · {percentage(marketGap)}</strong>
            <span>수요 대비 저평가 후보 · 원본 시장 기준</span>
            {proposed && reset}
          </div>
          <div><small>내 매수가 점 · {valid ? '입력 가정' : '미입력'}</small>
            <strong>{valid ? `${money(value)}만원 ÷ ${area}㎡ = ${money(value / area,1)}만원/㎡ · ${percentage(gap!)}` : '—'}</strong>
            <span>{assumedVerdict}</span>
            {proposed && input}
          </div>
          <p id={proposed ? 'propertyPurchaseHint' : undefined}>비교 기준: 시군구 동일유형 · 유사자산 {money(peer,1)}만원/㎡. 시장가격 점과 가정 점은 별개이며 투자 후보 순위에는 반영되지 않습니다.</p>
        </div>
      </section>

      <section className="workspace" id="workspace">
        <article className="analysis-card chart-card">
          <div className="card-head"><div>
            <h2>관광수요 × 유사자산 가격 포지셔닝</h2>
            <p>관광수요 백분위와 유사자산 대비 가격을 함께 비교합니다.</p>
          </div><div className="chart-mode"><button type="button">현재 위치</button></div></div>
          <div className="chart-frame">
            <div className="y-axis-guide"><b>높음<br/>(프리미엄)</b><span>↑</span><strong>유사자산 대비 가격 (%)</strong><span>↓</span><b>낮음<br/>(할인)</b></div>
            <div className="chart-main">
              <div className="chart-wrap">
                <div className="quad q-top-left"><b>③ 가격 부담</b><strong>(관광수요 낮음 / 가격 높음)</strong><span>수요보다 가격 부담이 큰 구간</span></div>
                <div className="quad q-top-right"><b>② 수요 프리미엄</b><strong>(관광수요 높음 / 가격 높음)</strong><span>강한 관광수요가 가격에 반영된 구간</span></div>
                <div className="quad q-bottom-left"><b>④ 저가·수요 확인 필요</b><strong>(관광수요 낮음 / 가격 낮음)</strong><span>가격은 낮지만 수요 확인이 필요한 구간</span></div>
                <div className="quad q-bottom-right"><b>① 수요 대비 저평가 후보</b><strong>(관광수요 높음 / 가격 낮음)</strong><span>수요에 비해 가격이 낮은 후보 구간</span></div>
                <svg className="plot" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="관광수요와 유사자산 가격 산점도">
                  <line x1="50" y1="0" x2="50" y2="100" stroke="#9db5bd" strokeWidth=".22" strokeDasharray="1 1" />
                  <line x1="0" y1="50" x2="100" y2="50" stroke="#9db5bd" strokeWidth=".22" strokeDasharray="1 1" />
                  {examplePoints.map(([x,y], i) => <ellipse key={i} cx={x} cy={y} rx=".55" ry=".85" fill={x>55 ? '#5191a4' : '#869aa6'} opacity=".63"/>)}
                  <ellipse cx={tourism} cy={chartY(marketGap)} rx="1.4" ry="2.15" fill="#eb6834" stroke="white" strokeWidth=".5"/>
                  {gap != null && <ellipse cx={tourism} cy={chartY(gap)} rx="1.4" ry="2.15" fill={proposed ? '#8e44ad' : '#165ab6'} stroke="white" strokeWidth=".5"/>}
                </svg>
              </div>
              <div className="x-axis-guide"><b>낮음</b><span>←</span><strong>관광수요 지수 (전국 백분위)</strong><span>→</span><b>높음</b></div>
              <div className="legend"><span><i className="legend-selected"/>선택 단지</span><span><i/>같은 시군구</span><span><i/>기타 단지</span><span>┆ 관광 기준 50</span><span>┄ 유사자산 기준 0%</span></div>
            </div>
          </div>
          <div className="baseline-strip"><div className="baseline">선택 건물 비교<b>시군구 동일유형</b></div><div className="baseline">관광수요 기준<b>50</b></div><div className="baseline">유사자산 가격 기준<b>0%</b></div><div className="baseline">분석 표본<b>예시</b></div></div>
          <div className="property-point-key"><span><i/>주황색: 시장 실거래 점</span><span><i/>{proposed ? '보라색' : '파란색'}: 내 매수가 가정 점</span></div>
        </article>
        <div className="property-results-column">
          <section className="analysis-card analysis-report-verdict" aria-live="polite">
            <span className="report-verdict-label">종합평가 · 부동산투자분석</span>
            <strong>수요 대비 저평가 후보</strong><p>최근 12개월 거래의 ㎡당 중앙가격은 유사자산보다 낮습니다. 제시 매수가 가정과 관계없이 시장 평가를 유지합니다.</p>
          </section>
          <section className="analysis-card transaction-trend-card" aria-label="선택 건물 실거래 추이">
            <div className="card-head"><div><h2>실거래 추이</h2><p>선택 건물의 전유면적별 거래금액과 거래량입니다.</p></div></div>
            <div className="transaction-trend-wrap"><svg viewBox="0 0 400 150" preserveAspectRatio="none" aria-hidden="true">
              <path d="M0 115 L400 115" stroke="#dde6e9"/><path d="M0 73 L400 73" stroke="#dde6e9"/><path d="M0 30 L400 30" stroke="#dde6e9"/>
              <path d="M9 76 L80 57 L152 82 L225 40 L300 67 L390 24" stroke="#2673cf" fill="none" strokeWidth="2.5"/>
              {[9,80,152,225,300,390].map((x,i) => <circle key={i} cx={x} cy={[76,57,82,40,67,24][i]} r="4" fill="#2673cf"/>)}
              {[18,95,168,239,315,380].map((x,i) => <rect key={i} x={x} y={120-[22,38,18,48,32,25][i]} width="16" height={[22,38,18,48,32,25][i]} fill="#b4863f" opacity=".6"/>)}
            </svg></div>
            <div className="transaction-trend-legend"><span><i className="price"/>평균 거래금액(만원)</span><span><i/>거래량</span></div>
          </section>
          <aside className="analysis-card detail-card"><h3>선택 건물 분석 근거</h3><p>최근 12개월 호실 실거래 중앙값 기준</p>
            <div className="detail-values"><div><small>관광수요 지수</small><b>{tourism}점</b></div><div><small>유사자산 대비 가격</small><b>{percentage(marketGap)}</b></div></div>
          </aside>
        </div>
      </section>
    </div>
  </div>;
}