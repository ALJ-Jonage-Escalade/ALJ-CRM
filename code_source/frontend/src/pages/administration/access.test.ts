import { describe, expect, it } from "vitest";
import { accessRole, actionLabel, addFormError, authorLabel, isOwnEntry, lastSignIn, roleChange } from "./access";

describe("Accès view", () => {
  it("writes the role change of a history entry", () => {
    expect(roleChange({ action: "role_changed", old_role: "coach", new_role: "admin" })).toBe("Coach → Administrateur");
    expect(roleChange({ action: "added", old_role: null, new_role: "readonly" })).toBe("→ Lecture seule");
    expect(roleChange({ action: "removed", old_role: "coach", new_role: null })).toBe("Coach →");
    expect(roleChange({ action: "name_changed", old_role: "coach", new_role: "coach" })).toBe("");
    expect(roleChange({ action: "request_dismissed", old_role: null, new_role: null })).toBe("");
  });

  it("names the actions and the bootstrap author", () => {
    expect(actionLabel("request_granted")).toBe("Demande acceptée");
    expect(authorLabel("bootstrap")).toBe("Démarrage du serveur");
    expect(authorLabel("albus@alj.example")).toBe("albus@alj.example");
  });

  it("shows the last sign-in date, or never", () => {
    expect(lastSignIn("2026-10-30T09:15:00+00:00")).toBe("30/10/2026");
    expect(lastSignIn(null)).toBe("Jamais");
  });

  it("checks the address of the add form", () => {
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
