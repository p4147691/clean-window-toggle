const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const background = fs.readFileSync("background.js", "utf8")
  .split("chrome.action.onClicked.addListener")[0];

function createRuntime() {
  let now = 1000;
  let nextTimer = 1;
  const timers = new Map();
  const calls = [];
  const windows = new Map([
    [10, { id: 10, focused: true, tabs: [{ id: 100, windowId: 10, active: true }] }],
    [20, { id: 20, focused: false, tabs: [{ id: 200, windowId: 20, active: true }] }]
  ]);
  const tabs = new Map([
    [100, { id: 100, windowId: 10, active: true }],
    [200, { id: 200, windowId: 20, active: true }]
  ]);
  const context = vm.createContext({
    console,
    Date: class extends Date { static now() { return now; } },
    setTimeout(callback) { const id = nextTimer++; timers.set(id, callback); return id; },
    clearTimeout(id) { timers.delete(id); },
    chrome: {
      runtime: { getManifest: () => ({ version: "2.3.22" }) },
      windows: {
        get: async (id) => {
          if (!windows.has(id)) throw new Error("missing window");
          return structuredClone(windows.get(id));
        }
      },
      tabs: {
        get: async (id) => {
          if (!tabs.has(id)) throw new Error("missing tab");
          return structuredClone(tabs.get(id));
        }
      }
    },
    calls
  });
  vm.runInContext(background, context);
  vm.runInContext("toggleCleanWindow = async (windowId, tabId, source) => calls.push({ windowId, tabId, source });", context);
  return {
    context,
    calls,
    windows,
    tabs,
    advance(ms) { now += ms; },
    async runTimers() {
      const callbacks = [...timers.values()];
      timers.clear();
      for (const callback of callbacks) {
        callback();
        await new Promise((resolve) => setImmediate(resolve));
      }
    }
  };
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

(async () => {
  {
    const runtime = createRuntime();
    // A command from chrome://newtab must remain routable even when Chrome's
    // focused flag is stale after a Windows virtual-desktop switch.
    runtime.windows.get(10).focused = false;
    const resolved = await vm.runInContext("getCommandContext({ id: 100, windowId: 999 })", runtime.context);
    assert.equal(resolved.window.id, 10);
    assert.equal(resolved.tab.id, 100);
    const trusted = await vm.runInContext("getFocusedContext(10, 100, true)", runtime.context);
    assert.equal(trusted.window.id, 10);
    const ordinary = await vm.runInContext("getFocusedContext(10, 100, false)", runtime.context);
    assert.equal(ordinary.window, null);
  }

  {
    const runtime = createRuntime();
    vm.runInContext("scheduleContentFallback(10, 100)", runtime.context);
    await runtime.runTimers();
    assert.deepEqual(plain(runtime.calls), [{ windowId: 10, tabId: 100, source: "content-fallback" }]);
  }

  {
    const runtime = createRuntime();
    vm.runInContext("scheduleContentFallback(10, 100); noteCommandInput(10, 100)", runtime.context);
    await runtime.runTimers();
    assert.deepEqual(plain(runtime.calls), []);
  }

  {
    const runtime = createRuntime();
    vm.runInContext("noteCommandInput(10, 100); scheduleContentFallback(10, 100)", runtime.context);
    await runtime.runTimers();
    assert.deepEqual(plain(runtime.calls), []);
  }

  {
    const runtime = createRuntime();
    vm.runInContext("transitionQueue.push({ windowId: 20, tabId: 200, inputSource: 'command' }); scheduleQueuedToggle()", runtime.context);
    await runtime.runTimers();
    assert.deepEqual(plain(runtime.calls), [], "a queued input must not jump to the focused window on another desktop");

    runtime.windows.get(10).focused = false;
    runtime.windows.get(20).focused = true;
    vm.runInContext("transitionQueue.push({ windowId: 20, tabId: 200, inputSource: 'command' }); scheduleQueuedToggle()", runtime.context);
    await runtime.runTimers();
    assert.deepEqual(plain(runtime.calls), [{ windowId: 20, tabId: 200, source: "command-retry" }]);
  }

  console.log("PASS background input routing");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
