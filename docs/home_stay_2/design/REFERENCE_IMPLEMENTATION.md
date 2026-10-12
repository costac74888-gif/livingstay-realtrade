# HOME & STAY reference implementation notes

This refactor uses the corrected public captures and `observations.json` in
`generated-artifacts/hs2-rebuild/reference-current/` as the visual evidence. It keeps
the existing HOME & STAY marks, native map/provider surface, search controls,
routes, and controller behavior; styling is limited to the approved frontend
layers.

## Observed

- **33m2 public home** returned HTTP 200 at mobile (390px) and desktop
  (1440px), redirecting to `web.33m2.co.kr/guest/main`. The captured page has a
  white navigation bar, short-stay messaging, property-type tiles, a prominent
  map-search link, editorial guide cards, reviews, and a compact AI help action.
- **Airbnb public home** returned HTTP 200 at 390px and 1440px. Its mobile
  capture uses a pill-shaped search entry, horizontal category chips, two-up
  listing cards, and a persistent bottom navigation bar.
- **33m2 search** at the corrected DOM URL
  `https://web.33m2.co.kr/guest/search` returned a live search screen at 390px
  and 1440px. Mobile shows an identity/search strip above a horizontally
  browsable, two-column accommodation list; desktop shows search and filter
  controls, a two-column result list, and a large map at the right. Weekly rent
  is explicitly labelled by its per-week basis.
- **33m2 host entry** at the corrected DOM URL
  `https://web.33m2.co.kr/ko/host/main` returned the public host introduction
  at 390px and 1440px. A promotional modal overlays the page in these captures.
  The page presents registration/onboarding benefits, not an authenticated
  operator dashboard.
- **Airbnb Seoul search** returned HTTP 200 at 1440px. The observed desktop
  layout has a compact header and filter row, a two-column results area on the
  left, and a large map on the right. The 390px search capture shows a map
  above a listing card, with bottom navigation.
- **Airbnb hosting entry** redirected to its login route. The mobile capture
  is an email/phone sign-in surface; the desktop capture shows a sign-in card
  over host-promotion artwork.
- Monthly/weekly rentals use a blue price and map-marker treatment; nightly
  lodging uses red to distinguish the Airbnb-style stay category.

## Not observed / not claimed

- Earlier `33m2.co.kr/guest/search` and `/host/main` URLs were not the current
  public entry points; those obsolete captures are superseded and excluded.
- Authenticated 33m2 operator workflows and Airbnb host dashboards were not
  captured. HOME & STAY operator management remains **NOT_OBSERVED** against
  those references; the existing owner interface is preserved without
  asserting equivalence.
- Public search was observed at 390px and 1440px. Public property detail was
  additionally captured at 360px, 390px, 430px and 1440px for both services in
  `generated-artifacts/hs2-rebuild/reference-detail/`.
- The actual 33m2 host room, contract and chat links were visited at all four
  widths. Each redirected to sign-in; their internal screens remain
  **NOT_OBSERVED**.
- HOME & STAY has fresh browser evidence at 360px, 390px, 430px and 1440px.
  These checks cover overflow, owned photo loading, current computed price and
  action colors, list scrolling and horizontal-versus-vertical touch-event
  handling. DOM touch-event checks are not physical iPhone verification.
- The owned fixture booking/chat/payment flow passed 14 scenarios. It does
  not validate real legacy identities, a Toss merchant or competitor parity.
  Registry coverage remains 45 API/fixture-mapped items and 201 local
  presentation items; the overall preproduction request is **INCOMPLETE**.

## Implementation choices and boundaries

- White remains the page surface. Existing HOME & STAY logos are unchanged.
- The audited brand uses Pretendard at compact 13px and regular 16px sizes.
  The original local font setup is retained instead of copying proprietary
  font files. The Airbnb mark's observed pink (`#ff385c`) remains reference
  context only; the HOME & STAY wordmark is not replaced.
- Week/month prices and map markers are blue; nightly lodging prices and
  markers use the observed Airbnb red `#ff385c`. No olive, mustard, or gold
  presentation is introduced.
- Consumer mobile map/list controls are limited to the existing native results
  and map surfaces; the owner route does not receive the new consumer switch.
  The mobile result grid follows the observed two-across, horizontally
  browsable 33m2 card presentation. Photo controls stay compact and in normal
  result flow rather than becoming fixed overlays.
- Existing APIs, IDs, routes, map provider, controllers, and legacy screens
  remain untouched. Local preview/mock behavior is not claimed as functional
  production behavior.
- Owner booking and chat links now select the native `operator` scope rather
  than silently selecting consumer scope with an unsupported `owner` value.
  Old `view=owner` links redirect with their selected booking context intact;
  changing the URL does not grant a role.
- Historical comparison files and captures remain in their original directory.
  The new workbook retains previous sheets and adds current observations; its
  old olive adoption text is historical, not evidence for this rebuild.
- Current Toss configuration was checked without displaying values or calling
  the provider. Both keys are document-example keys, so real merchant approval,
  cancellation and refund checks are **BLOCKED**, not passed.
