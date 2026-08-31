const STORAGE_KEY = "cleanWindowSessionsV8";
const DESKTOP_EXTENSION_ID = "fcjhjgbebcebpdmfedcoabaonhfkjmfo";
const NO_GROUP = -1;

let transitionInProgress = false;
const returningPopups = new Set();

function nativeWindowRequest(type) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(DESKTOP_EXTENSION_ID, { type }, (response) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      resolve(response || { ok: false, error: "Native helper 응답이 없습니다." });
    });
  });
}

async function getSessions() {
  const result = await chrome.storage.local.get(STORAGE_KEY);
  return result[STORAGE_KEY] || {};
}

async function saveSessions(sessions) {
  await chrome.storage.local.set({ [STORAGE_KEY]: sessions });
}

async function safeGetWindow(windowId, populate = false) {
  if (!Number.isInteger(windowId)) return null;
  try { return await chrome.windows.get(windowId, { populate }); }
  catch (_) { return null; }
}

async function getFocusedContext(preferredWindowId, preferredTabId) {
  const window = Number.isInteger(preferredWindowId)
    ? await chrome.windows.get(preferredWindowId, { populate: true })
    : await chrome.windows.getLastFocused({ populate: true });
  const tab = Number.isInteger(preferredTabId)
    ? window.tabs?.find((candidate) => candidate.id === preferredTabId)
    : window.tabs?.find((candidate) => candidate.active);
  return { window, tab };
}

function getBounds(window) {
  if (![window.left, window.top, window.width, window.height].every(Number.isInteger)) return null;
  return { left: window.left, top: window.top, width: window.width, height: window.height };
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

async function setMediaPaused(tabIds, paused) {
  const type = paused ? "pause-clean-window-media" : "resume-clean-window-media";
  await Promise.all(tabIds.filter(Number.isInteger).map((tabId) => sendTabMessage(tabId, { type })));
}

async function sendFullscreenMessage(tabId, enabled) {
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
  } catch (_) {
    return response;
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
  return tabs.sort((a, b) => (order.get(a.id) ?? 999999) - (order.get(b.id) ?? 999999));
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
  try {
    popup = await chrome.windows.create({
      tabId: tab.id,
      type: "popup",
      focused: true,
      ...bounds
    });
    if (popup?.id == null) throw new Error("Clean Window을 만들 수 없습니다.");

    const sourceStillExists = await safeGetWindow(source.id);
    const session = {
      sourceWindowId: sourceStillExists?.id ?? null,
      sourceBounds: bounds,
      mode: "clean",
      tabOrder,
      tabMeta: metadata
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
        try { await showWindow(source.id, bounds); } catch (_) {}
      }
      returningPopups.delete(popup.id);
    }
    throw error;
  }
}

async function enterWindowedFullscreen(tab, popup, session, sessions) {
  const content = await sendFullscreenMessage(tab.id, true);
  const frame = await nativeWindowRequest("hideCleanWindowFrame");
  session.mode = "windowed-fullscreen";
  session.contentFullscreen = Boolean(content?.ok);
  session.frameHidden = Boolean(frame?.ok);
  sessions[String(popup.id)] = session;
  await saveSessions(sessions);
  await publishSessionState(popup.id, session);
}

async function returnToNormalWindow(tab, popup, session, sessions) {
  const bounds = getBounds(popup) || session.sourceBounds;
  await sendFullscreenMessage(tab.id, false);
  await sendTabMessage(tab.id, { type: "set-clean-window-shell", active: false });
  await nativeWindowRequest("restoreCleanWindowFrame");

  returningPopups.add(popup.id);
  try {
    const source = await safeGetWindow(session.sourceWindowId);
    if (source) {
      await movePopupTabBack(tab.id, source.id, session.tabMeta[String(tab.id)]);
      await chrome.tabs.update(tab.id, { active: true });
      delete sessions[String(popup.id)];
      await saveSessions(sessions);
      await setMediaPaused(session.tabOrder, false);
      // 복귀 과정의 마지막 작업으로 원본 Chrome 창을 활성화한다.
      // 마지막 popup/임시 창이 닫힌 뒤 포커스가 빠지는 것을 방지한다.
      await showWindow(source.id, bounds, true);
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
    await chrome.windows.update(source.id, { state: "minimized" });
    await setMediaPaused([targetTabId], false);

    delete sessions[String(popupId)];
    sessions[String(newPopup.id)] = session;
    await saveSessions(sessions);
    if (session.mode === "windowed-fullscreen") {
      await sendFullscreenMessage(targetTabId, true);
      await nativeWindowRequest("hideCleanWindowFrame");
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
      if (source) await showWindow(source.id, session.sourceBounds, true).catch(() => {});
      await setMediaPaused(session.tabOrder || [], false);
      delete sessions[popupKey];
      changed = true;
    } else if (!source && session.sourceWindowId != null) {
      session.sourceWindowId = null;
      changed = true;
    } else if (source && source.state !== "minimized") {
      await chrome.windows.update(source.id, { state: "minimized" }).catch(() => {});
    }
  }
  if (changed) await saveSessions(sessions);
  return sessions;
}

async function toggleCleanWindow(preferredWindowId, preferredTabId) {
  if (transitionInProgress) return;
  transitionInProgress = true;
  try {
    const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);
    if (!window || window.id == null || !tab || tab.id == null) return;
    const sessions = await recoverSessions();
    const session = sessions[String(window.id)];
    if (!session) {
      const parkedSession = Object.entries(sessions).find(([, candidate]) => candidate.sourceWindowId === window.id);
      if (parkedSession) {
        await chrome.windows.update(Number(parkedSession[0]), { focused: true }).catch(() => {});
        return;
      }
      await enterCleanWindow(tab, window, sessions);
    }
    else if (session.mode === "clean") await enterWindowedFullscreen(tab, window, session, sessions);
    else await returnToNormalWindow(tab, window, session, sessions);
  } finally {
    transitionInProgress = false;
  }
}

chrome.action.onClicked.addListener((tab) => {
  toggleCleanWindow(tab?.windowId, tab?.id).catch(console.error);
});

// 페이지나 주소창 중 어디에 키보드 포커스가 있든 Chrome이 활성 상태이면
// 공식 commands 경로로 Alt+C를 처리한다. content script의 keydown은
// popup에서 commands 이벤트가 누락되는 환경을 위한 보조 경로로 유지한다.
chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "toggle-clean-window") return;
  toggleCleanWindow(tab?.windowId, tab?.id).catch(console.error);
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "toggle-clean-window-request") {
    toggleCleanWindow(sender.tab?.windowId, sender.tab?.id).catch(console.error);
    return false;
  }
  if (message?.type === "activate-clean-window-tab") {
    const popupId = sender.tab?.windowId;
    const tabId = Number(message.tabId);
    if (Number.isInteger(popupId) && Number.isInteger(tabId)) {
      getSessions()
        .then((sessions) => switchCleanWindowTab(popupId, tabId, sessions))
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

chrome.tabs.onUpdated.addListener(async (_tabId, changeInfo, tab) => {
  if (!changeInfo.title) return;
  const sessions = await getSessions();
  for (const [popupKey, session] of Object.entries(sessions)) {
    if (tab.windowId === Number(popupKey) || tab.windowId === session.sourceWindowId) {
      await publishSessionState(Number(popupKey), session).catch(() => {});
    }
  }
});

chrome.windows.onRemoved.addListener(async (windowId) => {
  if (returningPopups.has(windowId)) return;
  const sessions = await getSessions();
  const closedPopupSession = sessions[String(windowId)];
  if (closedPopupSession) {
    delete sessions[String(windowId)];
    await saveSessions(sessions);
    const source = await safeGetWindow(closedPopupSession.sourceWindowId);
    if (source) await showWindow(source.id, closedPopupSession.sourceBounds, true).catch(() => {});
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
});

recoverSessions().catch(console.error);
