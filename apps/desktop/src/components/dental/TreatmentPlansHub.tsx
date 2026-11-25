import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Select,
  Status,
  Table,
  Td,
  Textarea,
  Th,
} from "@healthcare-os/ui";
import { fmtWhen, statusLabel } from "../../lib/format";
import {
  activatePlan,
  addPlanItem,
  cancelPlan,
  completePlan,
  createDentalConsent,
  createTreatmentPlan,
  decideDentalConsent,
  getTreatmentPlan,
  listDentalProcedureCatalog,
  listTreatmentPlans,
  PLAN_ITEM_NEXT,
  transitionPlanItem,
  type DentalConsent,
  type DentalProcedureCatalog,
  type PlanItem,
  type TreatmentPlan,
} from "../../lib/dentalApi";
import { hasPerm } from "../../lib/nav";
import { listPatients, type Patient } from "../../lib/patientsApi";
import { listPractitioners, type Practitioner } from "../../lib/schedulingApi";
import { useSession } from "../../lib/session";

function shortId(id: string): string {
  return id.slice(0, 8);
}

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

export function TreatmentPlansHub({
  onSessionExpired,
  onOpenPatient,
  initialPatientId,
}: {
  onSessionExpired: () => void;
  onOpenPatient: (id: string) => void;
  initialPatientId?: string | null;
}) {
  const { tenant, workspace } = useSession();
  const canRead =
    hasPerm(workspace?.permissions, "dental.read") ||
    hasPerm(workspace?.permissions, "plan.manage");
  const canPlanManage = hasPerm(workspace?.permissions, "plan.manage");

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [patientFilterId, setPatientFilterId] = useState(initialPatientId ?? "");
  const [patientQ, setPatientQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [patientOptions, setPatientOptions] = useState<Patient[]>([]);

  const [plans, setPlans] = useState<TreatmentPlan[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [planDetail, setPlanDetail] = useState<TreatmentPlan | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [practitioners, setPractitioners] = useState<Practitioner[]>([]);
  const [procedureCatalog, setProcedureCatalog] = useState<DentalProcedureCatalog[]>([]);

  const [createPractitionerId, setCreatePractitionerId] = useState("");
  const [createNotes, setCreateNotes] = useState("");
  const [createProcCode, setCreateProcCode] = useState("");
  const [createTooth, setCreateTooth] = useState("");
  const [createSurface, setCreateSurface] = useState("");

  const [addProcCode, setAddProcCode] = useState("");
  const [addTooth, setAddTooth] = useState("");
  const [addSurface, setAddSurface] = useState("");
  const [addNotes, setAddNotes] = useState("");

  const [sessionConsents, setSessionConsents] = useState<DentalConsent[]>([]);
  const [consenterName, setConsenterName] = useState("");
  const [consenterRelation, setConsenterRelation] = useState("");

  const [activateOpen, setActivateOpen] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQ(patientQ.trim()), 250);
    return () => window.clearTimeout(id);
  }, [patientQ]);

  useEffect(() => {
    if (initialPatientId) setPatientFilterId(initialPatientId);
  }, [initialPatientId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !hasPerm(workspace?.permissions, "patient.read")) return;
      try {
        const data = await listPatients(tenant.id, {
          q: debouncedQ || undefined,
          limit: 30,
          activeOnly: true,
        });
        if (!cancelled) setPatientOptions(data);
      } catch {
        if (!cancelled) setPatientOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, debouncedQ, workspace?.permissions]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant) return;
      try {
        const [prac, cat] = await Promise.all([
          listPractitioners(tenant.id),
          listDentalProcedureCatalog(tenant.id),
        ]);
        if (cancelled) return;
        setPractitioners(prac);
        setProcedureCatalog(cat);
        if (prac[0]) setCreatePractitionerId((p) => p || prac[0].id);
        if (cat[0]) {
          setCreateProcCode((p) => p || cat[0].code);
          setAddProcCode((p) => p || cat[0].code);
        }
      } catch (e) {
        handleApiError(e, onSessionExpired, setError, "Could not load catalog.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, onSessionExpired]);

  const patientSelectOptions = useMemo(
    () => [
      { value: "", label: "Select patient" },
      ...patientOptions.map((p) => ({
        value: p.id,
        label: `${p.display_name} (${shortId(p.id)})`,
      })),
      ...(patientFilterId && !patientOptions.some((p) => p.id === patientFilterId)
        ? [{ value: patientFilterId, label: `Selected (${shortId(patientFilterId)})` }]
        : []),
    ],
    [patientOptions, patientFilterId],
  );

  const procOptions = useMemo(
    () => procedureCatalog.map((p) => ({ value: p.code, label: `${p.code} — ${p.display}` })),
    [procedureCatalog],
  );

  const practitionerOptions = useMemo(
    () => practitioners.map((p) => ({ value: p.id, label: p.display_name })),
    [practitioners],
  );

  const reloadPlans = useCallback(async () => {
    if (!tenant || !patientFilterId || !canRead) {
      setPlans([]);
      return;
    }
    setLoadingList(true);
    setError(null);
    try {
      const rows = await listTreatmentPlans(tenant.id, patientFilterId);
      setPlans(rows);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Could not load treatment plans.");
      setPlans([]);
    } finally {
      setLoadingList(false);
    }
  }, [tenant, patientFilterId, canRead, onSessionExpired]);

  useEffect(() => {
    void reloadPlans();
    setSelectedPlanId(null);
    setPlanDetail(null);
  }, [reloadPlans]);

  const reloadDetail = useCallback(
    async (planId: string) => {
      if (!tenant) return;
      setLoadingDetail(true);
      try {
        const plan = await getTreatmentPlan(tenant.id, planId);
        setPlanDetail(plan);
      } catch (e) {
        handleApiError(e, onSessionExpired, setError, "Could not load plan detail.");
        setPlanDetail(null);
      } finally {
        setLoadingDetail(false);
      }
    },
    [tenant, onSessionExpired],
  );

  useEffect(() => {
    if (selectedPlanId) void reloadDetail(selectedPlanId);
    else setPlanDetail(null);
  }, [selectedPlanId, reloadDetail]);

  async function onCreatePlan(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canPlanManage || !patientFilterId) return;
    if (!createPractitionerId || !createProcCode.trim()) {
      setError("Practitioner and procedure are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const plan = await createTreatmentPlan(tenant.id, {
        patient_id: patientFilterId,
        practitioner_id: createPractitionerId,
        notes: createNotes.trim() || null,
        items: [
          {
            procedure_code: createProcCode.trim(),
            tooth: createTooth.trim() ? Number(createTooth) : null,
            surface: createSurface.trim() || null,
          },
        ],
      });
      setCreateNotes("");
      setCreateTooth("");
      setCreateSurface("");
      setInfo("Draft treatment plan created.");
      await reloadPlans();
      setSelectedPlanId(plan.id);
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Create plan failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onAddItem(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !planDetail || planDetail.status !== "draft" || !canPlanManage) return;
    if (!addProcCode.trim()) {
      setError("Procedure code is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addPlanItem(tenant.id, planDetail.id, {
        procedure_code: addProcCode.trim(),
        tooth: addTooth.trim() ? Number(addTooth) : null,
        surface: addSurface.trim() || null,
        notes: addNotes.trim() || null,
      });
      setAddTooth("");
      setAddSurface("");
      setAddNotes("");
      setInfo("Plan item added.");
      await reloadDetail(planDetail.id);
      await reloadPlans();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Add item failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onPlanLifecycle(action: "activate" | "complete" | "cancel") {
    if (!tenant || !planDetail || !canPlanManage) return;
    setBusy(true);
    setError(null);
    try {
      if (action === "activate") await activatePlan(tenant.id, planDetail.id);
      if (action === "complete") await completePlan(tenant.id, planDetail.id);
      if (action === "cancel") await cancelPlan(tenant.id, planDetail.id);
      setInfo(`Plan ${action}d.`);
      await reloadDetail(planDetail.id);
      await reloadPlans();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Plan update failed.");
    } finally {
      setBusy(false);
      setActivateOpen(false);
      setCompleteOpen(false);
      setCancelOpen(false);
    }
  }

  async function onTransitionItem(itemId: string, status: string) {
    if (!tenant || !canPlanManage) return;
    setBusy(true);
    setError(null);
    try {
      await transitionPlanItem(tenant.id, itemId, status);
      setInfo("Plan item updated.");
      if (planDetail) await reloadDetail(planDetail.id);
      await reloadPlans();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Item transition failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCreatePlanConsent(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !planDetail || !consenterName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createDentalConsent(tenant.id, {
        plan_id: planDetail.id,
        consenter_name: consenterName.trim(),
        consenter_relation: consenterRelation.trim() || null,
      });
      setSessionConsents((prev) => [...prev, created]);
      setConsenterName("");
      setConsenterRelation("");
      setInfo("Consent record created (pending). Use decide below.");
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Consent create failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onDecideConsent(consentId: string, decision: "granted" | "declined") {
    if (!tenant) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await decideDentalConsent(tenant.id, consentId, decision);
      setSessionConsents((prev) => prev.map((c) => (c.id === consentId ? updated : c)));
      setInfo(`Consent ${decision}.`);
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Consent decide failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!canRead) {
    return (
      <EmptyState title="Treatment plans unavailable">
        You need dental.read or plan.manage permission.
      </EmptyState>
    );
  }

  return (
    <div className="hos-stack">
      <p className="hos-caption">
        Treatment plans are clinical care roadmaps. They are not estimates (pricing quotes) and not
        invoices (billing documents). Plan activation is not consent-gated (P3.6).
      </p>

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

      <div className="hos-toolbar-row">
        <Field label="Patient search" htmlFor="tp-pq">
          {({ describedBy }) => (
            <Input
              id="tp-pq"
              aria-describedby={describedBy}
              value={patientQ}
              onChange={(ev) => setPatientQ(ev.target.value)}
              placeholder="Search patients"
            />
          )}
        </Field>
        <Field label="Patient" htmlFor="tp-patient" required>
          {({ describedBy }) => (
            <Select
              id="tp-patient"
              aria-describedby={describedBy}
              value={patientFilterId}
              onChange={(ev) => setPatientFilterId(ev.target.value)}
              options={patientSelectOptions}
            />
          )}
        </Field>
        {patientFilterId && (
          <Button type="button" variant="secondary" onClick={() => onOpenPatient(patientFilterId)}>
            Open patient profile
          </Button>
        )}
      </div>

      <div className="hos-billing-layout">
        <Card title="Plans for patient">
          {!patientFilterId ? (
            <EmptyState title="Select a patient">Choose a patient to list treatment plans.</EmptyState>
          ) : loadingList && plans.length === 0 ? (
            <LoadingState label="Loading plans" />
          ) : plans.length === 0 ? (
            <EmptyState title="No plans">No treatment plans for this patient.</EmptyState>
          ) : (
            <Table
              caption="Treatment plans"
              columns={
                <>
                  <Th>Status</Th>
                  <Th>Version</Th>
                  <Th>Updated</Th>
                  <Th>Items</Th>
                  <Th>Actions</Th>
                </>
              }
            >
              {plans.map((pl) => (
                <tr key={pl.id}>
                  <Td>
                    <Status value={pl.status} />
                  </Td>
                  <Td>{pl.version}</Td>
                  <Td>{fmtWhen(pl.updated_at)}</Td>
                  <Td>{pl.items?.length ?? 0}</Td>
                  <Td>
                    <button
                      type="button"
                      className="hos-link-btn"
                      onClick={() => setSelectedPlanId(pl.id)}
                    >
                      Open
                    </button>
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="Plan detail">
          {loadingDetail && selectedPlanId ? (
            <LoadingState label="Loading plan" />
          ) : !planDetail ? (
            <EmptyState title="No plan selected">Select a plan from the list.</EmptyState>
          ) : (
            <>
              <dl className="hos-dl">
                <div>
                  <dt>Status</dt>
                  <dd>
                    <Status value={planDetail.status} />
                  </dd>
                </div>
                <div>
                  <dt>Notes</dt>
                  <dd>{planDetail.notes ?? "—"}</dd>
                </div>
                <div>
                  <dt>Encounter</dt>
                  <dd>{planDetail.encounter_id ? shortId(planDetail.encounter_id) : "—"}</dd>
                </div>
              </dl>

              {canPlanManage && (
                <div className="hos-inline-actions">
                  {planDetail.status === "draft" && (
                    <Button type="button" onClick={() => setActivateOpen(true)} disabled={busy}>
                      Activate
                    </Button>
                  )}
                  {planDetail.status === "active" && (
                    <Button type="button" onClick={() => setCompleteOpen(true)} disabled={busy}>
                      Complete plan
                    </Button>
                  )}
                  {(planDetail.status === "draft" || planDetail.status === "active") && (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setCancelOpen(true)}
                      disabled={busy}
                    >
                      Cancel plan
                    </Button>
                  )}
                </div>
              )}

              <Table
                caption="Plan items"
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
                {(planDetail.items ?? []).map((item: PlanItem) => {
                  const next = PLAN_ITEM_NEXT[item.status] ?? [];
                  return (
                    <tr key={item.id}>
                      <Td>{item.procedure_display || item.procedure_code}</Td>
                      <Td numeric>{item.tooth ?? "—"}</Td>
                      <Td>{item.surface ?? "—"}</Td>
                      <Td>
                        <Status value={item.status} />
                      </Td>
                      <Td>
                        {canPlanManage &&
                          next.map((st) => (
                            <Button
                              key={st}
                              size="sm"
                              variant={st === "cancelled" ? "secondary" : "primary"}
                              disabled={busy}
                              onClick={() => void onTransitionItem(item.id, st)}
                            >
                              → {statusLabel(st)}
                            </Button>
                          ))}
                      </Td>
                    </tr>
                  );
                })}
              </Table>

              {canPlanManage && planDetail.status === "draft" && (
                <form onSubmit={onAddItem}>
                  <h3>Add item (draft only)</h3>
                  <Field label="Procedure" htmlFor="tp-add-proc" required>
                    {({ describedBy }) => (
                      <Select
                        id="tp-add-proc"
                        aria-describedby={describedBy}
                        value={addProcCode}
                        onChange={(ev) => setAddProcCode(ev.target.value)}
                        options={procOptions}
                      />
                    )}
                  </Field>
                  <Field label="Tooth" htmlFor="tp-add-tooth">
                    {({ describedBy }) => (
                      <Input
                        id="tp-add-tooth"
                        type="number"
                        aria-describedby={describedBy}
                        value={addTooth}
                        onChange={(ev) => setAddTooth(ev.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Surface" htmlFor="tp-add-surf">
                    {({ describedBy }) => (
                      <Input
                        id="tp-add-surf"
                        aria-describedby={describedBy}
                        value={addSurface}
                        onChange={(ev) => setAddSurface(ev.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Notes" htmlFor="tp-add-notes">
                    {({ describedBy }) => (
                      <Textarea
                        id="tp-add-notes"
                        aria-describedby={describedBy}
                        value={addNotes}
                        onChange={(ev) => setAddNotes(ev.target.value)}
                      />
                    )}
                  </Field>
                  <Button type="submit" disabled={busy} loading={busy}>
                    Add item
                  </Button>
                </form>
              )}

              <Card title="Consents (session)">
                <p className="hos-caption">
                  Consents for this plan are created and decided here. There is no list-consents API —
                  only consents from this session are shown. Plan activation does not require consent.
                </p>
                <form onSubmit={onCreatePlanConsent}>
                  <Field label="Consenter name" htmlFor="tp-cn-name" required>
                    {({ describedBy }) => (
                      <Input
                        id="tp-cn-name"
                        aria-describedby={describedBy}
                        value={consenterName}
                        onChange={(ev) => setConsenterName(ev.target.value)}
                        required
                      />
                    )}
                  </Field>
                  <Field label="Relation" htmlFor="tp-cn-rel">
                    {({ describedBy }) => (
                      <Input
                        id="tp-cn-rel"
                        aria-describedby={describedBy}
                        value={consenterRelation}
                        onChange={(ev) => setConsenterRelation(ev.target.value)}
                      />
                    )}
                  </Field>
                  <Button type="submit" disabled={busy} loading={busy}>
                    Create pending consent
                  </Button>
                </form>
                {sessionConsents.filter((c) => c.plan_id === planDetail.id).length === 0 ? (
                  <EmptyState title="No session consents">None created for this plan yet.</EmptyState>
                ) : (
                  <Table
                    caption="Session consents"
                    columns={
                      <>
                        <Th>Consenter</Th>
                        <Th>Status</Th>
                        <Th>Actions</Th>
                      </>
                    }
                  >
                    {sessionConsents
                      .filter((c) => c.plan_id === planDetail.id)
                      .map((c) => (
                        <tr key={c.id}>
                          <Td>{c.consenter_name}</Td>
                          <Td>
                            <Status value={c.status} />
                          </Td>
                          <Td>
                            {c.status === "pending" && (
                              <div className="hos-inline-actions">
                                <Button
                                  size="sm"
                                  onClick={() => void onDecideConsent(c.id, "granted")}
                                  disabled={busy}
                                >
                                  Grant
                                </Button>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => void onDecideConsent(c.id, "declined")}
                                  disabled={busy}
                                >
                                  Decline
                                </Button>
                              </div>
                            )}
                          </Td>
                        </tr>
                      ))}
                  </Table>
                )}
              </Card>
            </>
          )}
        </Card>
      </div>

      {canPlanManage && patientFilterId && (
        <Card title="Create draft plan">
          <form onSubmit={onCreatePlan}>
            <Field label="Practitioner" htmlFor="tp-prac" required>
              {({ describedBy }) => (
                <Select
                  id="tp-prac"
                  aria-describedby={describedBy}
                  value={createPractitionerId}
                  onChange={(ev) => setCreatePractitionerId(ev.target.value)}
                  options={practitionerOptions}
                />
              )}
            </Field>
            <Field label="Notes" htmlFor="tp-notes">
              {({ describedBy }) => (
                <Textarea
                  id="tp-notes"
                  aria-describedby={describedBy}
                  value={createNotes}
                  onChange={(ev) => setCreateNotes(ev.target.value)}
                />
              )}
            </Field>
            <Field label="First procedure" htmlFor="tp-proc" required>
              {({ describedBy }) => (
                <Select
                  id="tp-proc"
                  aria-describedby={describedBy}
                  value={createProcCode}
                  onChange={(ev) => setCreateProcCode(ev.target.value)}
                  options={procOptions}
                />
              )}
            </Field>
            <Field label="Tooth" htmlFor="tp-tooth">
              {({ describedBy }) => (
                <Input
                  id="tp-tooth"
                  type="number"
                  aria-describedby={describedBy}
                  value={createTooth}
                  onChange={(ev) => setCreateTooth(ev.target.value)}
                />
              )}
            </Field>
            <Field label="Surface" htmlFor="tp-surf">
              {({ describedBy }) => (
                <Input
                  id="tp-surf"
                  aria-describedby={describedBy}
                  value={createSurface}
                  onChange={(ev) => setCreateSurface(ev.target.value)}
                />
              )}
            </Field>
            <Button type="submit" disabled={busy} loading={busy}>
              Create draft plan
            </Button>
          </form>
        </Card>
      )}

      <ConfirmDialog
        open={activateOpen}
        onOpenChange={setActivateOpen}
        title="Activate treatment plan?"
        confirmLabel="Activate"
        pending={busy}
        onConfirm={() => void onPlanLifecycle("activate")}
      >
        Activates the plan for care tracking. Does not issue estimates or invoices.
      </ConfirmDialog>

      <ConfirmDialog
        open={completeOpen}
        onOpenChange={setCompleteOpen}
        title="Complete treatment plan?"
        confirmLabel="Complete"
        pending={busy}
        onConfirm={() => void onPlanLifecycle("complete")}
      >
        Marks the plan complete when all intended items are done or waived.
      </ConfirmDialog>

      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title="Cancel treatment plan?"
        confirmLabel="Cancel plan"
        pending={busy}
        onConfirm={() => void onPlanLifecycle("cancel")}
      >
        Cancels the plan. Open items should be cancelled or reconciled on the chart.
      </ConfirmDialog>
    </div>
  );
}