<script setup lang="ts">
/* Administration › Accès: who may use the CRM and with which role (the only source of roles, server
   role_directory), the access requests of the accounts that signed in without access, and the history of the changes.
   Every refusal (own access, last admin, address already listed) comes from the server and is shown as it is. */
import { computed, inject, onMounted, ref } from "vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiCard from "../../components/ui/UiCard.vue";
import UiToast from "../../components/ui/UiToast.vue";
import { AUTH_KEY } from "../../composables/auth";
import { dialogs } from "../../composables/dialogs";
import { useToast } from "../../composables/toast";
import { CLIENT_KEY, errorText, type Schemas } from "../../lib/client";
import { createAdminApi } from "../../services/admin";
import {
  actionLabel,
  addFormError,
  authorLabel,
  dateTime,
  isOwnEntry,
  lastSignIn,
  roleChange,
  roleName,
  ROLE_OPTIONS,
  accessRole,
  type AccessRole,
} from "./access";

const adminApi = createAdminApi(inject(CLIENT_KEY)!);
const auth = inject(AUTH_KEY)!;
const toast = useToast();

const signedInEmail = computed(() => (auth.state.value.status === "signedIn" ? auth.state.value.user.email : ""));

const entries = ref<Schemas["AccessEntry"][]>([]);
const requests = ref<Schemas["AccessRequest"][]>([]);
const history = ref<Schemas["AccessHistoryEntry"][]>([]);
const loaded = ref(false);
const loadError = ref("");
/** E-mail of the row whose change is being sent (its buttons wait). */
const busy = ref("");

async function load(): Promise<void> {
  try {
    [entries.value, requests.value, history.value] = await Promise.all([adminApi.roles(), adminApi.requests(), adminApi.history()]);
    loadError.value = "";
  } catch (e) {
    loadError.value = errorText(e);
  } finally {
    loaded.value = true;
  }
}

onMounted(load);
defineExpose({ reload: load });

/** Sends one change, then reloads the three lists (the history gets its entry); the server's refusal is shown. */
async function change(email: string, send: () => Promise<unknown>, done: string): Promise<boolean> {
  busy.value = email;
  try {
    await send();
    toast.show(done);
    return true;
  } catch (e) {
    toast.show(`❌ ${errorText(e)}`, 8000);
    return false;
  } finally {
    busy.value = "";
    await load();
  }
}

// ------------------------------------------------------------ Add a person
const newEmail = ref("");
const newName = ref("");
const newRole = ref<AccessRole>("coach");
const addError = ref("");
const adding = ref(false);

async function add(): Promise<void> {
  addError.value = addFormError(newEmail.value);
  if (addError.value) {
    return;
  }
  const email = newEmail.value.trim();
  const body = { email, role: newRole.value, display_name: newName.value.trim() };
  adding.value = true;
  try {
    if (await change(email, () => adminApi.addRole(body), `✅ Accès ${roleName(body.role)} donné à ${email}.`)) {
      newEmail.value = "";
      newName.value = "";
    }
  } finally {
    adding.value = false;
  }
}

// ------------------------------------------------------------ Change an entry
function onRoleChange(entry: Schemas["AccessEntry"], event: Event): void {
  const role = event.target instanceof HTMLSelectElement ? accessRole(event.target.value) : null;
  if (!role) {
    return;
  }
  void change(entry.email, () => adminApi.updateRole(entry.email, { role }), `✅ ${entry.email} : ${roleName(role)}.`);
}

async function rename(entry: Schemas["AccessEntry"]): Promise<void> {
  const name = await dialogs.prompt({
    title: "Nom affiché",
    label: `Nom de ${entry.email}`,
    value: entry.display_name,
    confirmLabel: "Enregistrer",
  });
  if (name === null) {
    return;
  }
  await change(entry.email, () => adminApi.updateRole(entry.email, { display_name: name }), "✅ Nom enregistré.");
}

async function remove(entry: Schemas["AccessEntry"]): Promise<void> {
  const ok = await dialogs.confirm({
    title: "Retirer l'accès",
    message: `${entry.email} (${roleName(entry.role)}) ne pourra plus consulter les données du club.`,
    confirmLabel: "Retirer l'accès",
    variant: "danger",
  });
  if (ok) {
    await change(entry.email, () => adminApi.removeRole(entry.email), `🗑️ Accès de ${entry.email} retiré.`);
  }
}

// ------------------------------------------------------------ Access requests
/** Role chosen for each request before granting it. */
const grantRoles = ref<Record<string, AccessRole>>({});

function grant(request: Schemas["AccessRequest"]): void {
  const role = grantRoles.value[request.email] ?? "readonly";
  void change(request.email, () => adminApi.grantRequest(request.email, { role }), `✅ Accès ${roleName(role)} donné à ${request.email}.`);
}

function dismiss(request: Schemas["AccessRequest"]): void {
  void change(request.email, () => adminApi.dismissRequest(request.email), `🙈 Demande de ${request.email} ignorée (30 jours).`);
}

const FIELD = "rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[13px]";
const LABEL = "mb-1 block text-[11.5px] font-semibold text-slate-500 uppercase";
</script>

<template>
  <div class="flex flex-col gap-3">
    <p v-if="!loaded" class="text-sm text-slate-500" role="status">Chargement des accès…</p>
    <p
      v-else-if="loadError"
      data-testid="access-load-error"
      role="alert"
      class="rounded-lg border border-red-300 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800"
    >
      ❌ {{ loadError }}
      <UiButton small variant="muted" class="ml-2" @click="load">🔄 Réessayer</UiButton>
    </p>

    <template v-else>
      <UiCard>
        <h2 class="text-base font-bold">👥 Accès</h2>
        <p class="mb-3 text-xs text-slate-500">
          Les personnes autorisées à se connecter, avec leur rôle. Un changement s'applique en moins d'une minute.
        </p>

        <form
          class="mb-3 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3"
          novalidate
          @submit.prevent="add"
        >
          <div class="min-w-56 flex-1">
            <label for="access-email" :class="LABEL">Adresse e-mail Google</label>
            <input
              id="access-email"
              v-model="newEmail"
              data-testid="access-email"
              type="email"
              autocomplete="off"
              placeholder="prenom.nom@exemple.fr"
              :class="[FIELD, 'w-full']"
            />
          </div>
          <div class="min-w-40 flex-1">
            <label for="access-name" :class="LABEL">Nom affiché</label>
            <input id="access-name" v-model="newName" data-testid="access-name" type="text" :class="[FIELD, 'w-full']" />
          </div>
          <div>
            <label for="access-role" :class="LABEL">Rôle</label>
            <select id="access-role" v-model="newRole" data-testid="access-role" :class="FIELD">
              <option v-for="option in ROLE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>
          <UiButton type="submit" small data-testid="access-add" :busy="adding && 'Ajout…'">➕ Ajouter</UiButton>
          <p v-if="addError" data-testid="access-add-error" role="alert" class="w-full text-xs text-red-700">{{ addError }}</p>
        </form>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-[13px]" data-testid="access-table">
            <thead class="text-[11.5px] text-slate-500 uppercase">
              <tr>
                <th class="py-1.5 pr-3">Nom</th>
                <th class="py-1.5 pr-3">E-mail</th>
                <th class="py-1.5 pr-3">Rôle</th>
                <th class="py-1.5 pr-3">Dernière connexion</th>
                <th class="py-1.5"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in entries" :key="entry.email" :data-email="entry.email" class="border-t border-slate-100">
                <td class="py-1.5 pr-3">{{ entry.display_name || "—" }}</td>
                <td class="py-1.5 pr-3 break-all">{{ entry.email }}</td>
                <td class="py-1.5 pr-3">
                  <select
                    :value="entry.role"
                    data-testid="entry-role"
                    :aria-label="`Rôle de ${entry.email}`"
                    :disabled="busy === entry.email || isOwnEntry(entry.email, signedInEmail)"
                    :title="isOwnEntry(entry.email, signedInEmail) ? 'Vous ne pouvez pas changer votre propre rôle' : undefined"
                    :class="FIELD"
                    @change="onRoleChange(entry, $event)"
                  >
                    <option v-for="option in ROLE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </td>
                <td class="py-1.5 pr-3 whitespace-nowrap" data-testid="entry-last-sign-in">{{ lastSignIn(entry.last_sign_in_at) }}</td>
                <td class="py-1.5 text-right whitespace-nowrap">
                  <UiButton small variant="muted" data-testid="entry-rename" :disabled="busy === entry.email" @click="rename(entry)">
                    ✏️ Nom
                  </UiButton>
                  <UiButton
                    small
                    variant="danger"
                    class="ml-1.5"
                    data-testid="entry-remove"
                    :disabled="busy === entry.email || isOwnEntry(entry.email, signedInEmail)"
                    :title="isOwnEntry(entry.email, signedInEmail) ? 'Vous ne pouvez pas retirer votre propre accès' : undefined"
                    @click="remove(entry)"
                  >
                    🗑️ Retirer
                  </UiButton>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>

      <UiCard>
        <h2 class="text-base font-bold">📨 Demandes d'accès</h2>
        <p class="mb-3 text-xs text-slate-500">
          Les comptes Google qui se sont connectés sans accès. Une demande ignorée ne revient pas avant 30 jours ; sans réponse, elle
          disparaît après 30 jours.
        </p>
        <p v-if="!requests.length" data-testid="requests-empty" class="text-[13px] text-slate-500">Aucune demande en attente.</p>
        <ul v-else class="flex flex-col gap-2" data-testid="requests">
          <li
            v-for="request in requests"
            :key="request.email"
            :data-email="request.email"
            class="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 px-3 py-2"
          >
            <div class="min-w-48 flex-1">
              <div class="font-semibold break-all">{{ request.email }}</div>
              <div class="text-xs text-slate-500">
                {{ request.google_display_name || "Nom Google inconnu" }} · le {{ dateTime(request.last_requested_at) }}
              </div>
            </div>
            <select
              v-model="grantRoles[request.email]"
              data-testid="request-role"
              :aria-label="`Rôle pour ${request.email}`"
              :class="FIELD"
            >
              <option :value="undefined" disabled>Rôle…</option>
              <option v-for="option in ROLE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <UiButton
              small
              data-testid="request-grant"
              :disabled="busy === request.email || !grantRoles[request.email]"
              @click="grant(request)"
            >
              ✅ Accorder
            </UiButton>
            <UiButton small variant="muted" data-testid="request-dismiss" :disabled="busy === request.email" @click="dismiss(request)">
              Ignorer
            </UiButton>
          </li>
        </ul>
      </UiCard>

      <UiCard>
        <h2 class="text-base font-bold">🕘 Historique</h2>
        <p class="mb-3 text-xs text-slate-500">Chaque changement d'accès, le plus récent en premier. Non modifiable.</p>
        <p v-if="!history.length" class="text-[13px] text-slate-500">Aucun changement enregistré.</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-left text-[13px]" data-testid="history">
            <thead class="text-[11.5px] text-slate-500 uppercase">
              <tr>
                <th class="py-1.5 pr-3">Date</th>
                <th class="py-1.5 pr-3">Par</th>
                <th class="py-1.5 pr-3">Action</th>
                <th class="py-1.5 pr-3">Personne</th>
                <th class="py-1.5">Rôle</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in history" :key="`${item.at}-${index}`" class="border-t border-slate-100">
                <td class="py-1.5 pr-3 whitespace-nowrap">{{ dateTime(item.at) }}</td>
                <td class="py-1.5 pr-3 break-all">{{ authorLabel(item.author) }}</td>
                <td class="py-1.5 pr-3">{{ actionLabel(item.action) }}</td>
                <td class="py-1.5 pr-3 break-all">{{ item.target_email }}</td>
                <td class="py-1.5 whitespace-nowrap">{{ roleChange(item) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>
    </template>

    <UiToast :message="toast.message.value" />
  </div>
</template>
