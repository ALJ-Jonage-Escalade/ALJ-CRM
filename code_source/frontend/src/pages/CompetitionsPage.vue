<script setup lang="ts">
/* Compétitions (/competitions and /bureau/competitions, any role: read-only accounts too, as on the former phone
   page). Coaches and admins change everything here. Layout of the sub-pages (the list, HelloAsso, Bilan, Coachs:
   router.ts): polls the data they share, keeps the outbox of the changes made offline and sends it back. */
import { computed, inject, onScopeDispose, provide, ref, watch } from "vue";
import { RouterView, useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";
import UiToast from "../components/ui/UiToast.vue";
import { AUTH_KEY } from "../composables/auth";
import { useSyncedResource } from "../composables/syncedResource";
import { useToast } from "../composables/toast";
import { pageVerdict } from "../lib/access";
import { formatDateTime } from "../lib/format";
import { CLIENT_KEY } from "../lib/client";
import { createCompetitionsApi } from "../services/competitions";
import { isStaff } from "../lib/roles";
import { offlineStore, STORE_KEY } from "../lib/store";
import {
  competitionMembersPath,
  sortCompetitions,
  toMemberSlots,
  type Coach,
  type Competition,
  type CompetitorContact,
  type MemberSlot,
} from "./competitions/competitions";
import type { HelloAssoItem } from "./competitions/helloasso/helloasso";
import { createOutbox, pendingLine, replayMessage } from "./competitions/outbox";
import { createWriter, WRITER_KEY } from "./competitions/writer";
import { COMPETITIONS_KEY } from "./competitions/context";

const auth = inject(AUTH_KEY)!;
const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const store = inject(STORE_KEY, null) ?? offlineStore();
const route = useRoute();
const toast = useToast();

const access = computed(() => pageVerdict(auth.state.value, "competitions"));
const open = computed(() => access.value === "allow" || access.value === "offline");
const uid = computed(() => {
  const authState = auth.state.value;
  return open.value && (authState.status === "signedIn" || authState.status === "error") ? authState.user.uid : null;
});
const signedIn = computed(() => auth.state.value.status === "signedIn");
// Coaches and admins see the contacts; offline the role is unknown: only a copy kept for this user can show
const staff = computed(() => auth.state.value.status === "signedIn" && isStaff(auth.state.value.role));
const contactsShown = computed(() => staff.value || access.value === "offline");

const competitions = useSyncedResource<Competition[]>("competitions", () => (open.value ? "/api/competitions" : null), {
  offline: true,
  uid,
});
const competitors = useSyncedResource<CompetitorContact[]>(
  "competitors",
  () => (open.value && contactsShown.value ? "/api/members/competitors" : null),
  { offline: true, uid },
);
// Offline the role cannot be checked: a device keeping the contacts is a coach's (they are never kept for others)
const canWrite = computed(() => staff.value || (access.value === "offline" && competitors.data.value !== null));
// Tariffs and slot groups to group the participants, names and e-mails to add or write to them: online only
const members = useSyncedResource<MemberSlot[]>(
  "competition-members",
  () => (open.value && signedIn.value ? competitionMembersPath() : null),
  {
    offline: false,
    select: toMemberSlots,
    intervalMs: 60_000,
  },
);
const coaches = useSyncedResource<Coach[]>("coaches", () => (staff.value ? "/api/coaches" : null), { offline: false, intervalMs: 60_000 });

// The open sub-page (router.ts): its id, as AppShell lists it
const sub = computed(() => route.meta.sub ?? "competitions");
const items = useSyncedResource<HelloAssoItem[]>(
  "helloasso-items",
  () => (staff.value && sub.value === "helloasso" ? "/api/helloasso/items" : null),
  { offline: false },
);

// ---------------------------------------------------------------- Network and outbox

const networkUp = ref(navigator.onLine);
const onNetwork = () => (networkUp.value = navigator.onLine);
window.addEventListener("online", onNetwork);
window.addEventListener("offline", onNetwork);
onScopeDispose(() => {
  window.removeEventListener("online", onNetwork);
  window.removeEventListener("offline", onNetwork);
});
const online = computed(() => {
  const authState = auth.state.value;
  return networkUp.value && competitions.state.value !== "offline" && !(authState.status === "error" && authState.offline);
});

const outbox = createOutbox(store, (competitionId, adherentId, body) => competitionsApi.updateParticipant(competitionId, adherentId, body));
watch(uid, (u) => void outbox.load(u), { immediate: true });

/* Sent as soon as the API answers again (each successful poll), oldest first. */
async function replay(): Promise<void> {
  if (!uid.value || !online.value || !outbox.changes.value.size) {
    return;
  }
  const result = await outbox.replay(uid.value);
  if (!result) {
    return;
  }
  if (result.denied) {
    // Role lost: nothing kept on the device, unsent changes included
    outbox.forget();
    await store.clearAll();
    toast.show("🔒 Accès refusé par le serveur : les modifications faites hors ligne n'ont pas été envoyées.", 9000);
    return;
  }
  toast.show(replayMessage(result), result.refused.length ? 15_000 : 4000);
  void competitions.refresh();
}

watch([() => competitions.checkedAt.value, uid, online, () => outbox.changes.value.size], () => void replay());

// ---------------------------------------------------------------- Writes

const writer = createWriter({
  online: () => online.value,
  apply: (doc) => {
    const list = competitions.data.value ?? [];
    competitions.set(list.some((c) => c.id === doc.id) ? list.map((c) => (c.id === doc.id ? doc : c)) : [doc, ...list]);
  },
  dropped: (id) => competitions.set((competitions.data.value ?? []).filter((c) => c.id !== id)),
  reload: () => {
    void competitions.refresh();
    void competitors.refresh();
    void items.refresh();
    void coaches.refresh();
  },
  toast: (m, ms) => toast.show(m, ms),
});
provide(WRITER_KEY, writer);

const all = computed(() => sortCompetitions(competitions.data.value ?? []));
provide(COMPETITIONS_KEY, {
  competitions,
  all,
  competitors,
  members,
  coaches,
  items,
  canWrite,
  staff,
  contactsShown,
  online,
  outbox,
  uid,
  listPath: computed(() => route.matched[0]?.path ?? "/bureau/competitions"),
});
// Offline, the sub-pages for coaches open on a device keeping the contacts: unknown while their copy is being read
const staffCopy = computed(() => (competitors.data.value !== null ? true : competitors.state.value === "loading" ? null : false));

const syncInfo = computed(() => {
  const at = competitions.dataAt.value;
  const since = at ? ` — données du ${formatDateTime(at)}` : "";
  const state = competitions.state.value;
  const waiting = pendingLine(outbox.changes.value.size);
  if (competitions.httpStatus.value === 403) {
    return "🔒 Accès restreint";
  }
  if (state === "offline" || auth.state.value.status === "error") {
    return `📴 Hors ligne${since || " : aucune donnée sur cet appareil"}${waiting}`;
  }
  if (state === "error") {
    return `⚠️ Serveur injoignable — nouvel essai automatique${since}${waiting}`;
  }
  if (state === "loading") {
    return at ? `💾 Données du ${formatDateTime(at)}${waiting}` : waiting.slice(3);
  }
  return waiting.slice(3);
});
</script>

<template>
  <AppShell page="competitions" title="Compétitions" :sub="sub" :staff-copy="staffCopy" :sync="syncInfo">
    <RouterView />
    <UiToast :message="toast.message.value" />
  </AppShell>
</template>
