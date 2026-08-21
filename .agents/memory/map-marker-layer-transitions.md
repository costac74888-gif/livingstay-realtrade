---
name: Map marker layer transitions
description: Rendering rule for smooth Kakao Map layer swaps.
---

Map overlays that participate in zoom-level layer swaps must use DOM-backed
`CustomOverlay` instances, including visually small dot markers.

**Why:** Kakao native `Marker` instances do not expose an opacity transition.
Removing them while numbered badges or cluster overlays fade causes a visible
hard cut during a layer swap.

**How to apply:** When adding a new marker style to the map, attach its DOM
element as the overlay's content, store it in the current layer collection, and
set the element on the overlay's transition path before removing it.