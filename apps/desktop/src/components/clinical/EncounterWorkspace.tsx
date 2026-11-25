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
  MoneyDisplay,
  PatientIdentityHeader,
  Select,
  Status,
  Table,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Td,
  Textarea,
  Th,
} from "@healthcare-os/ui";
import {
  amendNote,
  closeEncounter,
  createDiagnosis,
  createFollowUp,
  createNote,
  createObservation,
  createPrescription,
  createTreatmentPlan,
  ClinicalNote,
  Diagnosis,
  DiagnosisCode,
  Encounter,
  Estimate,
  FollowUp,
  getEncounter,
  listDiagnoses,
  listEstimates,
  listFollowUps,
  listMedications,
  listNotes,
  listObservations,
  listPrescriptions,
  listTreatmentPlans,
  Medication,
  Observation,
  Prescription,
  searchDiagnosisCodes,
  signPrescription,
  TreatmentPlan,
  finalizeNote,
} from "../../lib/clinicalApi";
import { fmtWhen, statusLabel } from "../../lib/format";
import { hasPerm } from "../../lib/nav";
import {
  getPatient,
  getPatientOverview,
  getPatientTimeline,
  Patient,
  PatientOverview,
  TimelineItem,
} from "../../lib/patientsApi";
import { useSession } from "../../lib/session";
import { DentalChartPanel } from "../dental/DentalChartPanel";
import {
  activatePlan,
  cancelPlan,
  completePlan,
  type PlanItem,
} from "../../lib/dentalApi";

/** Codes must exist in GET /observation-types — invalid codes are rejected by API. */
const VITAL_TYPES = [
  { value: "bp_systolic", label: "BP systolic" },
  { value: "bp_diastolic", label: "BP diastolic" },
  { value: "heart_rate", label: "Heart rate" },
  { value: "temperature_c", label: "Temperature (°C)" },
  { value: "spo2", label: "SpO₂" },
  { value: "weight_kg", label: "Weight (kg)" },
] as const;

const RX_ROUTES = [
  { value: "oral", label: "Oral" },
  { value: "topical", label: "Topical" },
  { value: "iv", label: "IV" },
  { value: "im", label: "IM" },
  { value: "inhaled", label: "Inhaled" },
  { value: "sublingual", label: "Sublingual" },
] as const;

function isForbidden(err: unknown): boolean {
  return String(err).includes("forbidden");
}

function isSessionExpired(err: unknown): boolean {
  return String(err).includes("session_expired");
}

export function EncounterWorkspace({
  encounterId,
  onBack,
  onOpenPatient,
  onSessionExpired,
}: {
  encounterId: string;
  onBack: () => void;
  onOpenPatient: (patientId: string) => void;
  onSessionExpired: () => void;
}) {
  const { tenant, workspace } = useSession();

  const canClinicalCreate = hasPerm(workspace?.permissions, "clinical.create");
  const canRxCreate = hasPerm(workspace?.permissions, "prescription.create");
  const canRxSign = hasPerm(workspace?.permissions, "prescription.sign");
  const canPlanManage = hasPerm(workspace?.permissions, "plan.manage");
  const canDentalRead = hasPerm(workspace?.permissions, "dental.read");
  const canDentalRecord = hasPerm(workspace?.permissions, "dental.record");
  const canFollowupManage = hasPerm(workspace?.permissions, "followup.manage");
  const canClose = hasPerm(workspace?.permissions, "encounter.close");

  const [encounter, setEncounter] = useState<Encounter | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [overview, setOverview] = useState<PatientOverview | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [notes, setNotes] = useState<ClinicalNote[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [plans, setPlans] = useState<TreatmentPlan[]>([]);
  const [estimates, setEstimates] = useState<Estimate[]>([]);
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  const [omitted, setOmitted] = useState<string[]>([]);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tabError, setTabError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const readOnly = encounter?.status === "closed";
  const writesAllowed = !readOnly;

  // Notes form
  const [noteChief, setNoteChief] = useState("");
  const [noteSubj, setNoteSubj] = useState("");
  const [noteObj, setNoteObj] = useState("");
  const [noteAssess, setNoteAssess] = useState("");
  const [notePlan, setNotePlan] = useState("");
  const [noteFinalizeOnSave, setNoteFinalizeOnSave] = useState(false);
  const [amendNoteId, setAmendNoteId] = useState("");
  const [amendChief, setAmendChief] = useState("");
  const [amendSubj, setAmendSubj] = useState("");
  const [amendObj, setAmendObj] = useState("");
  const [amendAssess, setAmendAssess] = useState("");
  const [amendPlan, setAmendPlan] = useState("");

  // Vitals
  const [vitalType, setVitalType] = useState("bp_systolic");
  const [vitalValue, setVitalValue] = useState("");

  // Diagnoses
  const [dxMode, setDxMode] = useState<"code" | "free_text">("code");
  const [dxSearch, setDxSearch] = useState("");
  const [dxCodes, setDxCodes] = useState<DiagnosisCode[]>([]);
  const [dxSelectedCode, setDxSelectedCode] = useState("");
  const [dxFreeText, setDxFreeText] = useState("");
  const [dxPrimary, setDxPrimary] = useState(false);

  // Rx
  const [medQ, setMedQ] = useState("");
  const [medications, setMedications] = useState<Medication[]>([]);
  const [rxMedCode, setRxMedCode] = useState("");
  const [rxDose, setRxDose] = useState("");
  const [rxRoute, setRxRoute] = useState("oral");
  const [rxFreq, setRxFreq] = useState("");
  const [rxDuration, setRxDuration] = useState("");
  const [rxInstructions, setRxInstructions] = useState("");
  const [rxReviewing, setRxReviewing] = useState(false);

  // Plans
  const [planNotes, setPlanNotes] = useState("");
  const [planProcedure, setPlanProcedure] = useState("");
  const [planTooth, setPlanTooth] = useState("");

  // Follow-up
  const [fuDue, setFuDue] = useState("");
  const [fuReason, setFuReason] = useState("");

  const [planActivateId, setPlanActivateId] = useState<string | null>(null);
  const [planCompleteId, setPlanCompleteId] = useState<string | null>(null);
  const [planCancelId, setPlanCancelId] = useState<string | null>(null);

  // Close
  const [closeOpen, setCloseOpen] = useState(false);
  const [closeNoteWaiver, setCloseNoteWaiver] = useState(false);
  const [closeVitalsWaiver, setCloseVitalsWaiver] = useState(false);
  const [closePending, setClosePending] = useState(false);

  const noteDirty = useMemo(
    () =>
      !!(noteChief || noteSubj || noteObj || noteAssess || notePlan ||
        amendChief || amendSubj || amendObj || amendAssess || amendPlan),
    [noteChief, noteSubj, noteObj, noteAssess, notePlan, amendChief, amendSubj, amendObj, amendAssess, amendPlan],
  );

  const formDirty = useMemo(
    () =>
      noteDirty ||
      !!vitalValue ||
      !!dxSearch ||
      !!dxFreeText ||
      !!rxDose ||
      !!planProcedure ||
      !!fuReason,
    [noteDirty, vitalValue, dxSearch, dxFreeText, rxDose, planProcedure, fuReason],
  );

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (formDirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [formDirty]);

  const reloadEncounterData = useCallback(async () => {
    if (!tenant) return;
    setTabError(null);
    const skipped: string[] = [];
    let enc: Encounter;
    try {
      enc = await getEncounter(tenant.id, encounterId);
      setEncounter(enc);
    } catch (e) {
      if (isSessionExpired(e)) onSessionExpired();
      else if (String(e).includes("not_found")) setLoadError("Encounter not found.");
      else setLoadError("Could not load encounter.");
      throw e;
    }

    const patientId = enc.patient_id;

    try {
      const p = await getPatient(tenant.id, patientId);
      setPatient(p);
    } catch (e) {
      if (isSessionExpired(e)) onSessionExpired();
      else if (isForbidden(e)) skipped.push("patient");
    }

    try {
      setOverview(await getPatientOverview(tenant.id, patientId));
    } catch (e) {
      if (isSessionExpired(e)) onSessionExpired();
      else if (isForbidden(e)) skipped.push("overview");
    }

    try {
      const tl = await getPatientTimeline(tenant.id, patientId, { limit: 20 });
      setTimeline(tl.items);
    } catch (e) {
      if (isSessionExpired(e)) onSessionExpired();
      else if (isForbidden(e)) skipped.push("timeline");
    }

    const loadSection = async <T,>(
      label: string,
      loader: () => Promise<T[]>,
    ): Promise<T[]> => {
      try {
        return await loader();
      } catch (e) {
        if (isSessionExpired(e)) {
          onSessionExpired();
          return [];
        }
        if (isForbidden(e)) {
          skipped.push(label);
          return [];
        }
        return [];
      }
    };

    const [n, obs, d, rx, pl] = await Promise.all([
      loadSection("notes", () => listNotes(tenant.id, encounterId)),
      loadSection("vitals", () => listObservations(tenant.id, encounterId)),
      loadSection("diagnoses", () => listDiagnoses(tenant.id, encounterId)),
      loadSection("prescriptions", () => listPrescriptions(tenant.id, encounterId)),
      loadSection("plans", () => listTreatmentPlans(tenant.id, patientId)),
    ]);
    setNotes(n);
    setObservations(obs);
    setDiagnoses(d);
    setPrescriptions(rx);
    setPlans(pl);

    try {
      setEstimates(await listEstimates(tenant.id, patientId));
    } catch (e) {
      if (isSessionExpired(e)) onSessionExpired();
      else if (isForbidden(e)) skipped.push("estimates");
    }

    try {
      setFollowUps(await listFollowUps(tenant.id, patientId));
    } catch (e) {
      if (isSessionExpired(e)) onSessionExpired();
      else if (isForbidden(e)) skipped.push("follow-ups");
    }

    setOmitted(skipped);
  }, [tenant, encounterId, onSessionExpired]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant) return;
      setLoading(true);
      setLoadError(null);
      try {
        await reloadEncounterData();
      } catch {
        if (!cancelled) {
          /* loadError set in reload */
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, encounterId, reloadEncounterData]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !dxSearch.trim() || dxMode !== "code") {
        setDxCodes([]);
        return;
      }
      try {
        const rows = await searchDiagnosisCodes(tenant.id, dxSearch);
        if (!cancelled) setDxCodes(rows);
      } catch (e) {
        if (isSessionExpired(e)) onSessionExpired();
        if (!cancelled) setDxCodes([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, dxSearch, dxMode, onSessionExpired]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !medQ.trim()) {
        setMedications([]);
        return;
      }
      try {
        const rows = await listMedications(tenant.id, medQ);
        if (!cancelled) setMedications(rows);
      } catch (e) {
        if (isSessionExpired(e)) onSessionExpired();
        if (!cancelled) setMedications([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, medQ, onSessionExpired]);

  function handleBack() {
    if (formDirty && !window.confirm("You have unsaved changes. Leave this encounter?")) return;
    onBack();
  }

  async function onSaveNote(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !encounter || !canClinicalCreate || !writesAllowed) return;
    const hasContent =
      noteChief.trim() ||
      noteSubj.trim() ||
      noteObj.trim() ||
      noteAssess.trim() ||
      notePlan.trim();
    if (!hasContent) {
      setTabError("Enter at least one note field before saving.");
      return;
    }
    setBusy(true);
    setTabError(null);
    try {
      const created = await createNote(tenant.id, encounter.id, {
        chief_complaint: noteChief.trim() || null,
        subjective: noteSubj.trim() || null,
        objective: noteObj.trim() || null,
        assessment: noteAssess.trim() || null,
        plan: notePlan.trim() || null,
      });
      if (noteFinalizeOnSave) {
        await finalizeNote(tenant.id, created.id);
      }
      setNoteChief("");
      setNoteSubj("");
      setNoteObj("");
      setNoteAssess("");
      setNotePlan("");
      setNoteFinalizeOnSave(false);
      setInfo(noteFinalizeOnSave ? "Note saved and finalized." : "Draft note saved.");
      await reloadEncounterData();
    } catch (err) {
      const msg = String(err);
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(msg.replace(/^Error:\s*/, "") || "Could not save note.");
    } finally {
      setBusy(false);
    }
  }

  async function onAmendNote(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !amendNoteId || !canClinicalCreate || !writesAllowed) return;
    const hasContent =
      amendChief.trim() ||
      amendSubj.trim() ||
      amendObj.trim() ||
      amendAssess.trim() ||
      amendPlan.trim();
    if (!hasContent) {
      setTabError("Amendment requires at least one content field.");
      return;
    }
    setBusy(true);
    setTabError(null);
    try {
      await amendNote(tenant.id, amendNoteId, {
        chief_complaint: amendChief.trim() || null,
        subjective: amendSubj.trim() || null,
        objective: amendObj.trim() || null,
        assessment: amendAssess.trim() || null,
        plan: amendPlan.trim() || null,
      });
      setAmendNoteId("");
      setAmendChief("");
      setAmendSubj("");
      setAmendObj("");
      setAmendAssess("");
      setAmendPlan("");
      setInfo("Amendment recorded.");
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Amend failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onRecordVital(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !encounter || !canClinicalCreate || !writesAllowed) return;
    const num = Number(vitalValue);
    if (!Number.isFinite(num)) {
      setTabError("Enter a numeric value.");
      return;
    }
    setBusy(true);
    setTabError(null);
    try {
      await createObservation(tenant.id, encounter.id, {
        type_code: vitalType,
        value_numeric: num,
      });
      setVitalValue("");
      setInfo("Observation recorded.");
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Could not record vital.");
    } finally {
      setBusy(false);
    }
  }

  async function onAddDiagnosis(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !encounter || !canClinicalCreate || !writesAllowed) return;
    const code = dxMode === "code" ? dxSelectedCode.trim() : "";
    const text = dxMode === "free_text" ? dxFreeText.trim() : "";
    if ((code && text) || (!code && !text)) {
      setTabError("Provide exactly one of diagnosis code or free text.");
      return;
    }
    setBusy(true);
    setTabError(null);
    try {
      await createDiagnosis(tenant.id, encounter.id, {
        diagnosis_code: code || null,
        free_text: text || null,
        is_primary: dxPrimary,
      });
      setDxSelectedCode("");
      setDxFreeText("");
      setDxSearch("");
      setDxPrimary(false);
      setInfo("Diagnosis added.");
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Diagnosis failed.");
    } finally {
      setBusy(false);
    }
  }

  function rxSummary() {
    const med = medications.find((m) => m.code === rxMedCode);
    return {
      medication: med ? `${med.name} (${med.code})` : rxMedCode,
      dose: rxDose,
      route: rxRoute,
      frequency: rxFreq,
      duration: rxDuration.trim() ? `${rxDuration} days` : "—",
      instructions: rxInstructions,
    };
  }

  async function onCreateRx(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !encounter || !canRxCreate || !writesAllowed) return;
    if (!rxMedCode || !rxDose.trim() || !rxRoute || !rxFreq.trim() || !rxInstructions.trim()) {
      setTabError("Medication, dose, route, frequency, and instructions are required.");
      return;
    }
    if (!rxReviewing) {
      setRxReviewing(true);
      return;
    }
    setBusy(true);
    setTabError(null);
    try {
      await createPrescription(tenant.id, encounter.id, [
        {
          medication_code: rxMedCode,
          dose: rxDose.trim(),
          route: rxRoute,
          frequency: rxFreq.trim(),
          duration_days: rxDuration.trim() ? Number(rxDuration) : null,
          instructions: rxInstructions.trim(),
        },
      ]);
      setRxMedCode("");
      setRxDose("");
      setRxFreq("");
      setRxDuration("");
      setRxInstructions("");
      setRxReviewing(false);
      setMedQ("");
      setInfo("Prescription draft created.");
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Prescription failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onSignRx(prescriptionId: string) {
    if (!tenant || !canRxSign || !writesAllowed) return;
    setBusy(true);
    setTabError(null);
    try {
      await signPrescription(tenant.id, prescriptionId);
      setInfo("Prescription signed.");
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Sign failed.");
    } finally {
      setBusy(false);
    }
  }

  const planOverlayItems = useMemo((): PlanItem[] => {
    const items: PlanItem[] = [];
    for (const pl of plans) {
      for (const raw of pl.items ?? []) {
        items.push({
          id: raw.id,
          procedure_code: raw.procedure_code,
          procedure_display: raw.procedure_code,
          tooth: raw.tooth ?? null,
          surface: null,
          sequence: 0,
          status: raw.status ?? "proposed",
          notes: null,
        });
      }
    }
    return items;
  }, [plans]);

  async function onPlanActivate() {
    if (!tenant || !planActivateId || !canPlanManage) return;
    setBusy(true);
    setTabError(null);
    try {
      await activatePlan(tenant.id, planActivateId);
      setInfo("Treatment plan activated.");
      setPlanActivateId(null);
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else if (isForbidden(err)) setTabError("You do not have permission to activate plans.");
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Activate failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onPlanComplete() {
    if (!tenant || !planCompleteId || !canPlanManage) return;
    setBusy(true);
    setTabError(null);
    try {
      await completePlan(tenant.id, planCompleteId);
      setInfo("Treatment plan completed.");
      setPlanCompleteId(null);
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else if (isForbidden(err)) setTabError("You do not have permission.");
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Complete failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onPlanCancel() {
    if (!tenant || !planCancelId || !canPlanManage) return;
    setBusy(true);
    setTabError(null);
    try {
      await cancelPlan(tenant.id, planCancelId);
      setInfo("Treatment plan cancelled.");
      setPlanCancelId(null);
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else if (isForbidden(err)) setTabError("You do not have permission.");
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Cancel failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCreatePlan(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !encounter || !canPlanManage || !writesAllowed) return;
    if (!planProcedure.trim()) {
      setTabError("Procedure code is required.");
      return;
    }
    setBusy(true);
    setTabError(null);
    try {
      await createTreatmentPlan(tenant.id, {
        patient_id: encounter.patient_id,
        encounter_id: encounter.id,
        practitioner_id: encounter.practitioner_id,
        notes: planNotes.trim() || null,
        items: [
          {
            procedure_code: planProcedure.trim(),
            tooth: planTooth.trim() ? Number(planTooth) : null,
          },
        ],
      });
      setPlanNotes("");
      setPlanProcedure("");
      setPlanTooth("");
      setInfo("Treatment plan draft created.");
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Plan create failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCreateFollowUp(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !encounter || !canFollowupManage || !writesAllowed) return;
    if (!fuDue || !fuReason.trim()) {
      setTabError("Due date and reason are required.");
      return;
    }
    setBusy(true);
    setTabError(null);
    try {
      await createFollowUp(tenant.id, {
        patient_id: encounter.patient_id,
        location_id: encounter.location_id,
        due_at: new Date(fuDue).toISOString(),
        reason: fuReason.trim(),
        source_id: encounter.id,
      });
      setFuDue("");
      setFuReason("");
      setInfo("Follow-up scheduled.");
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Follow-up failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCloseEncounter() {
    if (!tenant || !encounter || !canClose) return;
    setClosePending(true);
    setTabError(null);
    try {
      const updated = await closeEncounter(tenant.id, encounter.id, {
        note_waiver: closeNoteWaiver,
        vitals_waiver: closeVitalsWaiver,
      });
      setEncounter(updated);
      setCloseOpen(false);
      setCloseNoteWaiver(false);
      setCloseVitalsWaiver(false);
      setInfo("Encounter closed.");
      await reloadEncounterData();
    } catch (err) {
      if (isSessionExpired(err)) onSessionExpired();
      else setTabError(String(err).replace(/^Error:\s*/, "") || "Close failed.");
    } finally {
      setClosePending(false);
    }
  }

  const finalizedNotes = notes.filter((n) => n.status === "finalized");
  const draftRxCount = prescriptions.filter((p) => p.status === "draft").length;
  const draftPlanCount = plans.filter((p) => p.status === "draft").length;
  const anyFinalizedNote = notes.some((n) => n.status === "finalized");

  const medOptions = useMemo(() => {
    const opts = medications.map((m) => ({
      value: m.code,
      label: `${m.name}${m.strength ? ` · ${m.strength}` : ""}`,
    }));
    if (rxMedCode && !opts.some((o) => o.value === rxMedCode)) {
      opts.unshift({ value: rxMedCode, label: rxMedCode });
    }
    return [{ value: "", label: "Select medication…" }, ...opts];
  }, [medications, rxMedCode]);

  const dxCodeOptions = useMemo(
    () => [
      { value: "", label: "Select code…" },
      ...dxCodes.map((c) => ({
        value: c.code,
        label: `${c.code} — ${c.display}`,
      })),
    ],
    [dxCodes],
  );

  if (loading) {
    return <LoadingState label="Loading encounter workspace" />;
  }

  if (loadError || !encounter) {
    return (
      <div className="hos-consult-workspace">
        <Alert tone="danger" title="Encounter">
          {loadError ?? "Could not load encounter."}
        </Alert>
        <Button type="button" variant="secondary" onClick={onBack}>
          Back
        </Button>
      </div>
    );
  }

  return (
    <div className="hos-consult-workspace">
      <div className="hos-toolbar-row">
        <Button type="button" variant="secondary" size="sm" onClick={handleBack}>
          ← Back
        </Button>
        <button
          type="button"
          className="hos-link-btn"
          onClick={() => onOpenPatient(encounter.patient_id)}
        >
          Open patient chart
        </button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => void reloadEncounterData()}
        >
          Refresh
        </Button>
      </div>

      {patient ? (
        <PatientIdentityHeader
          name={patient.display_name}
          patientId={patient.id}
          meta={patient.phone ?? undefined}
          status={encounter.status}
        />
      ) : (
        <Alert tone="warning" title="Patient">
          Patient record unavailable or not authorized.
        </Alert>
      )}

      {readOnly && (
        <Alert tone="info" title="Read-only">
          This encounter is closed. Clinical writes are disabled.
        </Alert>
      )}

      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}
      {tabError && (
        <Alert tone="danger" title="Action">
          {tabError}
        </Alert>
      )}
      {omitted.length > 0 && (
        <p className="hos-caption">
          Some sections omitted (missing permission): {omitted.join(", ")}
        </p>
      )}

      <div className="hos-consult-layout">
        <Card title="Patient context">
          <dl className="hos-dl">
            <div>
              <dt>DOB</dt>
              <dd>{patient?.date_of_birth ? fmtWhen(patient.date_of_birth) : "—"}</dd>
            </div>
            <div>
              <dt>Last visit</dt>
              <dd>
                {overview?.last_visit_at ? fmtWhen(overview.last_visit_at) : "—"}
              </dd>
            </div>
            <div>
              <dt>Outstanding</dt>
              <dd>
                {overview ? (
                  <MoneyDisplay
                    amount={overview.outstanding_balance}
                    currency={overview.currency}
                  />
                ) : (
                  "—"
                )}
              </dd>
            </div>
          </dl>
          <h3 className="hos-muted">Recent timeline</h3>
          {timeline.length === 0 ? (
            <EmptyState title="No timeline items">Nothing recent to show.</EmptyState>
          ) : (
            <ul>
              {timeline.map((t) => (
                <li key={t.event_id}>{t.title}</li>
              ))}
            </ul>
          )}
        </Card>

        <div style={{ gridColumn: "1 / -1" }}>
          <Tabs defaultValue="notes">
            <TabsList>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="vitals">Vitals</TabsTrigger>
              <TabsTrigger value="diagnoses">Diagnoses</TabsTrigger>
              <TabsTrigger value="rx">Rx</TabsTrigger>
              <TabsTrigger value="plans">Plans</TabsTrigger>
              <TabsTrigger value="dental">Dental</TabsTrigger>
              <TabsTrigger value="followup">Follow-up</TabsTrigger>
            </TabsList>

            <TabsContent value="notes">
              <Card title="Clinical notes">
                {notes.length === 0 ? (
                  <EmptyState title="No notes">Document the visit below.</EmptyState>
                ) : (
                  <Table
                    caption="Clinical notes"
                    density="compact"
                    columns={
                      <>
                        <Th>Type</Th>
                        <Th>Status</Th>
                        <Th>Created</Th>
                        <Th>Addendum</Th>
                      </>
                    }
                  >
                    {notes.map((n) => (
                      <tr key={n.id}>
                        <Td>{n.note_type}</Td>
                        <Td>
                          <Status value={n.status} />
                        </Td>
                        <Td>{fmtWhen(n.created_at)}</Td>
                        <Td>{n.is_addendum ? "yes" : "—"}</Td>
                      </tr>
                    ))}
                  </Table>
                )}

                {canClinicalCreate && writesAllowed && (
                  <>
                    <h3>New draft note</h3>
                    <form onSubmit={onSaveNote}>
                      <Field label="Chief complaint" htmlFor="ew-cc">
                        {({ describedBy }) => (
                          <Textarea
                            id="ew-cc"
                            aria-describedby={describedBy}
                            value={noteChief}
                            onChange={(ev) => setNoteChief(ev.target.value)}
                          />
                        )}
                      </Field>
                      <Field label="Subjective" htmlFor="ew-subj">
                        {({ describedBy }) => (
                          <Textarea
                            id="ew-subj"
                            aria-describedby={describedBy}
                            value={noteSubj}
                            onChange={(ev) => setNoteSubj(ev.target.value)}
                          />
                        )}
                      </Field>
                      <Field label="Objective" htmlFor="ew-obj">
                        {({ describedBy }) => (
                          <Textarea
                            id="ew-obj"
                            aria-describedby={describedBy}
                            value={noteObj}
                            onChange={(ev) => setNoteObj(ev.target.value)}
                          />
                        )}
                      </Field>
                      <Field label="Assessment" htmlFor="ew-assess">
                        {({ describedBy }) => (
                          <Textarea
                            id="ew-assess"
                            aria-describedby={describedBy}
                            value={noteAssess}
                            onChange={(ev) => setNoteAssess(ev.target.value)}
                          />
                        )}
                      </Field>
                      <Field label="Plan" htmlFor="ew-plan">
                        {({ describedBy }) => (
                          <Textarea
                            id="ew-plan"
                            aria-describedby={describedBy}
                            value={notePlan}
                            onChange={(ev) => setNotePlan(ev.target.value)}
                          />
                        )}
                      </Field>
                      <Field label="Finalize on save" htmlFor="ew-fin">
                        {({ describedBy }) => (
                          <Input
                            id="ew-fin"
                            type="checkbox"
                            aria-describedby={describedBy}
                            checked={noteFinalizeOnSave}
                            onChange={(ev) => setNoteFinalizeOnSave(ev.target.checked)}
                          />
                        )}
                      </Field>
                      <Button type="submit" disabled={busy} loading={busy}>
                        Save note
                      </Button>
                      <p className="hos-caption">
                        Drafts are never edited in place — save a new draft or amend a finalized
                        note.
                      </p>
                    </form>

                    {finalizedNotes.length > 0 && (
                      <>
                        <h3>Amend finalized note</h3>
                        <form onSubmit={onAmendNote}>
                          <Field label="Note to amend" htmlFor="ew-amend-id" required>
                            {({ describedBy }) => (
                              <Select
                                id="ew-amend-id"
                                aria-describedby={describedBy}
                                value={amendNoteId}
                                onChange={(ev) => setAmendNoteId(ev.target.value)}
                                required
                                options={[
                                  { value: "", label: "Select finalized note…" },
                                  ...finalizedNotes.map((n) => ({
                                    value: n.id,
                                    label: `${n.note_type} · ${fmtWhen(n.created_at)}`,
                                  })),
                                ]}
                              />
                            )}
                          </Field>
                          <Field label="Chief complaint" htmlFor="ew-am-cc">
                            {({ describedBy }) => (
                              <Textarea
                                id="ew-am-cc"
                                aria-describedby={describedBy}
                                value={amendChief}
                                onChange={(ev) => setAmendChief(ev.target.value)}
                              />
                            )}
                          </Field>
                          <Field label="Subjective" htmlFor="ew-am-subj">
                            {({ describedBy }) => (
                              <Textarea
                                id="ew-am-subj"
                                aria-describedby={describedBy}
                                value={amendSubj}
                                onChange={(ev) => setAmendSubj(ev.target.value)}
                              />
                            )}
                          </Field>
                          <Field label="Objective" htmlFor="ew-am-obj">
                            {({ describedBy }) => (
                              <Textarea
                                id="ew-am-obj"
                                aria-describedby={describedBy}
                                value={amendObj}
                                onChange={(ev) => setAmendObj(ev.target.value)}
                              />
                            )}
                          </Field>
                          <Field label="Assessment" htmlFor="ew-am-assess">
                            {({ describedBy }) => (
                              <Textarea
                                id="ew-am-assess"
                                aria-describedby={describedBy}
                                value={amendAssess}
                                onChange={(ev) => setAmendAssess(ev.target.value)}
                              />
                            )}
                          </Field>
                          <Field label="Plan" htmlFor="ew-am-plan">
                            {({ describedBy }) => (
                              <Textarea
                                id="ew-am-plan"
                                aria-describedby={describedBy}
                                value={amendPlan}
                                onChange={(ev) => setAmendPlan(ev.target.value)}
                              />
                            )}
                          </Field>
                          <Button type="submit" variant="secondary" disabled={busy} loading={busy}>
                            Submit amendment
                          </Button>
                        </form>
                      </>
                    )}
                  </>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="vitals">
              <Card title="Vitals &amp; observations">
                {observations.length === 0 ? (
                  <EmptyState title="No observations" />
                ) : (
                  <Table
                    caption="Observations"
                    density="clinical-dense"
                    columns={
                      <>
                        <Th>Type</Th>
                        <Th numeric>Value</Th>
                        <Th>Taken</Th>
                      </>
                    }
                  >
                    {observations.map((o) => (
                      <tr key={o.id}>
                        <Td>{o.type_display ?? o.type_code}</Td>
                        <Td numeric>
                          {o.value_numeric}
                          {o.unit ? ` ${o.unit}` : ""}
                        </Td>
                        <Td>{fmtWhen(o.taken_at)}</Td>
                      </tr>
                    ))}
                  </Table>
                )}
                {canClinicalCreate && writesAllowed && (
                  <form onSubmit={onRecordVital}>
                    <Field label="Type" htmlFor="ew-vital-type" required>
                      {({ describedBy }) => (
                        <Select
                          id="ew-vital-type"
                          aria-describedby={describedBy}
                          value={vitalType}
                          onChange={(ev) => setVitalType(ev.target.value)}
                          options={[...VITAL_TYPES]}
                        />
                      )}
                    </Field>
                    <Field label="Value" htmlFor="ew-vital-val" required>
                      {({ describedBy }) => (
                        <Input
                          id="ew-vital-val"
                          type="number"
                          step="any"
                          aria-describedby={describedBy}
                          value={vitalValue}
                          onChange={(ev) => setVitalValue(ev.target.value)}
                          required
                        />
                      )}
                    </Field>
                    <Button type="submit" disabled={busy} loading={busy}>
                      Record
                    </Button>
                  </form>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="diagnoses">
              <Card title="Diagnoses">
                {diagnoses.length === 0 ? (
                  <EmptyState title="No diagnoses" />
                ) : (
                  <Table
                    caption="Diagnoses"
                    columns={
                      <>
                        <Th>Diagnosis</Th>
                        <Th>Primary</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {diagnoses.map((d) => (
                      <tr key={d.id}>
                        <Td>{d.diagnosis_code ?? d.free_text ?? "—"}</Td>
                        <Td>{d.is_primary ? "yes" : "—"}</Td>
                        <Td>
                          <Status value={d.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
                {canClinicalCreate && writesAllowed && (
                  <form onSubmit={onAddDiagnosis}>
                    <Field label="Entry mode" htmlFor="ew-dx-mode" required>
                      {({ describedBy }) => (
                        <Select
                          id="ew-dx-mode"
                          aria-describedby={describedBy}
                          value={dxMode}
                          onChange={(ev) => {
                            setDxMode(ev.target.value as "code" | "free_text");
                            setDxSelectedCode("");
                            setDxFreeText("");
                            setDxSearch("");
                          }}
                          options={[
                            { value: "code", label: "Diagnosis code search" },
                            { value: "free_text", label: "Free text" },
                          ]}
                        />
                      )}
                    </Field>
                    {dxMode === "code" ? (
                      <>
                        <Field label="Search codes" htmlFor="ew-dx-q">
                          {({ describedBy }) => (
                            <Input
                              id="ew-dx-q"
                              aria-describedby={describedBy}
                              value={dxSearch}
                              onChange={(ev) => setDxSearch(ev.target.value)}
                              placeholder="Type to search"
                            />
                          )}
                        </Field>
                        <Field label="Code" htmlFor="ew-dx-code" required>
                          {({ describedBy }) => (
                            <Select
                              id="ew-dx-code"
                              aria-describedby={describedBy}
                              value={dxSelectedCode}
                              onChange={(ev) => setDxSelectedCode(ev.target.value)}
                              required
                              options={dxCodeOptions}
                            />
                          )}
                        </Field>
                      </>
                    ) : (
                      <Field label="Free text diagnosis" htmlFor="ew-dx-ft" required>
                        {({ describedBy }) => (
                          <Input
                            id="ew-dx-ft"
                            aria-describedby={describedBy}
                            value={dxFreeText}
                            onChange={(ev) => setDxFreeText(ev.target.value)}
                            required
                          />
                        )}
                      </Field>
                    )}
                    <Field label="Primary diagnosis" htmlFor="ew-dx-primary">
                      {({ describedBy }) => (
                        <Input
                          id="ew-dx-primary"
                          type="checkbox"
                          aria-describedby={describedBy}
                          checked={dxPrimary}
                          onChange={(ev) => setDxPrimary(ev.target.checked)}
                        />
                      )}
                    </Field>
                    <Button type="submit" disabled={busy} loading={busy}>
                      Add diagnosis
                    </Button>
                  </form>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="rx">
              <Card title="Prescriptions">
                {prescriptions.length === 0 ? (
                  <EmptyState title="No prescriptions" />
                ) : (
                  <Table
                    caption="Prescriptions"
                    columns={
                      <>
                        <Th>Status</Th>
                        <Th>Items</Th>
                        <Th>Action</Th>
                      </>
                    }
                  >
                    {prescriptions.map((p) => (
                      <tr key={p.id}>
                        <Td>
                          <Status value={p.status} />
                        </Td>
                        <Td>
                          {p.items
                            .map(
                              (i) =>
                                `${i.medication_name ?? i.medication_code} ${i.dose} ${i.frequency}`,
                            )
                            .join("; ")}
                        </Td>
                        <Td>
                          {p.status === "draft" && canRxSign && writesAllowed && (
                            <Button
                              type="button"
                              size="sm"
                              disabled={busy}
                              onClick={() => void onSignRx(p.id)}
                            >
                              Sign
                            </Button>
                          )}
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
                {canRxCreate && writesAllowed && (
                  <>
                    <form onSubmit={onCreateRx}>
                      <Field label="Search medications" htmlFor="ew-med-q">
                        {({ describedBy }) => (
                          <Input
                            id="ew-med-q"
                            aria-describedby={describedBy}
                            value={medQ}
                            onChange={(ev) => setMedQ(ev.target.value)}
                            placeholder="Name or code"
                          />
                        )}
                      </Field>
                      <Field label="Medication" htmlFor="ew-med" required>
                        {({ describedBy }) => (
                          <Select
                            id="ew-med"
                            aria-describedby={describedBy}
                            value={rxMedCode}
                            onChange={(ev) => setRxMedCode(ev.target.value)}
                            required
                            options={medOptions}
                          />
                        )}
                      </Field>
                      <Field label="Dose" htmlFor="ew-dose" required>
                        {({ describedBy }) => (
                          <Input
                            id="ew-dose"
                            aria-describedby={describedBy}
                            value={rxDose}
                            onChange={(ev) => setRxDose(ev.target.value)}
                            required
                          />
                        )}
                      </Field>
                      <Field label="Route" htmlFor="ew-route" required>
                        {({ describedBy }) => (
                          <Select
                            id="ew-route"
                            aria-describedby={describedBy}
                            value={rxRoute}
                            onChange={(ev) => setRxRoute(ev.target.value)}
                            options={[...RX_ROUTES]}
                          />
                        )}
                      </Field>
                      <Field label="Frequency" htmlFor="ew-freq" required>
                        {({ describedBy }) => (
                          <Input
                            id="ew-freq"
                            aria-describedby={describedBy}
                            value={rxFreq}
                            onChange={(ev) => setRxFreq(ev.target.value)}
                            required
                          />
                        )}
                      </Field>
                      <Field label="Duration (days)" htmlFor="ew-dur">
                        {({ describedBy }) => (
                          <Input
                            id="ew-dur"
                            type="number"
                            aria-describedby={describedBy}
                            value={rxDuration}
                            onChange={(ev) => setRxDuration(ev.target.value)}
                          />
                        )}
                      </Field>
                      <Field label="Instructions" htmlFor="ew-inst" required>
                        {({ describedBy }) => (
                          <Textarea
                            id="ew-inst"
                            aria-describedby={describedBy}
                            value={rxInstructions}
                            onChange={(ev) => setRxInstructions(ev.target.value)}
                            required
                          />
                        )}
                      </Field>
                      {rxReviewing && (
                        <Card title="Review before creating">
                          <dl className="hos-dl">
                            <div>
                              <dt>Medication</dt>
                              <dd>{rxSummary().medication}</dd>
                            </div>
                            <div>
                              <dt>Dose / route / frequency</dt>
                              <dd>
                                {rxSummary().dose} · {statusLabel(rxRoute)} · {rxSummary().frequency}
                              </dd>
                            </div>
                            <div>
                              <dt>Duration</dt>
                              <dd>{rxSummary().duration}</dd>
                            </div>
                            <div>
                              <dt>Instructions</dt>
                              <dd>{rxSummary().instructions}</dd>
                            </div>
                          </dl>
                        </Card>
                      )}
                      <Button type="submit" disabled={busy} loading={busy}>
                        {rxReviewing ? "Confirm and create draft" : "Review prescription"}
                      </Button>
                      {rxReviewing && (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => setRxReviewing(false)}
                        >
                          Edit
                        </Button>
                      )}
                    </form>
                    <p className="hos-caption">
                      Select medications from the catalog only — no dose or drug recommendations
                      are suggested by this UI.
                    </p>
                  </>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="dental">
              {tenant && encounter && (
                <DentalChartPanel
                  tenantId={tenant.id}
                  encounterId={encounter.id}
                  patientId={encounter.patient_id}
                  writesAllowed={writesAllowed}
                  canRead={canDentalRead}
                  canRecord={canDentalRecord}
                  onSessionExpired={onSessionExpired}
                  planItems={planOverlayItems}
                />
              )}
            </TabsContent>

            <TabsContent value="plans">
              <Card title="Treatment plans">
                {plans.length === 0 ? (
                  <EmptyState title="No treatment plans" />
                ) : (
                  <Table
                    caption="Treatment plans"
                    columns={
                      <>
                        <Th>Status</Th>
                        <Th>Procedures</Th>
                        <Th>Notes</Th>
                        <Th>Actions</Th>
                      </>
                    }
                  >
                    {plans.map((pl) => (
                      <tr key={pl.id}>
                        <Td>
                          <Status value={pl.status} />
                        </Td>
                        <Td>
                          {(pl.items ?? [])
                            .map((i) =>
                              i.tooth != null
                                ? `${i.procedure_code} (tooth ${i.tooth})`
                                : i.procedure_code,
                            )
                            .join(", ") || "—"}
                        </Td>
                        <Td>{pl.notes ?? "—"}</Td>
                        <Td>
                          {canPlanManage && writesAllowed && (
                            <div className="hos-inline-actions">
                              {pl.status === "draft" && (
                                <Button
                                  size="sm"
                                  onClick={() => setPlanActivateId(pl.id)}
                                  disabled={busy}
                                >
                                  Activate
                                </Button>
                              )}
                              {pl.status === "active" && (
                                <Button
                                  size="sm"
                                  onClick={() => setPlanCompleteId(pl.id)}
                                  disabled={busy}
                                >
                                  Complete
                                </Button>
                              )}
                              {(pl.status === "draft" || pl.status === "active") && (
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => setPlanCancelId(pl.id)}
                                  disabled={busy}
                                >
                                  Cancel
                                </Button>
                              )}
                            </div>
                          )}
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
                <p className="hos-caption">
                  Procedure in_progress/completed requires dental consent on the Dental tab. Full plan
                  lifecycle, item transitions, and consents: Treatment plans hub (
                  <code>/dental/plans</code>). Plan ≠ estimate ≠ invoice.
                </p>
                {canPlanManage && writesAllowed && (
                  <form onSubmit={onCreatePlan}>
                    <Field label="Plan notes" htmlFor="ew-pl-notes">
                      {({ describedBy }) => (
                        <Textarea
                          id="ew-pl-notes"
                          aria-describedby={describedBy}
                          value={planNotes}
                          onChange={(ev) => setPlanNotes(ev.target.value)}
                        />
                      )}
                    </Field>
                    <Field label="Procedure code" htmlFor="ew-pl-proc" required>
                      {({ describedBy }) => (
                        <Input
                          id="ew-pl-proc"
                          aria-describedby={describedBy}
                          value={planProcedure}
                          onChange={(ev) => setPlanProcedure(ev.target.value)}
                          required
                        />
                      )}
                    </Field>
                    <Field label="Tooth number (optional)" htmlFor="ew-pl-tooth">
                      {({ describedBy }) => (
                        <Input
                          id="ew-pl-tooth"
                          type="number"
                          aria-describedby={describedBy}
                          value={planTooth}
                          onChange={(ev) => setPlanTooth(ev.target.value)}
                        />
                      )}
                    </Field>
                    <Button type="submit" disabled={busy} loading={busy}>
                      Create draft plan
                    </Button>
                  </form>
                )}
              </Card>
              <Card title="Estimates (read-only)">
                {estimates.length === 0 ? (
                  <EmptyState title="No estimates" />
                ) : (
                  <Table
                    caption="Estimates"
                    columns={
                      <>
                        <Th>Status</Th>
                        <Th>Total</Th>
                      </>
                    }
                  >
                    {estimates.map((est) => (
                      <tr key={est.id}>
                        <Td>
                          <Status value={est.status} />
                        </Td>
                        <Td>
                          {est.grand_total ? (
                            <MoneyDisplay
                              amount={est.grand_total}
                              currency={est.currency ?? "INR"}
                            />
                          ) : (
                            "—"
                          )}
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="followup">
              <Card title="Follow-ups">
                {followUps.length === 0 ? (
                  <EmptyState title="No follow-ups" />
                ) : (
                  <Table
                    caption="Follow-ups"
                    columns={
                      <>
                        <Th>Due</Th>
                        <Th>Reason</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {followUps.map((f) => (
                      <tr key={f.id}>
                        <Td>{fmtWhen(f.due_at)}</Td>
                        <Td>{f.reason}</Td>
                        <Td>
                          <Status value={f.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
                {canFollowupManage && writesAllowed && (
                  <form onSubmit={onCreateFollowUp}>
                    <Field label="Due at" htmlFor="ew-fu-due" required>
                      {({ describedBy }) => (
                        <Input
                          id="ew-fu-due"
                          type="datetime-local"
                          aria-describedby={describedBy}
                          value={fuDue}
                          onChange={(ev) => setFuDue(ev.target.value)}
                          required
                        />
                      )}
                    </Field>
                    <Field label="Reason" htmlFor="ew-fu-reason" required>
                      {({ describedBy }) => (
                        <Textarea
                          id="ew-fu-reason"
                          aria-describedby={describedBy}
                          value={fuReason}
                          onChange={(ev) => setFuReason(ev.target.value)}
                          required
                        />
                      )}
                    </Field>
                    <Button type="submit" disabled={busy} loading={busy}>
                      Schedule follow-up
                    </Button>
                  </form>
                )}
              </Card>
            </TabsContent>
          </Tabs>

          {encounter.status === "open" && canClose && (
            <Card title="Close encounter">
              <p className="hos-muted">
                Closing requires finalized documentation and vitals unless you explicitly waive
                clinical requirements below.
              </p>
              <Button type="button" variant="danger" onClick={() => setCloseOpen(true)}>
                Close encounter…
              </Button>
            </Card>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={planActivateId != null}
        onOpenChange={(open) => {
          if (!open) setPlanActivateId(null);
        }}
        title="Activate treatment plan?"
        confirmLabel="Activate"
        pending={busy}
        onConfirm={() => void onPlanActivate()}
      >
        Activates the plan for care tracking. Plan activation is not consent-gated.
      </ConfirmDialog>

      <ConfirmDialog
        open={planCompleteId != null}
        onOpenChange={(open) => {
          if (!open) setPlanCompleteId(null);
        }}
        title="Complete treatment plan?"
        confirmLabel="Complete"
        pending={busy}
        onConfirm={() => void onPlanComplete()}
      >
        Marks the plan complete when intended care is finished.
      </ConfirmDialog>

      <ConfirmDialog
        open={planCancelId != null}
        onOpenChange={(open) => {
          if (!open) setPlanCancelId(null);
        }}
        title="Cancel treatment plan?"
        confirmLabel="Cancel plan"
        pending={busy}
        onConfirm={() => void onPlanCancel()}
      >
        Cancels the plan. Reconcile open items on the chart or in the Treatment plans hub.
      </ConfirmDialog>

      <ConfirmDialog
        open={closeOpen}
        onOpenChange={setCloseOpen}
        title="Close encounter?"
        confirmLabel="Close encounter"
        pending={closePending}
        onConfirm={() => void onCloseEncounter()}
      >
        <p>
          Patient: <strong>{patient?.display_name ?? encounter.patient_id}</strong>
        </p>
        <ul>
          <li>Finalized note: {anyFinalizedNote ? "yes" : "none"}</li>
          <li>Draft prescriptions: {draftRxCount}</li>
          <li>Draft treatment plans: {draftPlanCount}</li>
        </ul>
        <Field label="Clinical waiver — note requirements" htmlFor="ew-close-note-w">
          {({ describedBy }) => (
            <Input
              id="ew-close-note-w"
              type="checkbox"
              aria-describedby={describedBy}
              checked={closeNoteWaiver}
              onChange={(ev) => setCloseNoteWaiver(ev.target.checked)}
            />
          )}
        </Field>
        <Field label="Clinical waiver — vitals requirements" htmlFor="ew-close-vit-w">
          {({ describedBy }) => (
            <Input
              id="ew-close-vit-w"
              type="checkbox"
              aria-describedby={describedBy}
              checked={closeVitalsWaiver}
              onChange={(ev) => setCloseVitalsWaiver(ev.target.checked)}
            />
          )}
        </Field>
        <p className="hos-caption">
          Waivers are off by default. The server will reject close if requirements are unmet.
        </p>
      </ConfirmDialog>
    </div>
  );
}