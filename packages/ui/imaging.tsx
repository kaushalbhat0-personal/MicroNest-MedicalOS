"use client";

import * as React from "react";
import {
  FlipHorizontal2,
  FlipVertical2,
  Maximize,
  Minimize,
  RefreshCcw,
  RotateCcw,
  RotateCw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { IconButton } from "./Button";
import { Badge, Card, EmptyState, ErrorState, LoadingState } from "./feedback";
import {
  PAN_KEY_STEP,
  ZOOM_MAX,
  ZOOM_MIN,
  ZOOM_STEP_BUTTON,
  buildFilterCss,
  buildTransformCss,
  isDefaultTransform,
  panEnabled,
  resetTransform,
  rotateClockwise,
  rotateCounterClockwise,
  setBrightness,
  setContrast,
  setPan,
  toggleFlipH,
  toggleFlipV,
  viewerKeyAction,
  zoomBy,
  zoomPercentLabel,
  type ViewerTransform,
} from "./imaging-transform";

/**
 * Read-only clinical image viewer.
 *
 * Presentational only: the caller supplies an authorized image URL via
 * `image.src` (see security contract below) and owns loading/error state.
 * Zoom, rotation, flip, brightness and contrast are VIEW-TIME CSS projections
 * — the stored original is never altered, overwritten, or re-uploaded.
 *
 * SECURITY CONTRACT (D1): there is currently NO authorized image-byte
 * retrieval endpoint in the Healthcare OS (document references carry metadata
 * only; StoragePort.signed_access has no API wiring; portal downloads are
 * honestly unavailable). Do NOT wire this viewer to invented URLs or pass
 * storage keys as `src`. Integration stays unwired until a tenant-scoped,
 * patient-authorized signed-URL endpoint is separately approved and built.
 * Callers must pass minimal-PHI display text (DESIGN.md §16: no PHI in
 * titles, toasts, or logs). No image data is persisted in browser storage.
 */

export type ViewerImageMeta = { label: string; value: string };

export type ViewerImage = {
  /** Authorized retrieval URL. Must come from an approved authorized flow. */
  src: string;
  /** Minimal display title (no PHI beyond what the chart surface already shows). */
  title: string;
  subtitle?: string;
  meta?: ViewerImageMeta[];
};

export type ViewerStatus = "loading" | "ready" | "empty" | "error";

export type ClinicalImageViewerProps = {
  image: ViewerImage | null;
  /** Full authorized collection for prev/next stepping (same encounter scope). */
  images?: ViewerImage[];
  currentIndex?: number;
  onIndexChange?: (index: number) => void;
  status: ViewerStatus;
  /** Non-PHI failure summary shown in the error state. */
  errorMessage?: string;
  onRetry?: () => void;
  label?: string;
};

const ICON_SIZE = 18;

export function ClinicalImageViewer({
  image,
  images,
  currentIndex = 0,
  onIndexChange,
  status,
  errorMessage,
  onRetry,
  label = "Clinical image viewer",
}: ClinicalImageViewerProps) {
  const [t, setT] = React.useState<ViewerTransform>(() => resetTransform());
  const [mediaFailed, setMediaFailed] = React.useState(false);
  const [retryNonce, setRetryNonce] = React.useState(0);
  const [canFullscreen, setCanFullscreen] = React.useState(false);
  const [isFullscreen, setIsFullscreen] = React.useState(false);
  const wrapRef = React.useRef<HTMLElement | null>(null);
  const dragRef = React.useRef<{ startX: number; startY: number; baseX: number; baseY: number } | null>(null);

  const collection = images && images.length > 1 ? images : null;
  const position = collection ? `${currentIndex + 1} of ${collection.length}` : null;

  // Presentation state never carries across images: a new image starts true.
  React.useEffect(() => {
    setT(resetTransform());
    setMediaFailed(false);
  }, [image?.src]);

  React.useEffect(() => {
    if (typeof document === "undefined") return;
    setCanFullscreen(Boolean(document.fullscreenEnabled));
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const adjusted = !isDefaultTransform(t);
  const zoomed = panEnabled(t.zoom);

  function toggleFullscreen() {
    if (typeof document === "undefined") return;
    if (document.fullscreenElement) {
      void document.exitFullscreen().catch(() => {});
      return;
    }
    const el = wrapRef.current as unknown as { requestFullscreen?: () => Promise<void> } | null;
    if (el?.requestFullscreen) {
      void el.requestFullscreen().catch(() => {});
    }
  }

  function go(delta: 1 | -1) {
    if (!collection || !onIndexChange) return;
    const next = (currentIndex + delta + collection.length) % collection.length;
    onIndexChange(next);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    const action = viewerKeyAction(e.key, {
      zoomed,
      hasMultipleImages: Boolean(collection && onIndexChange),
    });
    if (!action) return;
    e.preventDefault();
    switch (action) {
      case "zoom-in":
        setT((v) => zoomBy(v, ZOOM_STEP_BUTTON));
        break;
      case "zoom-out":
        setT((v) => zoomBy(v, -ZOOM_STEP_BUTTON));
        break;
      case "rotate-cw":
        setT((v) => rotateClockwise(v));
        break;
      case "rotate-ccw":
        setT((v) => rotateCounterClockwise(v));
        break;
      case "reset":
        setT(resetTransform());
        break;
      case "fullscreen":
        if (canFullscreen) toggleFullscreen();
        break;
      case "prev-image":
        go(-1);
        break;
      case "next-image":
        go(1);
        break;
      case "pan-left":
        setT((v) => setPan(v, v.panX + PAN_KEY_STEP, v.panY));
        break;
      case "pan-right":
        setT((v) => setPan(v, v.panX - PAN_KEY_STEP, v.panY));
        break;
      case "pan-up":
        setT((v) => setPan(v, v.panX, v.panY + PAN_KEY_STEP));
        break;
      case "pan-down":
        setT((v) => setPan(v, v.panX, v.panY - PAN_KEY_STEP));
        break;
    }
  }

  function handlePointerDown(e: React.PointerEvent) {
    if (!zoomed) return;
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    dragRef.current = { startX: e.clientX, startY: e.clientY, baseX: t.panX, baseY: t.panY };
  }

  function handlePointerMove(e: React.PointerEvent) {
    const drag = dragRef.current;
    if (!drag) return;
    setT((v) => setPan(v, drag.baseX + (e.clientX - drag.startX), drag.baseY + (e.clientY - drag.startY)));
  }

  function endDrag() {
    dragRef.current = null;
  }

  function handleRetry() {
    setRetryNonce((n) => n + 1);
    setMediaFailed(false);
    onRetry?.();
  }

  if (status === "loading") {
    return (
      <Card title={label}>
        <LoadingState label="Loading image" />
      </Card>
    );
  }

  if (status === "error" || mediaFailed) {
    return (
      <Card title={label}>
        <ErrorState
          title="Image unavailable"
          onRetry={onRetry || mediaFailed ? handleRetry : undefined}
        >
          {errorMessage ?? "The image could not be displayed. No presentation changes were made."}
        </ErrorState>
      </Card>
    );
  }

  if (status === "empty" || !image) {
    return (
      <Card title={label}>
        <EmptyState title="No image selected">
          When an authorized image is available for this record, it can be viewed here.
        </EmptyState>
      </Card>
    );
  }

  const brightnessId = `civ-brightness-${retryNonce}`;
  const contrastId = `civ-contrast-${retryNonce}`;
  const hintId = `civ-hint-${retryNonce}`;

  return (
    <Card
      title={image.title}
      actions={adjusted ? <Badge tone="info">Adjusted view</Badge> : <Badge tone="neutral">Original view</Badge>}
    >
      <section
        ref={wrapRef as React.Ref<HTMLElement>}
        aria-label={label}
        aria-describedby={hintId}
        style={{ background: "var(--hos-surface)", color: "var(--hos-text-primary)" }}
      >
        {image.subtitle ? <p className="hos-helper">{image.subtitle}</p> : null}
        {image.meta && image.meta.length > 0 ? (
          <ul className="hos-helper" style={{ marginTop: 0, paddingLeft: "var(--hos-space-4)" }}>
            {image.meta.map((m) => (
              <li key={m.label}>
                {m.label}: {m.value}
              </li>
            ))}
          </ul>
        ) : null}
        {collection ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--hos-space-2)",
              marginBottom: "var(--hos-space-2)",
              flexWrap: "wrap",
            }}
          >
            <IconButton label="Previous image" onClick={() => go(-1)}>
              <span aria-hidden="true">‹</span>
            </IconButton>
            <span className="hos-helper" role="status">
              Image {position}
            </span>
            <IconButton label="Next image" onClick={() => go(1)}>
              <span aria-hidden="true">›</span>
            </IconButton>
          </div>
        ) : null}
        <div
          tabIndex={0}
          role="group"
          aria-label={`Image stage. ${zoomed ? "Zoomed in; drag or use arrow keys to pan." : "Fit to container."} Press plus to zoom in, minus to zoom out, R to rotate, 0 to reset${canFullscreen ? ", F for fullscreen" : ""}.`}
          onKeyDown={handleKeyDown}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          style={{
            position: "relative",
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "240px",
            maxHeight: "min(70vh, 640px)",
            background: "var(--hos-surface-muted)",
            border: "1px solid var(--hos-border)",
            borderRadius: "var(--hos-radius-sm)",
            cursor: zoomed ? "grab" : "default",
            touchAction: zoomed ? "none" : "pan-y",
          }}
        >
          <img
            key={`${image.src}#${retryNonce}`}
            src={image.src}
            alt={image.title}
            draggable={false}
            referrerPolicy="no-referrer"
            onError={() => setMediaFailed(true)}
            style={{
              maxWidth: "100%",
              maxHeight: "min(70vh, 640px)",
              width: "auto",
              height: "auto",
              transform: buildTransformCss(t),
              filter: buildFilterCss(t),
            }}
          />
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--hos-space-2)",
            flexWrap: "wrap",
            marginTop: "var(--hos-space-3)",
          }}
        >
          <IconButton label={`Zoom out (currently ${zoomPercentLabel(t)}, minimum ${Math.round(ZOOM_MIN * 100)} percent)`} onClick={() => setT((v) => zoomBy(v, -ZOOM_STEP_BUTTON))} disabled={t.zoom <= ZOOM_MIN}>
            <ZoomOut size={ICON_SIZE} aria-hidden="true" />
          </IconButton>
          <span className="hos-helper" role="status" style={{ minWidth: "48px", textAlign: "center" }}>
            {zoomPercentLabel(t)}
          </span>
          <IconButton label={`Zoom in (currently ${zoomPercentLabel(t)}, maximum ${Math.round(ZOOM_MAX * 100)} percent)`} onClick={() => setT((v) => zoomBy(v, ZOOM_STEP_BUTTON))} disabled={t.zoom >= ZOOM_MAX}>
            <ZoomIn size={ICON_SIZE} aria-hidden="true" />
          </IconButton>
          <IconButton label="Rotate clockwise" onClick={() => setT((v) => rotateClockwise(v))}>
            <RotateCw size={ICON_SIZE} aria-hidden="true" />
          </IconButton>
          <IconButton label="Rotate counter-clockwise" onClick={() => setT((v) => rotateCounterClockwise(v))}>
            <RotateCcw size={ICON_SIZE} aria-hidden="true" />
          </IconButton>
          <IconButton label={t.flipH ? "Remove horizontal flip" : "Flip horizontally"} onClick={() => setT((v) => toggleFlipH(v))} aria-pressed={t.flipH}>
            <FlipHorizontal2 size={ICON_SIZE} aria-hidden="true" />
          </IconButton>
          <IconButton label={t.flipV ? "Remove vertical flip" : "Flip vertically"} onClick={() => setT((v) => toggleFlipV(v))} aria-pressed={t.flipV}>
            <FlipVertical2 size={ICON_SIZE} aria-hidden="true" />
          </IconButton>
          {canFullscreen ? (
            <IconButton label={isFullscreen ? "Exit fullscreen" : "View fullscreen"} onClick={toggleFullscreen}>
              {isFullscreen ? (
                <Minimize size={ICON_SIZE} aria-hidden="true" />
              ) : (
                <Maximize size={ICON_SIZE} aria-hidden="true" />
              )}
            </IconButton>
          ) : null}
          <IconButton label="Reset view to original presentation" onClick={() => setT(resetTransform())} disabled={!adjusted}>
            <RefreshCcw size={ICON_SIZE} aria-hidden="true" />
          </IconButton>
        </div>
        <div
          style={{
            display: "flex",
            gap: "var(--hos-space-4)",
            flexWrap: "wrap",
            marginTop: "var(--hos-space-3)",
          }}
        >
          <div style={{ flex: "1 1 200px", minWidth: "200px" }}>
            <label className="hos-label" htmlFor={brightnessId}>
              Brightness: {t.brightness}%
            </label>
            <input
              id={brightnessId}
              type="range"
              min={0}
              max={200}
              step={5}
              value={t.brightness}
              onChange={(e) => setT((v) => setBrightness(v, Number(e.target.value)))}
              style={{ width: "100%", minHeight: "var(--hos-density-control-compact)" }}
            />
          </div>
          <div style={{ flex: "1 1 200px", minWidth: "200px" }}>
            <label className="hos-label" htmlFor={contrastId}>
              Contrast: {t.contrast}%
            </label>
            <input
              id={contrastId}
              type="range"
              min={0}
              max={200}
              step={5}
              value={t.contrast}
              onChange={(e) => setT((v) => setContrast(v, Number(e.target.value)))}
              style={{ width: "100%", minHeight: "var(--hos-density-control-compact)" }}
            />
          </div>
        </div>
        <p className="hos-helper" id={hintId} style={{ marginBottom: 0 }}>
          Display adjustments are presentation-only and do not change the stored image.
          Brightness and contrast changes do not improve diagnostic accuracy.
          Keyboard: + zoom in, - zoom out, R rotate, 0 reset
          {canFullscreen ? ", F fullscreen" : ""}
          {zoomed ? "; arrow keys pan" : collection ? "; left and right arrows change image" : ""}.
        </p>
      </section>
    </Card>
  );
}
