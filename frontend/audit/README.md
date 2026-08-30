# UI audit (Playwright)

One-shot audit of the running frontend: navigates every dashboard tab and
route at mobile / tablet / desktop widths and records, per combination:

- a **full-page screenshot** → `output/<view>__<viewport>.png`
- **axe-core** accessibility violations (WCAG 2 A + AA)
- **horizontal overflow** (page wider than the viewport) with the offending elements
- **navigation timing** (DOMContentLoaded / load) and total transfer size
- **console / page errors**

A machine-readable `output/report.json` is written and a summary is printed.

## Run

The frontend must be reachable (default `http://localhost:80`, i.e. the
`brainbets-frontend` container, or `npm run dev` on `:5173`).

```bash
cd frontend
npm install                       # first time
npx playwright install chromium   # first time
npm run audit
# custom target:
AUDIT_BASE_URL=http://localhost:5173 npm run audit
```

## Using it to compare before / after a redesign

1. Run once now, copy `output/` to `output-baseline/`.
2. Make UI changes.
3. Run again and diff the screenshots (any image tool) and the `report.json`
   (`violations`, `overflowPx`, `timing`).

`output/` is gitignored; commit `run-audit.mjs` and this README only.
