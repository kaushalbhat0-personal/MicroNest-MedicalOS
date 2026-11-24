import { describe, expect, it } from "vitest";
import { portalEnrollMessage, staffInviteMessage } from "./shareLinks";

describe("shareLinks messages", () => {
  it("keeps staff invite under 500 chars and includes url", () => {
    const url = "http://localhost:3000/invite?token=abc";
    const msg = staffInviteMessage({ clinicName: "P34 Clinic", inviteUrl: url });
    expect(msg.length).toBeLessThanOrEqual(500);
    expect(msg).toContain(url);
    expect(msg.toLowerCase()).not.toContain("diagnosis");
  });

  it("portal enroll message has no clinical content", () => {
    const msg = portalEnrollMessage({
      clinicName: "P34 Clinic",
      email: "p34.patient@example.com",
      resetUrl: "http://localhost:3000/password-reset",
      portalUrl: "http://localhost:3000/portal",
    });
    expect(msg).toContain("p34.patient@example.com");
    expect(msg).toContain("/password-reset");
    expect(msg.toLowerCase()).not.toMatch(/soap|diagnosis|tooth|caries/);
  });
});
