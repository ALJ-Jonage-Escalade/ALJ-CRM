/* What the Paramètres page shows for each server answer (texts of the former web/bureau/parametres.html). */
import type { BadgeColor } from "../../components/ui/palette";
import type { Schemas } from "../../lib/client";
import { formatDateTime, formatDateTimeSeconds, formatTime, parseDate } from "../../lib/format";

export interface Status {
  color: BadgeColor;
  label: string;
  text: string;
}

export const CHECKING: Status = { color: "slate", label: "Vérification…", text: "" };
export const UNAVAILABLE: Status = { color: "slate", label: "Indisponible", text: "" };

export function googleStatus(google: Schemas["GoogleStatus"]): Status {
  if (google.status === "connected") {
    return {
      color: "green",
      label: "🟢 Connecté & Opérationnel",
      text: "Le jeton Google OAuth2 est valide. L'accès à la BDD et aux envois d'e-mails est pleinement fonctionnel.",
    };
  }
  if (google.status === "expired") {
    return {
      color: "red",
      label: "🔴 Jeton expiré ou révoqué",
      text: "Le jeton de connexion Google a expiré. Cliquez sur « Renouveler la connexion Google » pour rétablir les accès.",
    };
  }
  return { color: "amber", label: "🟡 Non connecté", text: "Aucun jeton Google n'est configuré. Connectez le compte de l'association." };
}

export interface CheckLine {
  ok: boolean;
  label: string;
  message: string;
}

export function googleChecks(test: Schemas["GoogleTest"]): CheckLine[] {
  const { oauth_token, database, gmail } = test.results;
  return [
    { ok: oauth_token.ok, label: "Jeton Google OAuth2", message: oauth_token.message },
    { ok: database.ok, label: "Base de Données", message: database.message },
    { ok: gmail.ok, label: "Service Gmail API", message: gmail.message },
  ];
}

export function cacheStatus(status: Schemas["CloudDbStatus"]): Status {
  if (status.db_exists) {
    return {
      color: "green",
      label: "🟢 Cache opérationnel",
      text: "Le cache SQLite du serveur est initialisé et actif pour les requêtes rapides et les exports.",
    };
  }
  return {
    color: "amber",
    label: "🟡 Cache non trouvé",
    text: "Le cache SQLite du serveur n'est pas encore créé. Lancez une synchronisation.",
  };
}

export function cacheFileText(status: Schemas["CloudDbStatus"]): string {
  return status.db_exists
    ? `${status.db_filename || "database.db"} (${status.db_size_kb} Ko · ${status.member_count} adhérents)`
    : "Non initialisé";
}

export function pendingText(pending: number): string {
  return pending > 0 ? `⏳ ${pending} en attente` : "0 (à jour)";
}

/** Last cache sync (Unix time in seconds; 0 or null: never). */
export function lastSyncText(seconds: number | null | undefined): string {
  return seconds ? formatDateTimeSeconds(new Date(seconds * 1000)) : "Non renseignée";
}

/** Last run of the results batch (ISO date written by the server; shown as is when it is not one). */
export function lastRunText(iso: string): string {
  if (!iso) {
    return "Jamais exécuté";
  }
  const date = parseDate(iso);
  return date ? formatDateTime(date) : iso;
}

export function timeNow(now: Date = new Date()): string {
  return formatTime(now);
}

export function syncReport(report: Schemas["SyncCounters"] | null | undefined, now?: Date): string[] {
  return [
    `🟢 Synchronisation réussie à ${timeNow(now)}${report?.full ? " (reconstruction complète)" : ""}`,
    `• Documents reçus depuis Firestore : ${report?.pulled ?? 0}`,
    `• Modifications envoyées à Firestore : ${report?.pushed ?? 0}`,
  ];
}

export function batchReport(batch: Schemas["BatchReport"], now?: Date): string[] {
  const email = batch.email_sent
    ? `Oui (à ${batch.notification_email})`
    : batch.competitions_updated > 0
      ? "Erreur envoi"
      : "Non (aucun nouveau résultat)";
  return [
    `🟢 Analyse MyCompet terminée à ${timeNow(now)}`,
    `• Compétitions passées vérifiées : ${batch.competitions_checked}`,
    `• Résultats officiels trouvés : ${batch.competitions_updated}`,
    `• E-mail récapitulatif expédié : ${email}`,
    ...(batch.partial ? [`⏱️ Temps imparti écoulé : ${batch.competitions_remaining} compétition(s) reportée(s) au prochain passage`] : []),
    ...batch.details.map((c) => DETAIL_LINES[c.status](c)),
  ];
}

const DETAIL_LINES: Record<Schemas["BatchCompetition"]["status"], (c: Schemas["BatchCompetition"]) => string> = {
  found: (c) => `🏆 ${c.nom} : ${c.athletes.length} athlète(s) classé(s) pour le club`,
  pending: (c) => `⏳ ${c.nom} : pas encore de résultats publiés`,
  needs_url: (c) => `✍️ ${c.nom} : une page de même nom existe, mais pas à cette date : URL à saisir sur la fiche`,
  error: (c) => `⚠️ ${c.nom} : résultats illisibles ou non enregistrés pour le moment (nouvel essai au prochain passage)`,
};
