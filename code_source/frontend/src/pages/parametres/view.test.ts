import { describe, expect, it } from "vitest";
import type { Schemas } from "../../lib/client";
import { batchReport, cacheFile, googleChecks, googleStatus, lastRun, lastSync, pendingText, syncReport } from "./view";

const GOOGLE: Schemas["GoogleStatus"] = {
  status: "disconnected",
  valid: false,
  configured: false,
  client_id_configured: false,
  refresh_token_present: false,
  user_email: null,
  backend: "firestore",
  db_accessible: false,
  error: "",
};
const CACHE: Schemas["CloudDbStatus"] = {
  status: "success",
  enabled: true,
  db_exists: true,
  db_filename: "database.db",
  db_size_kb: 812.5,
  member_count: 42,
  pending: 0,
  last_error: "",
  last_sync: 0,
};
const AT = new Date(2026, 9, 22, 7, 5, 9);

describe("Paramètres view", () => {
  it.each([
    ["connected", "green", "🟢 Connecté & Opérationnel"],
    ["expired", "red", "🔴 Jeton expiré ou révoqué"],
    ["disconnected", "amber", "🟡 Non connecté"],
  ] as const)("Google %s", (status, color, label) => {
    expect(googleStatus({ ...GOOGLE, status })).toMatchObject({ color, label });
  });

  it("lists the three Google checks", () => {
    const check = (ok: boolean, message: string) => ({ ok, message });
    const lines = googleChecks({
      status: "warning",
      all_ok: false,
      results: { oauth_token: check(true, "a"), database: check(true, "b"), gmail: check(false, "c") },
    });
    expect(lines.map((l) => [l.ok, l.label, l.message])).toEqual([
      [true, "Jeton OAuth2", "a"],
      [true, "Base de Données", "b"],
      [false, "Service Gmail API", "c"],
    ]);
  });

  it("describes the server cache", () => {
    expect(cacheFile(CACHE)).toBe("database.db (812.5 Ko · 42 adhérents)");
    expect(cacheFile({ ...CACHE, db_exists: false })).toBe("Non initialisé");
    expect(pendingText(0)).toBe("0 (à jour)");
    expect(pendingText(3)).toBe("⏳ 3 en attente");
  });

  it("formats dates in French", () => {
    expect(lastSync(0)).toBe("Non renseignée");
    expect(lastSync(null)).toBe("Non renseignée");
    expect(lastSync(AT.getTime() / 1000)).toBe("22/10/2026 07:05:09");
    expect(lastRun("")).toBe("Jamais exécuté");
    expect(lastRun("2026-10-22T07:05:09.123")).toBe("22/10/2026 07:05");
    expect(lastRun("hier")).toBe("hier");
  });

  it("reports a sync", () => {
    expect(syncReport({ pulled: 5, pushed: 1, full: true }, AT)).toEqual([
      "🟢 Synchronisation réussie à 07:05:09 (reconstruction complète)",
      "• Documents reçus depuis Firestore : 5",
      "• Modifications envoyées à Firestore : 1",
    ]);
    expect(syncReport({ pulled: 0, pushed: 0, full: false }, AT)[0]).toBe("🟢 Synchronisation réussie à 07:05:09");
  });

  it("reports a results batch", () => {
    const comp = (nom: string, status: "found" | "pending", athletes: number) => ({
      id: nom,
      nom,
      date: "",
      lieu: "",
      url: "",
      status,
      athletes: Array.from({ length: athletes }, () => ({})),
    });
    const report: Schemas["BatchReport"] = {
      status: "success",
      executed_at: "",
      competitions_checked: 2,
      competitions_updated: 1,
      email_sent: true,
      notification_email: "n@x.fr",
      details: [comp("Open de Lyon", "found", 3), comp("Coupe", "pending", 0)],
    };
    expect(batchReport(report, AT)).toEqual([
      "🟢 Analyse MyCompet terminée à 07:05:09",
      "• Compétitions passées vérifiées : 2",
      "• Résultats officiels trouvés : 1",
      "• E-mail récapitulatif expédié : Oui (à n@x.fr)",
      "🏆 Open de Lyon : 3 athlète(s) classé(s) pour le club",
      "⏳ Coupe : pas encore de résultats publiés",
    ]);
    expect(batchReport({ ...report, email_sent: false }, AT)[3]).toBe("• E-mail récapitulatif expédié : Erreur envoi");
    expect(batchReport({ ...report, email_sent: false, competitions_updated: 0 }, AT)[3]).toBe(
      "• E-mail récapitulatif expédié : Non (aucun nouveau résultat)",
    );
  });
});
