"use client";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
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
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../../shell";
import { Odontogram } from "@healthcare-os/ui";
import { DocsTab, type DocRef } from "./docs-tab";

type Encounter = {
  id: string;
  patient_id: string;
  patient_name?: string;
  status: string;
  opened_at: string;
  appointment_id: string | null;
};
type Note = {
  id: string;
  note_type: string;
  status: string;
  chief_complaint: string | null;
  subjective: string | null;
  objective: string | null;
  assessment: string | null;
  plan: string | null;
  is_addendum: boolean;
  supersedes_id: string | null;
};
type Observation = {
  id: string;
  type_code: string;
  value_numeric: string | null;
  value_text: string | null;
  unit: string | null;
  taken_at: string;
  corrected_by_id: string | null;
};
type Diagnosis = {
  id: string;
  diagnosis_code: string | null;
  free_text: string | null;
  is_primary: boolean;
  status: string;
  review_needed: boolean;
};
type Prescription = {
  id: string;
  status: string;
  version: number;
  items: { line_no: number; medication_code: string; dose: string; frequency: string }[];
};
type Finding = { id: string; tooth: number; condition_code: string; status: string };
type Patient = { id: string; display_name: string; phone: string | null };

export default function EncounterWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [enc, setEnc] = useState<Encounter | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [obs, setObs] = useState<Observation[]>([]);
  const [dx, setDx] = useState<Diagnosis[]>([]);
  const [rx, setRx] = useState<Prescription[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [docs, setDocs] = useState<DocRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [closing, setClosing] = useState(false);

  function t() {
    return getSelectedTenant() ?? "";
  }

  function load() {
    const tenant = getSelectedTenant();
    if (!tenant) {
      router.push("/");
      return;
    }
    setLoading(true);
    const get = <T,>(path: string) => api.get<T>(`/api/v1/tenants/${tenant}${path}`, tenant);
    get<Encounter>(`/encounters/${id}`)
      .then((e) => {
        setEnc(e);
        return Promise.all([
          get<Patient>(`/patients/${e.patient_id}`).then(setPatient).catch(() => {}),
          get<Note[]>(`/encounters/${id}/clinical-notes`).then(setNotes).catch(() => setNotes([])),
          get<Observation[]>(`/encounters/${id}/observations`).then(setObs).catch(() => setObs([])),
          get<Diagnosis[]>(`/encounters/${id}/diagnoses`).then(setDx).catch(() => setDx([])),
          get<Prescription[]>(`/encounters/${id}/prescriptions`).then(setRx).catch(() => setRx([])),
          get<Finding[]>(`/encounters/${id}/tooth-findings`).then(setFindings).catch(() => setFindings([])),
          get<DocRef[]>(`/encounters/${id}/documents`).then(setDocs).catch(() => setDocs([])),
        ]);
      })
      .then(() => setError(""))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [id, router]);

  async function close() {
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${t()}/encounters/${id}/close`,
        { note_waiver: false, vitals_waiver: false, reason: "wrap-up" },
        t(),
      );
      setClosing(false);
      setMessage("Encounter closed.");
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Shell>
      {loading ? (
        <LoadingState label="Loading encounter" />
      ) : error && !enc ? (
        <Alert tone="danger" title="Could not load encounter">
          {error}
        </Alert>
      ) : enc ? (
        <>
          {patient ? (
            <PatientIdentityHeader
              name={patient.display_name}
              patientId={patient.id}
              meta={patient.phone ?? undefined}
              status={enc.status}
            />
          ) : null}
          {error ? (
            <Alert tone="danger" title="Something went wrong">
              {error}
            </Alert>
          ) : null}
          {message ? <Alert tone="success">{message}</Alert> : null}
          <Tabs defaultValue="notes">
            <TabsList>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="vitals">Vitals</TabsTrigger>
              <TabsTrigger value="diagnoses">Diagnoses</TabsTrigger>
              <TabsTrigger value="rx">Prescriptions</TabsTrigger>
              <TabsTrigger value="dental">Dental</TabsTrigger>
              <TabsTrigger value="docs">Documents</TabsTrigger>
            </TabsList>
            <TabsContent value="notes">
              <NotesTab encounterId={id} notes={notes} onChange={load} />
            </TabsContent>
            <TabsContent value="vitals">
              <VitalsTab encounterId={id} obs={obs} onChange={load} />
            </TabsContent>
            <TabsContent value="diagnoses">
              <DiagnosesTab encounterId={id} items={dx} onChange={load} />
            </TabsContent>
            <TabsContent value="rx">
              <RxTab encounterId={id} items={rx} onChange={load} />
            </TabsContent>
            <TabsContent value="dental">
              <DentalTab encounterId={id} findings={findings} onChange={load} />
            </TabsContent>
            <TabsContent value="docs">
              <DocsTab encounterId={id} docs={docs} onChange={load} />
            </TabsContent>
          </Tabs>
          {enc.status === "open" ? (
            <Card title="Close encounter">
              <p>
                Closing requires a finalized note (or waiver), vitals (or waiver), and no
                open prescriptions or treatment plans.
              </p>
              <Button variant="danger" onClick={() => setClosing(true)}>
                Close encounter...
              </Button>
            </Card>
          ) : (
            <Alert tone="info">This encounter is closed and read-only.</Alert>
          )}
          <ConfirmDialog
            open={closing}
            onOpenChange={setClosing}
            title="Close encounter?"
            confirmLabel="Close encounter"
            onConfirm={() => void close()}
          >
            Close without waivers. The server will reject the close if requirements
            are unmet - fix what it reports and try again.
          </ConfirmDialog>
        </>
      ) : null}
    </Shell>
  );
}

function post(path: string, body: unknown) {
  const t = getSelectedTenant() ?? "";
  return api.post(`/api/v1/tenants/${t}${path}`, body, t);
}

function NotesTab({
  encounterId,
  notes,
  onChange,
}: {
  encounterId: string;
  notes: Note[];
  onChange: () => void;
}) {
  const [subjective, setSubjective] = useState("");
  const [objective, setObjective] = useState("");
  const [assessment, setAssessment] = useState("");
  const [plan, setPlan] = useState("");
  const [error, setError] = useState("");

  async function create(e: React.FormEvent, noteType = "general") {
    e.preventDefault();
    setError("");
    try {
      await post(`/encounters/${encounterId}/clinical-notes`, {
        note_type: noteType,
        subjective: subjective || null,
        objective: objective || null,
        assessment: assessment || null,
        plan: plan || null,
      });
      setSubjective("");
      setObjective("");
      setAssessment("");
      setPlan("");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function transition(noteId: string, action: "finalize" | "amend") {
    setError("");
    try {
      if (action === "finalize") {
        await post(`/clinical-notes/${noteId}/finalize`, {});
      } else {
        await post(`/clinical-notes/${noteId}/amend`, {
          subjective,
          objective,
          assessment,
          plan,
        });
      }
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Card title="Clinical notes">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {notes.length === 0 ? (
        <EmptyState title="No notes yet">Document the first note below.</EmptyState>
      ) : (
        <Table
          caption="Clinical notes"
          columns={
            <>
              <Th>Type</Th>
              <Th>Status</Th>
              <Th>Addendum</Th>
              <Th>Actions</Th>
            </>
          }
        >
          {notes.map((n) => (
            <tr key={n.id}>
              <Td>{n.note_type}</Td>
              <Td>
                <Status value={n.status} />
              </Td>
              <Td>{n.is_addendum ? "yes" : "-"}</Td>
              <Td>
                {n.status === "draft" ? (
                  <Button size="sm" onClick={() => void transition(n.id, "finalize")}>
                    Finalize
                  </Button>
                ) : n.status === "finalized" ? (
                  <span className="hos-helper">Use the form to amend (creates a new version)</span>
                ) : (
                  <Badge tone="neutral">amended record</Badge>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      )}
      <h3>New note / amendment content</h3>
      <form onSubmit={(e) => void create(e)}>
        <Field label="Subjective" htmlFor="n-subj">
          {() => (
            <Textarea id="n-subj" value={subjective} onChange={(e) => setSubjective(e.target.value)} />
          )}
        </Field>
        <Field label="Objective" htmlFor="n-obj">
          {() => (
            <Textarea id="n-obj" value={objective} onChange={(e) => setObjective(e.target.value)} />
          )}
        </Field>
        <Field label="Assessment" htmlFor="n-ass">
          {() => (
            <Textarea id="n-ass" value={assessment} onChange={(e) => setAssessment(e.target.value)} />
          )}
        </Field>
        <Field label="Plan" htmlFor="n-plan">
          {() => <Textarea id="n-plan" value={plan} onChange={(e) => setPlan(e.target.value)} />}
        </Field>
        <p>
          <Button type="submit">Save draft note</Button>
        </p>
      </form>
      <h3>Amend a finalized note</h3>
      {notes
        .filter((n) => n.status === "finalized")
        .map((n) => (
          <p key={n.id}>
            <Button size="sm" variant="secondary" onClick={() => void transition(n.id, "amend")}>
              Amend {n.note_type} note with form content
            </Button>
          </p>
        ))}
    </Card>
  );
}

function VitalsTab({
  encounterId,
  obs,
  onChange,
}: {
  encounterId: string;
  obs: Observation[];
  onChange: () => void;
}) {
  const [typeCode, setTypeCode] = useState("bp_systolic");
  const [value, setValue] = useState("");
  const [error, setError] = useState("");

  async function record(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await post(`/encounters/${encounterId}/observations`, {
        type_code: typeCode,
        value_numeric: Number(value),
      });
      setValue("");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Card title="Vitals & observations">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {obs.length === 0 ? (
        <EmptyState title="No observations recorded" />
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
          {obs.map((o) => (
            <tr key={o.id}>
              <Td>{o.type_code}</Td>
              <Td numeric>
                {o.value_numeric ?? o.value_text ?? "-"} {o.unit ?? ""}
              </Td>
              <Td>{new Date(o.taken_at).toLocaleString()}</Td>
            </tr>
          ))}
        </Table>
      )}
      <h3>Record observation</h3>
      <form onSubmit={record}>
        <Field label="Type" htmlFor="o-type" required>
          {() => (
            <Select
              id="o-type"
              value={typeCode}
              onChange={(e) => setTypeCode(e.target.value)}
              required
              options={["bp_systolic", "bp_diastolic", "pulse", "spo2", "temperature"].map(
                (c) => ({ value: c, label: c }),
              )}
            />
          )}
        </Field>
        <Field label="Value" htmlFor="o-value" required description="Catalog range-checked server-side.">
          {({ describedBy }) => (
            <Input
              id="o-value"
              type="number"
              step="any"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
              aria-describedby={describedBy}
            />
          )}
        </Field>
        <p>
          <Button type="submit">Record</Button>
        </p>
      </form>
    </Card>
  );
}

function DiagnosesTab({
  encounterId,
  items,
  onChange,
}: {
  encounterId: string;
  items: Diagnosis[];
  onChange: () => void;
}) {
  const [code, setCode] = useState("");
  const [freeText, setFreeText] = useState("");
  const [error, setError] = useState("");

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await post(`/encounters/${encounterId}/diagnoses`, {
        diagnosis_code: code || null,
        free_text: freeText || null,
      });
      setCode("");
      setFreeText("");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function resolve(id: string, outcome: "resolved" | "ruled_out") {
    setError("");
    try {
      await post(`/diagnoses/${id}/resolve`, { outcome });
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Card title="Diagnoses">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {items.length === 0 ? (
        <EmptyState title="No diagnoses" />
      ) : (
        <Table
          caption="Diagnoses"
          columns={
            <>
              <Th>Diagnosis</Th>
              <Th>Status</Th>
              <Th>Actions</Th>
            </>
          }
        >
          {items.map((d) => (
            <tr key={d.id}>
              <Td>
                {d.diagnosis_code ?? d.free_text ?? "-"}
                {d.is_primary ? " (primary)" : ""}
                {d.review_needed ? " - needs review" : ""}
              </Td>
              <Td>
                <Status value={d.status} />
              </Td>
              <Td>
                {d.status === "active" ? (
                  <>
                    <Button size="sm" variant="secondary" onClick={() => void resolve(d.id, "resolved")}>
                      Resolve
                    </Button>{" "}
                    <Button size="sm" variant="secondary" onClick={() => void resolve(d.id, "ruled_out")}>
                      Rule out
                    </Button>
                  </>
                ) : null}
              </Td>
            </tr>
          ))}
        </Table>
      )}
      <h3>Add diagnosis</h3>
      <form onSubmit={add}>
        <Field label="ICD code (optional)" htmlFor="dx-code" description="Leave empty for free-text diagnosis.">
          {({ describedBy }) => (
            <Input id="dx-code" value={code} onChange={(e) => setCode(e.target.value)} aria-describedby={describedBy} />
          )}
        </Field>
        <Field label="Free text (optional)" htmlFor="dx-text">
          {() => <Input id="dx-text" value={freeText} onChange={(e) => setFreeText(e.target.value)} />}
        </Field>
        <p>
          <Button type="submit">Add</Button>
        </p>
      </form>
    </Card>
  );
}

function RxTab({
  encounterId,
  items,
  onChange,
}: {
  encounterId: string;
  items: Prescription[];
  onChange: () => void;
}) {
  const [medCode, setMedCode] = useState("");
  const [dose, setDose] = useState("");
  const [route, setRoute] = useState("oral");
  const [frequency, setFrequency] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState("");

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await post(`/encounters/${encounterId}/prescriptions`, {
        items: [{ medication_code: medCode, dose, route, frequency, instructions }],
      });
      setMedCode("");
      setDose("");
      setFrequency("");
      setInstructions("");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function act(id: string, action: "sign" | "cancel") {
    setError("");
    try {
      await post(
        `/prescriptions/${id}/${action}`,
        action === "cancel" ? { reason: "cancelled from workspace" } : {},
      );
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Card title="Prescriptions">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {items.length === 0 ? (
        <EmptyState title="No prescriptions" />
      ) : (
        <Table
          caption="Prescriptions"
          columns={
            <>
              <Th>ID</Th>
              <Th>Status</Th>
              <Th>Items</Th>
              <Th>Actions</Th>
            </>
          }
        >
          {items.map((p) => (
            <tr key={p.id}>
              <Td>{p.id.slice(0, 8)}... (v{p.version})</Td>
              <Td>
                <Status value={p.status} />
              </Td>
              <Td>
                {p.items.map((i) => `${i.medication_code} ${i.dose} ${i.frequency}`).join("; ")}
              </Td>
              <Td>
                {p.status === "draft" ? (
                  <Button size="sm" onClick={() => void act(p.id, "sign")}>
                    Sign
                  </Button>
                ) : p.status === "signed" ? (
                  <Button size="sm" variant="secondary" onClick={() => void act(p.id, "cancel")}>
                    Cancel
                  </Button>
                ) : null}
              </Td>
            </tr>
          ))}
        </Table>
      )}
      <h3>New prescription (draft)</h3>
      <form onSubmit={create}>
        <Field label="Medication code" htmlFor="rx-med" required>
          {() => (
            <Input id="rx-med" value={medCode} onChange={(e) => setMedCode(e.target.value)} required />
          )}
        </Field>
        <Field label="Dose" htmlFor="rx-dose" required>
          {() => <Input id="rx-dose" value={dose} onChange={(e) => setDose(e.target.value)} required />}
        </Field>
        <Field label="Route" htmlFor="rx-route" required>
          {() => (
            <Input id="rx-route" value={route} onChange={(e) => setRoute(e.target.value)} required />
          )}
        </Field>
        <Field label="Frequency" htmlFor="rx-freq" required>
          {() => (
            <Input id="rx-freq" value={frequency} onChange={(e) => setFrequency(e.target.value)} required />
          )}
        </Field>
        <Field label="Instructions" htmlFor="rx-inst" required description="How to take it; printed for the patient.">
          {({ describedBy }) => (
            <Input
              id="rx-inst"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              required
              aria-describedby={describedBy}
            />
          )}
        </Field>
        <p>
          <Button type="submit">Create draft</Button>
        </p>
      </form>
      <p className="hos-helper">
        Signing requires the prescriber practitioner. Corrections create a new draft version.
      </p>
    </Card>
  );
}

function DentalTab({
  encounterId,
  findings,
  onChange,
}: {
  encounterId: string;
  findings: Finding[];
  onChange: () => void;
}) {
  const [tooth, setTooth] = useState<number | null>(null);
  const [condition, setCondition] = useState("caries");
  const [error, setError] = useState("");

  const states: Record<number, "finding" | "planned" | "completed"> = {};
  for (const f of findings) {
    if (f.status === "active") states[f.tooth] = "finding";
  }

  async function record() {
    if (!tooth) return;
    setError("");
    try {
      await post(`/encounters/${encounterId}/tooth-findings`, {
        tooth,
        condition_code: condition,
      });
      setTooth(null);
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function resolve(id: string) {
    setError("");
    try {
      await post(`/tooth-findings/${id}/resolve`, {});
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Card title="Dental findings">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <Odontogram states={states} selected={tooth} onSelect={setTooth} />
      <Field label="Tooth (FDI)" htmlFor="d-tooth" description="Pick on the chart or type the number.">
        {({ describedBy }) => (
          <Input
            id="d-tooth"
            type="number"
            min={11}
            max={48}
            value={tooth ?? ""}
            onChange={(e) => setTooth(e.target.value ? Number(e.target.value) : null)}
            aria-describedby={describedBy}
          />
        )}
      </Field>
      <Field label="Condition" htmlFor="d-cond" required>
        {() => (
          <Input id="d-cond" value={condition} onChange={(e) => setCondition(e.target.value)} required />
        )}
      </Field>
      <p>
        <Button onClick={() => void record()} disabled={!tooth}>
          Record finding
        </Button>
      </p>
      {findings.length === 0 ? (
        <EmptyState title="No findings recorded" />
      ) : (
        <Table
          caption="Tooth findings"
          columns={
            <>
              <Th numeric>Tooth</Th>
              <Th>Condition</Th>
              <Th>Status</Th>
              <Th>Actions</Th>
            </>
          }
        >
          {findings.map((f) => (
            <tr key={f.id}>
              <Td numeric>{f.tooth}</Td>
              <Td>{f.condition_code}</Td>
              <Td>
                <Status value={f.status} />
              </Td>
              <Td>
                {f.status === "active" ? (
                  <Button size="sm" variant="secondary" onClick={() => void resolve(f.id)}>
                    Resolve
                  </Button>
                ) : null}
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
