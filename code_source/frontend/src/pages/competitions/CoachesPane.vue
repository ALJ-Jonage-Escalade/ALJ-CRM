<script setup lang="ts">
/* « Coachs » (coaches and admins): the club's coaches and the competitions each one follows. Renaming a coach renames
   them on their competitions, deleting one takes them off (server side). */
import { computed, inject, ref } from "vue";
import { RouterLink } from "vue-router";
import UiButton from "../../components/ui/UiButton.vue";
import { CLIENT_KEY } from "../../lib/client";
import { createCompetitionsApi } from "../../services/competitions";
import { coachedBy, period, sortCompetitions, type Coach, type Competition } from "./competitions";
import { WRITER_KEY } from "./writer";
import { dialogs } from "../../composables/dialogs";

/** listPath: address of the competitions list (the page's index route), where a competition opens. */
const props = defineProps<{ coaches: readonly Coach[] | null; competitions: readonly Competition[]; listPath: string }>();
const emit = defineEmits<{ changed: [] }>();
const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!);
const writer = inject(WRITER_KEY)!;

const sorted = computed(() => (props.coaches ?? []).slice().sort((a, b) => (a.nom ?? "").localeCompare(b.nom ?? "", "fr")));
const newName = ref("");
const editing = ref<number | null>(null);
const editName = ref("");

async function create(): Promise<void> {
  const nom = newName.value.trim();
  if (!nom) {
    return writer.toast("⚠️ Le nom du coach est obligatoire.");
  }
  if (await writer.run(() => competitionsApi.createCoach(nom), { done: "✅ Coach ajouté." })) {
    newName.value = "";
    emit("changed");
  }
}

function edit(c: Coach): void {
  editing.value = c.id;
  editName.value = c.nom ?? "";
}

async function rename(c: Coach): Promise<void> {
  const nom = editName.value.trim();
  if (!nom) {
    return writer.toast("⚠️ Le nom du coach est obligatoire.");
  }
  if (
    await writer.run(() => competitionsApi.renameCoach(c.id, nom), {
      done: "✅ Coach mis à jour.",
    })
  ) {
    editing.value = null;
    emit("changed");
  }
}

async function remove(c: Coach): Promise<void> {
  if (
    !(await dialogs.confirm({
      title: "Supprimer le coach",
      message: `Supprimer le coach « ${c.nom} » ? Il sera retiré de toutes ses compétitions.`,
      confirmLabel: "Supprimer",
      variant: "danger",
    }))
  ) {
    return;
  }
  if (
    await writer.run(() => competitionsApi.removeCoach(c.id), {
      done: "🗑 Coach supprimé.",
    })
  ) {
    emit("changed");
  }
}

const field = "rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[13px]";
</script>

<template>
  <section aria-label="Coachs" data-testid="coaches-pane">
    <form class="mb-3 flex flex-wrap gap-2" @submit.prevent="create">
      <input v-model="newName" data-testid="coach-new-name" placeholder="Nom du nouveau coach" :class="[field, 'min-w-48 flex-1']" />
      <UiButton type="submit" data-testid="coach-add" :busy="writer.busy.value && !editing && 'Ajout…'">➕ Ajouter</UiButton>
    </form>
    <p v-if="!coaches" class="text-xs text-slate-500">⏳ Chargement des coachs…</p>
    <ul class="grid gap-2 xl:grid-cols-2">
      <li
        v-for="c in sorted"
        :key="c.id"
        data-testid="coach-card"
        class="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 shadow-sm"
      >
        <form v-if="editing === c.id" class="flex flex-wrap gap-2" @submit.prevent="rename(c)">
          <input v-model="editName" data-testid="coach-edit-name" :class="[field, 'min-w-40 flex-1']" />
          <UiButton variant="muted" small @click="editing = null">Annuler</UiButton>
          <UiButton type="submit" small data-testid="coach-save">💾 Enregistrer</UiButton>
        </form>
        <div v-else class="flex items-center justify-between gap-2">
          <b class="text-[14.5px]" data-testid="coach-name">🏃 {{ c.nom }}</b>
          <span class="flex gap-1.5">
            <UiButton variant="muted" small data-testid="coach-edit" @click="edit(c)">✏️ Renommer</UiButton>
            <UiButton variant="danger" small data-testid="coach-delete" @click="remove(c)">🗑</UiButton>
          </span>
        </div>
        <ul class="mt-1.5 text-xs" data-testid="coach-competitions">
          <li v-for="comp in sortCompetitions(coachedBy(competitions, c))" :key="comp.id">
            <RouterLink
              :to="{ path: listPath, query: { id: String(comp.id) } }"
              data-testid="coach-competition"
              class="text-slate-700 no-underline hover:text-accent"
            >
              🏆 {{ comp.nom }} · {{ period(comp) }}
            </RouterLink>
          </li>
          <li v-if="!coachedBy(competitions, c).length" class="text-slate-400">Aucune épreuve assignée.</li>
        </ul>
      </li>
      <li v-if="coaches && !coaches.length" class="rounded-xl border border-slate-200 bg-white px-4 py-6 text-center text-slate-500">
        Aucun coach enregistré.
      </li>
    </ul>
  </section>
</template>
