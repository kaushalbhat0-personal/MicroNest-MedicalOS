import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Odontogram,
  Select,
  Status,
  Table,
  Td,
  Textarea,
  Th,
  type ToothState,
} from "@healthcare-os/ui";
import { fmtWhen, statusLabel } from "../../lib/format";
import {
  createDentalConsent,
  createProcedureRecord,
  decideDentalConsent,
  deriveOdontogramStates,
  DENTAL_SURFACES,
  listDentalConditions,
  listDentalProcedureCatalog,
  listProcedureRecords,
  listToothFindings,
  PROCEDURE_RECORD_NEXT,
  procedureTransitionNeedsConsent,
  recordToothFinding,
  resolveToothFinding,
  transitionProcedureRecord,
  type DentalCondition,
  type DentalConsent,
  type DentalProcedureCatalog,
  type PlanItem,
  type ProcedureRecord,
  type ToothFinding,
} from "../../lib/dentalApi";

function handleApiError(
  e: unknown,
  onSessionExpired: () => void,
  setError: (msg: string) => void,
  fallback: string,
) {
  const msg = String(e);
  if (msg.includes("session_expired")) onSessionExpired();
  else if (msg.includes("forbidden")) setError("You do not have permission for this action.");
  else setError(msg.replace(/^Error:\s*/, "") || fallback);
}

const LEGEND: Array<{ state: ToothState; label: string }> = [
  { state: "finding", label: "Finding (clinical)" },
  { state: "planned", label: "Planned procedure" },
  { state: "completed", label: "Completed procedure" },
  { state: "healthy", label: "Healthy / no overlay" },
];

export function DentalChartPanel({
  tenantId,
  encounterId,
  patientId: _patientId,
  writesAllowed,
  canRead,
  canRecord,
  onSessionExpired,
  planItems,
}: {
  tenantId: string;
  encounterId: string;
  patientId: string;
  writesAllowed: boolean;
  canRead: boolean;
  canRecord: boolean;
  onSessionExpired: () => void;
  planItems?: PlanItem[];
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [findings, setFindings] = useState<ToothFinding[]>([]);
  const [procedures, setProcedures] = useState<ProcedureRecord[]>([]);
  const [conditions, setConditions] = useState<DentalCondition[]>([]);
  const [procedureCatalog, setProcedureCatalog] = useState<DentalProcedureCatalog[]>([]);

  const [selectedTooth, setSelectedTooth] = useState<number | null>(null);
  const [conditionCode, setConditionCode] = useState("");
  const [surfaceSet, setSurfaceSet] = useState<Record<string, boolean>>({});
  const [findingDetails, setFindingDetails] = useState("");

  const [newProcCode, setNewProcCode] = useState("");
  const [newProcTooth, setNewProcTooth] = useState("");
  const [newProcSurface, setNewProcSurface] = useState("");

  const [sessionConsents, setSessionConsents] = useState<DentalConsent[]>([]);
  const [consentDialog, setConsentDialog] = useState<{
    recordId: string;
    toStatus: string;
    procedureLabel: string;
  } | null>(null);
  const [consenterName, setConsenterName] = useState("");
  const [consenterRelation, setConsenterRelation] = useState("");
  const [consentBusy, setConsentBusy] = useState(false);

  const reload = useCallback(async () => {
    if (!canRead) {
      setLoading(false);
      return;
    }
    setError(null);
    try {
      const [f, p, c, cat] = await Promise.all([
        listToothFindings(tenantId, encounterId),
        listProcedureRecords(tenantId, encounterId),
        listDentalConditions(tenantId),
        listDentalProcedureCatalog(tenantId),
      ]);
      setFindings(f);
      setProcedures(p);
      setConditions(c);
      setProcedureCatalog(cat);
      if (c[0]) setConditionCode((prev) => prev || c[0].code);
      if (cat[0]) setNewProcCode((prev) => prev || cat[0].code);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Could not load dental data.");
    } finally {
      setLoading(false);
    }
  }, [tenantId, encounterId, canRead, onSessionExpired]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const planOverlayProcedures = useMemo(() => {
    const rows: Array<{ tooth: number | null; status: string }> = [];
    for (const item of planItems ?? []) {
      if (item.tooth == null) continue;
      const st =
        item.status === "proposed" || item.status === "planned" || item.status === "in_progress"
          ? item.status === "in_progress"
            ? "in_progress"
            : "planned"
          : item.status === "completed"
            ? "completed"
            : null;
      if (st) rows.push({ tooth: item.tooth, status: st });
    }
    return rows;
  }, [planItems]);

  const chartStates = useMemo(() => {
    const merged = [
      ...procedures.map((p) => ({ tooth: p.tooth, status: p.status })),
      ...planOverlayProcedures,
    ];
    return deriveOdontogramStates(findings, merged);
  }, [findings, procedures, planOverlayProcedures]);

  const conditionOptions = useMemo(
    () => conditions.map((c) => ({ value: c.code, label: `${c.code} — ${c.display}` })),
    [conditions],
  );

  const procCatalogOptions = useMemo(
    () => procedureCatalog.map((p) => ({ value: p.code, label: `${p.code} — ${p.display}` })),
    [procedureCatalog],
  );

  const surfaceOptions = useMemo(
    () => DENTAL_SURFACES.map((s) => ({ value: s, label: statusLabel(s) })),
    [],
  );

  const selectedSurfaces = useMemo(
    () => DENTAL_SURFACES.filter((s) => surfaceSet[s]),
    [surfaceSet],
  );

  function hasGrantedConsent(recordId: string): boolean {
    return sessionConsents.some(
      (c) => c.procedure_record_id === recordId && c.status === "granted",
    );
  }

  async function onRecordFinding(e: FormEvent) {
    e.preventDefault();
    if (!canRecord || !writesAllowed || selectedTooth == null) return;
    if (!conditionCode) {
      setError("Select a condition from the catalog.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await recordToothFinding(tenantId, encounterId, {
        tooth: selectedTooth,
        condition_code: conditionCode,
        surfaces: selectedSurfaces.length ? [...selectedSurfaces] : undefined,
        details: findingDetails.trim() || null,
      });
      setFindingDetails("");
      setSurfaceSet({});
      setInfo("Finding recorded.");
      await reload();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Could not record finding.");
    } finally {
      setBusy(false);
    }
  }

  async function onResolveFinding(findingId: string) {
    if (!canRecord || !writesAllowed) return;
    setBusy(true);
    setError(null);
    try {
      await resolveToothFinding(tenantId, findingId);
      setInfo("Finding resolved.");
      await reload();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Could not resolve finding.");
    } finally {
      setBusy(false);
    }
  }

  async function onCreateProcedure(e: FormEvent) {
    e.preventDefault();
    if (!canRecord || !writesAllowed) return;
    if (!newProcCode) {
      setError("Select a procedure from the catalog.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createProcedureRecord(tenantId, encounterId, {
        procedure_code: newProcCode,
        tooth: newProcTooth.trim() ? Number(newProcTooth) : null,
        surface: newProcSurface || null,
      });
      setNewProcTooth("");
      setNewProcSurface("");
      setInfo("Procedure record created (planned).");
      await reload();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Could not create procedure record.");
    } finally {
      setBusy(false);
    }
  }

  function requestProcedureTransition(rec: ProcedureRecord, toStatus: string) {
    if (!canRecord || !writesAllowed) return;
    if (procedureTransitionNeedsConsent(toStatus) && !hasGrantedConsent(rec.id)) {
      setConsenterName("");
      setConsenterRelation("");
      setConsentDialog({
        recordId: rec.id,
        toStatus,
        procedureLabel: rec.procedure_display || rec.procedure_code,
      });
      return;
    }
    void runProcedureTransition(rec.id, toStatus);
  }

  async function runProcedureTransition(recordId: string, toStatus: string) {
    setBusy(true);
    setError(null);
    try {
      await transitionProcedureRecord(tenantId, recordId, toStatus);
      setInfo(`Procedure marked ${statusLabel(toStatus)}.`);
      await reload();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Procedure status change failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onConsentConfirm() {
    if (!consentDialog || !consenterName.trim()) {
      setError("Consenter name is required before proceeding.");
      return;
    }
    setConsentBusy(true);
    setError(null);
    try {
      const created = await createDentalConsent(tenantId, {
        procedure_record_id: consentDialog.recordId,
        consenter_name: consenterName.trim(),
        consenter_relation: consenterRelation.trim() || null,
      });
      const decided = await decideDentalConsent(tenantId, created.id, "granted");
      setSessionConsents((prev) => [...prev, decided]);
      const { recordId, toStatus } = consentDialog;
      setConsentDialog(null);
      await runProcedureTransition(recordId, toStatus);
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Consent or procedure transition failed.");
    } finally {
      setConsentBusy(false);
    }
  }

  if (!canRead) {
    return (
      <EmptyState title="Dental chart unavailable">
        You need dental.read permission to view findings and procedures.
      </EmptyState>
    );
  }

  if (loading) {
    return <LoadingState label="Loading dental chart" />;
  }

  return (
    <div className="hos-stack">
      {error && (
        <Alert tone="danger" title="Error">
          {error}
        </Alert>
      )}
      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}

      <Card title="Odontogram">
        <p className="hos-caption">
          FDI permanent dentition (11–48) only. Primary dentition (51–85) is deferred. Findings are
          clinical facts; procedure records reflect planned or performed treatment on this encounter.
        </p>
        <Odontogram
          states={chartStates}
          selected={selectedTooth}
          onSelect={(t) => {
            setSelectedTooth(t);
            setNewProcTooth(String(t));
          }}
        />
        <p className="hos-caption">
          Legend: {LEGEND.map((row) => row.label).join(" · ")}.
        </p>
      </Card>

      <Card title="Record finding">
        <p className="hos-caption">
          Select a tooth on the chart, then record an active finding from the condition catalog.
        </p>
        {canRecord && writesAllowed ? (
          <form onSubmit={onRecordFinding}>
            <Field label="Tooth (FDI)" htmlFor="dc-tooth" required>
              {({ describedBy }) => (
                <Input
                  id="dc-tooth"
                  type="number"
                  aria-describedby={describedBy}
                  value={selectedTooth ?? ""}
                  onChange={(ev) =>
                    setSelectedTooth(ev.target.value ? Number(ev.target.value) : null)
                  }
                  required
                />
              )}
            </Field>
            <Field label="Condition" htmlFor="dc-cond" required>
              {({ describedBy }) => (
                <Select
                  id="dc-cond"
                  aria-describedby={describedBy}
                  value={conditionCode}
                  onChange={(ev) => setConditionCode(ev.target.value)}
                  options={conditionOptions}
                />
              )}
            </Field>
            <Field label="Surfaces (optional)" htmlFor="dc-surf">
              {({ describedBy }) => (
                <div id="dc-surf" aria-describedby={describedBy} className="hos-checkbox-row">
                  {DENTAL_SURFACES.map((s) => (
                    <Checkbox
                      key={s}
                      id={`dc-surf-${s}`}
                      label={statusLabel(s)}
                      checked={!!surfaceSet[s]}
                      onChange={(ev) =>
                        setSurfaceSet((prev) => ({ ...prev, [s]: ev.target.checked }))
                      }
                    />
                  ))}
                </div>
              )}
            </Field>
            <Field label="Details" htmlFor="dc-details">
              {({ describedBy }) => (
                <Textarea
                  id="dc-details"
                  aria-describedby={describedBy}
                  value={findingDetails}
                  onChange={(ev) => setFindingDetails(ev.target.value)}
                />
              )}
            </Field>
            <Button type="submit" disabled={busy || selectedTooth == null} loading={busy}>
              Record finding
            </Button>
          </form>
        ) : (
          <p className="hos-muted">Read-only — encounter closed or missing dental.record permission.</p>
        )}
      </Card>

      <Card title="Tooth findings">
        {findings.length === 0 ? (
          <EmptyState title="No findings">No tooth findings on this encounter.</EmptyState>
        ) : (
          <Table
            caption="Tooth findings for encounter"
            columns={
              <>
                <Th numeric>Tooth</Th>
                <Th>Condition</Th>
                <Th>Surfaces</Th>
                <Th>Status</Th>
                <Th>Recorded</Th>
                <Th>Actions</Th>
              </>
            }
          >
            {findings.map((f) => (
              <tr key={f.id}>
                <Td numeric>{f.tooth}</Td>
                <Td>{f.condition_display || f.condition_code}</Td>
                <Td>{f.surfaces?.length ? f.surfaces.join(", ") : "—"}</Td>
                <Td>
                  <Status value={f.status} />
                </Td>
                <Td>{fmtWhen(f.created_at)}</Td>
                <Td>
                  {f.status === "active" && canRecord && writesAllowed && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void onResolveFinding(f.id)}
                      disabled={busy}
                    >
                      Resolve
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Procedure records">
        <p className="hos-caption">
          Procedure records track planned and performed treatment on this encounter. Moving to
          in_progress or completed requires a granted consent on the backend — use the consent flow
          below; consents created here are kept in this session only (no list-consents API).
        </p>
        {canRecord && writesAllowed && (
          <form onSubmit={onCreateProcedure}>
            <Field label="Procedure" htmlFor="dc-proc" required>
              {({ describedBy }) => (
                <Select
                  id="dc-proc"
                  aria-describedby={describedBy}
                  value={newProcCode}
                  onChange={(ev) => setNewProcCode(ev.target.value)}
                  options={procCatalogOptions}
                />
              )}
            </Field>
            <Field label="Tooth (optional)" htmlFor="dc-proc-tooth">
              {({ describedBy }) => (
                <Input
                  id="dc-proc-tooth"
                  type="number"
                  aria-describedby={describedBy}
                  value={newProcTooth}
                  onChange={(ev) => setNewProcTooth(ev.target.value)}
                />
              )}
            </Field>
            <Field label="Surface (optional)" htmlFor="dc-proc-surf">
              {({ describedBy }) => (
                <Select
                  id="dc-proc-surf"
                  aria-describedby={describedBy}
                  value={newProcSurface}
                  onChange={(ev) => setNewProcSurface(ev.target.value)}
                  options={[{ value: "", label: "—" }, ...surfaceOptions]}
                />
              )}
            </Field>
            <Button type="submit" disabled={busy} loading={busy}>
              Create planned record
            </Button>
          </form>
        )}

        {procedures.length === 0 ? (
          <EmptyState title="No procedure records">No procedures documented yet.</EmptyState>
        ) : (
          <Table
            caption="Procedure records"
            columns={
              <>
                <Th>Procedure</Th>
                <Th numeric>Tooth</Th>
                <Th>Surface</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
          >
            {procedures.map((rec) => {
              const next = PROCEDURE_RECORD_NEXT[rec.status] ?? [];
              return (
                <tr key={rec.id}>
                  <Td>{rec.procedure_display || rec.procedure_code}</Td>
                  <Td numeric>{rec.tooth ?? "—"}</Td>
                  <Td>{rec.surface ?? "—"}</Td>
                  <Td>
                    <Status value={rec.status} />
                  </Td>
                  <Td>
                    <div className="hos-inline-actions">
                      {canRecord &&
                        writesAllowed &&
                        next.map((st) => (
                          <Button
                            key={st}
                            size="sm"
                            variant={st === "cancelled" ? "secondary" : "primary"}
                            disabled={busy}
                            onClick={() => requestProcedureTransition(rec, st)}
                          >
                            → {statusLabel(st)}
                          </Button>
                        ))}
                    </div>
                  </Td>
                </tr>
              );
            })}
          </Table>
        )}

        {sessionConsents.length > 0 && (
          <Table
            caption="Consents recorded this session"
            columns={
              <>
                <Th>Consenter</Th>
                <Th>Status</Th>
                <Th>Procedure record</Th>
              </>
            }
          >
            {sessionConsents.map((c) => (
              <tr key={c.id}>
                <Td>{c.consenter_name}</Td>
                <Td>
                  <Status value={c.status} />
                </Td>
                <Td>{c.procedure_record_id?.slice(0, 8) ?? "—"}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <ConfirmDialog
        open={consentDialog != null}
        onOpenChange={(open) => {
          if (!open) setConsentDialog(null);
        }}
        title="Consent required"
        confirmLabel="Grant consent and continue"
        pending={consentBusy}
        onConfirm={() => void onConsentConfirm()}
      >
        <p>
          Backend requires a <strong>granted</strong> consent before{" "}
          {consentDialog ? statusLabel(consentDialog.toStatus) : "this transition"} for{" "}
          {consentDialog?.procedureLabel ?? "the procedure"}.
        </p>
        <Field label="Consenter name" htmlFor="dc-consent-name" required>
          {({ describedBy }) => (
            <Input
              id="dc-consent-name"
              aria-describedby={describedBy}
              value={consenterName}
              onChange={(ev) => setConsenterName(ev.target.value)}
              required
            />
          )}
        </Field>
        <Field label="Relation (optional)" htmlFor="dc-consent-rel">
          {({ describedBy }) => (
            <Input
              id="dc-consent-rel"
              aria-describedby={describedBy}
              value={consenterRelation}
              onChange={(ev) => setConsenterRelation(ev.target.value)}
            />
          )}
        </Field>
        <p className="hos-caption">
          Consents are created and decided here, then stored on the server. This UI does not reload
          consents from a list API — only consents from this session are shown below.
        </p>
      </ConfirmDialog>
    </div>
  );
}