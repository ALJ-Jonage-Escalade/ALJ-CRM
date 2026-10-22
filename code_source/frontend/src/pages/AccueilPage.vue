<script setup lang="ts">
import AppShell from "../components/AppShell.vue";

/* Pages not migrated yet are links to their former page (full page load). */
const LINKS = [
  { href: "/bureau/adherents", title: "👥 Adhérents", text: "Liste des adhérents, filtre par tarif et fiche détaillée." },
  { href: "/bureau/communications", title: "✉️ Communications", text: "Modèles d'e-mails et de messages du club." },
  { href: "/bureau/outils", title: "🛠️ Outils", text: "Carte interactive et analyse des effectifs." },
  { href: "/bureau/competitions", title: "🏆 Compétitions", text: "Compétitions, participants et paiements HelloAsso." },
  { href: "/bureau/planning", title: "📅 Créneaux & Planning", text: "Création, modification des créneaux, animateurs, tarifs et impression du planning." },
  { href: "/bureau/parametres", title: "⚙️ Paramètres", text: "Connexion Google du club, statut de la base de données et services associés." },
  { href: "/competitions?vue=mobile", title: "📱 Version mobile", text: "Ouvre l'application smartphone et mémorise ce choix sur cet appareil." },
];
const BANNER = "https://alj-escalade.fr/wp-content/uploads/2026/09/De-nouveaux-blocs-tous-les-15-jours-3-1024x512.png";
</script>

<template>
  <AppShell page="accueil" title="Accueil">
    <template #default="{ role }">
      <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3.5">
        <a
          v-for="link in LINKS"
          :key="link.href"
          :href="link.href"
          class="block rounded-xl border border-slate-200 bg-white px-4.5 py-4 text-slate-800 no-underline shadow-sm hover:border-accent"
        >
          <b class="mb-1 block text-base">{{ link.title }}</b>
          <span class="text-[13px] leading-snug text-slate-500">{{ link.text }}</span>
        </a>
      </div>
      <img
        :src="BANNER"
        alt="De nouveaux blocs tous les 15 jours — ALJ Escalade"
        loading="lazy"
        class="mt-5.5 max-h-[480px] w-full rounded-2xl border border-slate-200 object-cover shadow-md"
      >
      <p class="mt-4.5 text-slate-500">
        Connecté en tant que {{ role === "admin" ? "administrateur" : "coach" }}. Les données sont lues depuis la base du club et actualisées automatiquement.
      </p>
    </template>
  </AppShell>
</template>
