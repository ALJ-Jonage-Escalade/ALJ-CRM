/* What the Paramètres page shows for each server answer (texts of the former web/bureau/parametres.html). */
import type { Tone } from "../../components/ui/UiBadge.vue";
import type { Schemas } from "../../lib/client";

export interface Status {
  tone: Tone;
  label: string;
  text: string;
}

export const CHECKING: Status = { tone: "neutral", label: "Vérification…", text: "" };
export const UNAVAILABLE: Status = { tone: "neutral", label: "Indisponible", text: "" };

export function googleStatus(s: Schemas["GoogleStatus"]): Status {
  if (s.status === "connected") {
    return {
      tone: "success",
      label: "🟢 Connecté & Opérationnel",
      text: "Le jeton Google OAuth2 est valide. L'accès à la BDD et aux envois d'e-mails est pleinement fonctionnel.",
    };
  }
  if (s.status === "expired") {
    return {
      tone: "danger",
      label: "🔴 Jeton expiré ou révoqué",
      text: "Le jeton de connexion Google a expiré. Cliquez sur « Renouveler la connexion Google » pour rétablir les accès.",
    };
  }
  return { tone: "warning", label: "🟡 Non connecté", text: "Aucun jeton Google n'est configuré. Connectez le compte de l'association." };
}

export function dbMode(s: Schemas["GoogleStatus"]): string {
  return s.backend === "drive" ? "Google Drive (mode secours)" : "Firestore (Google Cloud)";
}

export interface CheckLine {
  ok: boolean;
  label: string;
  message: string;
}

export function googleChecks(t: Schemas["GoogleTest"]): CheckLine[] {
  const { oauth_token, database, gmail } = t.results;
  return [
    { ok: oauth_token.ok, label: "Jeton OAuth2", message: oauth_token.message },
    { ok: database.ok, label: "Base de Données", message: database.message },
    { ok: gmail.ok, label: "Service Gmail API", message: gmail.message },
  ];
}

export function cacheStatus(s: Schemas["CloudDbStatus"]): Status {
  if (s.db_exists) {
    return { tone: "success", label: "🟢 Cache opérationnel", text: "Le cache SQLite du serveur est initialisé et actif pour les requêtes rapides et les exports." };
  }
  return { tone: "warning", label: "🟡 Cache non trouvé", text: "Le cache SQLite du serveur n'est pas encore créé. Lancez une synchronisation." };
}

export function cacheFile(s: Schemas["CloudDbStatus"]): string {
  return s.db_exists ? `${s.db_filename || "database.db"} (${s.db_size_kb} Ko · ${s.member_count} adhérents)` : "Non initialisé";
}

export function pendingText(pending: number): string {
  return pending > 0 ? `⏳ ${pending} en attente` : "0 (à jour)";
}

const DATE_TIME = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "medium" });
const DATE_TIME_SHORT = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
const TIME = new Intl.DateTimeFormat("fr-FR", { timeStyle: "medium" });

/** Last cache sync (Unix time in seconds; 0 or null: never). */
export function lastSync(seconds: number | null | undefined): string {
  return seconds ? DATE_TIME.format(new Date(seconds * 1000)) : "Non renseignée";
}

/** Last run of the results batch (ISO date written by the server; shown as is when it is not one). */
export function lastRun(iso: string): string {
  if (!iso) return "Jamais exécuté";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE_TIME_SHORT.format(date);
}

export function timeNow(now: Date = new Date()): string {
  return TIME.format(now);
}

export function syncReport(r: Schemas["SyncCounters"] | null | undefined, now?: Date): string[] {
  return [
    `🟢 Synchronisation réussie à ${timeNow(now)}${r?.full ? " (reconstruction complète)" : ""}`,
    `• Documents reçus depuis Firestore : ${r?.pulled ?? 0}`,
    `• Modifications envoyées à Firestore : ${r?.pushed ?? 0}`,
  ];
}

export function batchReport(b: Schemas["BatchReport"], now?: Date): string[] {
  const email = b.email_sent
    ? `Oui (à ${b.notification_email})`
    : b.competitions_updated > 0 ? "Erreur envoi" : "Non (aucun nouveau résultat)";
  return [
    `🟢 Analyse MyCompet terminée à ${timeNow(now)}`,
    `• Compétitions passées vérifiées : ${b.competitions_checked}`,
    `• Résultats officiels trouvés : ${b.competitions_updated}`,
    `• E-mail récapitulatif expédié : ${email}`,
    ...b.details.map((c) =>
      c.status === "found" ? `🏆 ${c.nom} : ${c.athletes.length} athlète(s) classé(s) pour le club` : `⏳ ${c.nom} : pas encore de résultats publiés`),
  ];
}

/** Rough check before asking the server, which checks again. */
export function looksLikeEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}
