<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";
import PageLink from "../components/PageLink.vue";
import { canOpen, pageAccess, pageScreen, PAGES, REFUSED_QUERY, shownOn, type Access, type Screen } from "../lib/access";
import type { Role } from "../lib/roles";

/* Links to the migrated pages stay in the app; the others load their former page. Only the cards the role may open are
   shown, and Adhérents or the directory depending on the screen, as in the menu. */
const LINKS: { href: string; title: string; text: string; access: Access; screen?: Screen }[] = [
  {
    href: "/bureau/adherents",
    title: "👥 Adhérents",
    text: "Liste des adhérents, filtre par tarif et fiche détaillée.",
    access: pageAccess("adherents"),
    screen: pageScreen("adherents"),
  },
  {
    href: "/index",
    title: "📇 Annuaire",
    text: "Coordonnées et contacts d'urgence des adhérents, consultables hors ligne.",
    access: pageAccess("annuaire"),
    screen: pageScreen("annuaire"),
  },
  {
    href: "/bureau/communications",
    title: "✉️ Communications",
    text: "Modèles d'e-mails et de messages du club.",
    access: pageAccess("communications"),
  },
  { href: "/bureau/outils", title: "🛠️ Outils", text: "Carte interactive et analyse des effectifs.", access: pageAccess("outils") },
  {
    href: "/bureau/competitions",
    title: "🏆 Compétitions",
    text: "Compétitions, participants et paiements HelloAsso.",
    access: pageAccess("competitions"),
  },
  {
    href: "/bureau/planning",
    title: "📅 Créneaux & Planning",
    text: "Création, modification des créneaux, animateurs, tarifs et impression du planning.",
    access: pageAccess("planning"),
  },
  {
    href: "/bureau/parametres",
    title: "⚙️ Paramètres",
    text: "Connexion Google du club, statut de la base de données et services associés.",
    access: pageAccess("parametres"),
  },
];
const BANNER = "https://alj-escalade.fr/wp-content/uploads/2026/09/De-nouveaux-blocs-tous-les-15-jours-3-1024x512.png";

const linksFor = (role: Role) => LINKS.filter((link) => canOpen(role, link.access));

// Sent back by the router guards from an admin page: only a known page is named
const route = useRoute();
const refused = computed(() => PAGES.find((p) => p.href === route.query[REFUSED_QUERY])?.label);
</script>

<template>
  <AppShell page="accueil" title="Accueil">
    <template #default="{ role }">
      <p
        v-if="refused"
        id="refused-page"
        role="status"
        class="mb-3.5 rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-2.5 text-[13px] text-amber-900"
      >
        ⛔ La page {{ refused }} est réservée aux administrateurs.
      </p>
      <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3.5">
        <PageLink
          v-for="link in linksFor(role)"
          :key="link.href"
          :href="link.href"
          :class="shownOn(link.screen ?? 'any', 'block')"
          class="rounded-xl border border-slate-200 bg-white px-4.5 py-4 text-slate-800 no-underline shadow-sm hover:border-accent"
        >
          <b class="mb-1 block text-base">{{ link.title }}</b>
          <span class="text-[13px] leading-snug text-slate-500">{{ link.text }}</span>
        </PageLink>
      </div>
      <img
        :src="BANNER"
        alt="De nouveaux blocs tous les 15 jours — ALJ Escalade"
        loading="lazy"
        class="mt-5.5 max-h-[480px] w-full rounded-2xl border border-slate-200 object-cover shadow-md"
      />
      <p class="mt-4.5 text-slate-500">
        Connecté en tant que {{ role === "admin" ? "administrateur" : "coach" }}. Les données sont lues depuis la base du club et
        actualisées automatiquement.
      </p>
    </template>
  </AppShell>
</template>
