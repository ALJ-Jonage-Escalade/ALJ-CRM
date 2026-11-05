/* Whether the browser has a network connection (navigator.onLine), kept up to date. Screens that only work online
   disable their actions with an explanation instead of failing mid-way. */
import { onScopeDispose, ref, type Ref } from "vue";

export function useNetworkUp(): Readonly<Ref<boolean>> {
  const up = ref(navigator.onLine);
  const onChange = () => (up.value = navigator.onLine);
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  onScopeDispose(() => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  });
  return up;
}
