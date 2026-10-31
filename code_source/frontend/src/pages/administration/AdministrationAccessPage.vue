<script setup lang="ts">
/* Administration › Accès: who may use the CRM and with which role (the only source of roles, server
   role_directory), the invitations (a role given on the first Google sign-in within 7 days) and the history of the
   changes. Every refusal (own access, last admin, address already listed) comes from the server and is shown as it is. */
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
  accessStatus,
  actionLabel,
  addFormError,
  authorLabel,
  dateTime,
  emailNotSent,
  invitationMessage,
  isOwnEntry,
  lastSignIn,
  roleChange,
  roleName,
  ROLE_OPTIONS,
  accessRole,
  statusLabel,
  type AccessRole,
} from "./access";

const adminApi = createAdminApi(inject(CLIENT_KEY)!);
const auth = inject(AUTH_KEY)!;
const toast = useToast();

const signedInEmail = computed(() => (auth.state.value.status === "signedIn" ? auth.state.value.user.email : ""));

const entries = ref<Schemas["AccessEntry"][]>([]);
const history = ref<Schemas["AccessHistoryEntry"][]>([]);
const loaded = ref(false);
const loadError = ref("");
/** When the list was read: the invitation statuses are worked out against it. */
const now = ref(new Date());
/** E-mail of the row whose change is being sent (its buttons wait). */
const busy = ref("");

async function load(): Promise<void> {
  try {
    [entries.value, history.value] = await Promise.all([adminApi.roles(), adminApi.history()]);
    now.value = new Date();
    loadError.value = "";
  } catch (e) {
    loadError.value = errorText(e);
  } finally {
    loaded.value = true;
  }
}

onMounted(load);
defineExpose({ reload: load });

/** Sends one change, then reloads both lists (the history gets its entry); the server's refusal is shown. `done`: the
   message, or a function of the answer giving it and how long it stays. */
async function change<T>(email: string, send: () => Promise<T>, done: string | ((answer: T) => [string, number])): Promise<boolean> {
  busy.value = email;
  try {
    const answer = await send();
    const [message, duration] = typeof done === "string" ? [done, undefined] : done(answer);
    toast.show(message, duration);
    return true;
  } catch (e) {
    toast.show(`❌ ${errorText(e)}`, 8000);
    return false;
  } finally {
    busy.value = "";
    await load();
  }
}

/** An invitation's toast: kept longer when its e-mail failed (the admin has to act). */
function invitationDone(invitation: Schemas["AccessInvitation"]): [string, number] {
  return [invitationMessage(invitation), invitation.email_sent ? 4000 : 12000];
}

// ------------------------------------------------------------ Invite a person
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
    if (await change(email, () => adminApi.invite(body), invitationDone)) {
      newEmail.value = "";
      newName.value = "";
    }
  } finally {
    adding.value = false;
  }
}

// ------------------------------------------------------------ Change an entry
function resend(entry: Schemas["AccessEntry"]): void {
  void change(entry.email, () => adminApi.resendInvitation(entry.email), invitationDone);
}

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
  const invitation = accessStatus(entry, now.value) !== "active";
  const ok = await dialogs.confirm(
    invitation
      ? {
          title: "Annuler l'invitation",
          message: `${entry.email} (${roleName(entry.role)}) ne pourra pas se connecter avec le lien reçu.`,
          confirmLabel: "Annuler l'invitation",
          variant: "danger",
        }
      : {
          title: "Retirer l'accès",
          message: `${entry.email} (${roleName(entry.role)}) ne pourra plus consulter les données du club.`,
          confirmLabel: "Retirer l'accès",
          variant: "danger",
        },
  );
  if (ok) {
    const done = invitation ? `🗑️ Invitation de ${entry.email} annulée.` : `🗑️ Accès de ${entry.email} retiré.`;
    await change(entry.email, () => adminApi.removeRole(entry.email), done);
  }
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
        <p class="mb-3 text-xs text-slate-500">
          Une invitation envoie un lien par e-mail : la personne reçoit son rôle en se connectant avec un compte Google de cette adresse
          dans les 7 jours. Passé ce délai, utilisez « Renvoyer ».
        </p>

        <form
          class="mb-3 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3"
          novalidate
          @submit.prevent="add"
        >
          <div class="min-w-56 flex-1">
            <label for="access-email" :class="LABEL">Adresse e-mail (compte Google)</label>
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
          <UiButton type="submit" small data-testid="access-add" :busy="adding && 'Invitation…'">✉️ Inviter</UiButton>
          <p v-if="addError" data-testid="access-add-error" role="alert" class="w-full text-xs text-red-700">{{ addError }}</p>
        </form>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-[13px]" data-testid="access-table">
            <thead class="text-[11.5px] text-slate-500 uppercase">
              <tr>
                <th class="py-1.5 pr-3">Nom</th>
                <th class="py-1.5 pr-3">E-mail</th>
                <th class="py-1.5 pr-3">Rôle</th>
                <th class="py-1.5 pr-3">Statut</th>
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
                <td class="py-1.5 pr-3" data-testid="entry-status">
                  <span
                    :class="{
                      'text-amber-700': accessStatus(entry, now) === 'invited',
                      'font-semibold text-red-700': accessStatus(entry, now) === 'expired',
                    }"
                  >
                    {{ statusLabel(entry, now) }}
                  </span>
                  <span v-if="emailNotSent(entry)" data-testid="entry-email-not-sent" class="block text-xs text-red-700">
                    E-mail non envoyé
                  </span>
                </td>
                <td class="py-1.5 pr-3 whitespace-nowrap" data-testid="entry-last-sign-in">{{ lastSignIn(entry.last_sign_in_at) }}</td>
                <td class="py-1.5 text-right whitespace-nowrap">
                  <UiButton
                    v-if="accessStatus(entry, now) !== 'active'"
                    small
                    variant="muted"
                    class="mr-1.5"
                    data-testid="entry-resend"
                    :disabled="busy === entry.email"
                    @click="resend(entry)"
                  >
                    ✉️ Renvoyer
                  </UiButton>
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
        <h2 class="text-base font-bold">🕘 Historique</h2>
        <p class="mb-3 text-xs text-slate-500">Les 50 derniers changements d'accès, le plus récent en premier. Non modifiable.</p>
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
