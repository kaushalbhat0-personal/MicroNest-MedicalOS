/**
 * Absolute share URLs for onboarding handoff.
 * Tokens must come from the server; this only joins origin + path.
 * Never log the returned URL when it embeds a secret token.
 */

export function appOrigin(): string {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return "";
}

/** Staff / practitioner invitation accept URL (token from API). */
export function staffInviteShareUrl(token: string): string {
  const origin = appOrigin();
  const path = `/invite?token=${encodeURIComponent(token)}`;
  return origin ? `${origin}${path}` : path;
}

/**
 * Patient portal activation is via public password-reset (no enrollment token
 * is returned by the API). Share the page + email instructions only.
 */
export function portalActivationShareUrl(): string {
  const origin = appOrigin();
  const path = "/password-reset";
  return origin ? `${origin}${path}` : path;
}

export function portalHomeShareUrl(): string {
  const origin = appOrigin();
  const path = "/portal";
  return origin ? `${origin}${path}` : path;
}

export function staffInviteMessage(opts: {
  clinicName?: string;
  inviteUrl: string;
  expiresAt?: string | null;
}): string {
  const clinic = (opts.clinicName || "your clinic").trim() || "your clinic";
  const expiry = opts.expiresAt
    ? ` This invitation expires ${new Date(opts.expiresAt).toLocaleString()}.`
    : " This invitation expires; ask for a new one if needed.";
  return (
    `You're invited to join ${clinic} on Healthcare OS. ` +
    `Open this link to accept (do not forward): ${opts.inviteUrl}.${expiry}`
  ).slice(0, 500);
}

export function portalEnrollMessage(opts: {
  clinicName?: string;
  email: string;
  resetUrl: string;
  portalUrl: string;
}): string {
  const clinic = (opts.clinicName || "your clinic").trim() || "your clinic";
  return (
    `${clinic} enrolled you for the patient portal on Healthcare OS. ` +
    `Use email ${opts.email}. Set your password here: ${opts.resetUrl} ` +
    `then sign in at ${opts.portalUrl}. No clinical details are included in this message.`
  ).slice(0, 500);
}
