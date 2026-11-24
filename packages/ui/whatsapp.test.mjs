import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildWhatsAppUrl,
  isValidWhatsAppPhone,
  normalizeWhatsAppNumber,
} from "./whatsapp.ts";

describe("normalizeWhatsAppNumber", () => {
  it("strips formatting", () => {
    assert.equal(normalizeWhatsAppNumber("+91 98765-43210"), "919876543210");
  });
  it("rejects short values", () => {
    assert.throws(() => normalizeWhatsAppNumber("123"));
  });
});

describe("buildWhatsAppUrl", () => {
  it("encodes message text", () => {
    const url = buildWhatsAppUrl({ phone: "+919876543210", message: "Hello clinic" });
    assert.ok(url.startsWith("https://wa.me/919876543210?text="));
    assert.ok(url.includes(encodeURIComponent("Hello clinic")));
  });
  it("allows missing phone when opted in", () => {
    const url = buildWhatsAppUrl({
      phone: "",
      message: "Invite link",
      allowMissingPhone: true,
    });
    assert.equal(url, `https://wa.me/?text=${encodeURIComponent("Invite link")}`);
  });
  it("rejects missing phone by default", () => {
    assert.throws(() => buildWhatsAppUrl({ phone: "", message: "x" }));
  });
});

describe("isValidWhatsAppPhone", () => {
  it("returns false for empty", () => {
    assert.equal(isValidWhatsAppPhone(""), false);
  });
  it("returns true for E.164-like", () => {
    assert.equal(isValidWhatsAppPhone("+919876543210"), true);
  });
});
