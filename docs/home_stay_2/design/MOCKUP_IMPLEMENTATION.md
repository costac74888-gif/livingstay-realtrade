# HOME & STAY mockup restoration — private Preview

**추가 범위:** 이후 사용자 요청으로 성수동 가상 매물 직접 테스트 기능을 추가했다.
아래는 최초 복원 작업의 역사적 기록이며, 최신 사진·JS·개발 seed·모의 결제 범위와
새 검증은 [SEONGSU_PREVIEW.md](SEONGSU_PREVIEW.md)를 따른다.

## Reference identity and provenance

- The image used for this restoration is the **confirmed available reference**, not a confirmed final/approved product identity:
  `attached_assets/ChatGPT_Image_2026년_10월_10일_오전_11_47_32_(2)_1791600929106.png`
- SHA-256: `f8eae8f8bf551f2796aa35df96318916fb1ba7c09dd8721462adafe31809d597`
- Companion prompt: `attached_assets/Pasted---1791600976009_1791600976009.txt`
- The prompt's own framing at lines 18–19 says “최종적으로 첨부한 확정 목업처럼”; however, the task explicitly says the available image identity is not confirmed as the final identity. This implementation records the image as a reference only.

## Prompt citations and design criteria

The user requested the “reference's navy/blue, pale blue/white surfaces, gold search CTA, Korean sans typography, compact hierarchy, spacing, photo cards/badges/filter/detail tabs and HOME & STAY wordmark.”

The companion prompt's directly relevant passages:

- Lines 18–19: use the attached mockup as the target for an integrated listing experience.
- Lines 83–109: one common listing UI; keep the deal channels represented as separate data choices, not duplicated lists.
- Lines 113–157: top navigation and common filters in the original listing-system scope.
- Lines 368–393: consistent listing-card structure and distinct public badges.
- Lines 397–419: shared detail-page structure with independent information sections.
- Lines 525–542: PC-first reference, with a usable mobile adaptation and no clipped content.

Restoration criteria applied: navy wordmark and headings; pale blue page, map, and filter surfaces; gold search/primary action; Korean system sans stack; tighter controls and card spacing; distinct location/privacy badges; persistent detail-section navigation; and responsive list/map switching.

## Constraint adjustments

- **Navigation:** The source mockup's top-level direct/broker/auction categories were not copied into the short-stay consumer navigation. The current product constraint keeps short stays primary and sales, business-rights, and auction as independent map layers, rather than core top-nav tabs.
- **Minimum stay:** Existing detail behavior is preserved. Public summary data controls the minimum stay where available; current fallbacks remain one night for lodging and seven days for non-lodging. No mockup value was allowed to overwrite this.
- **Price:** Existing selected-stay-total quote behavior and terms remain unchanged. Prices are not converted into nightly, weekly, or monthly comparisons, and no quote is invented.
- **Privacy and bookings:** IDs, handlers, endpoints, hidden metadata, location withholding, authentication, quote confirmation, booking, payment, and Toss-related contracts were not changed.
- **Images:** Consumer result cards now clearly say “사진 비공개,” as required for withheld consumer listings. The inspected supermap and detail renderers expose no public image/photo field or photo element to style. No photos were fabricated or inferred, and no new data field was guessed. Thus real public photos are not yet rendered in supermap cards/detail; this needs an existing, explicitly public image field in the API contract before a UI can safely consume it.
- **Detail tabs:** The new detail navigation uses in-page links to existing sections. It does not change quote or reservation behavior.

## Missing exact assets and limitations

- No confirmed final identity, dedicated Korean font file, or new approved property photography was supplied. Typography uses the existing Korean system fallback stack; the HOME & STAY text wordmark uses that stack alongside the existing logo asset.
- The design implementation worker did not run browser tests. The subsequent main-agent verification is recorded below; actual provider connections are still unverified.

## Changed routes and files

- Consumer search: `hs2_consumer/web/main.html`, `hs2_consumer/web/main.css`
- Supermap search (desktop and mobile route styling): `hs2_supermap/web/search.html`, `hs2_supermap/web/search.css`, `hs2_supermap/web/mobile.css`
- Stay details: `hs2_details/web/detail.html`, `hs2_details/web/detail.css`

No application JavaScript, API, backend, fixture, database, or production files
were changed. Separate verification/report scripts and this documentation were added.

## Actual validation — 2026-10-11

- Functional regression: **19/19 PASS, zero skipped**, including phase 4–16 UI
  checks and phase 5/8/9/10/11/16 contracts. Owned temporary PostgreSQL, synthetic
  identities and payment fixtures only. Results:
  `generated-artifacts/mockup-regression/run-53n3qa_r/summary.json`.
- Source preservation: 1,228 tracked files checked; no test-induced modifications.
  The checks measure the changed HTML/CSS, not a pre-restoration version.
- Design criterion automation: `scripts/hs2_mockup_visual_check.cjs`, **8
  route/viewport combinations PASS** at 1440px and 390px. Checks navy/blue
  heading hierarchy, gold search `#b28a31`, white/off-white cards, HOME & STAY
  wordmark, nonempty cards, horizontal overflow, three detail section links,
  and mobile map switching. This is not a pixel-difference match against the
  source board, and it does not prove exact font identity.
- Manual comparison: reference image opened and compared with current consumer,
  desktop/mobile Super Map, and detail JPG captures. Blue/gold palette, pale-blue
  surfaces, card borders, filters and detail section navigation are present.
  Public photographs remain unavailable; no unapproved photographs were inserted.
- Final design judgment: **reference direction reproduced with documented
  adjustments; complete visual identity is NOT established**. Missing final
  single-screen approval, exact font/logo source and publicly consented photos
  prevent a claim of exact reproduction.
- Chromium environment caveat: the local Nix browser used by the automation
  lacks Korean fallback glyphs. Deliverable JPGs were separately captured with
  a Korean-capable browser and inspected. Automated PNGs are not evidence of
  Korean typography fidelity.
- Additional production-boundary test was attempted and exceeded the 120-second
  shell deadline; incomplete, **not PASS**. It is excluded from the 19 checks.
- The running Preview uses the unchanged synthetic bootstrap and owned SDK.
  No production DB, actual Toss, settlement, email/SMS or production deployment
  was used.

## Preview entry points

- `/` redirects to `/hs2/consumer`; its header now links to `/hs2/search/`.
- `/hs2/search/` is full desktop layer/filter/detail search.
- `/hs2/search/mobile/` preserves list↔map switching.
- `/hs2/details/?public_id=…` is reached by selecting an actual synthetic
  public result and opening its detail link. Its section navigation is in-page,
  not a replacement for booking, saved stays or inquiry behavior.
- Initial integrated sales UI remains `/listings` in the legacy app. It is not
  substituted for the consumer main, and the legacy route was not modified.

Comparison deliverable: `generated-artifacts/mockup-comparison/mockup-comparison.html`
generated by `scripts/hs2_mockup_comparison.py`. Historical before captures are
labelled with their different viewport sizes; no pixel-percentage score is claimed.
