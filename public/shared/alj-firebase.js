/* Single Firebase initialisation for every page (PWA and office portal).
   Classic script (not a module): usable from pages through <script> as well as from
   alj-core.js. Must be loaded after the firebase-app/auth compat SDKs and after
   /runtime-config.js, which defines window.ALJ_RUNTIME (served by server.py / server.ts).
*/
(function () {
  "use strict";

  const FIREBASE_CONFIG = Object.freeze({
    apiKey: "AIzaSyDtwH7A6XokZZjUcyoL83gx9ZjyuN4IJoQ",
    authDomain: "smart-amplifier-510811-n6.firebaseapp.com",
    projectId: "smart-amplifier-510811-n6",
    appId: "1:796572126711:web:a827fd60c313ba2c46f2f2"
  });

  const runtime = window.ALJ_RUNTIME || { env: "dev", isAIStudio: true };
  const isEmulator = runtime.env === "dev" || runtime.isAIStudio === true;
  let services = null;

  const DEV_USERS = {
    admin: {
      uid: "albus-dumbledore",
      email: "admin@alj-escalade.fr",
      displayName: "Albus Dumbledore (Admin)",
      claims: { admin: true }
    },
    coach: {
      uid: "severus-snape",
      email: "severus.snape@hogwarts.example",
      displayName: "Severus Snape (Coach)",
      claims: { coach: true }
    },
    readonly: {
      uid: "argus-filch",
      email: "argus.filch@hogwarts.example",
      displayName: "Argus Filch (Lecture seule)",
      claims: { readonly: true }
    }
  };

  function getStoredDevUser() {
    try {
      const saved = localStorage.getItem("alj_dev_role");
      if (saved === "none") return null;
      if (saved && DEV_USERS[saved]) return DEV_USERS[saved];
    } catch (e) {}
    // Default to admin for seamless immediate access
    return DEV_USERS.admin;
  }

  function showDevBanner() {
    const add = () => {
      if (document.getElementById("alj-dev-banner")) return;
      const b = document.createElement("div");
      b.id = "alj-dev-banner";
      b.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;">
          <span>🧗 <b>ALJ Escalade CRM</b> · Session active :</span>
          <div style="display:flex;gap:6px;">
            <button id="alj-sw-admin" style="cursor:pointer;background:#1e293b;color:#fff;border:1px solid #475569;border-radius:4px;padding:2px 8px;font-size:11px;">🛡️ Admin</button>
            <button id="alj-sw-coach" style="cursor:pointer;background:#1e293b;color:#fff;border:1px solid #475569;border-radius:4px;padding:2px 8px;font-size:11px;">🏃 Coach</button>
            <button id="alj-sw-ro" style="cursor:pointer;background:#1e293b;color:#fff;border:1px solid #475569;border-radius:4px;padding:2px 8px;font-size:11px;">👁️ Lecture</button>
            <button id="alj-sw-out" style="cursor:pointer;background:#7f1d1d;color:#fff;border:1px solid #991b1b;border-radius:4px;padding:2px 8px;font-size:11px;">🚪 Déco</button>
          </div>
        </div>
      `;
      b.setAttribute("role", "status");
      b.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:99999;padding:4px 12px;"
        + "background:#0f172a;color:#94a3b8;font:500 12px/1.4 system-ui,sans-serif;text-align:center;"
        + "border-top:1px solid #334155;box-shadow:0 -2px 10px rgba(0,0,0,.3);";
      document.body.appendChild(b);

      const attach = (id, roleKey) => {
        const btn = document.getElementById(id);
        if (btn) {
          btn.onclick = () => {
            if (roleKey === "none") {
              localStorage.setItem("alj_dev_role", "none");
            } else {
              localStorage.setItem("alj_dev_role", roleKey);
            }
            location.reload();
          };
        }
      };
      attach("alj-sw-admin", "admin");
      attach("alj-sw-coach", "coach");
      attach("alj-sw-ro", "readonly");
      attach("alj-sw-out", "none");
    };
    if (document.body) add();
    else document.addEventListener("DOMContentLoaded", add);
  }

  function createDevUser(profile) {
    if (!profile) return null;
    return {
      uid: profile.uid,
      email: profile.email,
      displayName: profile.displayName,
      emailVerified: true,
      getIdToken: async () => "dev-token-" + profile.uid,
      getIdTokenResult: async () => ({ claims: profile.claims || {} })
    };
  }

  /* Idempotent: returns { auth } (compat). */
  function init() {
    if (services) return services;

    // Check if real firebase app exists
    let realAuth = null;
    if (window.firebase && typeof firebase.initializeApp === "function") {
      try {
        if (!firebase.apps.length) {
          firebase.initializeApp(FIREBASE_CONFIG);
        }
        realAuth = firebase.auth();
      } catch (e) {
        console.warn("Firebase native init skipped:", e);
      }
    }

    if (isEmulator) {
      let currentDevProfile = getStoredDevUser();
      let currentDevUser = createDevUser(currentDevProfile);
      const listeners = [];

      const devAuth = {
        get currentUser() {
          return currentDevUser;
        },
        onAuthStateChanged(callback) {
          listeners.push(callback);
          setTimeout(() => callback(currentDevUser), 10);
          return () => {
            const idx = listeners.indexOf(callback);
            if (idx >= 0) listeners.splice(idx, 1);
          };
        },
        async signOut() {
          currentDevProfile = null;
          currentDevUser = null;
          try { localStorage.setItem("alj_dev_role", "none"); } catch (e) {}
          listeners.forEach(cb => cb(null));
        },
        async signInWithRedirect() {
          currentDevProfile = DEV_USERS.admin;
          currentDevUser = createDevUser(currentDevProfile);
          try { localStorage.setItem("alj_dev_role", "admin"); } catch (e) {}
          listeners.forEach(cb => cb(currentDevUser));
          return true;
        },
        async signInWithCredential() {
          return this.signInWithRedirect();
        },
        useEmulator() {
          // No-op for dev environment
        }
      };

      showDevBanner();
      services = { auth: devAuth };
      return services;
    }

    services = { auth: realAuth };
    return services;
  }

  function devLogin() {
    try {
      localStorage.setItem("alj_dev_role", "admin");
    } catch (e) {}
    if (services && services.auth && typeof services.auth.signInWithRedirect === "function") {
      return services.auth.signInWithRedirect();
    }
    location.reload();
  }

  async function completeDevLogin() {
    return false;
  }

  window.ALJFirebase = Object.freeze({
    init,
    devLogin,
    completeDevLogin,
    isEmulator,
    env: runtime.env
  });
})();
