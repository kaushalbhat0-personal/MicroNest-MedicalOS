# 03 — Coordinate and Transform Architecture

Constraint (verified): `packages/ui/imaging-transform.ts` is pure,
zero-dependency, and tested (`node --test imaging-transform.test.mjs`).
**Do not modify it.** The mapping below consumes its outputs and lives in
new annotation code.

## 1. Ground truth: what the D1 viewer actually renders

`imaging.tsx:312-327` renders `<img>` with (verified lines):

```
transform: translate(panX,panY) rotate(R) scale(sx,sy)   // R ∈ {0,90,180,270}
filter:    brightness/contrast only (geometry-free)
```

plus layout: flex-centered, `max-width:100%`, aspect preserved
(`width:auto;height:auto`), so the layout box is a uniform scale of the
natural image. CSS default `transform-origin: 50% 50%` applies: rotation
and scale happen **about the image-box center**, and the transform list
applies **right-to-left** (scale in image-local axes, then rotate, then
screen-space pan).

Consequence: brightness/contrast never enter geometry math. Only
`{zoom, rotation, flipH, flipV, panX, panY}` plus the layout scale matter.

## 2. Storage coordinate system (normative)

- **Normalized per-mille integers.** Every anchor is `(U,V)` with
  `0 ≤ U,V ≤ 1000`, mapping to `(u,v) = (U/1000, V/1000)` of the
  **natural** image (`naturalWidth × naturalHeight`).
- Rectangles: `{x, y, w, h}` per-mille, invariant `x+w ≤ 1000`, `y+h ≤ 1000`
  (fully inside the image — shapes are clamped at draw time, never
  stored out-of-bounds).
- Markers/labels: single `(U,V)` anchor, clamped to `[0,1000]`.
- Why integers: exact JSON round-trips, trivial server validation, no
  float drift across revisions, compact payloads. Precision (0.1% of image
  width ≈ sub-pixel on any clinical display) exceeds need.

Annotations attach to the **original image coordinate system**, never to
screen pixels. Zoom/pan/rotation/flip/responsive size change rendering
only; stored values never move.

## 3. Rendering: shared-transform SVG overlay (recommended)

Place an `<svg viewBox="0 0 1000 1000" preserveAspectRatio="none">`
absolutely covering the `<img>` layout box **inside the same transformed
wrapper**, so image and overlay share one identical CSS transform:

```
<div style={{ transform: buildTransformCss(t) }}>   // existing string
  <img ... />                                       // existing
  <svg viewBox="0 0 1000 1000" ... />               // overlay, same box
</div>
```

- Rendering then needs **no per-frame math**: the browser keeps overlay
  and image aligned under every supported transform by construction
  (proof obligation becomes a test: overlay box ≡ image box pre-transform).
- `preserveAspectRatio="none"` is safe **iff** the overlay box exactly
  equals the image layout box (both aspect-locked to the same natural
  ratio) — enforce by construction (same offset box), asserted in tests.
- SVG, not canvas (deliberate divergence from DentalERP's dual-canvas):
  resolution/DPR-independent, per-shape focus and `<title>` for the
  keyboard/SR path (§02-§5), no backing-store scaling math, no bitmap
  snapshot memory for undo.
- Stroke fidelity under zoom: `vector-effect="non-scaling-stroke"` keeps
  stroke width constant in screen px while shape geometry scales with the
  image (correct: the mark tracks anatomy; the line stays legible).
  Pin glyphs keep a minimum screen size via the same mechanism.

## 4. Pointer → normalized mapping (normative)

Frames: **N** normalized → **P** natural px → **L** layout px (top-left
origin, uniform display scale `d = offsetWidth/naturalWidth =
offsetHeight/naturalHeight`; assert uniformity, §6) → **S** stage coords:

```
S = T(pan) · T(c) · Rot(R) · F · Z(z) · T(−c) · L
c = layout-box center in stage coords, F = diag(±1,±1), Z = diag(z,z)
```

Inverse (what the draw handler implements):

```
q  = pointer in stage coords            // clientX/Y − stage rect
q1 = q − pan                            // invert screen-space pan first
q2 = q1 − c                             // move to rotation center
q3 = Rot(−R) · q2                       // exact quarter-turn (table below)
q4 = (flipH ? −q3.x : q3.x, flipV ? −q3.y : q3.y)
q5 = q4 / z
L  = q5 + c
(u,v) = (L.x / (d·W), L.y / (d·H));  clamp to [0,1]; store round(1000·u,v)
```

Quarter-turn inverses (CSS `rotate()` is clockwise-positive, y-down),
with `(x,y)` centered coords and `R` the current clockwise rotation:

| R   | forward `(a,b) →` | inverse `(x,y) →` |
|-----|-------------------|--------------------|
| 0   | `(a,b)`           | `(x,y)`            |
| 90  | `(−b,a)`          | `(y,−x)`           |
| 180 | `(−a,−b)`         | `(−x,−y)`          |
| 270 | `(b,−a)`          | `(−y,x)`           |

Composition order (matches the CSS chain): **un-rotate first, then
un-mirror** — the inverse of `Rot·Scale` is `Scale⁻¹·Rot⁻¹`. Getting this
backwards is the classic bug when flip and rotation combine; the test
matrix (§07) pins all 4×2×2 combinations.

Pseudocode (draw handler):

```
function toNormalized(evt, img, stage, t):
  r = stage.getBoundingClientRect()
  q = { x: evt.clientX - r.left, y: evt.clientY - r.top }
  // layout (transform-free) metrics only:
  d  = img.offsetWidth / img.naturalWidth
  c  = { x: img.offsetLeft + img.offsetWidth/2 - stage.offsetLeft...,
         y: ... }                       // layout coords, no transforms
  q1 = sub(q, {x: t.panX, y: t.panY})
  q3 = unrotate(sub(q1, c), t.rotation)  // table above
  q4 = { x: t.flipH ? -q3.x : q3.x, y: t.flipV ? -q3.y : q3.y }
  L  = add(div(q4, t.zoom), c)
  u  = clamp01(L.x / (d * img.naturalWidth))
  v  = clamp01(L.y / (d * img.naturalHeight))
  return { U: round(u*1000), V: round(v*1000) }
```

Notes: use `offsetWidth/offsetHeight/offsetLeft/offsetTop`
(transform-free layout metrics), never `getBoundingClientRect` of the
transformed image; `naturalWidth/Height` is the storage space; `d` must be
uniform — non-uniform `d` means the box is wrong, fail loudly, never store.

## 5. Why this survives every D1 transform

- **Resize / responsive / mobile-vs-desktop:** `d` is re-measured per
  render; stored per-mille values are size-agnostic.
- **Zoom/pan:** inverted exactly (`/z`, `−pan`); pan step constants stay
  screen-space, annotation math unaffected.
- **Rotation:** quarter-turn-only model (enforced by `normalizeRotation`)
  gives exact integer-center mapping — no trig, no drift.
- **Flip:** self-inverse mirror in image-local axes, composed before
  rotation exactly as the CSS chain does.
- **Combined rotate+flip:** order pinned by table + inverse order rule.
- **DPR:** vector overlay; no pixel math anywhere.
- **Aspect:** locked by the image element itself; overlay inherits the box.

## 6. Edge cases and rules

- Out-of-image pointer: clamp markers; reject zero-area rectangles
  (minimum 8×8 per-mille — below that it is a tap, store a marker).
- Zero-size image (metadata without bytes): annotation mode disabled —
  same eligibility gate as viewing (`image/` content type + successful
  grant).
- New image (new reference): new coordinate space; no transfer (§01-§3).
- Text labels: anchor + optional per-mille offset; text itself is metadata,
  never geometry; 140-char cap, plain text.
- Undo/redo: command stack over normalized values (transform-independent
  by construction — undo never needs re-projection).
