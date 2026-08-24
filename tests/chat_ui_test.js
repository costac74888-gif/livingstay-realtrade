const fs = require("fs");
const chat = require("../static/js/chat_common.js");

const containsMobile = chat.containsKoreanMobileNumber;
const shouldShowGreeting = chat.shouldShowGreeting;
const getRoleQuickReplies = chat.getRoleQuickReplies;
const fillQuickReply = chat.fillQuickReply;

const phoneCases = [
  ["010-1234-5678", true],
  ["연락처는 010 1234 5678 입니다", true],
  ["01012345678", true],
  ["011-123-4567", true],
  ["02-1234-5678", false],
  ["주문번호 1010123456789", false],
];
for (const [text, expected] of phoneCases) {
  const actual = containsMobile(text);
  if (actual !== expected) {
    throw new Error(`번호 감지 실패: ${text} => ${actual} (기대: ${expected})`);
  }
}
console.log(`OK  국내 휴대폰 번호 형식 감지 ${phoneCases.length}건`);

if (!shouldShowGreeting([])) {
  throw new Error("빈 채팅방에서 빠른 인사가 표시되지 않습니다.");
}
if (shouldShowGreeting([{ body: "기존 메시지" }]) || shouldShowGreeting(null)) {
  throw new Error("메시지가 있는 채팅방에서 빠른 인사가 표시됩니다.");
}
console.log("OK  빠른 인사는 빈 채팅방에서만 표시");

let focused = false;
const fakeInput = {
  value: "",
  focus() { focused = true; },
};
fillQuickReply(fakeInput, "안녕하세요");
if (fakeInput.value !== "안녕하세요" || !focused) {
  throw new Error("빠른 인사가 입력창을 채우고 포커스하지 못했습니다.");
}
console.log("OK  빠른 인사는 자동 전송 없이 입력창만 채움");

const buyerTemplates = getRoleQuickReplies("buyer");
const sellerTemplates = getRoleQuickReplies("seller");
if (buyerTemplates.length !== 5 ||
    buyerTemplates[0] !== "안녕하세요" ||
    buyerTemplates[4] !== "입주는 언제가능한지요?" ||
    sellerTemplates.length !== 5 ||
    sellerTemplates[0] !== "안녕하세요, 문의주셔서 감사합니다." ||
    sellerTemplates[4] !== "추가로 궁금한 점 있으세요?") {
  throw new Error("매수자·매도자 역할별 빠른답장 템플릿이 복원되지 않았습니다.");
}
console.log("OK  매수자·매도자 역할별 빠른답장 템플릿");

const safetyNotice = { textContent: "", style: { display: "none" } };
if (!chat.showSafetyNoticeForMessage("010-1234-5678", safetyNotice) ||
    safetyNotice.style.display !== "block" ||
    !safetyNotice.textContent.includes("사기 피해")) {
  throw new Error("휴대폰 번호 전송 후 개인정보·사기 주의 안내가 표시되지 않습니다.");
}
const untouchedNotice = { textContent: "", style: { display: "none" } };
if (chat.showSafetyNoticeForMessage("앱 안에서 대화해요", untouchedNotice) ||
    untouchedNotice.style.display !== "none") {
  throw new Error("휴대폰 번호가 없는 메시지에도 안전 안내가 표시됩니다.");
}
console.log("OK  번호 전송 성공 뒤 개인정보·사기 주의 안내 표시");

const roomAToken = {};
const roomBToken = {};
if (chat.isLatestMessageLoad(roomBToken, roomAToken, 1, 1, true) ||
    chat.isLatestMessageLoad(roomBToken, roomBToken, 1, 2, true) ||
    chat.isLatestMessageLoad(roomBToken, roomBToken, 2, 2, false) ||
    !chat.isLatestMessageLoad(roomBToken, roomBToken, 2, 2, true)) {
  throw new Error("이전 방 또는 오래된 메시지 응답을 올바르게 무효화하지 못했습니다.");
}
console.log("OK  방 전환 시 이전 방·오래된 메시지 응답 무효화");

async function checkVerificationRetry() {
  const originalFetch = global.fetch;
  const responses = [
    { ok: false, status: 403, json: async () => ({ ok: false, code: "PHONE_VERIFICATION_REQUIRED" }) },
    { ok: true, status: 200, json: async () => ({ ok: true, room_id: 77 }) },
  ];
  const requestBodies = [];
  let openedRoom = null;
  global.fetch = async (_url, options) => {
    requestBodies.push(JSON.parse(options.body));
    return responses.shift();
  };
  try {
    await chat.startListingChat(
      123,
      async (roomId) => { openedRoom = roomId; },
      { openPhoneVerification: async (_listingId, retry) => retry() },
    );
  } finally {
    global.fetch = originalFetch;
  }
  if (requestBodies.length !== 2 ||
      requestBodies.some((body) => body.listing_request_id !== 123) ||
      openedRoom !== 77) {
    throw new Error("휴대폰 인증 성공 후 원래 매물 채팅 재시도에 실패했습니다.");
  }
  console.log("OK  인증 성공 후 같은 매물 채팅을 자동 재시도");
}

function checkSharedEntryPoints() {
  const listings = fs.readFileSync("static/listings.html", "utf8");
  const index = fs.readFileSync("static/index.html", "utf8");
  const mypage = fs.readFileSync("static/mypage.html", "utf8");
  const main = fs.readFileSync("static/js/main.js", "utf8");
  const css = fs.readFileSync("static/css/main.css", "utf8");
  if (!listings.includes("LivingstayChat.startListingChat") ||
      !index.includes("/static/js/chat_common.js") ||
      !mypage.includes("/static/js/chat_common.js") ||
      !mypage.includes("LivingstayChat.showSafetyNoticeForMessage(") ||
      !mypage.includes("LivingstayChat.getRoleQuickReplies(") ||
      !main.includes('myRole === "seller" ? "seller" : "buyer"') ||
      !css.includes(".chat-template-chip.seller") ||
      !css.includes(".chat-template-chip.buyer")) {
    throw new Error("채팅 진입 화면이 공통 인증 흐름을 사용하지 않습니다.");
  }
  console.log("OK  홈페이지·매물목록·마이페이지가 공통 채팅 모듈 사용");
}

checkSharedEntryPoints();
checkVerificationRetry().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});