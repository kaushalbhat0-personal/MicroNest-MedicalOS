import { api } from "@/lib/api";

/**
 * Encounter document reference as returned by
 * `GET /api/v1/tenants/{tenant_id}/encounters/{encounter_id}/documents`.
 * Shape mirrors backend `DocumentRefResponse`: metadata only, no signed URLs.
 */
export type EncounterDocumentRef = {
  id: string;
  tenant_id?: string;
  encounter_id?: string;
  doc_type: string;
  storage_key?: string;
  content_type: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  notes: string | null;
  created_at?: string;
};

/**
 * Authorized access grant from
 * `POST /api/v1/tenants/{tenant_id}/documents/{document_id}/access`.
 * Carries a short-lived signed URL only — never a storage key or credentials.
 */
export type DocumentAccess = {
  document_id: string;
  url: string;
  expires_in_seconds: number;
  content_type: string | null;
};

/**
 * Trusted image eligibility. Uses only the persisted `content_type`
 * (server rule: `image/` prefix, case-insensitive). Never guesses from
 * `doc_type`, filenames, or labels: untyped documents are ineligible and the
 * access endpoint returns 422 for them.
 */
export function isEligibleImageDoc(doc: {
  content_type?: string | null;
}): boolean {
  return (doc.content_type ?? "").trim().toLowerCase().startsWith("image/");
}

/**
 * Mint a fresh signed URL for one eligible image reference.
 *
 * Sends only the opaque document id in the path with an empty body: no
 * storage key, no client-controlled expiry, no query parameters. The signed
 * URL is returned for in-memory viewer use only — callers must not persist
 * it (no browser storage, no route/query state) and must not log it.
 */
export function requestDocumentAccess(
  tenantId: string,
  documentId: string,
): Promise<DocumentAccess> {
  const tenant = (tenantId ?? "").trim();
  const docId = (documentId ?? "").trim();
  if (!tenant) throw new Error("tenant is required");
  if (!docId) throw new Error("document is required");
  return api.post<DocumentAccess>(
    `/api/v1/tenants/${tenant}/documents/${docId}/access`,
    {},
    tenant,
  );
}

/**
 * Non-PHI failure summary for the viewer. Maps HTTP status to a generic
 * message; never includes URLs, storage keys, or clinical content.
 */
export function documentAccessErrorMessage(status?: number): string {
  if (status === 403) return "You do not have permission to view this image.";
  if (status === 404) return "This image is no longer available.";
  if (status === 422) return "This document is not an eligible image.";
  if (status === 503)
    return "Image storage is temporarily unavailable. Try again.";
  return "The image could not be loaded. Try again.";
}
