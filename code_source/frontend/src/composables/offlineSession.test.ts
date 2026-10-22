import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import type { OfflineStore } from "../lib/store";
import type { AuthState } from "./auth";
import { bindOfflineStore } from "./offlineSession";

function fakeStore() {
  return { start: vi.fn(async () => {}), clearAll: vi.fn(async () => {}) } as unknown as OfflineStore & {
    start: ReturnType<typeof vi.fn>;
    clearAll: ReturnType<typeof vi.fn>;
  };
}

describe("bindOfflineStore", () => {
  it("wipes the store when signed out, and claims it for each user signing in", async () => {
    const state = ref<AuthState>({ status: "loading" });
    const store = fakeStore();
    bindOfflineStore(state, store);
    expect(store.start).not.toHaveBeenCalled();
    expect(store.clearAll).not.toHaveBeenCalled();

    state.value = { status: "signedIn", user: { uid: "u1", email: "a@x" }, role: "coach" };
    await nextTick();
    expect(store.start).toHaveBeenLastCalledWith("u1");

    state.value = { status: "error", user: { uid: "u1", email: "a@x" }, message: "x", offline: true };
    await nextTick();
    expect(store.start).toHaveBeenCalledTimes(1);  // same user: nothing to do

    state.value = { status: "signedOut" };
    await nextTick();
    expect(store.clearAll).toHaveBeenCalledOnce();

    state.value = { status: "signedIn", user: { uid: "u2", email: "b@x" }, role: null };
    await nextTick();
    expect(store.start).toHaveBeenLastCalledWith("u2");  // another account: start() wipes u1's data
  });

  it("wipes at once when the page opens signed out", () => {
    const store = fakeStore();
    bindOfflineStore(ref<AuthState>({ status: "signedOut" }), store);
    expect(store.clearAll).toHaveBeenCalledOnce();
  });
});
