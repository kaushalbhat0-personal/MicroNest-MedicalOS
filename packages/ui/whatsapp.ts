/**
 * User-initiated WhatsApp click-to-chat URL helpers.
 * Mirrors backend ``app.modules.communications.whatsapp`` rules.
 * Never sends messages. Never claims delivery.
 */

const DIGITS = /\D+/g;

export class WhatsAppPhoneError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WhatsAppPhoneError";
  }
}

/** Digits-only international number for wa.me. */
export function normalizeWhatsAppNumber(phone: string | null | undefined): string {
  const raw = (phone || "").trim();
  if (!raw) throw new WhatsAppPhoneError("phone number required");
  const digits = raw.replace(DIGITS, "");
  if (digits.length < 7 || digits.length > 15) {
    throw new WhatsAppPhoneError("invalid phone number for WhatsApp");
  }
  if (!/^\d+$/.test(digits)) {
    throw new WhatsAppPhoneError("invalid phone number for WhatsApp");
  }
  return digits;
}

export function isValidWhatsAppPhone(phone: string | null | undefined): boolean {
  try {
    normalizeWhatsAppNumber(phone);
    return true;
  } catch {
    return false;
  }
}

/**
 * Build ``https://wa.me/<digits>?text=…`` or ``https://wa.me/?text=…`` when
 * phone is omitted (user picks a contact in WhatsApp).
 */
export function buildWhatsAppUrl(opts: {
  phone?: string | null;
  message?: string | null;
  /** Allow opening without a destination number. */
  allowMissingPhone?: boolean;
}): string {
  const text = (opts.message || "").trim();
  if (text.length > 500) {
    throw new WhatsAppPhoneError("WhatsApp prefill message too long");
  }
  const phone = (opts.phone || "").trim();
  let base: string;
  if (!phone) {
    if (!opts.allowMissingPhone) {
      throw new WhatsAppPhoneError("phone number required");
    }
    base = "https://wa.me/";
  } else {
    base = `https://wa.me/${normalizeWhatsAppNumber(phone)}`;
  }
  if (!text) return base.endsWith("/") ? "https://wa.me/" : base;
  return `${base}?text=${encodeURIComponent(text)}`;
}
