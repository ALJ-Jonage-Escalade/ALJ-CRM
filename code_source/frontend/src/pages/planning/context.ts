/* What the Planning page (the layout, PlanningPage.vue) shares with its sub-pages, Vue semaine and Tableau des
   créneaux: the slots, loaded once for both, and the slot dialog (create / edit) and deletion it owns. */
import type { InjectionKey, Ref } from "vue";
import type { Slot } from "./slots";

export interface PlanningContext {
  slots: Ref<Slot[]>;
  /** Opens the slot dialog: on this slot, or empty for a new one. */
  open: (slot?: Slot) => void;
  /** Asks for confirmation, then deletes the slot. */
  remove: (slot: Slot) => Promise<void>;
}

export const PLANNING_KEY: InjectionKey<PlanningContext> = Symbol("planning");
