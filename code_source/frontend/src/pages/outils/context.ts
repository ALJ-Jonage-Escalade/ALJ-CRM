/* What the Outils page (the layout, OutilsPage.vue) shares with its sub-pages: the seasons, loaded once for the map and
   the pivot table, and the toast. */
import type { InjectionKey, Ref } from "vue";
import type { Toast } from "../../composables/toast";

export interface OutilsContext {
  seasons: Ref<string[]>;
  /** Season shown first: the server's active one; empty until the seasons are known. */
  initialSeason: Ref<string>;
  toast: Toast;
}

export const OUTILS_KEY: InjectionKey<OutilsContext> = Symbol("outils");

/** What every sub-page exposes to the layout's reload button. */
export interface ReloadablePage {
  reload(): unknown;
}
