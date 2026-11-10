"use client";

import * as React from "react";

/**
 * Odontogram foundation: an SVG projection of finding rows, never a stored
 * image. Callers pass tooth states derived from ToothFinding records;
 * selection maps back to FDI numbers + surfaces. Keyboard: roving
 * tabindex over teeth, Enter/Space selects.
 */

export type ToothState = "healthy" | "finding" | "planned" | "completed" | "selected";

export const PERMANENT_TEETH = [
  11, 12, 13, 14, 15, 16, 17, 18,
  21, 22, 23, 24, 25, 26, 27, 28,
  31, 32, 33, 34, 35, 36, 37, 38,
  41, 42, 43, 44, 45, 46, 47, 48,
];

const STATE_FILL: Record<ToothState, string> = {
  healthy: "var(--hos-surface)",
  finding: "var(--hos-clinical-attention-bg)",
  planned: "var(--hos-info-bg)",
  completed: "var(--hos-clinical-stable-bg)",
  selected: "var(--hos-blue-100)",
};

const STATE_STROKE: Record<ToothState, string> = {
  healthy: "var(--hos-border-strong)",
  finding: "var(--hos-clinical-attention)",
  planned: "var(--hos-info)",
  completed: "var(--hos-clinical-stable)",
  selected: "var(--hos-primary)",
};

export function Odontogram({
  states,
  selected,
  onSelect,
  label = "Dental chart",
}: {
  states: Record<number, Exclude<ToothState, "selected">>;
  selected?: number | null;
  onSelect?: (tooth: number) => void;
  label?: string;
}) {
  const [focusTooth, setFocusTooth] = React.useState<number>(11);
  const refs = React.useRef(new Map<number, SVGRectElement>());
  const move = (teeth: number[], tooth: number, dir: 1 | -1) => {
    const idx = teeth.indexOf(tooth);
    const next = teeth[idx + dir];
    if (next === undefined) return;
    setFocusTooth(next);
    refs.current.get(next)?.focus();
  };
  const upper = PERMANENT_TEETH.slice(0, 16);
  const lower = PERMANENT_TEETH.slice(16);
  const renderRow = (teeth: number[]) => (
    <g>
      {teeth.map((tooth, i) => {
        const state: ToothState = selected === tooth ? "selected" : (states[tooth] ?? "healthy");
        return (
          <g key={tooth}>
            <rect
              ref={(el) => {
                if (el) refs.current.set(tooth, el);
                else refs.current.delete(tooth);
              }}
              x={i * 34 + 4}
              y={0}
              width={28}
              height={34}
              rx={6}
              fill={STATE_FILL[state]}
              stroke={STATE_STROKE[state]}
              strokeWidth={selected === tooth ? 3 : 1.5}
              tabIndex={focusTooth === tooth ? 0 : -1}
              role="button"
              aria-pressed={selected === tooth}
              aria-label={`Tooth ${tooth}${state !== "healthy" ? `, ${state}` : ""}`}
              onClick={() => onSelect?.(tooth)}
              onFocus={() => setFocusTooth(tooth)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                  e.preventDefault();
                  move(teeth, tooth, e.key === "ArrowRight" ? 1 : -1);
                } else if ((e.key === "Enter" || e.key === " ") && onSelect) {
                  e.preventDefault();
                  onSelect(tooth);
                }
              }}
              style={{ cursor: onSelect ? "pointer" : "default", outlineOffset: 2 }}
            />
            <text
              x={i * 34 + 18}
              y={22}
              textAnchor="middle"
              fontSize={10}
              fill="var(--hos-text-primary)"
              pointerEvents="none"
              aria-hidden="true"
            >
              {tooth}
            </text>
          </g>
        );
      })}
    </g>
  );
  return (
    <figure role="group" aria-label={label} style={{ margin: 0 }}>
      <svg viewBox="0 0 548 90" width="100%" role="img" aria-label={`${label} diagram`}>
        {renderRow(upper)}
        <g transform="translate(0,44)">{renderRow(lower)}</g>
      </svg>
      <figcaption style={{ fontSize: "var(--hos-text-caption)", color: "var(--hos-text-muted)" }}>
        Projection of recorded findings - not a stored image. Select a tooth to record or review findings.
      </figcaption>
    </figure>
  );
}
