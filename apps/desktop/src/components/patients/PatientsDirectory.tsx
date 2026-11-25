import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Select,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { createPatient, listPatients, Patient } from "../../lib/patientsApi";
import { hasPerm } from "../../lib/nav";
import { useSession } from "../../lib/session";
import { fmtDate } from "../../lib/format";

const PAGE_SIZE = 50;

export function PatientsDirectory({
  onOpenPatient,
  onSessionExpired,
}: {
  onOpenPatient: (id: string) => void;
  onSessionExpired: () => void;
}) {
  const { tenant, workspace } = useSession();
  const canCreate = hasPerm(workspace?.permissions, "patient.create");

  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">(
    "active",
  );
  const [rows, setRows] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [dob, setDob] = useState("");
  const [emergName, setEmergName] = useState("");
  const [emergPhone, setEmergPhone] = useState("");
  const [creating, setCreating] = useState(false);
  const [dupNote, setDupNote] = useState<string | null>(null);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(id);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await listPatients(tenant.id, {
          q: debounced || undefined,
          limit: 100,
          activeOnly: activeFilter === "active",
        });
        if (cancelled) return;
        let filtered = data;
        if (activeFilter === "inactive") {
          filtered = data.filter((p) => !p.is_active);
        } else if (activeFilter === "all") {
          // backend active_only=false returns both
          filtered = data;
        }
        setRows(filtered);
        setPage(0);
      } catch (e) {
        if (cancelled) return;
        if (String(e).includes("session_expired")) onSessionExpired();
        else if (String(e).includes("forbidden"))
          setError("You do not have permission to view patients.");
        else setError("Failed to load patients.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, debounced, activeFilter]);

  const pageRows = useMemo(() => {
    const start = page * PAGE_SIZE;
    return rows.slice(start, start + PAGE_SIZE);
  }, [rows, page]);
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));

  async function onRegister(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canCreate) return;
    if (name.trim().length < 2) {
      setError("Display name must be at least 2 characters.");
      return;
    }
    setCreating(true);
    setError(null);
    setDupNote(null);
    try {
      const created = await createPatient(tenant.id, {
        display_name: name.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        date_of_birth: dob || null,
        emergency_contact_name: emergName.trim() || null,
        emergency_contact_phone: emergPhone.trim() || null,
      });
      if (created.potential_duplicates?.length) {
        setDupNote(
          `Registered. Similar phone/email already on file (${created.potential_duplicates.length} match). Review before merging manually.`,
        );
      }
      setName("");
      setPhone("");
      setEmail("");
      setDob("");
      setEmergName("");
      setEmergPhone("");
      onOpenPatient(created.id);
    } catch (err) {
      if (String(err).includes("session_expired")) onSessionExpired();
      else setError(String(err).replace(/^Error:\s*/, "") || "Registration failed.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="hos-patients">
      <header className="hos-module-header">
        <h1>Patients</h1>
        <p className="hos-muted">Search and register clinic patients</p>
      </header>

      {error && (
        <Alert tone="danger" title="Patients">
          {error}
        </Alert>
      )}
      {dupNote && (
        <Alert tone="warning" title="Possible duplicate">
          {dupNote}
        </Alert>
      )}

      <div className="hos-patients-layout">
        <Card title="Directory">
          <div className="hos-toolbar-row">
            <Field label="Search" htmlFor="patient-q">
              {({ describedBy }) => (
                <Input
                  id="patient-q"
                  aria-describedby={describedBy}
                  placeholder="Name, phone, or email"
                  value={query}
                  onChange={(ev) => setQuery(ev.target.value)}
                  autoComplete="off"
                />
              )}
            </Field>
            <Field label="Status" htmlFor="patient-status">
              {({ describedBy }) => (
                <Select
                  id="patient-status"
                  aria-describedby={describedBy}
                  value={activeFilter}
                  onChange={(ev) =>
                    setActiveFilter(ev.target.value as typeof activeFilter)
                  }
                  options={[
                    { value: "active", label: "Active" },
                    { value: "inactive", label: "Inactive" },
                    { value: "all", label: "All" },
                  ]}
                />
              )}
            </Field>
          </div>

          {loading ? (
            <LoadingState label="Loading patients" />
          ) : pageRows.length === 0 ? (
            <EmptyState title="No patients found">
              Adjust search or register a new patient.
            </EmptyState>
          ) : (
            <>
              <Table
                columns={
                  <>
                    <Th>Name</Th>
                    <Th>Phone</Th>
                    <Th>Email</Th>
                    <Th>DOB</Th>
                    <Th>Status</Th>
                    <Th>
                      <span className="hos-sr-only">Open</span>
                    </Th>
                  </>
                }
              >
                {pageRows.map((p) => (
                    <tr key={p.id}>
                      <Td>
                        <button
                          type="button"
                          className="hos-link-btn"
                          onClick={() => onOpenPatient(p.id)}
                        >
                          {p.display_name}
                        </button>
                      </Td>
                      <Td>{p.phone ?? "—"}</Td>
                      <Td>{p.email ?? "—"}</Td>
                      <Td>{fmtDate(p.date_of_birth)}</Td>
                      <Td>
                        <Status value={p.is_active ? "current" : "revoked"} />
                      </Td>
                      <Td>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => onOpenPatient(p.id)}
                        >
                          Open
                        </Button>
                      </Td>
                    </tr>
                  ))}
              </Table>
              <div className="hos-pager">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  Previous
                </Button>
                <span className="hos-caption">
                  Page {page + 1} of {pageCount} · {rows.length} loaded
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={page + 1 >= pageCount}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </>
          )}
        </Card>

        {canCreate && (
          <Card title="Register patient">
            <form onSubmit={onRegister} data-testid="patient-register-form">
              <Field label="Display name" htmlFor="reg-name" required>
                {({ describedBy }) => (
                  <Input
                    id="reg-name"
                    aria-describedby={describedBy}
                    value={name}
                    onChange={(ev) => setName(ev.target.value)}
                    required
                    minLength={2}
                  />
                )}
              </Field>
              <Field label="Phone" htmlFor="reg-phone">
                {({ describedBy }) => (
                  <Input
                    id="reg-phone"
                    aria-describedby={describedBy}
                    value={phone}
                    onChange={(ev) => setPhone(ev.target.value)}
                  />
                )}
              </Field>
              <Field label="Email" htmlFor="reg-email">
                {({ describedBy }) => (
                  <Input
                    id="reg-email"
                    type="email"
                    aria-describedby={describedBy}
                    value={email}
                    onChange={(ev) => setEmail(ev.target.value)}
                  />
                )}
              </Field>
              <Field label="Date of birth" htmlFor="reg-dob">
                {({ describedBy }) => (
                  <Input
                    id="reg-dob"
                    type="date"
                    aria-describedby={describedBy}
                    value={dob}
                    onChange={(ev) => setDob(ev.target.value)}
                  />
                )}
              </Field>
              <Field label="Emergency contact" htmlFor="reg-emerg-name">
                {({ describedBy }) => (
                  <Input
                    id="reg-emerg-name"
                    aria-describedby={describedBy}
                    value={emergName}
                    onChange={(ev) => setEmergName(ev.target.value)}
                  />
                )}
              </Field>
              <Field label="Emergency phone" htmlFor="reg-emerg-phone">
                {({ describedBy }) => (
                  <Input
                    id="reg-emerg-phone"
                    aria-describedby={describedBy}
                    value={emergPhone}
                    onChange={(ev) => setEmergPhone(ev.target.value)}
                  />
                )}
              </Field>
              <Button type="submit" disabled={creating} loading={creating}>
                Register
              </Button>
            </form>
          </Card>
        )}
      </div>
    </div>
  );
}
