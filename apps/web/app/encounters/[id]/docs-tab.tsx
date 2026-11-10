"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ClinicalImageViewer,
  EmptyState,
  Field,
  Input,
  Select,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import {
  documentAccessErrorMessage,
  isEligibleImageDoc,
  requestDocumentAccess,
} from "@/lib/documents";

export type DocRef = {
  id: string;
  doc_type: string;
  storage_key: string;
  /** Trusted persisted MIME type. Null/untyped rows are never viewable. */
  content_type: string | null;
  notes: string | null;
};

function post(path: string, body: unknown) {
  const t = getSelectedTenant() ?? "";
  return api.post(`/api/v1/tenants/${t}${path}`, body, t);
}

/**
 * Encounter Documents tab with D1c authorized image viewing.
 *
 * DocsTab owns document selection and D1b retrieval orchestration; the
 * reusable `ClinicalImageViewer` stays presentation-only and receives the
 * signed URL (in-memory React state) only after a successful grant. No
 * storage key, bucket, or internal path enters viewer props; nothing is
 * persisted to browser storage or placed in route/query state.
 */
export function DocsTab({
  encounterId,
  docs,
  onChange,
}: {
  encounterId: string;
  docs: DocRef[];
  onChange: () => void;
}) {
  const [docType, setDocType] = useState("report");
  const [storageKey, setStorageKey] = useState("");
  const [error, setError] = useState("");

  // --- D1c authorized viewer state (in-memory only) ---
  // The signed URL lives in React state for the current viewer session.
  // It is never written to browser storage, never placed in route/query
  // state, and never logged. A fresh URL is minted on open, on navigation,
  // and on retry; each mint replaces the previous value.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [signedUrl, setSignedUrl] = useState<string | null>(null);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerError, setViewerError] = useState("");
  const mintSeq = useRef(0);

  // Eligibility comes only from trusted persisted content_type.
  // doc_type, filenames, and labels are never used to guess eligibility.
  const eligible = useMemo(() => docs.filter(isEligibleImageDoc), [docs]);
  const selectedIndex = selectedId
    ? eligible.findIndex((d) => d.id === selectedId)
    : -1;
  const selectedDoc = selectedIndex >= 0 ? eligible[selectedIndex] : null;

  // If the underlying list changes so the selection is no longer eligible,
  // drop the viewer session rather than showing a stale image.
  useEffect(() => {
    if (selectedId && selectedIndex < 0) {
      mintSeq.current += 1;
      setSelectedId(null);
      setSignedUrl(null);
      setViewerError("");
      setViewerLoading(false);
    }
  }, [selectedId, selectedIndex]);

  // Focus the back control when the viewer opens; the viewer itself owns
  // stage keyboard handling from there.
  useEffect(() => {
    if (selectedId) {
      document.getElementById("docs-viewer-back")?.focus();
    }
  }, [selectedId]);

  async function mint(documentId: string) {
    const tenant = getSelectedTenant() ?? "";
    if (!tenant) {
      setViewerError(documentAccessErrorMessage());
      return;
    }
    const seq = (mintSeq.current += 1);
    setViewerLoading(true);
    setViewerError("");
    try {
      const grant = await requestDocumentAccess(tenant, documentId);
      if (mintSeq.current !== seq) return;
      setSignedUrl(grant.url);
      setViewerError("");
    } catch (err) {
      if (mintSeq.current !== seq) return;
      setSignedUrl(null);
      setViewerError(
        documentAccessErrorMessage((err as Error & { status?: number }).status),
      );
    } finally {
      if (mintSeq.current === seq) setViewerLoading(false);
    }
  }

  function openAt(index: number) {
    const doc = eligible[index];
    if (!doc) return;
    setSelectedId(doc.id);
    setSignedUrl(null);
    void mint(doc.id);
  }

  function closeViewer() {
    mintSeq.current += 1;
    setSelectedId(null);
    setSignedUrl(null);
    setViewerError("");
    setViewerLoading(false);
  }

  function retry() {
    if (selectedId) void mint(selectedId);
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await post(`/encounters/${encounterId}/documents`, {
        doc_type: docType,
        storage_key: storageKey,
      });
      setStorageKey("");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const viewerStatus = !selectedDoc
    ? null
    : viewerLoading
      ? "loading"
      : viewerError
        ? "error"
        : signedUrl
          ? "ready"
          : "loading";

  return (
    <Card title="Documents">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {docs.length === 0 ? (
        <EmptyState title="No documents referenced" />
      ) : (
        <Table
          caption="Document references"
          columns={
            <>
              <Th>Type</Th>
              <Th>Reference</Th>
              <Th>Notes</Th>
              <Th>Image</Th>
            </>
          }
        >
          {docs.map((d) => {
            const viewable = isEligibleImageDoc(d);
            return (
              <tr key={d.id}>
                <Td>{d.doc_type}</Td>
                <Td numeric>{d.storage_key}</Td>
                <Td>{d.notes ?? "-"}</Td>
                <Td>
                  {viewable ? (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        const idx = eligible.findIndex((e) => e.id === d.id);
                        if (idx >= 0) openAt(idx);
                      }}
                      aria-label={`View image ${d.doc_type} reference ending ${d.id.slice(-4)}`}
                    >
                      View
                    </Button>
                  ) : (
                    <span className="hos-helper">Not an image</span>
                  )}
                </Td>
              </tr>
            );
          })}
        </Table>
      )}
      <h3>Clinical images</h3>
      {eligible.length === 0 ? (
        <EmptyState title="No eligible images">
          Only documents with an image content type can be viewed here.
        </EmptyState>
      ) : selectedDoc && viewerStatus ? (
        <div>
          <p style={{ display: "flex", gap: "var(--hos-space-2)", flexWrap: "wrap" }}>
            <Button variant="secondary" onClick={closeViewer} id="docs-viewer-back">
              Back to document list
            </Button>
            {eligible.length > 1 ? (
              <>
                <Button
                  variant="secondary"
                  onClick={() =>
                    openAt((selectedIndex - 1 + eligible.length) % eligible.length)
                  }
                  disabled={viewerLoading}
                  aria-label={`Previous image (${selectedIndex + 1} of ${eligible.length})`}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => openAt((selectedIndex + 1) % eligible.length)}
                  disabled={viewerLoading}
                  aria-label={`Next image (${selectedIndex + 1} of ${eligible.length})`}
                >
                  Next
                </Button>
              </>
            ) : null}
          </p>
          <p className="hos-helper" role="status">
            Image {selectedIndex + 1} of {eligible.length}: {selectedDoc.doc_type}{" "}
            reference ending {selectedDoc.id.slice(-4)}. A fresh access link is
            minted on open and remains usable for 5 minutes; if it expires,
            retry mints a new one.
          </p>
          <ClinicalImageViewer
            label="Clinical image viewer"
            status={viewerStatus}
            errorMessage={viewerError || undefined}
            onRetry={retry}
            image={
              signedUrl && !viewerError
                ? {
                    src: signedUrl,
                    title: `Image ${selectedDoc.doc_type} (${selectedDoc.id.slice(0, 8)})`,
                    subtitle: `Image ${selectedIndex + 1} of ${eligible.length}`,
                    meta: [
                      { label: "Type", value: selectedDoc.doc_type },
                      { label: "Content type", value: selectedDoc.content_type ?? "unknown" },
                    ],
                  }
                : null
            }
          />
        </div>
      ) : (
        <p className="hos-helper">
          Select View on an eligible image row to load it here. A fresh access
          link is minted when the image opens.
        </p>
      )}
      <h3>Reference a document</h3>
      <p className="hos-helper">
        Only stored-object references are recorded here - file upload and signed
        download URLs are not available in this release. Image viewing uses a
        separate authorized access grant and never exposes storage keys.
      </p>
      <form onSubmit={create}>
        <Field label="Type" htmlFor="doc-type" required>
          {() => (
            <Select
              id="doc-type"
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              required
              options={["xray", "scan", "photo", "report", "other"].map((t) => ({
                value: t,
                label: t,
              }))}
            />
          )}
        </Field>
        <Field label="Storage key" htmlFor="doc-key" required>
          {() => (
            <Input id="doc-key" value={storageKey} onChange={(e) => setStorageKey(e.target.value)} required />
          )}
        </Field>
        <p>
          <Button type="submit">Add reference</Button>
        </p>
      </form>
    </Card>
  );
}
