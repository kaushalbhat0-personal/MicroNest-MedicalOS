# 03 — Visual-asset audit (dental-erp @ 389d9841)

Method: `git ls-files` grep for
`\.(svg|png|jpg|jpeg|webp|woff2?|ttf|otf|ico)$` + `public/` listing + manifest read.

## Asset inventory

| # | Path | Format / dims | Size | Purpose | Provenance | Suitability | Call |
|---|---|---|---|---|---|---|---|
| 1 | `app/icon.svg` | SVG, 442 B, tooth glyph on `#0891B2` rounded square + slash | 442 B | App icon (App Router convention) | **Original** — matches `theme_color #0891B2` in manifest; no third-party marks | Not for reuse (their brand mark; our white-label pipeline owns icons) | **Reject** |
| 2 | `public/manifest.json` | JSON, references `/icon-192.png` + `/icon-512.png` | 497 B | PWA manifest | Own file, but **referenced PNGs are absent from the repo** (broken reference) | — | **Reject** (and note: their repo ships a dangling manifest) |
| 3 | `uploads/.gitkeep` | placeholder | 0 B | Keeps runtime upload dir | — | — | **Reject** |

**No other image/font files are tracked.** No PNG/JPEG/WebP, no tooth diagrams,
no odontogram PNGs, no arch diagrams, no empty-state illustrations, no patient
education visuals, no bundled fonts.

## Category verdicts

1. **Original code-generated SVG artwork** — the odontogram/chart/imaging
   visuals are drawn in code (`dental-chart.tsx`, `dental-3d-viewer.tsx`,
   canvas annotator). This is the correct architectural idea (projection, not
   stored pixels — same principle as our DESIGN.md §14) but the code is not an
   "asset" to copy; see `06-reuse-candidates.md`.
2. **Original static artwork** — only `app/icon.svg` (their logo). Reject.
3. **Third-party artwork** — none found in the repo.
4. **Third-party icon libraries** — `lucide-react ^1.70.0` (npm dependency,
   ISC-licensed upstream). Using Lucide in our product is a dependency decision
   for our own repo, not a reuse from this audit; no icon files are vendored.
5. **Fonts** — none bundled (system stack + optional webfonts via next/font
   config; nothing to clear or copy).
6. **Unclear-provenance assets** — none found. (The two missing manifest PNGs
   are absent, not unclear — flagging so nobody goes hunting for them.)

## License note

MIT on the repository covers the code; it does **not** need to cover anything
here because there are no third-party artworks or fonts to clear. Had there
been any, MIT would not automatically clear them — verified by absence, not
assumption. If we later adopt Lucide independently, honor its upstream license
in our own dependency record.

## Bottom line

**Nothing to reuse, recreate only what we design ourselves.** Our odontogram
and any dental illustrations must be recreated natively under DESIGN.md
(tokens, no color-only meaning, contrast-verified). Do not copy their icon.
