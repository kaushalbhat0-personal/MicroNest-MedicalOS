# Odontogram Audit

## Model

Per P3-02: **no odontogram table**. Chart is a UI projection of `tooth_findings` (+ optional procedure-record shading). Shared component: `@healthcare-os/ui` `Odontogram`.

## Numbering

- Convention: **FDI two-digit permanent** (11–18, 21–28, 31–38, 41–48)
- Primary (51–85): **deferred** — backend rejects; desktop documents
- Surfaces: mesial, distal, occlusal, incisal, buccal, labial, lingual, palatal

## Visual states (backend-derived)

| State | Source |
|-------|--------|
| finding | Active tooth finding |
| planned | Procedure record planned/in_progress (and plan overlays where wired) |
| completed | Procedure record completed |
| healthy | Default / no row |
| selected | UI only |

Missing/restored/treated without a finding or procedure row are **not invented**.

## Findings vs planned treatment

- Findings = observed facts (`active`/`resolved`)
- Plan items / procedure records = intent and performance
- Desktop Dental tab separates sections and captions

## Accessibility

Odontogram: roving tabindex, ArrowLeft/Right, Enter/Space select, aria-labels with tooth + state.

## Desktop improvements (M11)

- Encounter **Dental** tab with Odontogram, catalog conditions, surfaces, resolve
- Procedure records with consent-aware transitions
- FDI validation helpers in `dentalApi.ts`

## Gaps requiring dentist decision

1. Confirm FDI permanent-only is acceptable for pilot clinics.  
2. Primary dentition timeline.  
3. Anterior/posterior surface appropriateness (not enforced).  
4. Whether missing tooth should be a condition code vs procedure.
