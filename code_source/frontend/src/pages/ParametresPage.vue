<script setup lang="ts">
/* Paramètres (admins): the club's Google connection, the server's SQLite cache of Firestore, the MyCompet results
   batch and the manual Google token. Online only: nothing is kept on the device. */
import { inject, onMounted, ref } from "vue";
import AppShell from "../components/AppShell.vue";
import UiBadge from "../components/ui/UiBadge.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiCard from "../components/ui/UiCard.vue";
import UiTile from "../components/ui/UiTile.vue";
import UiToast from "../components/ui/UiToast.vue";
import { useToast } from "../composables/toast";
import { CLIENT_KEY, errorText, type Schemas } from "../lib/client";
import { createCompetitionsApi } from "../services/competitions";
import { createIntegrationsApi } from "../services/integrations";
import { looksLikeEmail } from "../lib/email";
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
} from "./parametres/view";
import { dialogs } from "../composables/dialogs";

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

const REBUILD_CONFIRM =
  "Voulez-vous forcer la reconstruction intégrale du cache SQLite ?\n\n" +
  "Cette opération va télécharger à nouveau tous les documents de Firestore pour reconstruire database.db à neuf.";

async function sync(full: boolean): Promise<void> {
  if (
    full &&
    !(await dialogs.confirm({ title: "Reconstruire le cache", message: REBUILD_CONFIRM, confirmLabel: "Reconstruire", variant: "warning" }))
  ) {
    return;
  }
  syncing.value = full ? "rebuild" : "update";
  syncResult.value = { lines: [`⏳ Synchronisation avec Firestore en cours (${full ? "reconstruction complète" : "mode incrémental"})…`] };
  try {
    const result = await integrationsApi.syncCache(full);
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
const running = ref(false);
const batchResult = ref<Report | null>(null);

async function loadResults(): Promise<void> {
  try {
    results.value = await competitionsApi.resultsSettings();
    if (!editingEmail) {
      email.value = results.value.notification_email;
    }
  } catch (e) {
    console.warn("Paramètres du batch des résultats :", e);
  }
}

async function saveEmail(): Promise<void> {
  const value = email.value.trim();
  if (!looksLikeEmail(value)) {
    toast.show("❌ Veuillez saisir une adresse e-mail valide.");
    return;
  }
  savingEmail.value = true;
  try {
    await competitionsApi.saveResultsSettings(value);
    toast.show(`✅ Adresse de notification enregistrée : ${value}`);
    editingEmail = false;
    await loadResults();
  } catch (e) {
    toast.show(`❌ Échec : ${errorText(e)}`);
  } finally {
    savingEmail.value = false;
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
  <AppShell page="parametres" title="Paramètres">
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
              🗄️ Base de Données (SQLite ↔ Firestore)
              <UiBadge :color="cache.color" data-testid="cache-status">{{ cache.label }}</UiBadge>
            </h2>
            <p class="mt-1 text-[13px] text-slate-500">
              {{
                cache.text ||
                "Le serveur garde une copie SQLite (database.db) de la base Firestore ; la synchronisation échange les nouveautés."
              }}
            </p>
          </div>
          <UiButton :busy="syncing === 'update' && 'Mise à jour…'" :disabled="!!syncing" data-testid="cache-sync" @click="sync(false)">
            🔄 Synchroniser la BDD (Envoi & Réception)
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
        <details class="mt-4 border-t border-dashed border-slate-200 pt-2.5 text-xs text-slate-500">
          <summary data-testid="troubleshooting" class="cursor-pointer font-semibold">
            🛠️ Zone de dépannage avancée (Reconstruction intégrale)
          </summary>
          <div class="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2.5 text-amber-800">
            <p class="mb-2">
              <b>Attention :</b>
              cette opération télécharge à nouveau toutes les collections Firestore pour remplacer le cache du serveur. Ne l'utilisez que si
              le cache est corrompu, après avoir envoyé les modifications en attente.
            </p>
            <UiButton
              variant="warning"
              small
              :busy="syncing === 'rebuild' && 'Reconstruction…'"
              :disabled="!!syncing"
              data-testid="cache-rebuild"
              @click="sync(true)"
            >
              ⚠️ Forcer la reconstruction complète depuis Firestore
            </UiButton>
          </div>
        </details>
      </UiCard>

      <UiCard>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1 basis-72">
            <h2 class="flex flex-wrap items-center gap-2 text-[15px] font-bold">
              🏆 Suivi Automatique des Résultats MyCompet & Notifications
              <UiBadge color="green">{{ results?.cron_schedule || "Tous les jours à 07h00" }}</UiBadge>
            </h2>
            <p class="mt-1 text-[13px] text-slate-500">
              Un batch quotidien recherche les résultats officiels des compétitions passées sur MyCompet FFME, met à jour les classements
              des compétiteurs du club et envoie un e-mail récapitulatif dès que des résultats sont disponibles.
            </p>
          </div>
          <UiButton :busy="running && 'Détection en cours…'" data-testid="results-run" @click="runBatch">
            🚀 Lancer la détection maintenant
          </UiButton>
        </div>
        <div class="mt-4 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
          <form class="rounded-lg border border-slate-200 bg-slate-50 p-3" novalidate @submit.prevent="saveEmail">
            <label for="results-email" class="mb-1.5 block text-[11.5px] font-semibold text-slate-500 uppercase">
              E-mail de notification des résultats
            </label>
            <div class="flex items-center gap-2">
              <input
                id="results-email"
                v-model="email"
                type="email"
                data-testid="results-email"
                placeholder="adresse@exemple.fr"
                class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[13px]"
                @focus="editingEmail = true"
              />
              <UiButton type="submit" variant="muted" small :busy="savingEmail && 'Enregistrement…'" data-testid="results-email-save">
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
  </AppShell>
</template>
