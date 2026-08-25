"use strict";

// 브라우저 DOM 전체를 의존하지 않고 auth.js의 모달 상태 전환을 검증한다.
// 재설정 모드에서 숨긴 비밀번호 input은 required 상태로 남으면 브라우저가
// submit 이벤트 자체를 막기 때문에, disabled/required와 API 호출을 함께 확인한다.
const fs = require("fs");
const vm = require("vm");

function element(id) {
  return {
    id: id,
    style: { display: "none" },
    value: "",
    type: "password",
    required: id === "authPassword",
    disabled: false,
    checked: false,
    textContent: "",
    innerHTML: "",
    listeners: {},
    addEventListener(name, handler) { this.listeners[name] = handler; },
    setAttribute(name, value) { this[name] = value; },
    getAttribute(name) { return this[name]; },
    focus() {},
    reset() {},
    querySelectorAll() { return []; },
  };
}

const ids = [
  "authArea", "authModal", "authForm", "authModalTitle", "authError",
  "authNameField", "authName", "authEmail", "authPassword", "authSubmit",
  "authSwitchText", "authSwitchLink", "authModalClose", "authPwToggle",
  "authRememberRow", "authRemember", "authForgotLink", "authSocialLinks",
  "authConsent", "agreeAll", "agreeAge14", "agreeTerms", "agreePrivacy",
  "agreeMarketing", "privacyToggle", "privacyDetail",
];
const elements = Object.fromEntries(ids.map((id) => [id, element(id)]));
const passwordField = element("authPasswordField");
elements.authPassword.closest = () => passwordField;

const documentStub = {
  getElementById(id) { return elements[id] || null; },
  addEventListener() {},
  createElement() { return element("created"); },
  body: { appendChild() {} },
};
const fetchCalls = [];
global.document = documentStub;
global.window = {
  addEventListener() {},
  dispatchEvent() {},
  location: { search: "", pathname: "/" },
  history: { replaceState() {} },
};
global.fetch = (url, options) => {
  fetchCalls.push({ url, options });
  if (url === "/api/auth/me") {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ logged_in: false }) });
  }
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ ok: true, message: "안내 메일을 보냈습니다." }),
  });
};

vm.runInThisContext(fs.readFileSync("static/js/auth.js", "utf8"), {
  filename: "static/js/auth.js",
});

elements.authEmail.value = "member@example.test";
elements.authForgotLink.listeners.click({ preventDefault() {} });
if (!elements.authPassword.disabled || elements.authPassword.required) {
  throw new Error("재설정 모드에서 비밀번호 입력이 disabled=true, required=false가 아님");
}
if (passwordField.style.display !== "none") {
  throw new Error("재설정 모드에서 비밀번호 필드가 숨겨지지 않음");
}
elements.authForm.listeners.submit({ preventDefault() {} });
if (!fetchCalls.some((call) => call.url === "/api/auth/request-password-reset")) {
  throw new Error("재설정 모드 제출이 비밀번호 재설정 요청 API를 호출하지 않음");
}