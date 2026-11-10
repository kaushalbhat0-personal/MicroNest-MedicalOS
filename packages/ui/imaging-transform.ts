/**
 * Presentation math for the clinical image viewer (packages/ui/imaging.tsx).
 *
 * Pure functions only — no React, no DOM, no imports. Zoom, rotation, flip,
 * brightness and contrast are VIEW-TIME projections: they build CSS strings
 * for rendering and must never be written back to a stored image.
 *
 * Kept free of enums/namespaces so the module stays runnable under Node type
 * stripping (tests: `node --test imaging-transform.test.mjs`, zero deps).
 */

export const ZOOM_MIN = 0.25;
export const ZOOM_MAX = 5;
export const ZOOM_DEFAULT = 1;
export const ZOOM_STEP_BUTTON = 0.25;
export const ZOOM_STEP_WHEEL = 0.1;

export const LEVEL_MIN = 0;
export const LEVEL_MAX = 200;
export const LEVEL_DEFAULT = 100;

export type Rotation = 0 | 90 | 180 | 270;

export type ViewerTransform = {
  zoom: number;
  rotation: Rotation;
  flipH: boolean;
  flipV: boolean;
  brightness: number;
  contrast: number;
  panX: number;
  panY: number;
};

export const DEFAULT_TRANSFORM: ViewerTransform = Object.freeze({
  zoom: ZOOM_DEFAULT,
  rotation: 0,
  flipH: false,
  flipV: false,
  brightness: LEVEL_DEFAULT,
  contrast: LEVEL_DEFAULT,
  panX: 0,
  panY: 0,
}) as ViewerTransform;

function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export function clampZoom(zoom: number): number {
  return round2(clamp(zoom, ZOOM_MIN, ZOOM_MAX));
}

export function zoomBy(t: ViewerTransform, delta: number): ViewerTransform {
  return { ...t, zoom: clampZoom(t.zoom + delta) };
}

export function setZoom(t: ViewerTransform, zoom: number): ViewerTransform {
  return { ...t, zoom: clampZoom(zoom) };
}

/** Any number of degrees → nearest valid quarter-turn (0/90/180/270). */
export function normalizeRotation(degrees: number): Rotation {
  const snapped = Math.round(degrees / 90) * 90;
  const wrapped = ((snapped % 360) + 360) % 360;
  return wrapped as Rotation;
}

export function rotateClockwise(t: ViewerTransform): ViewerTransform {
  return { ...t, rotation: normalizeRotation(t.rotation + 90) };
}

export function rotateCounterClockwise(t: ViewerTransform): ViewerTransform {
  return { ...t, rotation: normalizeRotation(t.rotation - 90) };
}

export function toggleFlipH(t: ViewerTransform): ViewerTransform {
  return { ...t, flipH: !t.flipH };
}

export function toggleFlipV(t: ViewerTransform): ViewerTransform {
  return { ...t, flipV: !t.flipV };
}

export function setBrightness(t: ViewerTransform, value: number): ViewerTransform {
  return { ...t, brightness: Math.round(clamp(value, LEVEL_MIN, LEVEL_MAX)) };
}

export function setContrast(t: ViewerTransform, value: number): ViewerTransform {
  return { ...t, contrast: Math.round(clamp(value, LEVEL_MIN, LEVEL_MAX)) };
}

export function setPan(t: ViewerTransform, panX: number, panY: number): ViewerTransform {
  return { ...t, panX: round2(panX), panY: round2(panY) };
}

/** Drag-pan only engages past 1x — at fit scale there is nothing to pan to. */
export function panEnabled(zoom: number): boolean {
  return zoom > ZOOM_DEFAULT;
}

export function resetTransform(): ViewerTransform {
  return { ...DEFAULT_TRANSFORM };
}

/**
 * CSS transform for the stage image. Order is deliberate: translate (screen
 * space pan) → rotate → scale (zoom × mirror). Mirrors compose with zoom so a
 * flipped view keeps the same magnification.
 */
export function buildTransformCss(t: ViewerTransform): string {
  const sx = round2(t.zoom * (t.flipH ? -1 : 1));
  const sy = round2(t.zoom * (t.flipV ? -1 : 1));
  return `translate(${t.panX}px, ${t.panY}px) rotate(${t.rotation}deg) scale(${sx}, ${sy})`;
}

/**
 * CSS filter for the stage image. Returns "none" at defaults so the rendered
 * output provably matches the stored original until the clinician adjusts it.
 */
export function buildFilterCss(t: ViewerTransform): string {
  const parts: string[] = [];
  if (t.brightness !== LEVEL_DEFAULT) parts.push(`brightness(${t.brightness}%)`);
  if (t.contrast !== LEVEL_DEFAULT) parts.push(`contrast(${t.contrast}%)`);
  return parts.length === 0 ? "none" : parts.join(" ");
}

/** True only when every presentation control is at its original value. */
export function isDefaultTransform(t: ViewerTransform): boolean {
  return (
    t.zoom === ZOOM_DEFAULT &&
    t.rotation === 0 &&
    !t.flipH &&
    !t.flipV &&
    t.brightness === LEVEL_DEFAULT &&
    t.contrast === LEVEL_DEFAULT &&
    t.panX === 0 &&
    t.panY === 0
  );
}

export function zoomPercentLabel(t: ViewerTransform): string {
  return `${Math.round(t.zoom * 100)}%`;
}

export type ViewerKeyAction =
  | "zoom-in"
  | "zoom-out"
  | "rotate-cw"
  | "rotate-ccw"
  | "reset"
  | "fullscreen"
  | "prev-image"
  | "next-image"
  | "pan-left"
  | "pan-right"
  | "pan-up"
  | "pan-down";

export type ViewerKeyContext = {
  /** Pan arrows when zoomed; image-step arrows at fit scale. */
  zoomed: boolean;
  hasMultipleImages: boolean;
};

/**
 * Keyboard map for the viewer stage. Returns null for unhandled keys so the
 * caller can ignore them. Arrow keys pan only when zoomed (there is somewhere
 * to go); at fit scale Left/Right step through an image collection instead.
 */
export function viewerKeyAction(
  key: string,
  ctx: ViewerKeyContext,
): ViewerKeyAction | null {
  switch (key) {
    case "+":
    case "=":
      return "zoom-in";
    case "-":
    case "_":
      return "zoom-out";
    case "0":
      return "reset";
    case "r":
      return "rotate-cw";
    case "R":
      return "rotate-ccw";
    case "f":
    case "F":
      return "fullscreen";
    case "ArrowLeft":
      if (ctx.zoomed) return "pan-left";
      return ctx.hasMultipleImages ? "prev-image" : null;
    case "ArrowRight":
      if (ctx.zoomed) return "pan-right";
      return ctx.hasMultipleImages ? "next-image" : null;
    case "ArrowUp":
      return ctx.zoomed ? "pan-up" : null;
    case "ArrowDown":
      return ctx.zoomed ? "pan-down" : null;
    default:
      return null;
  }
}

/** Pan step in CSS pixels per arrow-key press while zoomed. */
export const PAN_KEY_STEP = 40;
