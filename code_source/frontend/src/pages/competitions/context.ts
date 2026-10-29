/* What the competitions page (the layout, CompetitionsPage.vue) shares with its sub-pages: the data, polled once for
   all of them, and the outbox of the changes made offline. */
import type { ComputedRef, InjectionKey } from "vue";
import type { SyncedResource } from "../../composables/syncedResource";
import type { Coach, Competition, CompetitorContact, MemberSlot } from "./competitions";
import type { HelloAssoItem } from "./helloasso/helloasso";
import type { Outbox } from "./outbox";

export interface CompetitionsContext {
  competitions: SyncedResource<Competition[]>;
  /** Every competition, sorted, archived ones included. */
  all: ComputedRef<Competition[]>;
  competitors: SyncedResource<CompetitorContact[]>;
  members: SyncedResource<MemberSlot[]>;
  coaches: SyncedResource<Coach[]>;
  /** HelloAsso items, loaded while the HelloAsso sub-page is open. */
  items: SyncedResource<HelloAssoItem[]>;
  /** Coaches and admins; offline, a device that keeps the contacts (a coach's). */
  canWrite: ComputedRef<boolean>;
  staff: ComputedRef<boolean>;
  contactsShown: ComputedRef<boolean>;
  /** The API can be reached. */
  online: ComputedRef<boolean>;
  outbox: Outbox;
  uid: ComputedRef<string | null>;
  /** Address of the list (the index route: /competitions or /bureau/competitions), where a competition opens. */
  listPath: ComputedRef<string>;
}

export const COMPETITIONS_KEY: InjectionKey<CompetitionsContext> = Symbol("competitions");
