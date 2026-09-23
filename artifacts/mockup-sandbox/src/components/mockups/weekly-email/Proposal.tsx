import React from "react";

const gold = "#b4863f";
const ink = "#16202e";

const favorites = [
  { name: "한화호텔앤리조트/평창", date: "2026. 09. 18", price: "2,696만원", traded: true },
  { name: "삼부르네상스 고덕스테이", traded: false },
  { name: "돌산읍우두리 1032-5", traded: false },
  { name: "아라트라움 아리스타", traded: false },
  { name: "엠제이스트 레지던스", traded: false },
];

const highs = [
  ["금호제주리조트", "+100.0%"],
  ["한화콘도미니엄", "+47.8%"],
  ["제주 더힐스테이", "+32.4%"],
  ["속초 마리나베이", "+28.1%"],
  ["스타웍스 호텔", "+21.6%"],
];

const volume = [
  ["스타웍스 호텔", "5건"],
  ["한화호텔앤리조트/평창", "4건"],
  ["제주 더힐스테이", "3건"],
  ["금호제주리조트", "2건"],
  ["속초 마리나베이", "2건"],
];

const news = [
  ["[제목 예시] 숙박업 정책·제도 관련 발표", "발행일 자동 표시", "문화체육관광부"],
  ["[제목 예시] 지역 관광 수요와 숙박 동향", "발행일 자동 표시", "한국관광공사"],
  ["[제목 예시] 숙박 관련 공공 보도자료", "발행일 자동 표시", "정책브리핑"],
];

function SectionTitle({ eyebrow, children }: { eyebrow: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 9, borderBottom: `1px solid ${gold}`, paddingBottom: 9, marginBottom: 14 }}>
      <span style={{ fontSize: 10, color: gold, letterSpacing: ".08em", fontWeight: 800 }}>{eyebrow}</span>
      <h2 style={{ margin: 0, color: ink, fontSize: 16, lineHeight: 1.3, fontWeight: 800 }}>{children}</h2>
    </div>
  );
}

function Rows({ items, accent }: { items: string[][]; accent: string }) {
  return (
    <div>
      {items.map(([name, value], index) => (
        <div key={name} style={{ display: "grid", gridTemplateColumns: "24px 1fr auto", gap: 7, alignItems: "center", padding: "9px 0", borderBottom: "1px solid #edf0f2" }}>
          <span style={{ fontFamily: "ui-monospace, SFMono-Regular, monospace", fontSize: 11, color: index === 0 ? accent : "#a4abb2" }}>{String(index + 1).padStart(2, "0")}</span>
          <span style={{ fontSize: 12, color: ink, fontWeight: index === 0 ? 750 : 600 }}>{name}</span>
          <span style={{ fontSize: 12, color: accent, fontWeight: 800, whiteSpace: "nowrap" }}>{value}</span>
        </div>
      ))}
    </div>
  );
}

export function Proposal() {
  return (
    <div style={{ minHeight: "100%", background: "#f1f3f5", padding: "24px 12px 40px", color: ink, fontFamily: "'Apple SD Gothic Neo','Noto Sans KR',sans-serif", boxSizing: "border-box" }}>
      <main style={{ maxWidth: 580, margin: "0 auto", background: "#fff", borderRadius: 12, overflow: "hidden", boxShadow: "0 3px 18px rgba(22,32,46,.10)" }}>
        <div style={{ background: "#fff8e8", color: "#76562b", padding: "9px 18px", textAlign: "center", fontSize: 11, letterSpacing: "-.02em" }}>
          디자인 검토용 목업 · 아래 수치와 뉴스는 모두 ILLUSTRATIVE이며 실제 발송·실시간 데이터가 아닙니다
        </div>
        <header style={{ background: ink, padding: "25px 28px 23px", textAlign: "center" }}>
          <img src="/__mockup/logo-email.png" alt="HOME & STAY" style={{ width: 182, maxWidth: "75%", height: "auto", display: "inline-block" }} />
          <div style={{ color: "#aeb7c0", fontSize: 11, marginTop: 8, letterSpacing: ".05em" }}>WEEKLY BRIEF · 주간 데이터 다이제스트</div>
          <div style={{ color: gold, fontSize: 11, fontWeight: 700, marginTop: 5 }}>대한민국 숙박부동산 데이터 플랫폼</div>
        </header>

        <section style={{ padding: "26px 28px 0" }}>
          <p style={{ margin: "0 0 6px", fontSize: 16, fontWeight: 800, letterSpacing: "-.04em" }}>미리보기님, 이번 주 확인할 흐름만 담았어요.</p>
          <p style={{ margin: 0, color: "#6f7880", fontSize: 13, lineHeight: 1.65 }}>관심 건물의 최근 실거래와 의뢰 현황, 시장에서 눈에 띈 변화를 한 번에 확인해 보세요.</p>
        </section>

        <section style={{ padding: "25px 28px 0" }}>
          <SectionTitle eyebrow="YOUR WATCHLIST">최근 30일 관심 건물</SectionTitle>
          <div style={{ border: "1px solid #e6e9eb", borderRadius: 8, overflow: "hidden" }}>
            {favorites.map((item) => item.traded ? (
              <div key={item.name} style={{ padding: "13px 14px", background: "#fbf7ef", borderBottom: "1px solid #e6e9eb" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 10 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 800 }}>{item.name}</div>
                    <div style={{ color: "#7f878d", fontSize: 11, marginTop: 5 }}>최근 실거래 · {item.date}</div>
                  </div>
                  <strong style={{ color: gold, fontSize: 15, whiteSpace: "nowrap" }}>{item.price}</strong>
                </div>
              </div>
            ) : null)}
            <div style={{ padding: "12px 14px", color: "#69747c", fontSize: 12, lineHeight: 1.6 }}>
              나머지 4곳은 최근 30일 새 실거래가 없습니다.
            </div>
          </div>
          <div style={{ fontSize: 10, color: "#a06e2b", marginTop: 8 }}>ILLUSTRATIVE · 거래일·가격 및 관심 건물 상태는 화면 구성용 예시입니다.</div>
        </section>

        <section style={{ padding: "25px 28px 0" }}>
          <SectionTitle eyebrow="REQUEST STATUS">진행 중인 매물의뢰</SectionTitle>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 14, padding: "14px 15px", background: "#f5f7f8", borderRadius: 8 }}>
            <div>
              <div style={{ color: "#7a838a", fontSize: 11, marginBottom: 5 }}>매물내놓기</div>
              <div style={{ fontSize: 13, fontWeight: 800 }}>한화호텔앤리조트/평창</div>
            </div>
            <span style={{ height: 24, padding: "0 10px", display: "inline-flex", alignItems: "center", borderRadius: 12, background: "#fff3cd", color: "#856404", fontSize: 11, fontWeight: 800 }}>검토 대기</span>
          </div>
          <div style={{ fontSize: 10, color: "#a06e2b", marginTop: 8 }}>ILLUSTRATIVE · 의뢰 상태는 기존 사용자 화면을 바탕으로 한 예시입니다.</div>
        </section>

        <section style={{ padding: "28px 28px 0" }}>
          <SectionTitle eyebrow="MARKET SIGNALS">최근 30일 시세 랭킹</SectionTitle>
          <div style={{ color: "#8a9298", fontSize: 11, margin: "-4px 0 17px" }}>2026. 08. 25 — 2026. 09. 24 기준 · ILLUSTRATIVE</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 22 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 3 }}>신고가 갱신 TOP5 <span style={{ color: gold, fontSize: 10, fontWeight: 700 }}>최근 30일</span></div>
              <Rows items={highs} accent="#bd7448" />
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 3 }}>거래량 TOP5 <span style={{ color: gold, fontSize: 10, fontWeight: 700 }}>최근 30일</span></div>
              <Rows items={volume} accent={gold} />
            </div>
          </div>
        </section>

        <section style={{ marginTop: 28, padding: "22px 28px 24px", background: "#f7f4ef" }}>
          <SectionTitle eyebrow="FIELD NOTE">이번 주 기능 팁</SectionTitle>
          <p style={{ margin: 0, fontSize: 14, fontWeight: 800 }}>건물 매물을 직접 등록해 보세요</p>
          <p style={{ margin: "7px 0 14px", fontSize: 12, color: "#66717a", lineHeight: 1.7 }}>관심 건물의 매물을 남기고, 담당 파트너의 검토 진행 상황까지 한 화면에서 확인할 수 있습니다.</p>
          <span style={{ display: "inline-block", padding: "9px 14px", background: ink, color: "#fff", borderRadius: 5, fontSize: 12, fontWeight: 800 }}>매물 등록 가이드 보기  →</span>
        </section>

        <section style={{ padding: "26px 28px 0" }}>
          <SectionTitle eyebrow="FROM THE FIELD">숙박부동산 뉴스</SectionTitle>
           <div style={{ fontSize: 10, color: "#a06e2b", marginBottom: 8 }}>예시 영역 · 실제 발송 시 출처와 원문 링크가 확인된 기사만 자동으로 표시합니다. 아래 제목과 링크 표시는 연결되지 않습니다.</div>
          {news.map(([title, date, source]) => (
            <div key={title} style={{ padding: "11px 0", borderBottom: "1px solid #edf0f2" }}>
              <div style={{ fontSize: 13, lineHeight: 1.45, fontWeight: 750 }}>{title}</div>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginTop: 5, color: "#92999f", fontSize: 11 }}>
                <span>{date} · {source}</span><span style={{ color: gold, fontWeight: 800 }}>링크 보기  ↗</span>
              </div>
            </div>
          ))}
        </section>

        <footer style={{ margin: "25px 28px 0", padding: "17px 0 25px", borderTop: "1px solid #e6e8e9", textAlign: "center", color: "#a0a6ab", fontSize: 10, lineHeight: 1.7 }}>
          <div style={{ color: gold, fontWeight: 800, marginBottom: 3 }}>대한민국 숙박부동산 데이터 플랫폼</div>
          <div>홈앤스테이 · 사업자등록번호 301-41-68319</div>
          <div>회원님의 주간 소식 수신 설정에 따라 발송됩니다. <span style={{ textDecoration: "underline" }}>수신거부</span></div>
        </footer>
      </main>
    </div>
  );
}