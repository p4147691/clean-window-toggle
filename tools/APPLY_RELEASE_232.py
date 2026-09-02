from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"marker not found: {label}")
    return text.replace(old, new, 1)

# manifest
manifest_path = ROOT / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = "2.3.2"
manifest["description"] = (
    "주소창과 탭바를 숨기고 작은 Chrome 창 안에서 집중해서 보며, "
    "한 탭 창에서도 원래 Chrome 창 정체성을 안정적으로 보존합니다."
)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# background
path = ROOT / "background.js"
text = path.read_text(encoding="utf-8")

# 1) Real Chrome New Tab Page: omit URL instead of about:blank.
text = replace_once(
    text,
    '''  const anchor = await chrome.tabs.create({
    windowId: source.id,
    url: "about:blank",
    active: false,
    index: sourceTabs.length
  });''',
    '''  const anchor = await chrome.tabs.create({
    windowId: source.id,
    // URL을 지정하지 않으면 Chrome의 평범한 새 탭(+) 화면이 열린다.
    active: false,
    index: sourceTabs.length
  });''',
    "anchor new tab",
)

# 2) Helpers for synthetic-anchor lifecycle and popup-gone cleanup.
anchor_marker = '''async function removeSourceAnchorAfterReturn(anchorTabId, sourceWindowId, returnedTabId) {
  if (!Number.isInteger(anchorTabId)) return;
  const returnedTab = await safeGetTab(returnedTabId);
  if (!returnedTab || returnedTab.windowId !== sourceWindowId) return;
  await removeSourceAnchor(anchorTabId);
}

'''
anchor_helpers = anchor_marker + '''function isSyntheticAnchorUrl(url) {
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

'''
text = replace_once(text, anchor_marker, anchor_helpers, "anchor lifecycle helpers")

# 3) Updated comment.
text = text.replace(
    '''    // If the active tab is the only tab, moving it straight into a popup can
    // destroy the original Chrome window. Keep a temporary blank anchor in the
    // source window so its real HWND/window identity survives the whole cycle.''',
    '''    // If the active tab is the only tab, moving it straight into a popup can
    // destroy the original Chrome window. Keep a temporary Chrome New Tab anchor
    // in the source so its real HWND/window identity survives the whole cycle.''',
    1,
)

# 4) Newly added source tabs: capture metadata before switching them into popup.
switch_marker = '''  const target = await chrome.tabs.get(targetTabId);
  if (!source || !current || target.windowId !== source.id || current.id === targetTabId) return;

  const bounds = getBounds(oldPopup) || session.sourceBounds;'''
switch_replacement = '''  const target = await chrome.tabs.get(targetTabId);
  if (!source || !current || target.windowId !== source.id || current.id === targetTabId) return;

  session.tabMeta ||= {};
  session.tabOrder ||= [];
  if (!session.tabMeta[String(target.id)]) {
    const metadata = await captureTabMetadata([target]);
    if (metadata[String(target.id)]) session.tabMeta[String(target.id)] = metadata[String(target.id)];
  }
  if (!session.tabOrder.includes(target.id)) session.tabOrder.push(target.id);

  const bounds = getBounds(oldPopup) || session.sourceBounds;'''
text = replace_once(text, switch_marker, switch_replacement, "switch metadata for new source tabs")

# 5) Recovery cleanup now distinguishes a sole synthetic anchor from real user tabs.
recover_old = '''    if (!popup) {
      if (source && Number.isInteger(session.anchorTabId)) {
        // The Clean popup itself is already gone, so its active tab is gone too.
        // Removing the sole anchor preserves the pre-2.3 single-tab close semantics.
        await removeSourceAnchor(session.anchorTabId);
      } else if (source) {
        await showWindow(source.id, session.sourceBounds, true).catch(() => {});
      }
      await setMediaPaused(session.tabOrder || [], false);'''
recover_new = '''    if (!popup) {
      if (source) await cleanupSourceAfterPopupGone(session, source);
      await setMediaPaused(session.tabOrder || [], false);'''
text = replace_once(text, recover_old, recover_new, "recover popup gone cleanup")

# 6) Anchor URL navigation => promote to normal user tab; keep normal shell updates.
updated_old = '''chrome.tabs.onUpdated.addListener(async (_tabId, changeInfo, tab) => {
  const sessions = await getSessions();
  for (const [popupKey, session] of Object.entries(sessions)) {
    if (tab.windowId === Number(popupKey) || tab.windowId === session.sourceWindowId) {
      if (changeInfo.title || changeInfo.status === "complete") {
        await publishSessionState(Number(popupKey), session).catch(() => {});
      }
      if (changeInfo.status === "complete"
          && tab.windowId === Number(popupKey)
          && tab.active
          && session.mode === "windowed-fullscreen") {
        await sendFullscreenMessage(tab.id, true).catch(() => {});
      }
    }
  }
});
'''
updated_new = '''chrome.tabs.onUpdated.addListener(async (_tabId, changeInfo, tab) => {
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
      if (changeInfo.status === "complete"
          && tab.windowId === Number(popupKey)
          && tab.active
          && session.mode === "windowed-fullscreen") {
        await sendFullscreenMessage(tab.id, true).catch(() => {});
      }
    }
  }
});

chrome.tabs.onCreated.addListener(async (tab) => {
  const sessions = await getSessions();
  for (const [popupKey, session] of Object.entries(sessions)) {
    if (tab.windowId === session.sourceWindowId) {
      await publishSessionState(Number(popupKey), session).catch(() => {});
    }
  }
});

chrome.tabs.onRemoved.addListener(async (tabId, removeInfo) => {
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
});

chrome.tabs.onAttached.addListener(async (tabId, attachInfo) => {
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
});
'''
text = replace_once(text, updated_old, updated_new, "tab lifecycle guardrails")

# 7) Popup close/manual merge cleanup.
window_old = '''  if (closedPopupSession) {
    delete sessions[String(windowId)];
    await saveSessions(sessions);
    const source = await safeGetWindow(closedPopupSession.sourceWindowId);
    if (source && Number.isInteger(closedPopupSession.anchorTabId)) {
      // Closing the Clean popup closes the only real tab. Remove the temporary
      // anchor too so a blank source window is not left behind.
      await removeSourceAnchor(closedPopupSession.anchorTabId);
    } else if (source) {
      await showWindow(source.id, closedPopupSession.sourceBounds, true).catch(() => {});
    }
    await setMediaPaused(closedPopupSession.tabOrder || [], false);
    return;
  }
'''
window_new = '''  if (closedPopupSession) {
    delete sessions[String(windowId)];
    await saveSessions(sessions);
    const source = await safeGetWindow(closedPopupSession.sourceWindowId);
    if (source) await cleanupSourceAfterPopupGone(closedPopupSession, source);
    await setMediaPaused(closedPopupSession.tabOrder || [], false);
    return;
  }
'''
text = replace_once(text, window_old, window_new, "window removed cleanup")

path.write_text(text, encoding="utf-8")

# README note
readme_path = ROOT / "README.md"
readme = readme_path.read_text(encoding="utf-8")
needle = "- 탭이 하나뿐인 창에서도 임시 Anchor 탭으로 원래 Chrome 창 자체를 살려 두어 복귀 안정성 향상\n"
replacement = (
    "- 탭이 하나뿐인 창에서도 임시 Anchor 탭으로 원래 Chrome 창 자체를 살려 두어 복귀 안정성 향상\n"
    "- Anchor는 Chrome의 평범한 새 탭 화면으로 만들며, 사용자가 그 탭에서 검색/탐색을 시작하면 자동으로 일반 사용자 탭으로 승격해 보존\n"
    "- 원본 창에 탭 추가·닫기·이동, popup 탭 수동 합치기 같은 조작이 있어도 Anchor만 안전하게 정리하고 사용자 탭은 유지\n"
)
if needle in readme and "일반 사용자 탭으로 승격" not in readme:
    readme = readme.replace(needle, replacement, 1)
readme_path.write_text(readme, encoding="utf-8")

print("Prepared Clean Window 2.3.2 anchor guardrails.")
