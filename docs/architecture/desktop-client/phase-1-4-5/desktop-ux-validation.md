# Desktop UX Validation — M5/M6

## Patient directory

- Search field with debounce; status filter; Open action + name link
- Loading / empty / error via `@healthcare-os/ui`
- Keyboard: native inputs + button focus styles (`:focus-visible`)

## Patient profile

- `PatientIdentityHeader` always visible
- Tabs: demographics, history, appointments, clinical, billing, care
- Overview metrics above tabs
- Forbidden related modules listed as omitted caption (not fabricated)

## Calendar

- Day/week toggle; previous/today/next
- Appointment chips show time, status, truncated ids (names resolved when patient search loaded)
- Detail panel for status/reschedule/cancel

## Reception

- Queue table with token, patient, time, practitioner, status, actions
- Check-in prominent primary button when transition allowed
- Walk-in card with patient lookup + quick register + handoff to full registration
- Explicit polling disclaimer (15s)

## Design system

- Tokens from `@healthcare-os/ui/tokens.css`
- Components: Alert, Button, Card, Field, Input, Select, Table, Tabs, ConfirmDialog, Status, Badge, EmptyState, LoadingState, MoneyDisplay, PatientIdentityHeader
- Target WCAG AA: focus outlines, text+tone status chips, no color-only meaning

## Workspace hygiene

- Switch clinic / logout clears patient view route state before re-auth
