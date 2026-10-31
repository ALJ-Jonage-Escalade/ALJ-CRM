<script setup lang="ts">
/* Layout of every page: navigation (side menu on desktop, bottom bar on phones) with the signed-in account, header,
   and the sign-in / access gate. The page content is only rendered for a role allowed on the page (lib/access.ts),
   and the menu only lists those pages. Without any page to offer, the gate is shown alone, full screen.
   Element ids are the ones of the former web/shared/alj-shell.js: the e2e tests rely on them.
   A page with sub-pages (lib/access.ts subPages) names the open one (`sub`): listed under the page in the side menu,
   as a strip under the title on phones. A sub-page the session may not open sends back to the page's index route,
   which says why (?reserve=<sub-page id>).
   Printed, only the page content remains (Planning prints its grid). */
import { computed, inject, ref, watch, watchEffect } from "vue";
import { routeLocationKey, routerKey } from "vue-router";
import { AUTH_KEY } from "../composables/auth";
import { SIGN_IN_ERROR_KEY } from "../composables/signIn";
import {
  canOpen,
  OFFLINE_PAGES,
  PAGES,
  pageVerdict,
  REFUSED_QUERY,
  shownOn,
  subHref,
  subPages,
  subVerdict,
  type PageId,
} from "../lib/access";
import { API_KEY } from "../lib/api";
import { formatDate, parseDate } from "../lib/format";
import { isStaff, roleLabel } from "../lib/roles";
import { isEmulator } from "../lib/runtime";
import { offlineStore, STORE_KEY } from "../lib/store";
import { logoutWarning } from "../pages/competitions/outbox";
import AppBrand from "./AppBrand.vue";
import PageLink from "./PageLink.vue";
import SubNav, { type SubNavItem } from "./SubNav.vue";
import UiButton from "./ui/UiButton.vue";
import VersionBadge from "./VersionBadge.vue";
import { dialogs } from "../composables/dialogs";

/** sync: freshness of the page's data, next to the title (Adhérents). A page readable offline (PAGES offlineRead) gets
    no role in its slot when it shows the copy kept on the device. sub: the open sub-page (its id); staffCopy: offline,
    whether the device holds a staff copy of the page's data (null while it is being read), see subVerdict. */
const props = defineProps<{ page: PageId; title: string; sync?: string; sub?: string; staffCopy?: boolean | null }>();

const auth = inject(AUTH_KEY)!;
const api = inject(API_KEY)!;
const store = inject(STORE_KEY, null) ?? offlineStore();
const state = auth.state;
/** « 06/11/2026 » when the signed-in address was invited but did not sign in in time; empty otherwise. */
const invitationExpiredOn = computed(() => {
  const expired = state.value.status === "signedIn" ? parseDate(state.value.invitationExpiredAt) : null;
  return expired ? formatDate(expired) : "";
});

/* Changes made offline and not sent yet (competitions outbox) go with the store on logout: asked first, on any page. */
async function logout(): Promise<void> {
  const s = state.value;
  const waiting = s.status === "signedIn" || s.status === "error" ? (await store.queued(s.user.uid)).length : 0;
  if (
    waiting &&
    !(await dialogs.confirm({
      title: "Se déconnecter",
      message: logoutWarning(waiting),
      confirmLabel: "Se déconnecter",
      variant: "warning",
    }))
  ) {
    return;
  }
  await auth.logout();
}

const email = computed(() =>
  state.value.status === "signedIn" || state.value.status === "error" ? state.value.user.email || "(compte sans e-mail)" : "",
);
// The shell (outside the full-screen gate) is only shown with a user: signed in, or role unchecked offline
const who = computed(() => `${email.value} · ${state.value.status === "signedIn" ? roleLabel(state.value.role) : "⚠️ rôle inconnu"}`);
const staff = computed(() => state.value.status === "signedIn" && isStaff(state.value.role));
const role = computed(() => (state.value.status === "signedIn" ? state.value.role : null));
const access = computed(() => pageVerdict(state.value, props.page));
const offline = computed(() => state.value.status === "error" && state.value.offline);
/* No page to offer (signed out, account refused, role unchecked with the network up): the gate alone, full screen,
   without the menu. Offline, the menu stays: it leads to the pages readable offline. */
const fullscreen = computed(() => {
  const pageVerdict = access.value;
  return (
    pageVerdict === "pending" || pageVerdict === "signIn" || pageVerdict === "noAccess" || (pageVerdict === "unverified" && !offline.value)
  );
});
const signInError = inject(SIGN_IN_ERROR_KEY, ref(null));
// Every page until the role is known, then only those the role may open (none outside the staff)
const nav = computed(() => (state.value.status === "signedIn" ? PAGES.filter((p) => canOpen(role.value, p.access)) : PAGES));

// ---------------------------------------------------------------- Sub-pages

// Absent from the components' tests mounted without a router
const router = inject(routerKey, null);
const route = inject(routeLocationKey, null);
const subs = computed(() =>
  subPages(props.page).map((sub) => ({
    sub,
    verdict: subVerdict(state.value, sub, props.staffCopy === undefined ? false : props.staffCopy),
  })),
);
const current = computed(() => subs.value.find(({ sub }) => sub.id === props.sub));
// Listed with at least two entries: a role seeing a single one gets the page as without sub-menu
const subMenu = computed<SubNavItem[]>(() => {
  const listed = subs.value.filter(({ verdict }) => verdict === "allow" || verdict === "disabled");
  return listed.length > 1
    ? listed.map(({ sub, verdict }) => ({ id: sub.id, label: sub.label, href: subHref(props.page, sub), disabled: verdict === "disabled" }))
    : [];
});
const subAllowed = computed(() => !current.value || current.value.verdict === "allow");
watch(
  () => current.value?.verdict,
  (verdict) => {
    const index = subs.value[0]?.sub;
    const sub = current.value?.sub;
    if (router && index && sub && sub !== index && (verdict === "hidden" || verdict === "disabled")) {
      void router.replace({ path: subHref(props.page, index), query: { [REFUSED_QUERY]: sub.id } });
    }
  },
  { immediate: true },
);
// Sent back from a sub-page: only a known one is named
const refusedSub = computed(() => {
  const sub = subPages(props.page).find((s) => s.path && s.id === route?.query[REFUSED_QUERY]);
  if (!sub) {
    return "";
  }
  if (offline.value) {
    return `📴 La page ${sub.label} n'est consultable qu'en ligne.`;
  }
  return `⛔ La page ${sub.label} est réservée aux ${sub.access === "admin" ? "administrateurs" : "coachs et administrateurs"}.`;
});

const pageLabel = computed(() => PAGES.find((p) => p.id === props.page)!.label);
// The index sub-page is the page itself: its title (plans/sub-menus.md D7)
const heading = computed(() => (current.value?.sub.path ? current.value.sub.label : props.title));
watchEffect(() => {
  document.title = current.value?.sub.path ? `${heading.value} · ${pageLabel.value} — ALJ Escalade` : `${heading.value} — ALJ Escalade`;
});

// Club Google token (Gmail, Drive) expired or revoked: warned on every page, checked once per user
const googleExpired = ref(false);
const renewUrl = `/api/auth/google/login?return_to=${encodeURIComponent(location.pathname)}`;
watch(
  () => (staff.value && state.value.status === "signedIn" ? state.value.user.uid : null),
  async (uid) => {
    googleExpired.value = false;
    if (!uid || isEmulator) {
      return;
    }
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
  <!-- Full screen: the gate alone on the menu's background; bottom padding keeps it clear of the dev banner -->
  <div
    v-if="fullscreen"
    id="login-screen"
    class="flex min-h-dvh flex-col items-center justify-center gap-5 bg-side px-4 pt-[max(2rem,env(safe-area-inset-top))] pb-[max(5rem,env(safe-area-inset-bottom))] text-side-text"
  >
    <AppBrand large class="text-center" />
    <p v-if="access === 'pending'" id="session-check" role="status" class="text-sm text-slate-300">Vérification de la connexion…</p>
    <section v-else id="gate" class="w-full max-w-sm rounded-xl bg-white px-4.5 py-4 text-slate-900 shadow-lg">
      <template v-if="access === 'signIn'">
        <div class="flex flex-col">
          <h2 class="mb-2 text-[17px] font-bold">🔐 Connexion</h2>
          <p class="my-1.5 leading-normal">
            {{
              isEmulator
                ? "Environnement local : connectez-vous avec un compte de test de l'émulateur."
                : "Le bureau est réservé aux coachs et administrateurs du club. Connectez-vous avec votre compte Google."
            }}
          </p>
          <p
            v-if="signInError"
            data-testid="sign-in-error"
            role="alert"
            class="my-2 rounded-lg border border-red-300 bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800"
          >
            ❌ {{ signInError }}
          </p>
          <UiButton id="gate-login" class="mt-2" @click="auth.login()">
            {{ isEmulator ? "🔑 Choisir un compte de test" : "🔑 Se connecter avec Google" }}
          </UiButton>
        </div>
      </template>
      <template v-else-if="access === 'unverified' && state.status === 'error'">
        <h2 class="mb-2 text-[17px] font-bold">⚠️ Droits non vérifiés</h2>
        <p class="my-1.5 leading-normal">{{ state.message }}</p>
        <div class="mt-2 flex flex-wrap gap-2">
          <UiButton id="gate-retry" @click="auth.retry()">🔄 Réessayer</UiButton>
          <UiButton id="gate-logout" variant="muted" @click="logout">🚪 Se déconnecter</UiButton>
        </div>
      </template>
      <template v-else-if="state.status === 'signedIn'">
        <h2 class="mb-2 text-[17px] font-bold">⛔ Accès réservé</h2>
        <p class="my-1.5 leading-normal">
          Connecté en tant que
          <b data-testid="gate-account">{{ email }}</b>
          <template v-if="state.role !== null">
            : ce compte n'est pas autorisé à consulter le bureau. Déconnectez-vous et utilisez un compte coach ou administrateur.
          </template>
          <template v-else>.</template>
        </p>
        <!-- Without any role: access is by invitation only (Administration › Accès), to this exact Google address -->
        <p
          v-if="state.role === null && invitationExpiredOn"
          data-testid="gate-invitation-expired"
          class="my-2 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-[13px] text-amber-900"
        >
          ⏰ Votre invitation a expiré le {{ invitationExpiredOn }}. Demandez à un administrateur du club de vous la renvoyer.
        </p>
        <p
          v-else-if="state.role === null"
          data-testid="gate-not-invited"
          class="my-2 rounded-lg border border-sky-200 bg-sky-50 px-3.5 py-2.5 text-[13px] text-sky-900"
        >
          ✉️ Le bureau est accessible sur invitation, et ce compte Google n'en a pas. Demandez à un administrateur du club de vous inviter à
          cette adresse, ou déconnectez-vous pour utiliser le compte Google qui a reçu l'invitation.
        </p>
        <!-- No menu here: the pages the role may still open (the competitions for a read-only account) -->
        <p v-if="nav.length" data-testid="gate-pages" class="my-1.5 leading-normal">
          Accessible avec ce compte :
          <PageLink v-for="item in nav" :key="item.id" :href="item.href" :data-page="item.id" class="font-semibold text-accent">
            {{ item.icon }} {{ item.label }}
          </PageLink>
        </p>
        <UiButton id="gate-logout" variant="muted" class="mt-2" @click="logout">🚪 Se déconnecter</UiButton>
      </template>
    </section>
  </div>

  <div v-else class="min-h-dvh md:grid md:grid-cols-[232px_minmax(0,1fr)] print:block">
    <aside class="print:hidden md:sticky md:top-0 md:flex md:h-dvh md:flex-col md:gap-5 md:bg-side md:px-3 md:py-5 md:text-side-text">
      <AppBrand class="hidden px-2 md:block" />
      <nav
        v-if="nav.length"
        aria-label="Navigation principale"
        class="fixed inset-x-0 bottom-0 z-40 flex h-16 justify-around border-t border-side-hover bg-side pb-[env(safe-area-inset-bottom)] md:static md:h-auto md:flex-col md:justify-start md:gap-0.5 md:border-0 md:pb-0"
      >
        <template v-for="item in nav" :key="item.id">
          <!-- With its sub-menu open, the page is "section active" (lighter, aria-current="true"), the open sub-page is the
               current page (accent) -->
          <PageLink
            :href="item.href"
            :data-page="item.id"
            :aria-current="item.id !== props.page ? undefined : subMenu.length ? 'true' : 'page'"
            :class="[
              shownOn(item.screen, 'flex'),
              'min-w-0 flex-1 flex-col items-center justify-center gap-0.5 font-semibold text-side-text no-underline',
              'md:flex-none md:flex-row md:justify-start md:gap-2 md:rounded-lg md:px-3 md:py-2.5',
              item.id !== props.page
                ? 'hover:text-white md:hover:bg-side-hover'
                : subMenu.length
                  ? 'text-white md:bg-side-hover'
                  : 'text-white md:bg-accent',
            ]"
          >
            <span aria-hidden="true" class="text-lg md:text-base">{{ item.icon }}</span>
            <span class="max-w-full truncate text-[10px] md:hidden">{{ item.short }}</span>
            <span class="hidden md:inline">{{ item.label }}</span>
          </PageLink>
          <SubNav
            v-if="item.id === props.page && subMenu.length"
            :items="subMenu"
            :current="props.sub"
            variant="side"
            class="hidden md:flex"
          />
        </template>
      </nav>
      <!-- Signed-in account: foot of the side menu on desktop, top of the page on phones (the menu is a bottom bar) -->
      <div
        v-if="email"
        class="flex items-center gap-2 px-4 pt-3 md:mt-auto md:flex-col md:items-start md:gap-2 md:border-t md:border-side-hover md:px-2 md:pt-4"
      >
        <span id="who" class="min-w-0 text-xs break-words text-slate-500 md:text-slate-400">{{ who }}</span>
        <UiButton id="logout-btn" variant="muted" small class="ml-auto shrink-0 md:ml-0" @click="logout">🚪 Se déconnecter</UiButton>
      </div>
    </aside>

    <div class="min-w-0 px-4 pt-4 pb-28 md:px-7 md:pt-6 md:pb-10 print:p-0">
      <header class="mb-4 flex print:hidden flex-wrap items-center gap-x-4 gap-y-2">
        <h1 class="m-0 text-xl font-bold md:text-[22px]">{{ heading }}</h1>
        <span id="sync-info" class="text-[13px] text-slate-500">{{ props.sync }}</span>
      </header>
      <SubNav v-if="subMenu.length" :items="subMenu" :current="props.sub" variant="strip" class="mb-3 flex print:hidden md:hidden" />

      <div
        v-show="googleExpired"
        id="google-auth-warning"
        class="mb-3.5 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-300 print:hidden bg-red-50 px-3.5 py-2.5 text-[13px] text-red-800"
      >
        <span>
          ⚠️
          <b>Accès Google & BDD suspendus :</b>
          le jeton de connexion Google du club a expiré ou a été révoqué.
        </span>
        <a :href="renewUrl" class="rounded-lg bg-red-600 px-2.5 py-1.5 text-xs font-bold text-white no-underline">🔄 Renouveler l'accès</a>
      </div>

      <p
        v-if="access === 'offline'"
        id="offline-notice"
        role="status"
        class="mb-3.5 rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-2.5 text-[13px] text-amber-900 print:hidden"
      >
        📴 Hors ligne : consultation des dernières données reçues sur cet appareil.
      </p>

      <!-- Gate kept in the layout: offline (the menu leads to the pages readable offline) and a coach on an admin page -->
      <section
        v-if="access === 'unverified' || access === 'adminOnly'"
        id="gate"
        class="max-w-xl rounded-xl border border-slate-200 bg-white px-4.5 py-4 shadow-sm"
      >
        <template v-if="access === 'unverified' && state.status === 'error'">
          <h2 class="mb-2 text-[17px] font-bold">⚠️ Droits non vérifiés</h2>
          <p class="my-1.5 leading-normal">{{ state.message }}</p>
          <p data-testid="offline-pages" class="my-1.5 leading-normal">
            Hors ligne, restent consultables :
            <template v-for="(item, index) in OFFLINE_PAGES" :key="item.id">
              <template v-if="index">·</template>
              <PageLink :href="item.href" class="font-semibold text-accent">{{ item.icon }} {{ item.label }}</PageLink>
            </template>
          </p>
          <UiButton id="gate-retry" class="mt-2" @click="auth.retry()">🔄 Réessayer</UiButton>
        </template>
        <template v-else>
          <h2 class="mb-2 text-[17px] font-bold">⛔ Réservé aux administrateurs</h2>
          <p class="my-1.5 leading-normal">Cette page est réservée aux administrateurs du club.</p>
          <a
            href="/bureau/"
            class="mt-2 inline-block rounded-lg bg-accent px-3.5 py-2 text-[13px] font-bold text-white no-underline hover:bg-accent-dark"
          >
            🏠 Retour à l'accueil
          </a>
        </template>
      </section>

      <p
        v-if="refusedSub && (access === 'allow' || access === 'offline')"
        id="refused-page"
        role="status"
        class="mb-3.5 rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-2.5 text-[13px] text-amber-900 print:hidden"
      >
        {{ refusedSub }}
      </p>

      <div v-if="(access === 'allow' || access === 'offline') && subAllowed" id="content">
        <slot :role="role" />
      </div>

      <p class="mt-8 text-center text-[11px] text-slate-400 md:hidden print:hidden">
        🧗 ALJ Escalade ·
        <VersionBadge />
      </p>
    </div>
  </div>
</template>
