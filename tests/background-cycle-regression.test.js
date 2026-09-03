const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const background = fs.readFileSync('background.js', 'utf8');
const manifest = JSON.parse(fs.readFileSync('manifest.json', 'utf8'));
const clone = structuredClone;
const settle = () => new Promise(resolve => setImmediate(resolve));

// Real background listeners and transitions; simulated Chrome/native boundaries.
// This verifies routing and anchor lifecycle, not actual Windows virtual desktops.
async function runtime(url = 'chrome://newtab/', options = {}) {
  let nextWindow = 30, nextTab = 300, nextTimer = 1, desktop = 'A';
  const timers = new Map(), windows = new Map(), tabs = new Map();
  const storage = {}, errors = [], activations = [];
  const event = () => ({ listeners: [], addListener(fn) { this.listeners.push(fn); } });
  const chrome = {
    runtime: { getManifest: () => manifest, onMessage: event(), onInstalled: event(),
      sendMessage(_id, _message, callback) { callback({ ok: true }); } },
    commands: { onCommand: event() }, action: { onClicked: event() },
    storage: { local: { get: async key => ({ [key]: clone(storage[key]) }),
      set: async values => Object.assign(storage, clone(values)) } },
    tabGroups: {}, windows: { onRemoved: event(), onBoundsChanged: event() },
    tabs: { onActivated: event(), onUpdated: event(), onCreated: event(),
      onRemoved: event(), onAttached: event() },
    scripting: { executeScript: async ({ target }) => {
      if (!/^https?:/.test(tabs.get(target.tabId).url)) throw Error('Cannot access a chrome:// URL');
    } }
  };
  function snapshot(id) {
    if (!windows.has(id)) throw Error('missing window');
    return { ...clone(windows.get(id)), tabs: [...tabs.values()]
      .filter(tab => tab.windowId === id).map(tab => clone(tab)) };
  }
  function focus(id) {
    desktop = windows.get(id).desktop;
    for (const w of windows.values()) w.focused = w.id === id;
    activations.push({ id, desktop });
  }
  function normalize(id) {
    const siblings = [...tabs.values()].filter(tab => tab.windowId === id);
    siblings.forEach((tab, index) => { tab.index = index; });
    if (siblings.length && !siblings.some(tab => tab.active)) siblings[0].active = true;
    if (!siblings.length) windows.delete(id);
  }
  function move(tab, destination) {
    const previous = tab.windowId;
    tab.windowId = destination; normalize(previous); normalize(destination);
  }
  function addWindow(id, location, tabId, page) {
    windows.set(id, { id, desktop: location, focused: false, type: 'normal', state: 'normal',
      left: 0, top: 0, width: 900, height: 700 });
    tabs.set(tabId, { id: tabId, windowId: id, active: true, index: 0,
      groupId: -1, pinned: false, url: page });
  }
  addWindow(10, 'A', 100, url); addWindow(20, 'B', 200, 'https://example.org/video');
  focus(10); activations.length = 0;
  Object.assign(chrome.windows, {
    get: async id => snapshot(id), getAll: async () => [...windows.keys()].map(snapshot),
    getLastFocused: async () => snapshot([...windows.values()].find(w => w.focused).id),
    update: async (id, values) => {
      if (!windows.has(id)) throw Error('missing window');
      Object.assign(windows.get(id), values);
      if (values.state === 'minimized') windows.get(id).focused = false;
      if (values.focused) focus(id);
      return snapshot(id);
    },
    create: async values => {
      const id = nextWindow++;
      windows.set(id, { id, desktop, focused: false, type: values.type || 'normal',
        state: values.state || 'normal', left: 0, top: 0, width: 900, height: 700 });
      if (values.tabId != null) move(tabs.get(values.tabId), id);
      if (values.focused) focus(id);
      return snapshot(id);
    },
    remove: async id => {
      windows.delete(id);
      for (const [tabId, tab] of tabs) if (tab.windowId === id) tabs.delete(tabId);
    }
  });
  Object.assign(chrome.tabs, {
    get: async id => { if (!tabs.has(id)) throw Error('missing tab'); return clone(tabs.get(id)); },
    query: async ({ windowId } = {}) => [...tabs.values()]
      .filter(tab => windowId == null || tab.windowId === windowId).map(tab => clone(tab)),
    create: async values => {
      const id = nextTab++;
      tabs.set(id, { id, windowId: values.windowId, active: !!values.active,
        index: values.index, pinned: false, groupId: -1, url: values.url || 'chrome://newtab/' });
      return clone(tabs.get(id));
    },
    update: async (id, values) => {
      const tab = tabs.get(id);
      if (values.active) for (const sibling of tabs.values()) {
        if (sibling.windowId === tab.windowId) sibling.active = sibling.id === id;
      }
      Object.assign(tab, values); return clone(tab);
    },
    move: async (id, values) => { move(tabs.get(id), values.windowId); return clone(tabs.get(id)); },
    remove: async id => { const tab = tabs.get(id); tabs.delete(id); if (tab) normalize(tab.windowId); },
    sendMessage(id, message, callback) {
      const tab = tabs.get(id);
      if (!tab || !/^https?:/.test(tab.url)) {
        chrome.runtime.lastError = { message: 'Receiving end does not exist.' };
        callback(); delete chrome.runtime.lastError;
      } else if (message.type === 'clean-window-runtime-probe') {
        callback({ ok: true, hotReload: true, version: manifest.version });
      } else if (message.type === 'set-windowed-fullscreen' && message.enabled) {
        callback(options.transient ? { ok: false, error: 'temporary runtime failure' }
          : options.noVideo ? { ok: false, reason: 'no-video' } : { ok: true });
      } else callback({ ok: true });
    }
  });
  const context = vm.createContext({ chrome,
    console: { error: (...args) => errors.push(args), log: console.log },
    setTimeout(fn) { const id = nextTimer++; timers.set(id, fn); return id; },
    clearTimeout(id) { timers.delete(id); }
  });
  vm.runInContext(background, context);
  // Diagnostic-only polling is not part of the transition under test.
  vm.runInContext('waitForRestoredWindowStable = async () => true;', context);
  await settle();
  return { context, windows, tabs, errors, activations,
    get sessions() { return storage.cleanWindowSessionsV8 || {}; },
    get popupId() { return tabs.get(100).windowId; }, focus,
    async command(eventTab = tabs.get(100)) {
      chrome.commands.onCommand.listeners[0]('toggle-clean-window', clone(eventTab));
      await settle(); assert.deepEqual(errors, []);
    },
    async runTimers() {
      const batch = [...timers.values()]; timers.clear();
      for (const fn of batch) { fn(); await settle(); }
    }
  };
}

test('stale command tab from B must not redirect focused A input', async () => {
  const r = await runtime();
  await r.command(r.tabs.get(200));
  assert.equal(r.tabs.get(200).windowId, 20, 'unrelated B tab must stay untouched');
  assert.notEqual(r.popupId, 10);
  assert(r.activations.every(entry => entry.desktop === 'A'));
});
test('B video cycle then A blank-new-tab cycle with stale B event metadata', async () => {
  const r = await runtime();
  for (let round = 0; round < 3; round++) {
    r.focus(20);
    for (let step = 0; step < 3; step++) await r.command(r.tabs.get(200));
    assert.equal(r.tabs.get(200).windowId, 20);
    r.focus(10);
    r.activations.length = 0;
    await r.command(r.tabs.get(200));
    assert.equal(r.sessions[r.popupId].sourceWindowId, 10);
    await r.command(r.tabs.get(200));
    assert.equal(r.tabs.get(100).windowId, 10);
    assert.equal(r.tabs.get(200).windowId, 20);
    assert(r.activations.every(entry => entry.desktop === 'A'));
    assert.deepEqual(r.sessions, {});
  }
});
test('blank new tab: 1 -> 2 -> 1 preserves source and removes its anchor', async () => {
  const r = await runtime(); await r.command();
  const anchor = r.sessions[r.popupId].anchorTabId;
  assert.equal(r.sessions[r.popupId].mode, 'clean');
  assert(Number.isInteger(anchor), 'a single blank tab DOES get an anchor');
  assert(r.tabs.has(anchor));
  await r.command();
  assert.equal(r.tabs.get(100).windowId, 10);
  assert(r.windows.get(10).focused); assert(!r.tabs.has(anchor));
  assert.deepEqual(r.sessions, {});
});
test('multi-tab source returns without an anchor and retains its other tab', async () => {
  const r = await runtime();
  r.tabs.set(101, { ...r.tabs.get(100), id: 101, active: false, index: 1 });
  await r.command(); assert.equal(r.sessions[r.popupId].anchorTabId, null);
  await r.command();
  assert.equal(r.tabs.get(100).windowId, 10); assert.equal(r.tabs.get(101).windowId, 10);
});
test('video page keeps 1 -> 2 -> 3 -> 1 and source identity', async () => {
  const r = await runtime('https://example.org/video');
  await r.command(); assert.equal(r.sessions[r.popupId].mode, 'clean');
  await r.command(); assert.equal(r.sessions[r.popupId].mode, 'windowed-fullscreen');
  await r.command(); assert.equal(r.tabs.get(100).windowId, 10);
  assert.deepEqual(r.sessions, {});
});
test('confirmed no-video returns; transient web errors keep mode 2', async () => {
  const empty = await runtime('https://example.org/', { noVideo: true });
  await empty.command(); await empty.command(); assert.equal(empty.tabs.get(100).windowId, 10);
  const transient = await runtime('https://example.org/', { transient: true });
  await transient.command(); await transient.command();
  assert.equal(transient.sessions[transient.popupId].mode, 'clean');
});
for (const url of ['chrome://new-tab-page/', 'chrome-search://local-ntp/local-ntp.html', 'about:blank']) {
  test(`browser-owned page returns without injecting fullscreen: ${url}`, async () => {
    const r = await runtime(url);
    await r.command(); await r.command();
    assert.equal(r.tabs.get(100).windowId, 10);
    assert.deepEqual(r.sessions, {});
  });
}
test('queue ignores unfocused B but follows A tab into its own popup', async () => {
  const r = await runtime('https://example.org/video');
  vm.runInContext('transitionQueue.push({ windowId: 20, tabId: 200 }); scheduleQueuedToggle();', r.context);
  await r.runTimers(); assert.equal(r.popupId, 10);
  await r.command();
  vm.runInContext('transitionQueue.push({ windowId: 10, tabId: 100 }); scheduleQueuedToggle();', r.context);
  await r.runTimers(); assert.equal(r.sessions[r.popupId].mode, 'windowed-fullscreen');
});
test('content runtime version agrees with manifest', () => {
  const content = fs.readFileSync('windowed_fullscreen.js', 'utf8');
  assert.equal(content.match(/const RUNTIME_VERSION = "([^"]+)"/)[1], manifest.version);
});
