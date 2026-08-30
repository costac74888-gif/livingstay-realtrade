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

The user-confirmed map-location interaction keeps the surrounding marker layer
visible and pulses only the selected building's existing point. Clicking that
point opens the building detail and clears the pulse; the detail's map-location
button starts the same interaction again.

**Why:** Replacing the layer with a building-ID-only response makes every other
point disappear and leaves users without visual context or an easy way back.

**How to apply:** Center and zoom to the selected coordinates, reload the normal
viewport marker set without the text-search term, then apply selection styling
by building ID. Never use a target-only buildings-geo request for this action.