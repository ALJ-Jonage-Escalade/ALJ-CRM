<script setup lang="ts">
/* Layout of every page: navigation (side menu on desktop, bottom bar on phones), header with the
   signed-in account, and the sign-in / access gate. The page content is only rendered for a role allowed on
   the page (lib/access.ts), and the menu only lists those pages.
   Element ids are the ones of the former web/shared/alj-shell.js: the e2e tests rely on them.
   Printed, only the page content remains (Planning prints its grid). */
import { computed, inject, ref, watch } from "vue";
import { AUTH_KEY } from "../composables/auth";
import { canOpen, pageAccess, PAGES, verdict, type PageId } from "../lib/access";
import { API_KEY } from "../lib/api";
import { isStaff, roleLabel } from "../lib/roles";
import PageLink from "./PageLink.vue";
import VersionBadge from "./VersionBadge.vue";

/** sync: freshness of the page's data, next to the title (Adhérents). */
const props = defineProps<{ page: PageId; title: string; sync?: string }>();

const auth = inject(AUTH_KEY)!;
const api = inject(API_KEY)!;
const state = auth.state;

const who = computed(() => {
  const s = state.value;
  if (s.status === "loading") return "Vérification de la connexion…";
  if (s.status === "signedOut") return "Non connecté";
  return `${s.user.email || "(compte sans e-mail)"} · ${s.status === "signedIn" ? roleLabel(s.role) : "⚠️ rôle inconnu"}`;
});
const staff = computed(() => state.value.status === "signedIn" && isStaff(state.value.role));
const role = computed(() => (state.value.status === "signedIn" ? state.value.role : null));
const access = computed(() => verdict(state.value, pageAccess(props.page)));
// Every page until the role is known, then only those the role may open (none outside the staff)
const nav = computed(() => (state.value.status === "signedIn" ? PAGES.filter((p) => canOpen(role.value, p.access)) : PAGES));

// Club Google token (Gmail, Drive) expired or revoked: warned on every page, checked once per user
const googleExpired = ref(false);
const renewUrl = `/api/auth/google/login?return_to=${encodeURIComponent(location.pathname)}`;
watch(
  () => (staff.value && state.value.status === "signedIn" ? state.value.user.uid : null),
  async (uid) => {
    googleExpired.value = false;
    if (!uid) return;
    try {
      const res = await api("/api/auth/google/status");
      const body = res.ok ? ((await res.json()) as { status?: unknown }) : null;
      googleExpired.value = body?.status === "expired";
    } catch {
      // offline: no warning
    }
  },
  { immediate: true },
);

defineSlots<{ default(props: { role: typeof role.value }): unknown }>();
</script>

<template>
  <div class="min-h-dvh md:grid md:grid-cols-[232px_minmax(0,1fr)] print:block">
    <aside class="print:hidden md:sticky md:top-0 md:flex md:h-dvh md:flex-col md:gap-5 md:bg-side md:px-3 md:py-5 md:text-side-text">
      <div class="hidden px-2 md:block">
        <b class="block text-base text-slate-50">🧗 ALJ Escalade</b>
        <span class="mt-0.5 block text-xs text-slate-400">Bureau · <VersionBadge /></span>
      </div>
      <nav
        v-if="nav.length"
        aria-label="Navigation principale"
        class="fixed inset-x-0 bottom-0 z-40 flex h-16 justify-around border-t border-side-hover bg-side pb-[env(safe-area-inset-bottom)] md:static md:h-auto md:flex-col md:justify-start md:gap-0.5 md:border-0 md:pb-0"
      >
        <PageLink
          v-for="item in nav"
          :key="item.id"
          :href="item.href"
          :data-page="item.id"
          :aria-current="item.id === props.page ? 'page' : undefined"
          :class="[
            'flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 font-semibold text-side-text no-underline',
            'md:flex-none md:flex-row md:justify-start md:gap-2 md:rounded-lg md:px-3 md:py-2.5',
            item.id === props.page ? 'text-white md:bg-accent' : 'hover:text-white md:hover:bg-side-hover',
          ]"
        >
          <span aria-hidden="true" class="text-lg md:text-base">{{ item.icon }}</span>
          <span class="max-w-full truncate text-[10px] md:hidden">{{ item.short }}</span>
          <span class="hidden md:inline">{{ item.label }}</span>
        </PageLink>
      </nav>
      <div class="mt-auto hidden flex-col gap-2 px-2 md:flex">
        <a class="text-[13px] text-side-text no-underline hover:text-white hover:underline" href="/competitions?vue=mobile">📱 Version mobile</a>
      </div>
    </aside>

    <div class="min-w-0 px-4 pt-4 pb-28 md:px-7 md:pt-6 md:pb-10 print:p-0">
      <header class="mb-4 flex print:hidden flex-wrap items-center gap-x-4 gap-y-2">
        <h1 class="m-0 text-xl font-bold md:text-[22px]">{{ props.title }}</h1>
        <span id="sync-info" class="text-[13px] text-slate-500">{{ props.sync }}</span>
        <div class="ml-auto flex min-w-0 items-center gap-2">
          <span id="who" class="min-w-0 text-xs break-words text-slate-500">{{ who }}</span>
          <button
            v-if="state.status === 'signedIn' || state.status === 'error'"
            id="logout-btn"
            type="button"
            class="shrink-0 cursor-pointer rounded-lg bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-300"
            @click="auth.logout()"
          >🚪 Se déconnecter</button>
        </div>
      </header>

      <div
        v-show="googleExpired"
        id="google-auth-warning"
        class="mb-3.5 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-300 print:hidden bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800"
      >
        <span>⚠️ <b>Accès Google & BDD suspendus :</b> le jeton de connexion Google du club a expiré ou a été révoqué.</span>
        <a :href="renewUrl" class="rounded-lg bg-red-600 px-2.5 py-1.5 text-xs font-bold text-white no-underline">🔄 Renouveler l'accès</a>
      </div>

      <section
        v-if="access !== 'allow' && access !== 'pending'"
        id="gate"
        class="max-w-xl rounded-xl border border-slate-200 bg-white px-4.5 py-4 shadow-sm"
      >
        <template v-if="access === 'signIn'">
          <h2 class="mb-2 text-[17px] font-bold">🔐 Connexion</h2>
          <p class="my-1.5 leading-normal">Le bureau est réservé aux coachs et administrateurs du club. Connectez-vous avec votre compte Google.</p>
          <button id="gate-login" type="button" class="mt-2 cursor-pointer rounded-lg bg-accent px-3.5 py-2 text-[13px] font-bold text-white hover:bg-accent-dark" @click="auth.login()">🔑 Se connecter avec Google</button>
        </template>
        <template v-else-if="access === 'unverified' && state.status === 'error'">
          <h2 class="mb-2 text-[17px] font-bold">⚠️ Droits non vérifiés</h2>
          <p class="my-1.5 leading-normal">{{ state.message }}</p>
          <button id="gate-retry" type="button" class="mt-2 cursor-pointer rounded-lg bg-accent px-3.5 py-2 text-[13px] font-bold text-white hover:bg-accent-dark" @click="auth.retry()">🔄 Réessayer</button>
        </template>
        <template v-else-if="access === 'adminOnly'">
          <h2 class="mb-2 text-[17px] font-bold">⛔ Réservé aux administrateurs</h2>
          <p class="my-1.5 leading-normal">Cette page est réservée aux administrateurs du club.</p>
          <a href="/bureau/" class="mt-2 inline-block rounded-lg bg-accent px-3.5 py-2 text-[13px] font-bold text-white no-underline hover:bg-accent-dark">🏠 Retour à l'accueil</a>
        </template>
        <template v-else>
          <h2 class="mb-2 text-[17px] font-bold">⛔ Accès réservé</h2>
          <p class="my-1.5 leading-normal">Ce compte n'est pas autorisé à consulter le bureau. Déconnectez-vous et utilisez un compte coach ou administrateur.</p>
          <button id="gate-logout" type="button" class="mt-2 cursor-pointer rounded-lg bg-slate-200 px-3.5 py-2 text-[13px] font-bold text-slate-600 hover:bg-slate-300" @click="auth.logout()">🚪 Se déconnecter</button>
        </template>
      </section>

      <div v-if="access === 'allow'" id="content">
        <slot :role="role" />
      </div>

      <p class="mt-8 text-center text-[11px] text-slate-400 md:hidden print:hidden">🧗 ALJ Escalade · <VersionBadge /></p>
    </div>
  </div>
</template>
