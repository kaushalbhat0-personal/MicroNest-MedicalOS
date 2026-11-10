/**
 * Zero-dependency tests for packages/ui/imaging-transform.ts.
 *
 * Run: node --test packages/ui/imaging-transform.test.mjs
 * (from the repository root; needs Node with type stripping, no install step).
 *
 * These cover the viewer's presentation math: zoom boundaries, rotation wrap,
 * flip toggles, brightness/contrast clamps, CSS builders, default detection,
 * and the keyboard map. Component rendering, focus order, and responsive
 * behavior have no DOM runner in this repo yet — see D1 report §8/§10.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_TRANSFORM,
  LEVEL_DEFAULT,
  LEVEL_MAX,
  LEVEL_MIN,
  ZOOM_MAX,
  ZOOM_MIN,
  buildFilterCss,
  buildTransformCss,
  clampZoom,
  isDefaultTransform,
  normalizeRotation,
  panEnabled,
  resetTransform,
  rotateClockwise,
  rotateCounterClockwise,
  setBrightness,
  setContrast,
  setPan,
  setZoom,
  toggleFlipH,
  toggleFlipV,
  viewerKeyAction,
  zoomBy,
  zoomPercentLabel,
} from "./imaging-transform.ts";

const base = () => ({ ...DEFAULT_TRANSFORM });

describe("zoom boundaries", () => {
  it("clamps below min and above max", () => {
    assert.equal(clampZoom(0.01), ZOOM_MIN);
    assert.equal(clampZoom(99), ZOOM_MAX);
    assert.equal(clampZoom(1.5), 1.5);
  });

  it("zoomBy never escapes the range", () => {
    assert.equal(zoomBy(base(), -10).zoom, ZOOM_MIN);
    assert.equal(zoomBy(base(), 10).zoom, ZOOM_MAX);
    assert.equal(zoomBy(base(), 0.25).zoom, 1.25);
  });

  it("setZoom clamps and rounds to 2dp", () => {
    assert.equal(setZoom(base(), 1.555).zoom, 1.56);
    assert.equal(setZoom(base(), 5.555).zoom, ZOOM_MAX);
    assert.equal(setZoom(base(), -3).zoom, ZOOM_MIN);
  });

  it("labels zoom as a whole percent", () => {
    assert.equal(zoomPercentLabel(base()), "100%");
    assert.equal(zoomPercentLabel(setZoom(base(), 2.5)), "250%");
  });
});

describe("rotation", () => {
  it("wraps clockwise past 270 back to 0", () => {
    const t = { ...base(), rotation: 270 };
    assert.equal(rotateClockwise(t).rotation, 0);
  });

  it("wraps counter-clockwise from 0 to 270", () => {
    assert.equal(rotateCounterClockwise(base()).rotation, 270);
  });

  it("normalizes arbitrary degrees to the nearest quarter-turn", () => {
    assert.equal(normalizeRotation(91), 90);
    assert.equal(normalizeRotation(359), 0);
    assert.equal(normalizeRotation(-45), 0);
    assert.equal(normalizeRotation(725), 0);
  });
});

describe("flip and levels", () => {
  it("toggles mirrors independently", () => {
    const t = toggleFlipH(toggleFlipV(base()));
    assert.equal(t.flipH, true);
    assert.equal(t.flipV, true);
    assert.equal(toggleFlipH(t).flipH, false);
  });

  it("clamps brightness/contrast to 0..200 integers", () => {
    assert.equal(setBrightness(base(), 999).brightness, LEVEL_MAX);
    assert.equal(setContrast(base(), -5).contrast, LEVEL_MIN);
    assert.equal(setBrightness(base(), 122.7).brightness, 123);
    assert.equal(setContrast(base(), LEVEL_DEFAULT).contrast, LEVEL_DEFAULT);
  });
});

describe("css builders (projection only)", () => {
  it("renders the documented transform order", () => {
    assert.equal(
      buildTransformCss({ ...base(), zoom: 2, rotation: 90, flipH: true, panX: 10, panY: -4 }),
      "translate(10px, -4px) rotate(90deg) scale(-2, 2)",
    );
  });

  it("returns filter none at defaults (original rendering proof)", () => {
    assert.equal(buildFilterCss(base()), "none");
    assert.equal(
      buildFilterCss(setBrightness(base(), 120)),
      "brightness(120%)",
    );
    assert.equal(
      buildFilterCss(setContrast(setBrightness(base(), 80), 140)),
      "brightness(80%) contrast(140%)",
    );
  });
});

describe("default detection and pan gating", () => {
  it("detects any deviation including pan", () => {
    assert.equal(isDefaultTransform(base()), true);
    assert.equal(isDefaultTransform(zoomBy(base(), 0.25)), false);
    assert.equal(isDefaultTransform(toggleFlipV(base())), false);
    assert.equal(isDefaultTransform(setPan(base(), 1, 0)), false);
    assert.equal(isDefaultTransform(resetTransform()), true);
  });

  it("enables drag-pan only past 1x", () => {
    assert.equal(panEnabled(1), false);
    assert.equal(panEnabled(1.01), true);
    assert.equal(panEnabled(0.5), false);
  });

  it("resetTransform returns an independent default copy", () => {
    const a = resetTransform();
    const b = resetTransform();
    assert.notEqual(a, b);
    assert.deepEqual(a, b);
  });
});

describe("keyboard map", () => {
  it("maps display keys regardless of collection", () => {
    const ctx = { zoomed: false, hasMultipleImages: false };
    assert.equal(viewerKeyAction("+", ctx), "zoom-in");
    assert.equal(viewerKeyAction("=", ctx), "zoom-in");
    assert.equal(viewerKeyAction("-", ctx), "zoom-out");
    assert.equal(viewerKeyAction("0", ctx), "reset");
    assert.equal(viewerKeyAction("r", ctx), "rotate-cw");
    assert.equal(viewerKeyAction("R", ctx), "rotate-ccw");
    assert.equal(viewerKeyAction("f", ctx), "fullscreen");
  });

  it("pans with arrows when zoomed, steps images at fit scale", () => {
    const zoomed = { zoomed: true, hasMultipleImages: true };
    assert.equal(viewerKeyAction("ArrowLeft", zoomed), "pan-left");
    assert.equal(viewerKeyAction("ArrowRight", zoomed), "pan-right");
    assert.equal(viewerKeyAction("ArrowUp", zoomed), "pan-up");
    assert.equal(viewerKeyAction("ArrowDown", zoomed), "pan-down");

    const fit = { zoomed: false, hasMultipleImages: true };
    assert.equal(viewerKeyAction("ArrowLeft", fit), "prev-image");
    assert.equal(viewerKeyAction("ArrowRight", fit), "next-image");
    assert.equal(viewerKeyAction("ArrowUp", fit), null);
  });

  it("returns null for single images and unknown keys", () => {
    const solo = { zoomed: false, hasMultipleImages: false };
    assert.equal(viewerKeyAction("ArrowLeft", solo), null);
    assert.equal(viewerKeyAction("ArrowRight", solo), null);
    assert.equal(viewerKeyAction("x", solo), null);
    assert.equal(viewerKeyAction("Enter", solo), null);
  });
});
