import { describe, expect, it } from "vitest";
import {
  accessRole,
  accessStatus,
  actionLabel,
  addFormError,
  authorLabel,
  emailNotSent,
  invitationMessage,
  isOwnEntry,
  lastSignInText,
  roleChange,
  statusLabel,
  type AccessEntry,
} from "./access";

describe("Accès view", () => {
  it("writes the role change of a history entry", () => {
    expect(roleChange({ action: "role_changed", old_role: "coach", new_role: "admin" })).toBe("Coach → Administrateur");
    expect(roleChange({ action: "added", old_role: null, new_role: "readonly" })).toBe("→ Lecture seule");
    expect(roleChange({ action: "removed", old_role: "coach", new_role: null })).toBe("Coach →");
    expect(roleChange({ action: "name_changed", old_role: "coach", new_role: "coach" })).toBe("");
    expect(roleChange({ action: "invitation_resent", old_role: "coach", new_role: "coach" })).toBe("Coach → Coach");
  });

  it("names the actions and the bootstrap author", () => {
    expect(actionLabel("invited")).toBe("Invitation");
    expect(actionLabel("invitation_resent")).toBe("Invitation renvoyée");
    expect(authorLabel("bootstrap")).toBe("Démarrage du serveur");
    expect(authorLabel("albus@alj.example")).toBe("albus@alj.example");
  });

  it("shows the last sign-in date, or never", () => {
    expect(lastSignInText("2026-10-30T09:15:00+00:00")).toBe("30/10/2026");
    expect(lastSignInText(null)).toBe("Jamais");
  });

  it("tells an access in use from an open or expired invitation", () => {
    const now = new Date("2026-11-01T12:00:00Z");
    expect(accessStatus({ invitation_expires_at: null }, now)).toBe("active");
    expect(accessStatus({ invitation_expires_at: "2026-11-06T09:00:00+00:00" }, now)).toBe("invited");
    expect(accessStatus({ invitation_expires_at: "2026-11-01T09:00:00+00:00" }, now)).toBe("expired");
    expect(statusLabel({ invitation_expires_at: null }, now)).toBe("Actif");
    expect(statusLabel({ invitation_expires_at: "2026-11-06T09:00:00+00:00" }, now)).toBe("Invité · expire le 06/11/2026");
    expect(statusLabel({ invitation_expires_at: "2026-11-01T09:00:00+00:00" }, now)).toBe("Invitation expirée le 01/11/2026");
  });

  it("flags an invitation whose e-mail did not go out", () => {
    expect(emailNotSent({ invitation_expires_at: "2026-11-06T09:00:00+00:00", invitation_sent_at: null })).toBe(true);
    expect(emailNotSent({ invitation_expires_at: "2026-11-06T09:00:00+00:00", invitation_sent_at: "2026-10-30T09:00:00+00:00" })).toBe(
      false,
    );
    expect(emailNotSent({ invitation_expires_at: null, invitation_sent_at: null })).toBe(false);
  });

  it("says whether the invitation e-mail went out", () => {
    const entry: AccessEntry = {
      email: "neville@alj.example",
      role: "coach",
      display_name: "",
      last_sign_in_at: null,
      created_at: null,
      created_by: null,
      updated_at: null,
      updated_by: null,
      invited_at: "2026-10-30T09:00:00+00:00",
      invitation_expires_at: "2026-11-06T09:00:00+00:00",
      invitation_sent_at: null,
      accepted_at: null,
    };
    expect(invitationMessage({ entry, email_sent: true, email_error: null })).toContain("Invitation envoyée");
    const failed = invitationMessage({ entry, email_sent: false, email_error: "quota" });
    expect(failed).toContain("n'a pas pu être envoyé : quota");
    expect(failed).toContain("Renvoyer");
  });

  it("checks the address of the invite form", () => {
    expect(addFormError("  ")).toContain("Saisissez");
    expect(addFormError("pas-une-adresse")).toBe("Adresse e-mail invalide.");
    expect(addFormError(" neville@alj.example ")).toBe("");
  });

  it("recognises the signed-in admin's own entry and the role values", () => {
    expect(isOwnEntry("albus@alj.example", " Albus@ALJ.example")).toBe(true);
    expect(isOwnEntry("severus@alj.example", "albus@alj.example")).toBe(false);
    expect(accessRole("coach")).toBe("coach");
    expect(accessRole("owner")).toBeNull();
  });
});
