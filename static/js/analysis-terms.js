(function () {
  "use strict";
  var meanings = Object.freeze({
    ADR: "객실 평균요금",
    OCC: "객실 이용률",
    RevPAR: "객실당 매출",
    NOI: "순영업소득",
    DSCR: "부채상환비율",
    "R-ONE": "한국부동산원 통계",
    OTA: "온라인 여행사",
    GOP: "영업총이익"
  });
  var pattern = /(^|[^A-Za-z0-9-])(RevPAR|R-ONE|DSCR|ADR|OCC|NOI|OTA|GOP)(?![A-Za-z0-9-])/g;
  var original = new WeakMap();
  function label(term) { return meanings[term] ? term + "(" + meanings[term] + ")" : term; }
  function expand(value, options) {
    var seen = options && options.seen || new Set();
    var text = String(value == null ? "" : value)
      .replace(/(?:판매객실 평균요금|객실 평균요금)\s*\(ADR\)/g, label("ADR"))
      .replace(/객실 이용률\s*\(OCC\)/g, label("OCC"))
      .replace(/순영업소득\s*\(NOI\)/g, label("NOI"));
    return text.replace(pattern, function (match, prefix, term, index, source) {
      var following = source.slice(index + match.length);
      var alreadyExplained = following.indexOf("(" + meanings[term] + ")") === 0;
      var first = !seen.has(term);
      seen.add(term);
      return prefix + (first && !alreadyExplained ? label(term) : term);
    });
  }
  window.livingstayAnalysisTerms = { meanings: meanings, label: label, expand: expand };

  function ignored(node) {
    var parent = node.parentElement;
    return !parent || !!parent.closest("script,style,textarea,option,[data-analysis-terms-ignore]");
  }
  function firstTermsInBlock(node) {
    var parent = node.parentElement, block = parent && parent.closest("p,li,.formula");
    var seen = new Set();
    if (!block) return seen;
    var walk = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    while (walk.nextNode() && walk.currentNode !== node) {
      var before = walk.currentNode.textContent;
      pattern.lastIndex = 0;
      var found;
      while ((found = pattern.exec(before))) seen.add(found[2]);
    }
    return seen;
  }
  function isShort(node, text) {
    var parent = node.parentElement;
    if (!parent) return false;
    if (parent.closest(".sensitivity-scroll th:first-child,.operation-sensitivity th:first-child")) return true;
    return window.innerWidth <= 480 && !!parent.closest("#operationSliders") &&
      /\b(?:ADR|OCC|RevPAR)\b/.test(text);
  }
  function translate(node) {
    if (ignored(node)) return;
    var entry = original.get(node), current = node.nodeValue;
    if (!entry || current !== entry.rendered) entry = { raw: current, rendered: current };
    if (!/(?:ADR|OCC|RevPAR|NOI|DSCR|R-ONE|OTA|GOP)/.test(entry.raw) &&
        !/(?:판매객실 평균요금|객실 이용률|순영업소득)\s*\(/.test(entry.raw)) return;
    var short = isShort(node, entry.raw), rendered = short ? entry.raw : expand(entry.raw, { seen: firstTermsInBlock(node) });
    if (short) {
      var match = entry.raw.match(/(?:RevPAR|R-ONE|DSCR|ADR|OCC|NOI|OTA|GOP)/);
      if (match && node.parentElement) node.parentElement.title = label(match[0]);
    }
    entry.rendered = rendered;
    original.set(node, entry);
    if (current !== rendered) node.nodeValue = rendered;
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) { translate(root); return; }
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    if (root.matches("script,style,textarea,option,[data-analysis-terms-ignore]")) return;
    var tree = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (tree.nextNode()) translate(tree.currentNode);
  }
  function start() {
    var roots = [document.querySelector("main.analysis-shell"), document.getElementById("printReport")].filter(Boolean);
    roots.forEach(function (root) {
      walk(root);
      new MutationObserver(function (records) {
        records.forEach(function (record) {
          if (record.type === "characterData") translate(record.target);
          else record.addedNodes.forEach(walk);
        });
      }).observe(root, { childList: true, subtree: true, characterData: true });
    });
    window.addEventListener("resize", function () { roots.forEach(walk); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();