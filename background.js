const STORAGE_KEY = "cleanWindowSessionsV8";
const FULLSCREEN_PENDING_KEY = "cleanWindowFullscreenPendingV1";
const DESKTOP_EXTENSION_ID = "fcjhjgbebcebpdmfedcoabaonhfkjmfo";
const NO_GROUP = -1;

let transitionInProgress = false;
let transitionStartedAt = 0;
const transitionQueue = [];
let transitionSerial = 0;
const TRANSITION_STALE_MS = 2500;
const MAX_TRANSITION_QUEUE = 3;
const DEBUG_KEY = "cleanWindowTransitionDebugV1";
const LAST_FAILURE_KEY = "cleanWindowLastFailureV1";
let sessionOperationTail = Promise.resolve();
const returningPopups = new Set();
const pendingFullscreenTransitions = new Set();
const fullscreenMaterializeTimers = new Map();
const fullscreenReapplyTimers = new Map();

// Every read/modify/write session operation shares this queue. A lifecycle event
// fired by tabs.move/remove must read the state AFTER its owning transition, not
// overwrite it later with a snapshot taken before the transition completed.
function runSessionOperation(operation) {
  const result = sessionOperationTail.then(operation);
  sessionOperationTail = result.catch(() => {});
  return result;
}

function nativeWindowRequest(type, details = {}) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(DESKTOP_EXTENSION_ID, { type, ...details }, (response) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      resolve(response || { ok: false, error: "Native helper 응답이 없습니다." });
    });
  });
}

async function recordTransitionDebug(stage, details = {}) {
  try {
    const entry = {
        stage,
        version: chrome.runtime.getManifest().version,
        at: Date.now(),
        transitionSerial,
        transitionInProgress,
        transitionStartedAt,
        ...details
    };
    const values = { [DEBUG_KEY]: entry };
    if (stage === "mode3-failed" || stage === "transition-error") values[LAST_FAILURE_KEY] = entry;
    await chrome.storage.local.set(values);
  } catch (_) {}
}

function scheduleQueuedToggle() {
  if (transitionQueue.length <= 0 || transitionInProgress) return;
  const request = transitionQueue.shift();
  setTimeout(() => {
    safeGetTab(request.tabId).then(async (queuedTab) => {
      // Follow the tab if the preceding transition moved it between its normal
      // window and popup. Never retarget a queued gesture to an unrelated window
      // that happened to gain focus on another Windows virtual desktop.
      const queuedWindow = queuedTab ? await safeGetWindow(queuedTab.windowId, true) : null;
      const activeTab = queuedWindow?.tabs?.find((candidate) => candidate.active);
      if (!queuedWindow || queuedWindow.focused !== true || activeTab?.id !== request.tabId) {
        scheduleQueuedToggle();
        return;
      }
      return toggleCleanWindow(queuedWindow.id, request.tabId, "command-retry");
    }).catch(console.error);
  }, 35);
}

async function getSessions() {
  const result = await chrome.storage.local.get(STORAGE_KEY);
  return result[STORAGE_KEY] || {};
}

async function saveSessions(sessions) {
  await chrome.storage.local.set({ [STORAGE_KEY]: sessions });
}

async function getFullscreenPending() {
  const result = await chrome.storage.local.get(FULLSCREEN_PENDING_KEY);
  return result[FULLSCREEN_PENDING_KEY] || {};
}

async function saveFullscreenPending(pending) {
  await chrome.storage.local.set({ [FULLSCREEN_PENDING_KEY]: pending });
}

async function safeGetWindow(windowId, populate = false) {
  if (!Number.isInteger(windowId)) return null;
  try { return await chrome.windows.get(windowId, { populate }); }
  catch (_) { return null; }
}

async function safeGetTab(tabId) {
  if (!Number.isInteger(tabId)) return null;
  try { return await chrome.tabs.get(tabId); }
  catch (_) { return null; }
}

async function getActuallyFocusedContext() {
  try {
    const windows = await chrome.windows.getAll({ populate: true });
    const focusedWindow = windows.find((candidate) => candidate.focused === true);
    if (!focusedWindow || focusedWindow.id == null) return { window: null, tab: null };
    const activeTab = focusedWindow.tabs?.find((candidate) => candidate.active);
    if (!activeTab || activeTab.id == null) return { window: null, tab: null };
    return { window: focusedWindow, tab: activeTab };
  } catch (_) {
    return { window: null, tab: null };
  }
}

async function getFocusedContext(preferredWindowId, preferredTabId) {
  // Alt+C is bound to the window/tab that actually emitted the input event.
  // Never redirect a popup shortcut through getLastFocused(): Chrome can report
  // a previously focused normal window while a Clean Window popup is active.
  if (Number.isInteger(preferredWindowId)) {
    const originWindow = await safeGetWindow(preferredWindowId, true);
    if (!originWindow || originWindow.id == null || originWindow.focused !== true) {
      return { window: null, tab: null };
    }

    const originTab = Number.isInteger(preferredTabId)
      ? originWindow.tabs?.find((candidate) => candidate.id === preferredTabId)
      : originWindow.tabs?.find((candidate) => candidate.active);
    if (!originTab || originTab.id == null || originTab.active !== true) {
      return { window: null, tab: null };
    }
    return { window: originWindow, tab: originTab };
  }

  // Fallback only for callers that genuinely have no origin window id.
  let focusedWindow = null;
  try {
    focusedWindow = await chrome.windows.getLastFocused({ populate: true });
  } catch (_) {
    return { window: null, tab: null };
  }
  if (!focusedWindow || focusedWindow.id == null || focusedWindow.focused === false) {
    return { window: null, tab: null };
  }
  const activeTab = focusedWindow.tabs?.find((candidate) => candidate.active);
  return activeTab ? { window: focusedWindow, tab: activeTab } : { window: null, tab: null };
}

function getBounds(window) {
  if (![window.left, window.top, window.width, window.height].every(Number.isInteger)) return null;
  return { left: window.left, top: window.top, width: window.width, height: window.height };
}

function boundsChanged(current, initial, tolerance = 3) {
  if (!current || !initial) return false;
  return ["left", "top", "width", "height"]
    .some((key) => Math.abs(current[key] - initial[key]) > tolerance);
}

async function showWindow(windowId, bounds, focused = true) {
  if (!Number.isInteger(windowId)) return;
  await chrome.windows.update(windowId, { state: "normal" });
  if (bounds) await chrome.windows.update(windowId, bounds);
  if (focused) await chrome.windows.update(windowId, { focused: true });
}

function sendTabMessage(tabId, message) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      resolve(response || { ok: false });
    });
  });
}

const CONTENT_RUNTIME_VERSION = chrome.runtime.getManifest().version;

async function ensureContentRuntimeCurrent(tabId) {
  if (!Number.isInteger(tabId)) return { ok: false, error: "invalid-tab" };
  let probe = await sendTabMessage(tabId, { type: "clean-window-runtime-probe" });

  // 2.3.8 and older tabs do not understand the probe. Never force-inject over
  // those pages because their anonymous listeners cannot be safely detached.
  if (!probe?.ok || probe.hotReload !== true) {
    return { ok: true, legacy: true, version: probe?.version || null };
  }
  if (probe.version === CONTENT_RUNTIME_VERSION) return probe;

  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["windowed_fullscreen.js"]
    });
  } catch (error) {
    return { ok: false, error: error?.message || String(error) };
  }

  probe = await sendTabMessage(tabId, { type: "clean-window-runtime-probe" });
  if (!probe?.ok || probe.version !== CONTENT_RUNTIME_VERSION) {
    return { ok: false, error: "runtime-hot-reload-verification-failed" };
  }
  return probe;
}

async function setMediaPaused(tabIds, paused) {
  const type = paused ? "pause-clean-window-media" : "resume-clean-window-media";
  await Promise.all(tabIds.filter(Number.isInteger).map((tabId) => sendTabMessage(tabId, { type })));
}

async function sendFullscreenMessage(tabId, enabled) {
  const tab = await safeGetTab(tabId);
  // Browser-owned new-tab/settings pages cannot host our content fullscreen.
  // This is a known unsupported mode, not a transient messaging failure. Keep
  // an unknown URL on the existing error path rather than guessing no-video.
  if (tab?.url && /^(?:chrome(?:-search|-untrusted)?:|chrome-extension:|about:)/i.test(tab.url)) {
    return enabled ? { ok: false, reason: "unsupported-page" } : { ok: true };
  }
  await ensureContentRuntimeCurrent(tabId).catch(() => {});
  if (enabled) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["fullscreen_guard.js"],
        world: "MAIN"
      });
    } catch (_) {
      // 제한 페이지에서는 보호 스크립트 없이 나머지 전환을 계속한다.
    }
  }

  let response = await sendTabMessage(tabId, { type: "set-windowed-fullscreen", enabled });
  if (response?.ok || !response?.error) return response;
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["windowed_fullscreen.js"] });
  } catch (error) {
    return { ...response, injectionError: error?.message || String(error) };
  }
  return sendTabMessage(tabId, { type: "set-windowed-fullscreen", enabled });
}

async function captureTabMetadata(tabs) {
  const groups = new Map();
  const metadata = {};
  for (const tab of tabs) {
    let group = null;
    if (Number.isInteger(tab.groupId) && tab.groupId !== NO_GROUP) {
      if (!groups.has(tab.groupId)) {
        try {
          const info = await chrome.tabGroups.get(tab.groupId);
          groups.set(tab.groupId, {
            id: tab.groupId,
            title: info.title || "",
            color: info.color,
            collapsed: Boolean(info.collapsed)
          });
        } catch (_) {
          groups.set(tab.groupId, null);
        }
      }
      group = groups.get(tab.groupId);
    }
    metadata[String(tab.id)] = {
      index: tab.index,
      pinned: Boolean(tab.pinned),
      group
    };
  }
  return metadata;
}

async function restoreGroup(tabId, sourceWindowId, meta) {
  if (!meta?.group) return;
  try {
    await chrome.tabs.group({ tabIds: [tabId], groupId: meta.group.id });
    return;
  } catch (_) {
    // 활성 탭 하나만 있던 그룹은 popup으로 이동할 때 사라질 수 있다.
  }
  try {
    const groupId = await chrome.tabs.group({
      tabIds: [tabId],
      createProperties: { windowId: sourceWindowId }
    });
    await chrome.tabGroups.update(groupId, {
      title: meta.group.title,
      color: meta.group.color,
      collapsed: meta.group.collapsed
    });
  } catch (_) {}
}

async function insertionIndexFor(sourceWindowId, meta) {
  const tabs = await chrome.tabs.query({ windowId: sourceWindowId });
  const pinnedCount = tabs.filter((tab) => tab.pinned).length;
  if (meta?.pinned) return Math.min(meta.index, pinnedCount);
  return Math.max(pinnedCount, Math.min(meta?.index ?? tabs.length, tabs.length));
}

async function movePopupTabBack(tabId, sourceWindowId, meta) {
  const temporary = await chrome.windows.create({
    tabId,
    type: "normal",
    focused: false,
    state: "minimized"
  });
  if (temporary?.id == null) throw new Error("임시 normal 창을 만들지 못했습니다.");

  try {
    await chrome.tabs.update(tabId, { pinned: Boolean(meta?.pinned) });
    const index = await insertionIndexFor(sourceWindowId, meta);
    await chrome.tabs.move(tabId, { windowId: sourceWindowId, index });
    await restoreGroup(tabId, sourceWindowId, meta);
    // Chrome 버전에 따라 마지막 탭을 옮긴 임시 normal 창에 대체 탭이
    // 자동 생성될 수 있으므로, 원래 탭 이동 성공 후 임시 창을 명시적으로 닫는다.
    try { await chrome.windows.remove(temporary.id); } catch (_) {}
    return temporary.id;
  } catch (error) {
    try { await chrome.windows.update(temporary.id, { state: "normal", focused: true }); } catch (_) {}
    throw error;
  }
}

async function getSessionTabs(popupId, session) {
  const tabs = [];
  const popup = await safeGetWindow(popupId, true);
  if (popup?.tabs) tabs.push(...popup.tabs);
  const source = await safeGetWindow(session.sourceWindowId, true);
  if (source?.tabs) tabs.push(...source.tabs);
  const order = new Map(session.tabOrder.map((tabId, index) => [tabId, index]));
  return tabs
    .filter((tab) => tab.id !== session.anchorTabId)
    .sort((a, b) => (order.get(a.id) ?? 999999) - (order.get(b.id) ?? 999999));
}

async function publishSessionState(popupId, session) {
  const tabs = await getSessionTabs(popupId, session);
  const popupTabs = (await safeGetWindow(popupId, true))?.tabs || [];
  const activeId = popupTabs.find((tab) => tab.active)?.id;
  const message = {
    type: "set-clean-window-shell",
    active: true,
    mode: session.mode,
    tabs: tabs.map((tab) => ({
      id: tab.id,
      title: tab.title || "새 탭",
      active: tab.id === activeId
    }))
  };
  await Promise.all(popupTabs.map((tab) => sendTabMessage(tab.id, message)));
}


async function createSourceAnchorIfNeeded(source, sourceTabs) {
  if (!Number.isInteger(source?.id) || sourceTabs.length !== 1) return null;
  const anchor = await chrome.tabs.create({
    windowId: source.id,
    // URL을 지정하지 않으면 Chrome의 평범한 새 탭(+) 화면이 열린다.
    active: false,
    index: sourceTabs.length
  });
  return Number.isInteger(anchor?.id) ? anchor : null;
}

async function removeSourceAnchor(anchorTabId) {
  if (!Number.isInteger(anchorTabId)) return;
  const anchor = await safeGetTab(anchorTabId);
  if (!anchor) return;
  try { await chrome.tabs.remove(anchorTabId); } catch (_) {}
}

async function removeSourceAnchorAfterReturn(anchorTabId, sourceWindowId, returnedTabId) {
  if (!Number.isInteger(anchorTabId)) return;
  const returnedTab = await safeGetTab(returnedTabId);
  if (!returnedTab || returnedTab.windowId !== sourceWindowId) return;
  await removeSourceAnchor(anchorTabId);
}

function isSyntheticAnchorUrl(url) {
  if (!url) return true;
  return url === "about:blank"
    || url.startsWith("chrome://newtab")
    || url.startsWith("chrome://new-tab-page")
    || url.startsWith("chrome-search://local-ntp");
}

async function promoteAnchorToUserTab(tab, sessions) {
  if (!Number.isInteger(tab?.id)) return false;
  let changed = false;
  const touchedPopups = [];
  for (const [popupKey, session] of Object.entries(sessions)) {
    if (session.anchorTabId !== tab.id) continue;
    session.anchorTabId = null;
    session.tabMeta ||= {};
    session.tabOrder ||= [];
    if (!session.tabOrder.includes(tab.id)) session.tabOrder.push(tab.id);
    const metadata = await captureTabMetadata([tab]);
    if (metadata[String(tab.id)]) session.tabMeta[String(tab.id)] = metadata[String(tab.id)];
    changed = true;
    touchedPopups.push([Number(popupKey), session]);
  }
  if (!changed) return false;
  await saveSessions(sessions);
  await Promise.all(touchedPopups.map(([popupId, session]) =>
    publishSessionState(popupId, session).catch(() => {})
  ));
  return true;
}

async function releaseAnchorReference(tabId, sessions) {
  if (!Number.isInteger(tabId)) return false;
  let changed = false;
  for (const session of Object.values(sessions)) {
    if (session.anchorTabId === tabId) {
      session.anchorTabId = null;
      changed = true;
    }
  }
  if (changed) await saveSessions(sessions);
  return changed;
}

async function cleanupSourceAfterPopupGone(session, source) {
  if (!source) return;
  if (!Number.isInteger(session.anchorTabId)) {
    await showWindow(source.id, null, true).catch(() => {});
    return;
  }

  const sourceTabs = await chrome.tabs.query({ windowId: source.id }).catch(() => []);
  const userTabs = sourceTabs.filter((tab) => tab.id !== session.anchorTabId);
  await removeSourceAnchor(session.anchorTabId);

  // popup을 X로 닫았고 원본 창에 Anchor밖에 없었다면 빈 원본 창도 닫힌다.
  // 반대로 사용자가 탭을 추가했거나 popup 탭을 원본 창으로 직접 합쳤다면
  // 그 실제 탭들을 그대로 살리고 원본 창만 다시 보여준다.
  if (userTabs.length > 0) {
    const stillThere = await safeGetWindow(source.id);
    if (stillThere) await showWindow(source.id, null, true).catch(() => {});
  }
}

async function enterCleanWindow(tab, source, sessions) {
  if (source.type !== "normal") throw new Error("일반 Chrome 창에서 시작해야 합니다.");
  const sourceTabs = source.tabs || await chrome.tabs.query({ windowId: source.id });
  const bounds = getBounds(source);
  if (!bounds) throw new Error("현재 창 위치와 크기를 확인할 수 없습니다.");

  const metadata = await captureTabMetadata(sourceTabs);
  const tabOrder = sourceTabs.map((candidate) => candidate.id);
  const parkedIds = tabOrder.filter((tabId) => tabId !== tab.id);
  await setMediaPaused(parkedIds, true);

  let popup = null;
  let anchorTab = null;
  try {
    // If the active tab is the only tab, moving it straight into a popup can
    // destroy the original Chrome window. Keep a temporary Chrome New Tab anchor
    // in the source so its real HWND/window identity survives the whole cycle.
    anchorTab = await createSourceAnchorIfNeeded(source, sourceTabs);

    popup = await chrome.windows.create({
      tabId: tab.id,
      type: "popup",
      focused: true,
      ...bounds
    });
    if (popup?.id == null) throw new Error("Clean Window을 만들 수 없습니다.");

    const sourceStillExists = await safeGetWindow(source.id);
    await showWindow(popup.id, bounds, true);
    const popupInitialBounds = getBounds(await safeGetWindow(popup.id)) || bounds;
    const session = {
      sourceWindowId: sourceStillExists?.id ?? null,
      sourceBounds: bounds,
      popupInitialBounds,
      mode: "clean",
      tabOrder,
      tabMeta: metadata,
      anchorTabId: anchorTab?.id ?? null,
      sourceHadSingleTab: sourceTabs.length === 1
    };
    sessions[String(popup.id)] = session;
    await saveSessions(sessions);
    if (session.sourceWindowId != null) {
      await chrome.windows.update(session.sourceWindowId, { state: "minimized" });
    }
    await publishSessionState(popup.id, session);
  } catch (error) {
    await setMediaPaused(parkedIds, false);
    if (popup?.id != null) {
      returningPopups.add(popup.id);
      delete sessions[String(popup.id)];
      await saveSessions(sessions);
      const sourceExists = await safeGetWindow(source.id);
      if (sourceExists) {
        try { await movePopupTabBack(tab.id, source.id, metadata[String(tab.id)]); } catch (_) {}
        await removeSourceAnchorAfterReturn(anchorTab?.id, source.id, tab.id);
        try { await showWindow(source.id, bounds); } catch (_) {}
      }
      returningPopups.delete(popup.id);
    } else {
      await removeSourceAnchor(anchorTab?.id);
    }
    throw error;
  }
}

async function enterWindowedFullscreen(tab, popup, session, sessions) {
  const content = await sendFullscreenMessage(tab.id, true);
  if (!content?.ok) {
    return {
      ok: false,
      reason: content?.reason || null,
      error: content?.error || null,
      injectionError: content?.injectionError || null
    };
  }
  session.mode = "windowed-fullscreen";
  session.contentFullscreen = true;
  session.frameHidden = false;
  sessions[String(popup.id)] = session;
  await saveSessions(sessions);
  await publishSessionState(popup.id, session);
  return { ok: true };
}

function cancelFullscreenReapply(popupId) {
  const timer = fullscreenReapplyTimers.get(popupId);
  if (timer) clearTimeout(timer);
  fullscreenReapplyTimers.delete(popupId);
}

function scheduleFullscreenReapply(popupId, tabId) {
  cancelFullscreenReapply(popupId);
  const timer = setTimeout(() => runSessionOperation(async () => {
    fullscreenReapplyTimers.delete(popupId);
    const latestSessions = await getSessions();
    const latestSession = latestSessions[String(popupId)];
    if (latestSession?.mode !== "windowed-fullscreen") return;
    const latestTab = await safeGetTab(tabId);
    if (!latestTab || latestTab.windowId !== popupId || latestTab.active !== true) return;
    await sendFullscreenMessage(tabId, true).catch(() => {});
  }).catch(console.error), 120);
  fullscreenReapplyTimers.set(popupId, timer);
}

async function downgradeWindowedFullscreenToClean(popupId, session, sessions) {
  if (!session || session.mode !== "windowed-fullscreen") return;
  cancelFullscreenReapply(popupId);
  const popup = await safeGetWindow(popupId, true);
  const activeTab = popup?.tabs?.find((candidate) => candidate.active);
  if (activeTab?.id != null) await sendFullscreenMessage(activeTab.id, false).catch(() => {});
  await nativeWindowRequest("restoreCleanWindowFrame").catch(() => {});
  session.mode = "clean";
  session.contentFullscreen = false;
  session.frameHidden = false;
  // Back/navigation from mode 3 intentionally lands in mode 2. The next
  // toggle should complete the cycle by returning to the normal Chrome window,
  // instead of immediately re-entering mode 3.
  session.returnToNormalNext = true;
  sessions[String(popupId)] = session;
  await saveSessions(sessions);
  await publishSessionState(popupId, session).catch(() => {});
}

async function waitForRestoredWindowStable(windowId, tabId, timeoutMs = 1200) {
  const deadline = Date.now() + timeoutMs;
  let stableHits = 0;
  while (Date.now() < deadline) {
    const restored = await safeGetWindow(windowId, true);
    const activeTab = restored?.tabs?.find((candidate) => candidate.active);
    const stable = restored
      && restored.state !== "minimized"
      && restored.focused === true
      && activeTab?.id === tabId;
    if (stable) {
      stableHits += 1;
      if (stableHits >= 2) return true;
    } else {
      stableHits = 0;
    }
    await new Promise((resolve) => setTimeout(resolve, 60));
  }
  return false;
}

async function returnToNormalWindow(tab, popup, session, sessions) {
  cancelFullscreenReapply(popup.id);
  const bounds = getBounds(popup) || session.sourceBounds;
  const useChangedBounds = boundsChanged(bounds, session.popupInitialBounds || session.sourceBounds);
  await sendFullscreenMessage(tab.id, false);
  await sendTabMessage(tab.id, { type: "set-clean-window-shell", active: false });
  await nativeWindowRequest("restoreCleanWindowFrame");

  returningPopups.add(popup.id);
  try {
    const source = await safeGetWindow(session.sourceWindowId);
    if (source) {
      await movePopupTabBack(tab.id, source.id, session.tabMeta[String(tab.id)]);
      await sendFullscreenMessage(tab.id, false).catch(() => {});
      await sendTabMessage(tab.id, { type: "set-clean-window-shell", active: false }).catch(() => {});
      await chrome.tabs.update(tab.id, { active: true });
      await removeSourceAnchorAfterReturn(session.anchorTabId, source.id, tab.id);
      delete sessions[String(popup.id)];
      await saveSessions(sessions);
      await setMediaPaused(session.tabOrder, false);
      // 복귀 과정의 마지막 작업으로 원본 Chrome 창을 활성화한다.
      // 마지막 popup/임시 창이 닫힌 뒤 포커스가 빠지는 것을 방지한다.
      await showWindow(source.id, useChangedBounds ? bounds : session.sourceBounds, true);
      // Focus verification is diagnostic only. Do not hold the global Alt+C
      // transition lock while Chrome settles the restored normal window.
      recordTransitionDebug("normal-restore-wait", { windowId: source.id, tabId: tab.id }).catch(() => {});
      waitForRestoredWindowStable(source.id, tab.id, 420)
        .then((restoreStable) => recordTransitionDebug(
          restoreStable ? "normal-restore-stable" : "normal-restore-timeout",
          { windowId: source.id, tabId: tab.id }
        ))
        .catch(() => {});
    } else {
      const normal = await chrome.windows.create({
        tabId: tab.id,
        type: "normal",
        focused: true,
        ...(bounds || {})
      });
      if (normal?.id == null) throw new Error("일반 Chrome 창으로 복귀하지 못했습니다.");
      await chrome.tabs.update(tab.id, { pinned: Boolean(session.tabMeta[String(tab.id)]?.pinned), active: true });
      await restoreGroup(tab.id, normal.id, session.tabMeta[String(tab.id)]);
      await removeSourceAnchor(session.anchorTabId);
      delete sessions[String(popup.id)];
      await saveSessions(sessions);
      await setMediaPaused(session.tabOrder, false);
      await chrome.windows.update(normal.id, { focused: true });
    }
  } catch (error) {
    delete sessions[String(popup.id)];
    await saveSessions(sessions);
    const source = await safeGetWindow(session.sourceWindowId);
    if (source) await showWindow(source.id, bounds || session.sourceBounds, true).catch(() => {});
    await setMediaPaused(session.tabOrder, false);
    throw error;
  } finally {
    returningPopups.delete(popup.id);
  }
}

async function switchCleanWindowTab(popupId, targetTabId, sessions) {
  const session = sessions[String(popupId)];
  if (!session) return;
  const source = await safeGetWindow(session.sourceWindowId);
  const oldPopup = await safeGetWindow(popupId, true);
  const current = oldPopup?.tabs?.find((tab) => tab.active);
  const target = await chrome.tabs.get(targetTabId);
  if (!source || !current || target.windowId !== source.id || current.id === targetTabId) return;

  session.tabMeta ||= {};
  session.tabOrder ||= [];
  if (!session.tabMeta[String(target.id)]) {
    const metadata = await captureTabMetadata([target]);
    if (metadata[String(target.id)]) session.tabMeta[String(target.id)] = metadata[String(target.id)];
  }
  if (!session.tabOrder.includes(target.id)) session.tabOrder.push(target.id);

  const bounds = getBounds(oldPopup) || session.sourceBounds;
  returningPopups.add(popupId);
  let newPopup = null;
  try {
    await setMediaPaused([current.id], true);
    await sendFullscreenMessage(current.id, false);
    await nativeWindowRequest("restoreCleanWindowFrame");
    await movePopupTabBack(current.id, source.id, session.tabMeta[String(current.id)]);

    newPopup = await chrome.windows.create({
      tabId: targetTabId,
      type: "popup",
      focused: true,
      ...(bounds || {})
    });
    if (newPopup?.id == null) throw new Error("선택한 탭의 Clean Window을 만들지 못했습니다.");
    session.popupInitialBounds = getBounds(newPopup) || bounds;
    await chrome.windows.update(source.id, { state: "minimized" });
    await setMediaPaused([targetTabId], false);

    delete sessions[String(popupId)];
    sessions[String(newPopup.id)] = session;
    await saveSessions(sessions);
    if (session.mode === "windowed-fullscreen") {
      const content = await sendFullscreenMessage(targetTabId, true);
      if (!content?.ok) {
        session.mode = "clean";
        session.contentFullscreen = false;
        session.frameHidden = false;
        await nativeWindowRequest("restoreCleanWindowFrame").catch(() => {});
        sessions[String(newPopup.id)] = session;
        await saveSessions(sessions);
      }
    }
    await publishSessionState(newPopup.id, session);
  } catch (error) {
    delete sessions[String(popupId)];
    if (newPopup?.id != null) delete sessions[String(newPopup.id)];
    await saveSessions(sessions);
    if (newPopup?.id != null) {
      returningPopups.add(newPopup.id);
      try {
        const targetNow = await chrome.tabs.get(targetTabId);
        if (targetNow.windowId !== source.id) {
          await movePopupTabBack(targetTabId, source.id, session.tabMeta[String(targetTabId)]);
        }
      } catch (_) {}
      returningPopups.delete(newPopup.id);
    }
    await showWindow(source.id, bounds || session.sourceBounds, true).catch(() => {});
    await setMediaPaused(session.tabOrder, false);
    throw error;
  } finally {
    returningPopups.delete(popupId);
  }
}

async function recoverSessions() {
  const sessions = await getSessions();
  let changed = false;
  for (const [popupKey, session] of Object.entries(sessions)) {
    const popupId = Number(popupKey);
    const popup = await safeGetWindow(popupId);
    const source = await safeGetWindow(session.sourceWindowId);
    if (!popup) {
      if (source) await cleanupSourceAfterPopupGone(session, source);
      await setMediaPaused(session.tabOrder || [], false);
      delete sessions[popupKey];
      changed = true;
    } else if (!source && session.sourceWindowId != null) {
      session.sourceWindowId = null;
      changed = true;
    }
  }
  if (changed) await saveSessions(sessions);
  return sessions;
}

async function materializeFullscreenMode(windowId) {
  if (!Number.isInteger(windowId) || pendingFullscreenTransitions.has(windowId)) return;
  pendingFullscreenTransitions.add(windowId);
  try {
    const pending = await getFullscreenPending();
    const request = pending[String(windowId)];
    if (!request) return;

    const source = await safeGetWindow(windowId, true);
    if (!source || source.state === "fullscreen") return;
    const tab = source.tabs?.find((candidate) => candidate.id === request.tabId)
      || source.tabs?.find((candidate) => candidate.active);
    if (!tab) return;

    const sessions = await getSessions();
    const existingSession = sessions[String(windowId)];
    if (request.kind === "existing-session" || existingSession) {
      if (!existingSession) return;
      const targetMode = request.kind === "existing-session"
        ? request.mode
        : (existingSession.mode === "clean" ? "windowed-fullscreen" : "normal");
      if (targetMode === "windowed-fullscreen") {
        await enterWindowedFullscreen(tab, source, existingSession, sessions);
      } else if (targetMode === "normal") {
        await returnToNormalWindow(tab, source, existingSession, sessions);
      }
      delete pending[String(windowId)];
      await saveFullscreenPending(pending);
      return;
    }

    await enterCleanWindow(tab, source, sessions);
    const popupEntry = Object.entries(sessions)
      .find(([, session]) => session.sourceWindowId === windowId);
    if (request.mode === "windowed-fullscreen" && popupEntry) {
      const popupId = Number(popupEntry[0]);
      const session = popupEntry[1];
      const popup = await safeGetWindow(popupId, true);
      const popupTab = popup?.tabs?.find((candidate) => candidate.active);
      if (popup && popupTab) await enterWindowedFullscreen(popupTab, popup, session, sessions);
    }

    delete pending[String(windowId)];
    await saveFullscreenPending(pending);
  } finally {
    pendingFullscreenTransitions.delete(windowId);
  }
}

function scheduleFullscreenMaterialize(windowId) {
  if (!Number.isInteger(windowId)) return;
  const previous = fullscreenMaterializeTimers.get(windowId);
  if (previous) clearTimeout(previous);
  const timer = setTimeout(() => {
    fullscreenMaterializeTimers.delete(windowId);
    runSessionOperation(() => materializeFullscreenMode(windowId)).catch(console.error);
  }, 75);
  fullscreenMaterializeTimers.set(windowId, timer);
}

async function toggleCleanWindow(preferredWindowId, preferredTabId, inputSource = "unknown") {
  // Validate the currently focused origin again before taking the lock. A stale
  // command tab from another virtual desktop is not authority to activate it.
  let { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);
  if (!window || window.id == null || !tab || tab.id == null) return;

  const now = Date.now();
  if (transitionInProgress) {
    if (now - transitionStartedAt < TRANSITION_STALE_MS) {
      if (transitionQueue.length < MAX_TRANSITION_QUEUE) {
        transitionQueue.push({ windowId: window.id, tabId: tab.id, inputSource });
      }
      await recordTransitionDebug("queued", { windowId: window.id, tabId: tab.id, inputSource, queuedCount: transitionQueue.length });
      return;
    }
    // A previous transition exceeded the guard interval. Do not leave Alt+C
    // permanently dead; retire the stale lock and let the freshly focused
    // command become the new owner. The serial prevents an old finally block
    // from clearing this newer transition.
    await recordTransitionDebug("stale-lock-recovered", { windowId: window.id, tabId: tab.id, inputSource });
    transitionInProgress = false;
  }

  transitionInProgress = true;
  transitionStartedAt = Date.now();
  const mySerial = ++transitionSerial;
  await recordTransitionDebug("start", { windowId: window.id, tabId: tab.id, inputSource });
  return runSessionOperation(async () => {
  try {
    const current = await getFocusedContext(window.id, tab.id);
    if (!current.window || !current.tab) return;
    window = current.window;
    tab = current.tab;
    await recordTransitionDebug("ensure-runtime", { windowId: window.id, tabId: tab.id });
    await ensureContentRuntimeCurrent(tab.id).catch(() => {});
    await recordTransitionDebug("recover-sessions", { windowId: window.id, tabId: tab.id });
    const sessions = await recoverSessions();
    const session = sessions[String(window.id)];
    const fullscreenPending = await getFullscreenPending();
    const pendingRequest = fullscreenPending[String(window.id)];

    if (window.state === "fullscreen") {
      if (session) {
        fullscreenPending[String(window.id)] = {
          kind: "existing-session",
          mode: "windowed-fullscreen",
          tabId: tab.id
        };
        await saveFullscreenPending(fullscreenPending);
        await chrome.windows.update(window.id, { state: "normal" });
        scheduleFullscreenMaterialize(window.id);
        return;
      }
      if (!pendingRequest) {
        fullscreenPending[String(window.id)] = { mode: "clean", tabId: tab.id };
        await saveFullscreenPending(fullscreenPending);
        return;
      }
      if (pendingRequest.mode === "clean") {
        pendingRequest.mode = "windowed-fullscreen";
        pendingRequest.tabId = tab.id;
        await saveFullscreenPending(fullscreenPending);
        await chrome.windows.update(window.id, { state: "normal" });
        scheduleFullscreenMaterialize(window.id);
        return;
      }
    } else if (pendingRequest) {
      await materializeFullscreenMode(window.id);
      return;
    }

    if (!session) {
      const parkedSession = Object.entries(sessions).find(([, candidate]) => candidate.sourceWindowId === window.id);
      if (parkedSession) {
        await chrome.windows.update(Number(parkedSession[0]), { focused: true }).catch(() => {});
        return;
      }
      await recordTransitionDebug("enter-clean", { windowId: window.id, tabId: tab.id });
      await enterCleanWindow(tab, window, sessions);
    }
    else if (session.mode === "clean") {
      if (session.returnToNormalNext === true) {
        session.returnToNormalNext = false;
        sessions[String(window.id)] = session;
        await saveSessions(sessions);
        await recordTransitionDebug("clean-to-normal", { windowId: window.id, tabId: tab.id });
        await returnToNormalWindow(tab, window, session, sessions);
      } else {
        await recordTransitionDebug("clean-to-windowed-fullscreen", { windowId: window.id, tabId: tab.id });
        const entered = await enterWindowedFullscreen(tab, window, session, sessions);
        if (!entered?.ok && ["no-video", "unsupported-page"].includes(entered?.reason)) {
          // After browser Back/SPA navigation the video can legitimately be gone.
          // Mode 3 is impossible on that page, so skip it instead of trapping the
          // cycle in mode 2: 1 -> 2 -> (no video/unsupported page) -> 1.
          await recordTransitionDebug("clean-skip-missing-video-to-normal", {
            windowId: window.id, tabId: tab.id, reason: entered.reason
          });
          await returnToNormalWindow(tab, window, session, sessions);
        } else if (!entered?.ok) {
          await recordTransitionDebug("mode3-failed", {
            windowId: window.id, tabId: tab.id,
            reason: entered?.reason || null,
            error: String(entered?.error || "No content fullscreen response").slice(0, 300),
            injectionError: entered?.injectionError ? String(entered.injectionError).slice(0, 300) : null
          });
          // A temporary runtime/native miss is different from a confirmed
          // no-video page. Preserve Clean mode so a transient failure never
          // ejects the user unexpectedly.
          await publishSessionState(window.id, session).catch(() => {});
        }
      }
    }
    else {
      await recordTransitionDebug("fullscreen-to-normal", { windowId: window.id, tabId: tab.id });
      await returnToNormalWindow(tab, window, session, sessions);
    }
  } catch (error) {
    await recordTransitionDebug("transition-error", {
      windowId: window.id, tabId: tab.id, error: String(error?.message || error).slice(0, 300)
    });
    throw error;
  } finally {
    // Only the transition that currently owns the serial may release the lock.
    // This matters when a stale transition finishes after a newer command has
    // already taken ownership.
    if (transitionSerial === mySerial) {
      transitionInProgress = false;
      transitionStartedAt = 0;
      await recordTransitionDebug("finish", { windowId: window.id, tabId: tab.id, inputSource });
      scheduleQueuedToggle();
    }
  }
  });
}

chrome.action.onClicked.addListener((tab) => {
  toggleCleanWindow(tab?.windowId, tab?.id, "action").catch(console.error);
});

// Use one input owner on both web pages and browser-owned new tabs. Ignore the
// event's optional tab: it can still describe the previously used Chrome window.
chrome.commands.onCommand.addListener((command) => {
  if (command !== "toggle-clean-window") return;
  getActuallyFocusedContext().then(({ window, tab }) => {
    if (!window || !tab) return;
    return toggleCleanWindow(window.id, tab.id, "command");
  }).catch(console.error);
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "toggle-clean-window-request") {
    // Old content runtimes may still send the same gesture. The official command
    // path owns Alt+C; do not duplicate it with speculative delayed callbacks.
    return false;
  }
  if (message?.type === "windowed-fullscreen-video-gone") {
    const popupId = sender.tab?.windowId;
    if (Number.isInteger(popupId)) {
      runSessionOperation(async () => {
        const sessions = await getSessions();
        const session = sessions[String(popupId)];
        if (session?.mode === "windowed-fullscreen") {
          await downgradeWindowedFullscreenToClean(popupId, session, sessions);
        }
      }).catch(console.error);
    }
    return false;
  }
  if (message?.type === "return-clean-window-normal-request") {
    const popupId = sender.tab?.windowId;
    const tabId = sender.tab?.id;
    runSessionOperation(async () => {
      const sessions = await getSessions();
      const session = sessions[String(popupId)];
      const popup = await safeGetWindow(popupId, true);
      const tab = popup?.tabs?.find((candidate) => candidate.id === tabId)
        || popup?.tabs?.find((candidate) => candidate.active);
      if (!session || !popup || !tab) return;
      await returnToNormalWindow(tab, popup, session, sessions);
    }).catch(console.error);
    return false;
  }
  if (message?.type === "activate-clean-window-tab") {
    const popupId = sender.tab?.windowId;
    const tabId = Number(message.tabId);
    if (Number.isInteger(popupId) && Number.isInteger(tabId)) {
      runSessionOperation(async () => switchCleanWindowTab(popupId, tabId, await getSessions()))
        .then(() => sendResponse({ ok: true }))
        .catch((error) => {
          console.error(error);
          sendResponse({ ok: false, error: error?.message || String(error) });
        });
      return true;
    }
    sendResponse({ ok: false, error: "전환할 탭 정보가 올바르지 않습니다." });
    return false;
  }
  if (message?.type === "get-clean-window-shell") {
    const popupId = sender.tab?.windowId;
    getSessions().then(async (sessions) => {
      const session = sessions[String(popupId)];
      if (!session) return sendResponse({ ok: true, active: false });
      const tabs = await getSessionTabs(popupId, session);
      sendResponse({
        ok: true,
        active: true,
        mode: session.mode,
        tabs: tabs.map((tab) => ({
          id: tab.id,
          title: tab.title || "새 탭",
          active: tab.windowId === popupId
        }))
      });
    }).catch((error) => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
  return false;
});

chrome.tabs.onActivated.addListener(async ({ windowId }) => {
  const sessions = await getSessions();
  const session = sessions[String(windowId)];
  if (session) await publishSessionState(windowId, session);
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => runSessionOperation(async () => {
  const sessions = await getSessions();

  // 사용자가 자리 지킴이 새 탭에서 검색하거나 사이트를 열기 시작하면
  // 그 순간부터는 사용자 탭이다. 더 이상 숨기거나 자동 삭제하지 않는다.
  if (changeInfo.url && !isSyntheticAnchorUrl(changeInfo.url)) {
    await promoteAnchorToUserTab(tab, sessions);
  }

  for (const [popupKey, session] of Object.entries(sessions)) {
    if (tab.windowId === Number(popupKey) || tab.windowId === session.sourceWindowId) {
      if (changeInfo.title || changeInfo.url || changeInfo.status === "complete") {
        await publishSessionState(Number(popupKey), session).catch(() => {});
      }
      if ((changeInfo.url || changeInfo.status === "complete")
          && tab.windowId === Number(popupKey)
          && tab.active
          && session.mode === "windowed-fullscreen") {
        scheduleFullscreenReapply(Number(popupKey), tab.id);
      }
    }
  }
}).catch(console.error));

chrome.tabs.onCreated.addListener(async (tab) => {
  const sessions = await getSessions();
  for (const [popupKey, session] of Object.entries(sessions)) {
    if (tab.windowId === session.sourceWindowId) {
      await publishSessionState(Number(popupKey), session).catch(() => {});
    }
  }
});

chrome.tabs.onRemoved.addListener((tabId, removeInfo) => runSessionOperation(async () => {
  const sessions = await getSessions();
  let changed = false;
  for (const [popupKey, session] of Object.entries(sessions)) {
    if (session.anchorTabId === tabId) {
      session.anchorTabId = null;
      changed = true;
    }
    // 원본 창에서 사용자가 일반 탭을 닫은 경우에만 세션 목록에서도 정리한다.
    if (removeInfo.windowId === session.sourceWindowId && session.tabOrder?.includes(tabId)) {
      session.tabOrder = session.tabOrder.filter((id) => id !== tabId);
      if (session.tabMeta) delete session.tabMeta[String(tabId)];
      changed = true;
      await publishSessionState(Number(popupKey), session).catch(() => {});
    }
  }
  if (changed) await saveSessions(sessions);
}).catch(console.error));

chrome.tabs.onAttached.addListener((tabId, attachInfo) => runSessionOperation(async () => {
  const sessions = await getSessions();
  let changed = false;
  for (const session of Object.values(sessions)) {
    if (session.anchorTabId === tabId && attachInfo.newWindowId !== session.sourceWindowId) {
      // Anchor를 다른 창으로 끌어냈다면 이제 사용자가 소유한 탭으로 보고 건드리지 않는다.
      session.anchorTabId = null;
      changed = true;
    }
  }
  if (changed) await saveSessions(sessions);
}).catch(console.error));

chrome.windows.onRemoved.addListener((windowId) => {
  if (returningPopups.has(windowId)) return;
  return runSessionOperation(async () => {
  const sessions = await getSessions();
  const closedPopupSession = sessions[String(windowId)];
  if (closedPopupSession) {
    delete sessions[String(windowId)];
    await saveSessions(sessions);
    const source = await safeGetWindow(closedPopupSession.sourceWindowId);
    if (source) await cleanupSourceAfterPopupGone(closedPopupSession, source);
    await setMediaPaused(closedPopupSession.tabOrder || [], false);
    return;
  }

  let changed = false;
  for (const session of Object.values(sessions)) {
    if (session.sourceWindowId === windowId) {
      session.sourceWindowId = null;
      changed = true;
    }
  }
  if (changed) await saveSessions(sessions);
  }).catch(console.error);
});

chrome.windows.onBoundsChanged.addListener((window) => {
  if (!Number.isInteger(window?.id)) return;
  scheduleFullscreenMaterialize(window.id);
});

runSessionOperation(() => recoverSessions()).catch(console.error);


chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason !== "update") return;
  chrome.tabs.query({}).then(async (tabs) => {
    for (const tab of tabs) {
      if (!Number.isInteger(tab.id)) continue;
      if (!/^https?:/i.test(tab.url || "")) continue;
      await ensureContentRuntimeCurrent(tab.id).catch(() => {});
    }
  }).catch(() => {});
});
