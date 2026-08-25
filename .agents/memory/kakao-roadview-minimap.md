---
name: Kakao Roadview minimap
description: Why Roadview needs an application-owned overview map instead of a presumed SDK control.
---

Kakao Maps JavaScript `Roadview` does not expose `addControl`, `RoadviewMapControl`, or `RoadviewControlPosition`. A Roadview minimap must be a second `kakao.maps.Map` embedded in the panel, with its marker and center synchronized to the active panorama.

**Why:** Guarding against non-existent SDK names silently skips the feature, leaving users with no small location map and no console error.

**How to apply:** Create and relayout the overview map only after its panel is visible; update it when a panorama is selected and when the Roadview panorama changes. Keep the overview map non-draggable and non-zoomable so it remains an orientation aid, not a competing map.