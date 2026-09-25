const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:5000";
const USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36";

async function run() {
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      || execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(),
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage({ userAgent: USER_AGENT });
    let role = "guest";
    let analysisRequests = 0;
    await page.route("**/api/auth/me", route => route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(role === "guest" ? { logged_in: false } : {
        logged_in: true, account_type: role, id: 44,
        name: "테스트 회원", email: "test@example.invalid",
      }),
    }));
    await page.route("**/api/analysis/assets?*", route => {
      analysisRequests++;
      return route.fulfill({
        status: role === "guest" ? 401 : 200,
        contentType: "application/json",
        body: JSON.stringify(role === "guest" ? { requires_login: true } : {
          ok: true, generated_at: "2026-09-25T00:00:00Z",
          items: [], summary: {}, methodology: {},
        }),
      });
    });

    for (role of ["guest", "user", "agent", "operator", "loan_consultant"]) {
      analysisRequests = 0;
      await page.goto(BASE_URL + "/menu");
      await page.locator("#siteHeader a[href='/analysis']").waitFor({ state: "visible" });
      await page.locator(".menu-shortcuts-grid a[href='/analysis']").waitFor({ state: "visible" });
      await page.goto(BASE_URL + "/analysis");
      if (role === "guest") {
        await page.waitForFunction(() =>
          document.querySelector("#state")?.textContent.includes("회원 로그인 후 이용"));
      } else {
        await page.waitForFunction(() =>
          document.querySelector("#state")?.textContent.includes("분석 가능한 건물이 없습니다"));
        if (!analysisRequests) throw new Error(`${role}: 로그인 뒤 투자분석 요청이 시작되지 않았습니다.`);
        for (const mode of ["rental", "operation", "property"]) {
          await page.locator(`#analysisTabs button[data-analysis-mode="${mode}"]`).click();
          const active = await page.locator("#analysisTabs button.active").getAttribute("data-analysis-mode");
          if (active !== mode) throw new Error(`${role}: ${mode} 분석 탭을 열 수 없습니다.`);
        }
      }
      const tabs = await page.locator("#analysisTabs button").count();
      if (tabs !== 3) throw new Error(`${role}: 분석 탭 3개가 표시되지 않습니다.`);
    }
    console.log("guest menu and member/partner analysis access checks passed");
  } finally {
    await browser.close();
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });