"use client";

import * as React from "react";
import { Button } from "./Button";
import { Alert } from "./feedback";
import { Checkbox, Field, HelperText, Input, Textarea } from "./fields";
import { buildWhatsAppUrl, isValidWhatsAppPhone } from "./whatsapp";

export type WhatsAppShareActionProps = {
  /** Short heading shown above the controls */
  title?: string;
  /** Context line (e.g. “Staff invitation”). Never include PHI. */
  contextLabel?: string;
  /** Prefill destination; user may edit. */
  initialPhone?: string | null;
  /** Prefill message; must already include any server-issued link. Max 500. */
  initialMessage: string;
  /** Absolute URL copied by “Copy link”. Parent supplies server-generated link. */
  linkToCopy: string;
  /** Optional async override (e.g. consent-gated patient API). */
  resolveOpenUrl?: (args: { phone: string; message: string }) => Promise<string>;
  requireConfirm?: boolean;
  confirmLabel?: string;
  disabled?: boolean;
  onOpened?: () => void;
  onCopied?: () => void;
};

/**
 * Reusable WhatsApp-assisted sharing for onboarding links.
 * Opens wa.me with a prefilled message — does not send automatically.
 */
export function WhatsAppShareAction({
  title = "Share via WhatsApp",
  contextLabel,
  initialPhone = "",
  initialMessage,
  linkToCopy,
  resolveOpenUrl,
  requireConfirm = true,
  confirmLabel = "I understand this opens WhatsApp. The message is not sent automatically.",
  disabled = false,
  onOpened,
  onCopied,
}: WhatsAppShareActionProps) {
  const phoneId = React.useId();
  const messageId = React.useId();
  const [phone, setPhone] = React.useState((initialPhone || "").trim());
  const [message, setMessage] = React.useState(initialMessage.slice(0, 500));
  const [confirmed, setConfirmed] = React.useState(!requireConfirm);
  const [busy, setBusy] = React.useState(false);
  const [copyState, setCopyState] = React.useState<"idle" | "copied" | "failed">("idle");
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    setPhone((initialPhone || "").trim());
  }, [initialPhone]);

  React.useEffect(() => {
    setMessage(initialMessage.slice(0, 500));
  }, [initialMessage]);

  const phoneOk = !phone.trim() || isValidWhatsAppPhone(phone);
  const phoneHint = !phone.trim()
    ? "No number yet — WhatsApp will ask you to pick a contact."
    : phoneOk
      ? "Digits with country code preferred (e.g. +9198…)."
      : "Enter a valid international phone, or clear the field to pick a contact in WhatsApp.";

  const canOpen =
    !disabled && confirmed && message.trim().length > 0 && message.trim().length <= 500 && phoneOk;

  async function openWhatsApp() {
    setError("");
    if (!canOpen) return;
    setBusy(true);
    try {
      let url: string;
      if (resolveOpenUrl) {
        url = await resolveOpenUrl({ phone: phone.trim(), message: message.trim() });
      } else {
        url = buildWhatsAppUrl({
          phone: phone.trim() || null,
          message: message.trim(),
          allowMissingPhone: true,
        });
      }
      window.open(url, "_blank", "noopener,noreferrer");
      onOpened?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open WhatsApp.");
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    setError("");
    setCopyState("idle");
    if (!linkToCopy) {
      setError("No link available to copy.");
      setCopyState("failed");
      return;
    }
    try {
      await navigator.clipboard.writeText(linkToCopy);
      setCopyState("copied");
      onCopied?.();
    } catch {
      setCopyState("failed");
      setError("Clipboard unavailable. Select and copy the link from the message instead.");
    }
  }

  return (
    <div className="hos-whatsapp-share" data-testid="whatsapp-share-action">
      <p className="hos-label" id={`${phoneId}-title`}>
        {title}
      </p>
      {contextLabel ? <HelperText>{contextLabel}</HelperText> : null}
      <Alert tone="info" title="Not sent automatically">
        Opening WhatsApp prepares a chat with your message. You still choose the contact and tap
        send in WhatsApp. This product never sends WhatsApp messages by itself.
      </Alert>

      {error ? (
        <Alert tone="danger" title="Could not continue">
          {error}
        </Alert>
      ) : null}

      <Field
        label="Recipient phone (optional)"
        htmlFor={phoneId}
        description={phoneHint}
      >
        {({ describedBy }) => (
          <Input
            id={phoneId}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={disabled || busy}
            aria-invalid={phoneOk ? undefined : true}
            aria-describedby={describedBy}
            placeholder="+91…"
          />
        )}
      </Field>

      <Field
        label="Message"
        htmlFor={messageId}
        required
        description={`${message.length}/500 · Keep clinical details out of this message.`}
      >
        {({ describedBy }) => (
          <Textarea
            id={messageId}
            value={message}
            onChange={(e) => setMessage(e.target.value.slice(0, 500))}
            required
            rows={5}
            disabled={disabled || busy}
            aria-describedby={describedBy}
          />
        )}
      </Field>

      {requireConfirm ? (
        <Checkbox
          label={confirmLabel}
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          disabled={disabled || busy}
        />
      ) : null}

      <div className="hos-quick-actions">
        <Button type="button" onClick={() => void openWhatsApp()} disabled={!canOpen} loading={busy}>
          Open in WhatsApp
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => void copyLink()}
          disabled={disabled || busy || !linkToCopy}
        >
          Copy link
        </Button>
      </div>
      {copyState === "copied" ? (
        <p className="hos-helper" role="status">
          Link copied. Share it only with the intended recipient.
        </p>
      ) : null}
    </div>
  );
}
