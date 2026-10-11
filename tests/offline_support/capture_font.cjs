"use strict";
const fs = require("node:fs");
const path = require("node:path");

const STYLE_ID = "offline-analysis-capture-font";
let stylesheet;

function captureFontCSS() {
  if (!stylesheet) {
    // Nanum Gothic is a Korean capture fixture, not production typography.
    // Alias the family's CSS name so existing DOM and canvas font settings
    // use it without changing app code or weakening layout assertions.
    // Keep Fontsource's Unicode ranges, but inline WOFF2 bytes. No server
    // endpoint, system font installation, or external request is needed.
    stylesheet = [400, 700].map(weight => {
      const file = require.resolve(`@fontsource/nanum-gothic/${weight}.css`);
      return fs.readFileSync(file, "utf8").replace(
        /src:\s*url\(([^)]+\.woff2)\)[^;]+;/g,
        (_match, relative) => {
          const bytes = fs.readFileSync(path.resolve(path.dirname(file), relative));
          return `src: url("data:font/woff2;base64,${bytes.toString("base64")}") format("woff2");`;
        });
    }).join("\n").replaceAll("font-family: 'Nanum Gothic'", "font-family: 'Noto Sans KR'");
    if (/https?:|@import|url\((?!["']?data:)/.test(stylesheet))
      throw Error("Capture font must be completely self-contained");
  }
  return stylesheet;
}

async function prepareCaptureFont(page) {
  if (process.env.SAVE_ANALYSIS_SCREENSHOTS !== "1") return;
  const installed = await page.evaluate(id => !!document.getElementById(id), STYLE_ID);
  if (!installed) {
    const style = await page.addStyleTag({ content: captureFontCSS() });
    await style.evaluate((element, id) => { element.id = id; }, STYLE_ID);
  }
  await page.evaluate(async () => {
    // Load every modern Hangul syllable, not just the current viewport. A
    // later report may introduce text not present when its font was prepared.
    const hangul = Array.from({ length: 0xd7a3 - 0xac00 + 1 },
      (_, index) => String.fromCharCode(0xac00 + index)).join("");
    for (const weight of [400, 700]) {
      const faces = await document.fonts.load(`${weight} 12px "Noto Sans KR"`,
        hangul + document.body.innerText);
      if (!faces.length || faces.some(face => face.status !== "loaded"))
        throw Error(`Local Korean capture font failed to load: ${weight}`);
    }
    await document.fonts.ready;
  });
}

module.exports = { prepareCaptureFont, captureFontCSS };
