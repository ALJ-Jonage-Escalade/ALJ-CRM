/* Runs web/shared/alj-sync.js in Node with a fetch whose answers the
   scenarios release one by one, then prints {scenario: result} as JSON for
   tests/web/test_sync_scripts.py. Usage: node sync_scripts_harness.js <web/shared dir> */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const sharedDir = process.argv[2];

function makeContext() {
  const noop = () => {};
  const ctx = {
    document: { hidden: false, addEventListener: noop, removeEventListener: noop },
    navigator: { onLine: true },
    setTimeout: () => 0,  // no automatic polling: scenarios refresh by hand
    clearTimeout: noop,
    console,
    Promise,
    Error
  };
  ctx.window = Object.assign(ctx, { addEventListener: noop, removeEventListener: noop });
  vm.createContext(ctx);
  for (const name of ["alj-sync.js"]) {
    vm.runInContext(fs.readFileSync(path.join(sharedDir, name), "utf8"), ctx, { filename: name });
  }
  return ctx;
}

/* fetch(url) stays pending until answer(url, body) is called. */
function makeFetch() {
  const pending = [];
  const requested = [];
  function fetch(url) {
    requested.push(url);
    return new Promise(resolve => pending.push({ url, resolve }));
  }
  async function answer(url, body) {
    const i = pending.findIndex(p => p.url === url);
    if (i < 0) throw new Error("no pending request for " + url + " (pending: " + pending.map(p => p.url) + ")");
    const [p] = pending.splice(i, 1);
    p.resolve({
      status: 200, ok: true,
      headers: { get: () => '"' + JSON.stringify(body).length + url + '"' },
      json: async () => body
    });
    await new Promise(r => setImmediate(r));  // let the page's callbacks run
  }
  return { fetch, answer, requested };
}

const scenarios = {
  /* ALJSync.poll: an answer on its way when stop() is called reaches no callback. */
  async stopped_poll_drops_its_answer() {
    const ctx = makeContext(), f = makeFetch();
    const calls = [];
    const p = ctx.ALJSync.poll("/api/competitions", {
      fetch: f.fetch,
      onData: () => calls.push("data"),
      onStatus: s => calls.push("status:" + s)
    });
    p.stop();
    await f.answer("/api/competitions", []);
    return { calls };
  }
};

(async () => {
  const out = {};
  for (const [name, run] of Object.entries(scenarios)) {
    try { out[name] = await run(); } catch (e) { out[name] = { error: String(e && e.stack || e) }; }
  }
  process.stdout.write(JSON.stringify(out));
})();
