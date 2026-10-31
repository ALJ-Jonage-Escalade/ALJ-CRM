<script setup lang="ts">
/* Paramètres › Campagne HelloAsso (admins): the club's HelloAsso campaigns of each kind, with their dates, and the
   choice of the active one: the membership form shown by the dashboard, the seasonal Event form competition payments
   are matched against. Online only: nothing is kept on the device. */
import { computed, inject, onMounted, ref } from "vue";
import UiBadge from "../../components/ui/UiBadge.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiToast from "../../components/ui/UiToast.vue";
import type { BadgeColor } from "../../components/ui/palette";
import { dialogs } from "../../composables/dialogs";
import { useToast } from "../../composables/toast";
import { CLIENT_KEY, errorText, type Schemas } from "../../lib/client";
import { formatDayText } from "../../lib/format";
import { createIntegrationsApi, type CampaignKind } from "../../services/integrations";

type Campaign = Schemas["HelloAssoCampaign"];
type CampaignRef = Schemas["HelloAssoCampaignRef"];

const integrationsApi = createIntegrationsApi(inject(CLIENT_KEY)!);
const toast = useToast();

const KINDS: { kind: CampaignKind; title: string; description: string; impact: string }[] = [
  {
    kind: "membership",
    title: "🧗 Adhésions",
    description: "Formulaire d'adhésion dont le tableau de bord affiche les inscriptions.",
    impact: "Le tableau de bord affichera les inscriptions de cette campagne.",
  },
  {
    kind: "competitions",
    title: "🏆 Compétitions",
    description: "Formulaire de la saison sur lequel les compétiteurs paient leurs inscriptions.",
    impact: "Les nouveaux paiements HelloAsso ne seront rapprochés qu'avec ce formulaire.",
  },
];

const STATES: Record<string, { label: string; color: BadgeColor }> = {
  Public: { label: "Public", color: "green" },
  Private: { label: "Privé", color: "slate" },
  Draft: { label: "Brouillon", color: "amber" },
  Disabled: { label: "Désactivé", color: "red" },
  Deleted: { label: "Supprimé", color: "red" },
};

const campaigns = ref<Schemas["HelloAssoCampaigns"] | null>(null);
const loading = ref(false);
// The request itself failed (server or network); HelloAsso's own failure is campaigns.error
const loadError = ref("");
const choosing = ref("");
// Shown after a competitions campaign is chosen: its payments are downloaded by the sync
const syncNotice = ref(false);

const helloAssoError = computed(() => campaigns.value?.error ?? "");
// Each kind with its campaigns, once loaded
const sections = computed(() => {
  const loaded = campaigns.value;
  return loaded ? KINDS.map((section) => ({ ...section, ...loaded[section.kind] })) : [];
});

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    campaigns.value = await integrationsApi.helloAssoCampaigns();
  } catch (e) {
    loadError.value = errorText(e);
  } finally {
    loading.value = false;
  }
}

function stateOf(campaign: Campaign): { label: string; color: BadgeColor } | undefined {
  return STATES[campaign.state];
}

function dayText(value: string | null): string {
  return value ? formatDayText(value) : "—";
}

function campaignName(kind: CampaignKind, ref: CampaignRef): string {
  const listed = campaigns.value?.[kind].campaigns.find((campaign) => campaign.slug === ref.slug);
  return listed?.title || ref.slug;
}

async function choose(kind: CampaignKind, title: string, impact: string, campaign: Campaign): Promise<void> {
  const active = campaigns.value?.[kind].active;
  const current = active ? `« ${campaignName(kind, active)} »` : "aucune";
  const ok = await dialogs.confirm({
    title: `Campagne active — ${title}`,
    message: `Actuelle : ${current}\nNouvelle : « ${campaign.title || campaign.slug} »\n\n${impact}`,
    confirmLabel: "Choisir cette campagne",
    variant: "warning",
  });
  if (!ok) {
    return;
  }
  choosing.value = `${kind}:${campaign.slug}`;
  try {
    await integrationsApi.chooseHelloAssoCampaign(kind, campaign);
    toast.show(`✅ Campagne active : ${campaign.title || campaign.slug}`);
    syncNotice.value = kind === "competitions";
    await load();
  } catch (e) {
    toast.show(`❌ ${errorText(e)}`);
  } finally {
    choosing.value = "";
  }
}

onMounted(load);
</script>

<template>
  <div class="flex flex-col gap-3.5">
    <UiCard class="flex flex-wrap items-center justify-between gap-2.5">
      <div>
        <h2 class="text-base font-bold">💳 Campagnes HelloAsso</h2>
        <p class="text-[13px] text-slate-500">Formulaires du club sur HelloAsso et campagne active de chaque type.</p>
      </div>
      <UiButton variant="muted" small data-testid="campaigns-refresh" :busy="loading && 'Chargement…'" @click="load">
        🔄 Actualiser
      </UiButton>
    </UiCard>

    <p
      v-if="loadError"
      data-testid="campaigns-load-error"
      role="alert"
      class="rounded-lg border border-red-200 bg-red-50 p-3 text-[13px] text-red-700"
    >
      ❌ {{ loadError }}
    </p>
    <div
      v-if="helloAssoError"
      data-testid="campaigns-helloasso-error"
      role="alert"
      class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-[13px] text-amber-800"
    >
      <span>⚠️ {{ helloAssoError }} Les campagnes actives restent affichées ; le choix est indisponible.</span>
      <UiButton variant="warning" small data-testid="campaigns-retry" :busy="loading && 'Chargement…'" @click="load">Réessayer</UiButton>
    </div>
    <p
      v-if="syncNotice"
      data-testid="campaigns-sync-notice"
      class="rounded-lg border border-blue-200 bg-blue-50 p-3 text-[13px] text-blue-800"
    >
      ℹ️ Les paiements de la nouvelle campagne seront récupérés à la prochaine synchronisation :
      <RouterLink to="/bureau/competitions/helloasso" class="font-bold underline">Compétitions › HelloAsso</RouterLink>
      .
    </p>

    <UiCard v-for="section in sections" :key="section.kind" :data-testid="`campaigns-${section.kind}`">
      <h3 class="text-[15px] font-bold">{{ section.title }}</h3>
      <p class="mt-1 text-[13px] text-slate-500">{{ section.description }}</p>
      <p class="mt-2 text-[13px]" data-testid="campaigns-active">
        Campagne active :
        <template v-if="section.active">
          <strong>{{ campaignName(section.kind, section.active) }}</strong>
          <span class="font-mono text-[11.5px] text-slate-500">({{ section.active.slug }})</span>
          <span v-if="!section.configured" data-testid="campaigns-default" class="text-amber-700">
            — valeur par défaut, aucune campagne choisie
          </span>
        </template>
        <strong v-else data-testid="campaigns-none" class="text-red-700">aucune campagne choisie</strong>
      </p>

      <div v-if="section.campaigns.length" class="mt-2 overflow-x-auto">
        <table class="w-full text-left text-[13px]" data-testid="campaigns-table">
          <thead class="text-[11.5px] text-slate-500 uppercase">
            <tr>
              <th class="py-1.5 pr-3">Campagne</th>
              <th class="py-1.5 pr-3">Slug</th>
              <th class="py-1.5 pr-3">État</th>
              <th class="py-1.5 pr-3">Début</th>
              <th class="py-1.5 pr-3">Fin</th>
              <th class="py-1.5 pr-3">Créée le</th>
              <th class="py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="campaign in section.campaigns"
              :key="campaign.slug"
              :data-slug="campaign.slug"
              data-testid="campaign-row"
              :class="['border-t border-slate-100', campaign.active && 'bg-blue-50/50']"
            >
              <td class="py-1.5 pr-3">
                <a v-if="campaign.url" :href="campaign.url" target="_blank" rel="noopener noreferrer" class="font-semibold underline">
                  {{ campaign.title || campaign.slug }}
                </a>
                <span v-else class="font-semibold">{{ campaign.title || campaign.slug }}</span>
                <span v-if="campaign.private_title && campaign.private_title !== campaign.title" class="block text-xs text-slate-500">
                  {{ campaign.private_title }}
                </span>
                <span v-if="campaign.warning" data-testid="campaign-warning" class="block text-xs font-semibold text-amber-700">
                  ⚠️ {{ campaign.warning }}
                </span>
              </td>
              <td class="py-1.5 pr-3 font-mono text-[11.5px] break-all text-slate-600">{{ campaign.slug }}</td>
              <td class="py-1.5 pr-3" data-testid="campaign-state">
                <UiBadge v-if="stateOf(campaign)" :color="stateOf(campaign)?.color ?? 'slate'" variant="soft">
                  {{ stateOf(campaign)?.label }}
                </UiBadge>
                <span v-else>{{ campaign.state || "—" }}</span>
              </td>
              <td class="py-1.5 pr-3 whitespace-nowrap" data-testid="campaign-start">{{ dayText(campaign.start_date) }}</td>
              <td class="py-1.5 pr-3 whitespace-nowrap" data-testid="campaign-end">{{ dayText(campaign.end_date) }}</td>
              <td class="py-1.5 pr-3 whitespace-nowrap" data-testid="campaign-created">{{ dayText(campaign.created_at) }}</td>
              <td class="py-1.5 text-right">
                <UiBadge v-if="campaign.active" color="blue" data-testid="campaign-active">Campagne active</UiBadge>
                <UiButton
                  v-else
                  small
                  variant="muted"
                  data-testid="campaign-choose"
                  :busy="choosing === `${section.kind}:${campaign.slug}` && 'Enregistrement…'"
                  :disabled="!!choosing || !!helloAssoError"
                  @click="choose(section.kind, section.title, section.impact, campaign)"
                >
                  Choisir
                </UiButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="!helloAssoError" data-testid="campaigns-empty" class="mt-2 text-[13px] text-slate-500">
        Aucune campagne publique ou privée de ce type sur HelloAsso.
      </p>
    </UiCard>
  </div>
  <UiToast :message="toast.message.value" />
</template>
