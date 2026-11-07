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

export function googleStatus(s: Schemas["GoogleStatus"]): Status {
  if (s.status === "connected") {
    return {
      color: "green",
      label: "🟢 Connecté & Opérationnel",
      text: "Le jeton Google OAuth2 est valide. L'accès à la BDD et aux envois d'e-mails est pleinement fonctionnel.",
    };
  }
  if (s.status === "expired") {
    return {
      color: "red",
      label: "🔴 Jeton expiré ou révoqué",
      text: "Le jeton de connexion Google a expiré. Cliquez sur « Renouveler la connexion Google » pour rétablir les accès.",
    };
  }
  return { color: "amber", label: "🟡 Non connecté", text: "Aucun jeton Google n'est configuré. Connectez le compte de l'association." };
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
    { ok: oauth_token.ok, label: "Jeton Google OAuth2", message: oauth_token.message },
    { ok: database.ok, label: "Base de Données", message: database.message },
    { ok: gmail.ok, label: "Service Gmail API", message: gmail.message },
  ];
}

export function cacheStatus(s: Schemas["CloudDbStatus"]): Status {
  if (s.db_exists) {
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

export function cacheFile(s: Schemas["CloudDbStatus"]): string {
  return s.db_exists ? `${s.db_filename || "database.db"} (${s.db_size_kb} Ko · ${s.member_count} adhérents)` : "Non initialisé";
}

export function pendingText(pending: number): string {
  return pending > 0 ? `⏳ ${pending} en attente` : "0 (à jour)";
}

/** Last cache sync (Unix time in seconds; 0 or null: never). */
export function lastSync(seconds: number | null | undefined): string {
  return seconds ? formatDateTimeSeconds(new Date(seconds * 1000)) : "Non renseignée";
}

/** Last run of the results batch (ISO date written by the server; shown as is when it is not one). */
export function lastRun(iso: string): string {
  if (!iso) {
    return "Jamais exécuté";
  }
  const date = parseDate(iso);
  return date ? formatDateTime(date) : iso;
}

export function timeNow(now: Date = new Date()): string {
  return formatTime(now);
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
    : b.competitions_updated > 0
      ? "Erreur envoi"
      : "Non (aucun nouveau résultat)";
  return [
    `🟢 Analyse MyCompet terminée à ${timeNow(now)}`,
    `• Compétitions passées vérifiées : ${b.competitions_checked}`,
    `• Résultats officiels trouvés : ${b.competitions_updated}`,
    `• E-mail récapitulatif expédié : ${email}`,
    ...(b.partial ? [`⏱️ Temps imparti écoulé : ${b.competitions_remaining} compétition(s) reportée(s) au prochain passage`] : []),
    ...b.details.map((c) => DETAIL_LINES[c.status](c)),
  ];
}

const DETAIL_LINES: Record<Schemas["BatchCompetition"]["status"], (c: Schemas["BatchCompetition"]) => string> = {
  found: (c) => `🏆 ${c.nom} : ${c.athletes.length} athlète(s) classé(s) pour le club`,
  pending: (c) => `⏳ ${c.nom} : pas encore de résultats publiés`,
  needs_url: (c) => `✍️ ${c.nom} : une page de même nom existe, mais pas à cette date : URL à saisir sur la fiche`,
  error: (c) => `⚠️ ${c.nom} : page MyCompet illisible pour le moment`,
};
