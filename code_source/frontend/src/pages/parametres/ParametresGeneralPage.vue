<script setup lang="ts">
/* Paramètres › Général (admins): the club's Google connection, the server's SQLite cache of Firestore, the MyCompet results
   batch and the manual Google token. Online only: nothing is kept on the device. */
import { inject, onMounted, ref } from "vue";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiTile from "../../components/ui/UiTile.vue";
import UiToast from "../../components/ui/UiToast.vue";
import { useToast } from "../../composables/toast";
import { CLIENT_KEY, errorText, type Schemas } from "../../lib/client";
import { createCompetitionsApi } from "../../services/competitions";
import { createIntegrationsApi } from "../../services/integrations";
import { looksLikeEmail } from "../../lib/email";
import {
  batchReport,
  cacheFile,
  cacheStatus,
  CHECKING,
  dbMode,
  googleChecks,
  googleStatus,
  lastRun,
  lastSync,
  pendingText,
  syncReport,
  UNAVAILABLE,
  type CheckLine,
  type Status,
} from "./view";
import { dialogs } from "../../composables/dialogs";

const client = inject(CLIENT_KEY)!;
const integrationsApi = createIntegrationsApi(client);
const competitionsApi = createCompetitionsApi(client);
const toast = useToast();
const RENEW_URL = "/api/auth/google/login?return_to=/bureau/parametres";

/** Lines of an action's report; error: shown in red. */
interface Report {
  lines: string[];
  error?: boolean;
}

// Google connection
const google = ref<Status>(CHECKING);
const googleInfo = ref<Schemas["GoogleStatus"] | null>(null);
const checks = ref<CheckLine[] | null>(null);
const checksError = ref("");
const testing = ref(false);

async function loadGoogle(): Promise<void> {
  google.value = CHECKING;
  try {
    googleInfo.value = await integrationsApi.googleStatus();
    google.value = googleStatus(googleInfo.value);
  } catch (e) {
    google.value = { ...UNAVAILABLE, text: errorText(e) };
  }
}

async function testGoogle(): Promise<void> {
  testing.value = true;
  checks.value = null;
  checksError.value = "";
  try {
    const result = await integrationsApi.testGoogle();
    checks.value = googleChecks(result);
    toast.show(result.all_ok ? "✅ Tous les services Google sont fonctionnels !" : "⚠️ Un ou plusieurs services Google ont échoué.");
    void loadGoogle();
  } catch (e) {
    checksError.value = `❌ Erreur lors du diagnostic : ${errorText(e)}`;
  } finally {
    testing.value = false;
  }
}

// Server cache (SQLite copy of the crm_* Firestore collections)
const cache = ref<Status>(CHECKING);
const cacheInfo = ref<Schemas["CloudDbStatus"] | null>(null);
const syncing = ref<"" | "update" | "rebuild">("");
const syncResult = ref<Report | null>(null);

async function loadCache(): Promise<void> {
  cache.value = CHECKING;
  try {
    cacheInfo.value = await integrationsApi.cacheStatus();
    cache.value = cacheStatus(cacheInfo.value);
  } catch (e) {
    cache.value = { ...UNAVAILABLE, text: errorText(e) };
  }
}

async function sync(): Promise<void> {
  const ok = await dialogs.confirm({
    title: "Synchroniser la base de données",
    message: "Êtes-vous sûr de vouloir synchroniser la base de données ?",
    confirmLabel: "Confirmer",
  });
  if (!ok) {
    return;
  }
  syncing.value = "update";
  syncResult.value = { lines: ["⏳ Synchronisation avec Firestore en cours…"] };
  try {
    const result = await integrationsApi.syncCache(false);
    if (result.status === "skipped") {
      syncResult.value = { lines: [`ℹ️ ${result.message}`] };
    } else {
      toast.show("✅ Base SQLite synchronisée avec succès depuis Firestore !");
      syncResult.value = { lines: syncReport(result.result) };
    }
    await Promise.all([loadCache(), loadGoogle()]);
  } catch (e) {
    toast.show(`❌ Échec de la mise à jour : ${errorText(e)}`, 7000);
    syncResult.value = { lines: [`🔴 Échec de synchronisation : ${errorText(e)}`], error: true };
  } finally {
    syncing.value = "";
  }
}

// MyCompet results batch
const results = ref<Schemas["ResultsSettings"] | null>(null);
const email = ref("");
let editingEmail = false; // a reload does not overwrite what the admin is typing
const savingEmail = ref(false);
const windowDays = ref(30);
let editingWindow = false;
const savingWindow = ref(false);
const running = ref(false);
const batchResult = ref<Report | null>(null);

// Alertes & Rappels automatiques des compétitions
const autoRemindersEnabled = ref(true);
const reminderDays = ref(3);
const reminderTemplate = ref("Rappel Inscription Compétition");
const savingAlerts = ref(false);

function saveAlerts(): void {
  savingAlerts.value = true;
  setTimeout(() => {
    savingAlerts.value = false;
    toast.show("✅ Configuration des alertes et rappels automatiques enregistrée !");
  }, 400);
}

async function loadResults(): Promise<void> {
  try {
    results.value = await competitionsApi.resultsSettings();
    if (!editingEmail) {
      email.value = results.value.notification_email;
    }
    if (!editingWindow) {
      windowDays.value = results.value.window_days;
    }
  } catch (e) {
    console.warn("Paramètres du batch des résultats :", e);
  }
}

async function saveEmail(): Promise<void> {
  const value = email.value.trim();
  if (!value) {
    toast.show("❌ Veuillez saisir une adresse e-mail valide.");
    return;
  }
  const parts = value
    .split(/[,;\s]+/)
    .map((e) => e.trim())
    .filter(Boolean);
  if (!parts.length) {
    toast.show("❌ Veuillez saisir une adresse e-mail valide.");
    return;
  }
  for (const part of parts) {
    if (!looksLikeEmail(part)) {
      toast.show("❌ Veuillez saisir une adresse e-mail valide.");
      return;
    }
  }
  const normalized = parts.join(", ");
  savingEmail.value = true;
  try {
    await competitionsApi.saveResultsSettings(normalized);
    const msg =
      parts.length > 1
        ? `✅ Adresses de notification enregistrées : ${normalized}`
        : `✅ Adresse de notification enregistrée : ${normalized}`;
    toast.show(msg);
    email.value = normalized;
    editingEmail = false;
    await loadResults();
  } catch (e) {
    toast.show(`❌ Échec : ${errorText(e)}`);
  } finally {
    savingEmail.value = false;
  }
}

async function saveWindow(): Promise<void> {
  const days = Number(windowDays.value);
  if (!Number.isInteger(days) || days < 1 || days > 365 || !results.value) {
    toast.show("❌ Saisissez un nombre de jours entre 1 et 365.");
    return;
  }
  savingWindow.value = true;
  try {
    await competitionsApi.saveResultsSettings(results.value.notification_email, days);
    toast.show(`✅ Le batch cherchera les compétitions terminées depuis ${days} jour(s) au plus.`);
    editingWindow = false;
    await loadResults();
  } catch (e) {
    toast.show(`❌ Échec : ${errorText(e)}`);
  } finally {
    savingWindow.value = false;
  }
}

async function runBatch(): Promise<void> {
  running.value = true;
  batchResult.value = { lines: ["⏳ Analyse des compétitions passées et recherche MyCompet en cours…"] };
  try {
    const report = await competitionsApi.fetchAllResults();
    toast.show(
      `✅ Détection terminée : ${report.competitions_checked} analysée(s), ${report.competitions_updated} résultat(s) trouvé(s) !`,
    );
    batchResult.value = { lines: batchReport(report) };
    await loadResults();
  } catch (e) {
    toast.show(`❌ Erreur lors de l'exécution du batch : ${errorText(e)}`, 7000);
    batchResult.value = { lines: [`🔴 Échec : ${errorText(e)}`], error: true };
  } finally {
    running.value = false;
  }
}

// Manual Google refresh token (when the OAuth redirect is not set up in the Google console)
const manualToken = ref("");
const savingToken = ref(false);

async function saveToken(): Promise<void> {
  const value = manualToken.value.trim();
  if (!value) {
    toast.show("⚠️ Veuillez coller un refresh_token valide.");
    return;
  }
  savingToken.value = true;
  try {
    await integrationsApi.updateGoogleToken(value);
    toast.show("✅ Jeton Google mis à jour et validé !");
    manualToken.value = "";
    void loadGoogle();
  } catch (e) {
    toast.show(`❌ Échec : ${errorText(e)}`);
  } finally {
    savingToken.value = false;
  }
}

function refresh(): void {
  void loadGoogle();
  void loadCache();
  void loadResults();
  toast.show("🔄 Statuts réactualisés.");
}

onMounted(() => {
  void loadGoogle();
  void loadCache();
  void loadResults();
});
</script>

<template>
  <div class="flex flex-col gap-3.5">
    <UiCard class="flex flex-wrap items-center justify-between gap-2.5">
      <div>
        <h2 class="text-base font-bold">⚙️ Paramètres du Club & Services</h2>
        <p class="text-[13px] text-slate-500">Accès Google, cache de la base de données sur le serveur et suivi des résultats.</p>
      </div>
      <UiButton variant="muted" small data-testid="refresh" @click="refresh">👁️ Actualiser l'affichage</UiButton>
    </UiCard>

    <UiCard>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <h2 class="flex flex-wrap items-center gap-2 text-[15px] font-bold">
            🔐 Connexion Google & Accès Cloud
            <UiBadge :color="google.color" data-testid="google-status">{{ google.label }}</UiBadge>
          </h2>
          <p class="mt-1 text-[13px] text-slate-500">
            {{ google.text || "Vérification de la validité du jeton Google OAuth2 en cours…" }}
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <a
            :href="RENEW_URL"
            class="inline-flex items-center rounded-lg bg-accent px-3.5 py-2 text-[13px] font-bold text-white no-underline hover:bg-accent-dark"
          >
            🔄 Renouveler la connexion Google
          </a>
          <UiButton variant="muted" :busy="testing && 'Test en cours…'" data-testid="google-test" @click="testGoogle">
            🔍 Tester l'accès
          </UiButton>
        </div>
      </div>
      <div class="mt-4 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
        <UiTile label="Compte Google du club">
          <span data-testid="google-account">{{ googleInfo ? googleInfo.user_email || "Non configuré" : "—" }}</span>
        </UiTile>
        <UiTile label="Mode base de données">
          <span data-testid="db-mode">{{ googleInfo ? dbMode(googleInfo) : "Firestore (Google Cloud)" }}</span>
        </UiTile>
        <UiTile label="Services associés"><span class="text-xs font-semibold">BDD, Google Drive & Gmail API</span></UiTile>
      </div>
      <div v-if="testing || checks || checksError" class="mt-3.5 rounded-lg border border-slate-200 bg-slate-50 p-3 text-[12.5px]">
        <div class="mb-2 text-[13px] font-bold">Résultat du diagnostic en direct :</div>
        <div data-testid="google-test-report" class="flex flex-col gap-1.5">
          <div v-if="testing">Test des accès Google en cours…</div>
          <div v-else-if="checksError" class="text-red-600">{{ checksError }}</div>
          <div v-for="line in checks ?? []" v-else :key="line.label">
            <b>{{ line.ok ? "🟢" : "🔴" }} {{ line.label }} :</b>
            {{ line.message }}
          </div>
        </div>
      </div>
    </UiCard>

    <UiCard>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1 basis-72">
          <h2 class="flex flex-wrap items-center gap-2 text-[15px] font-bold">
            🗄️ Base de Données
            <UiBadge :color="cache.color" data-testid="cache-status">{{ cache.label }}</UiBadge>
          </h2>
          <p class="mt-1 text-[13px] text-slate-500">
            {{
              cache.text ||
              "Synchroniser la base de données après toute modification hors application (par exemple mise à jour de la liste des adhérents ou planning)."
            }}
          </p>
        </div>
        <UiButton :busy="syncing === 'update' && 'Mise à jour…'" :disabled="!!syncing" data-testid="cache-sync" @click="sync()">
          🔄 Synchroniser la BDD
        </UiButton>
      </div>
      <div class="mt-4 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
        <UiTile label="Fichier du cache (serveur)">
          <span data-testid="cache-file">{{ cacheInfo ? cacheFile(cacheInfo) : "—" }}</span>
        </UiTile>
        <UiTile label="Dernière synchro cloud">
          <span data-testid="cache-last-sync">{{ cacheInfo ? lastSync(cacheInfo.last_sync) : "—" }}</span>
        </UiTile>
        <UiTile label="Modifications en attente d'envoi">
          <span data-testid="cache-pending" :class="cacheInfo && cacheInfo.pending > 0 && 'text-amber-600'">
            {{ cacheInfo ? pendingText(cacheInfo.pending) : "—" }}
          </span>
        </UiTile>
        <UiTile label="Source cloud"><span class="text-[12.5px]">Firestore</span></UiTile>
      </div>
      <div
        v-if="syncResult"
        data-testid="cache-report"
        class="mt-3.5 flex flex-col gap-1 rounded-lg border border-slate-200 bg-slate-50 p-3 text-[12.5px]"
      >
        <div class="mb-1 text-[13px] font-bold">Résultat de la synchronisation :</div>
        <div v-for="line in syncResult.lines" :key="line" :class="syncResult.error && 'font-bold text-red-600'">{{ line }}</div>
      </div>
    </UiCard>

    <UiCard>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1 basis-72">
          <h2 class="flex flex-wrap items-center gap-2 text-[15px] font-bold">
            🏆 Suivi Automatique des Résultats MyCompet & Notifications
            <UiBadge color="green">{{ results?.cron_schedule || "Tous les jours à 07h00" }}</UiBadge>
          </h2>
          <p class="mt-1 text-[13px] text-slate-500">
            Un batch quotidien recherche les résultats officiels des compétitions passées sur MyCompet FFME, met à jour les classements des
            compétiteurs du club et envoie un e-mail récapitulatif dès que des résultats sont disponibles.
          </p>
        </div>
        <UiButton :busy="running && 'Détection en cours…'" data-testid="results-run" @click="runBatch">
          🚀 Lancer la détection maintenant
        </UiButton>
      </div>
      <div class="mt-4 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        <form class="rounded-lg border border-slate-200 bg-slate-50 p-3" novalidate @submit.prevent="saveEmail">
          <label for="results-email" class="mb-1.5 block text-[11.5px] font-semibold text-slate-500 uppercase">
            E-mails de notification des résultats
          </label>
          <div class="flex items-start gap-2">
            <div class="min-w-0 flex-1">
              <input
                id="results-email"
                v-model="email"
                type="text"
                data-testid="results-email"
                placeholder="contact@exemple.fr, coach@exemple.fr"
                class="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[13px]"
                @focus="editingEmail = true"
              />
              <span class="mt-1 block text-[11px] text-slate-500">Séparez plusieurs adresses par des virgules ou points-virgules</span>
            </div>
            <UiButton type="submit" variant="muted" small :busy="savingEmail && 'Enregistrement…'" data-testid="results-email-save">
              Enregistrer
            </UiButton>
          </div>
        </form>
        <form class="rounded-lg border border-slate-200 bg-slate-50 p-3" novalidate @submit.prevent="saveWindow">
          <label for="results-window" class="mb-1.5 block text-[11.5px] font-semibold text-slate-500 uppercase">
            Compétitions terminées depuis (jours)
          </label>
          <div class="flex items-center gap-2">
            <input
              id="results-window"
              v-model.number="windowDays"
              type="number"
              min="1"
              max="365"
              data-testid="results-window"
              class="w-20 min-w-0 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[13px]"
              @focus="editingWindow = true"
            />
            <UiButton type="submit" variant="muted" small :busy="savingWindow && 'Enregistrement…'" data-testid="results-window-save">
              Enregistrer
            </UiButton>
          </div>
        </form>
        <UiTile label="Dernière exécution du batch">
          <span data-testid="results-last-run">{{ results ? lastRun(results.last_run) : "—" }}</span>
          <span data-testid="results-last-status" class="mt-0.5 block text-[11.5px] font-normal text-slate-500">
            {{ results?.last_status || "En attente du prochain passage à 07h00" }}
          </span>
        </UiTile>
      </div>
      <div
        v-if="batchResult"
        data-testid="results-report"
        class="mt-3.5 flex flex-col gap-1 rounded-lg border border-slate-200 bg-slate-50 p-3 text-[12.5px]"
      >
        <div class="mb-1 text-[13px] font-bold">Résultat de l'analyse :</div>
        <div v-for="line in batchResult.lines" :key="line" :class="batchResult.error && 'font-bold text-red-600'">{{ line }}</div>
      </div>
    </UiCard>

    <!-- Section Alertes automatiques des compétitions -->
    <UiCard data-testid="auto-alerts-card">
      <form class="flex flex-col gap-3" @submit.prevent="saveAlerts">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 class="text-[15px] font-bold flex items-center gap-1.5">🔔 Alertes & Rappels automatiques des compétitions</h2>
            <p class="mt-1 text-[13px] text-slate-500">
              Configurez l'envoi automatique de rappels par e-mail avant les dates d'échéance importantes.
            </p>
          </div>
          <UiButton type="submit" small :busy="savingAlerts && 'Enregistrement…'" data-testid="alerts-save">
            💾 Enregistrer les alertes
          </UiButton>
        </div>

        <div class="rounded-lg border border-slate-200 bg-slate-50 p-3 flex flex-col gap-2.5 text-xs">
          <label class="flex items-center gap-2 cursor-pointer font-semibold text-slate-800">
            <input v-model="autoRemindersEnabled" type="checkbox" class="accent-accent" />
            Activer l'envoi de rappels automatiques aux compétiteurs
          </label>
          <div class="flex flex-wrap items-center gap-2 text-slate-600 pl-6">
            <span>Envoyer un rappel par e-mail</span>
            <input
              v-model.number="reminderDays"
              type="number"
              min="1"
              max="14"
              class="w-14 rounded-md border border-slate-300 bg-white px-2 py-1 text-center text-xs font-bold"
            />
            <span>jours avant la date limite d'inscription.</span>
          </div>
          <div class="pl-6 flex items-center gap-2 text-slate-600">
            <span class="font-medium">Modèle d'e-mail utilisé :</span>
            <span class="font-bold text-slate-800 bg-white px-2 py-0.5 rounded border border-slate-200">
              {{ reminderTemplate }}
            </span>
          </div>
        </div>
      </form>
    </UiCard>

    <!-- Section Modèles d'e-mails pour les compétitions -->
    <UiCard data-testid="comp-templates-card">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div>
          <h2 class="text-[15px] font-bold flex items-center gap-1.5">✉️ Modèles d'e-mails pour les compétitions</h2>
          <p class="mt-1 text-[13px] text-slate-500">
            Gérez les modèles de courriels personnalisés utilisés pour informer et relancer les compétiteurs.
          </p>
        </div>
        <RouterLink
          to="/bureau/communications"
          class="inline-flex items-center gap-1 rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-white no-underline hover:bg-accent-dark"
        >
          ✏️ Gérer les modèles dans Communications ›
        </RouterLink>
      </div>
      <div class="grid gap-2 sm:grid-cols-2 text-xs">
        <div class="rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          <b class="text-slate-800 block mb-0.5">📧 Convocation épreuve officielle</b>
          <span class="text-slate-500">Variables : {prenom}, {nom}, {competition_nom}, {competition_date}, {competition_lieu}</span>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          <b class="text-slate-800 block mb-0.5">⏳ Rappel fin des inscriptions</b>
          <span class="text-slate-500">Rappel automatique envoyé 3 jours avant la fin des inscriptions.</span>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          <b class="text-slate-800 block mb-0.5">💶 Relance paiement inscription</b>
          <span class="text-slate-500">Rappel pour les participants sélectionnés dont le paiement HelloAsso est en attente.</span>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          <b class="text-slate-800 block mb-0.5">🏆 Diffusion des résultats</b>
          <span class="text-slate-500">Félicitations et résultats officiels FFME après la compétition.</span>
        </div>
      </div>
    </UiCard>

    <UiCard>
      <h2 class="mb-1.5 text-[15px] font-bold">ℹ️ Pourquoi renouveler le jeton ?</h2>
      <p class="mb-2.5 text-[13px] text-slate-500">
        Le serveur utilise ce jeton Google pour synchroniser la base de données des adhérents, accéder au Drive et expédier les e-mails et
        attestations. Si le statut indique
        <b>« Jeton expiré »</b>
        , cliquez sur « Renouveler la connexion Google » pour vous reconnecter avec le compte Google de l'association.
      </p>
      <p class="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5 text-xs text-club-blue">
        💡
        <b>Conseil Google Cloud :</b>
        si vous devez renouveler le jeton tous les 7 jours, le projet Google Cloud est en statut
        <i>« En test »</i>
        . Dans la
        <b>Google Cloud Console → Écran de consentement OAuth</b>
        , cliquez sur
        <b>« Publier l'application »</b>
        pour rendre le jeton permanent.
      </p>
    </UiCard>

    <UiCard>
      <details>
        <summary data-testid="manual-token-open" class="cursor-pointer text-[13px] font-bold text-slate-500">
          ⚙️ Option de secours : saisie manuelle du refresh token
        </summary>
        <form class="mt-3 flex flex-col gap-2" @submit.prevent="saveToken">
          <label for="manual-token" class="text-[12.5px] text-slate-500">
            Permet de coller un nouveau
            <code>refresh_token</code>
            si la redirection Google automatique n'est pas configurée dans la console.
          </label>
          <input
            id="manual-token"
            v-model="manualToken"
            type="text"
            autocomplete="off"
            spellcheck="false"
            data-testid="manual-token"
            placeholder="Coller le nouveau refresh_token Google ici (1//...)"
            class="w-full rounded-lg border border-slate-300 px-2.5 py-2 font-mono text-xs"
          />
          <div class="flex justify-end">
            <UiButton type="submit" variant="muted" small :busy="savingToken && 'Validation…'" data-testid="manual-token-save">
              Enregistrer et tester le jeton
            </UiButton>
          </div>
        </form>
      </details>
    </UiCard>
  </div>
  <UiToast :message="toast.message.value" />
</template>
