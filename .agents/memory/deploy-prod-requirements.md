---
name: Deploy slimming via prod-only requirements
description: How livingstay cut publish time by removing pandas from the deploy path
---
Rule: requirements.txt is what the deployment installs — keep it prod-only. Heavy libs used only by offline scripts (pandas/numpy ~150MB) must not be there, and nothing on the app boot path may import them.
**Why:** pandas was top-level imported by address_utils (imported by app.py at boot), forcing a 1.1s import and ~150MB into every deploy just to read one tab-separated cp949 CSV. Rewrote with stdlib csv (0.23s load, identical results modulo trailing-space strip).
**How to apply:** before adding a dep to requirements.txt, check it's needed at runtime in prod; keep boot-path imports light (lazy-import heavy libs inside functions, like the openpyxl Excel exports). Dev scripts keep pandas installed locally — documented in replit.md.
