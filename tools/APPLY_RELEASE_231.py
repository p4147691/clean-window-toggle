from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"marker not found: {label}")
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# manifest.json
# ---------------------------------------------------------------------------
manifest_path = ROOT / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = "2.3.1"
manifest["description"] = (
    "주소창과 탭바를 숨기고 작은 Chrome 창 안에서 집중해서 보며, "
    "한 탭 창에서도 원래 Chrome 창 정체성을 안정적으로 보존합니다."
)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# ---------------------------------------------------------------------------
# background.js: merge the local fullscreen/bounds work into the validated
# Anchor production baseline. Direct-return is intentionally NOT included.
# ---------------------------------------------------------------------------
path = ROOT / "background.js"
text = path.read_text(encoding="utf-8")

if 'const FULLSCREEN_PENDING_KEY = "cleanWindowFullscreenPendingV1";' not in text:
    text = replace_once(
        text,
        'const STORAGE_KEY = "cleanWindowSessionsV8";\n',
        'const STORAGE_KEY = "cleanWindowSessionsV8";\nconst FULLSCREEN_PENDING_KEY = "cleanWindowFullscreenPendingV1";\n',
        "fullscreen pending key",
    )

if "pendingFullscreenTransitions" not in text:
    text = replace_once(
        text,
        'let transitionInProgress = false;\nconst returningPopups = new Set();\n',
        'let transitionInProgress = false;\nconst returningPopups = new Set();\nconst pendingFullscreenTransitions = new Set();\nconst fullscreenMaterializeTimers = new Map();\n',
        "fullscreen transition state",
    )

text = text.replace(
    'function nativeWindowRequest(type) {\n  return new Promise((resolve) => {\n    chrome.runtime.sendMessage(DESKTOP_EXTENSION_ID, { type }, (response) => {',
    'function nativeWindowRequest(type, details = {}) {\n  return new Promise((resolve) => {\n    chrome.runtime.sendMessage(DESKTOP_EXTENSION_ID, { type, ...details }, (response) => {',
    1,
)

if "async function getFullscreenPending()" not in text:
    text = replace_once(
        text,
        '''async function saveSessions(sessions) {
  await chrome.storage.local.set({ [STORAGE_KEY]: sessions });
}

''',
        '''async function saveSessions(sessions) {
  await chrome.storage.local.set({ [STORAGE_KEY]: sessions });
}

async function getFullscreenPending() {
  const result = await chrome.storage.local.get(FULLSCREEN_PENDING_KEY);
  return result[FULLSCREEN_PENDING_KEY] || {};
}

async function saveFullscreenPending(pending) {
  await chrome.storage.local.set({ [FULLSCREEN_PENDING_KEY]: pending });
}

''',
        "fullscreen pending storage",
    )

if "function boundsChanged(" not in text:
    text = replace_once(
        text,
        '''function getBounds(window) {
  if (![window.left, window.top, window.width, window.height].every(Number.isInteger)) return null;
  return { left: window.left, top: window.top, width: window.width, height: window.height };
}

''',
        '''function getBounds(window) {
  if (![window.left, window.top, window.width, window.height].every(Number.isInteger)) return null;
  return { left: window.left, top: window.top, width: window.width, height: window.height };
}

function boundsChanged(current, initial, tolerance = 3) {
  if (!current || !initial) return false;
  return ["left", "top", "width", "height"]
    .some((key) => Math.abs(current[key] - initial[key]) > tolerance);
}

''',
        "boundsChanged",
    )

# Materialize popup to exact source bounds and remember the actual popup baseline.
if "const popupInitialBounds = getBounds(await safeGetWindow(popup.id)) || bounds;" not in text:
    text = replace_once(
        text,
        '''    const sourceStillExists = await safeGetWindow(source.id);
    const session = {
      sourceWindowId: sourceStillExists?.id ?? null,
      sourceBounds: bounds,
      mode: "clean",
''',
        '''    const sourceStillExists = await safeGetWindow(source.id);
    await showWindow(popup.id, bounds, true);
    const popupInitialBounds = getBounds(await safeGetWindow(popup.id)) || bounds;
    const session = {
      sourceWindowId: sourceStillExists?.id ?? null,
      sourceBounds: bounds,
      popupInitialBounds,
      mode: "clean",
''',
        "popup initial bounds",
    )

# Return: only push popup bounds back to the real source if user actually moved/resized it.
if "const useChangedBounds = boundsChanged(" not in text:
    text = replace_once(
        text,
        '''async function returnToNormalWindow(tab, popup, session, sessions) {
  const bounds = getBounds(popup) || session.sourceBounds;
''',
        '''async function returnToNormalWindow(tab, popup, session, sessions) {
  const bounds = getBounds(popup) || session.sourceBounds;
  const useChangedBounds = boundsChanged(bounds, session.popupInitialBounds || session.sourceBounds);
''',
        "changed bounds return flag",
    )

text = text.replace(
    '      await showWindow(source.id, bounds, true);',
    '      await showWindow(source.id, useChangedBounds ? bounds : null, true);',
    1,
)

# Tab switch creates a new popup, so refresh the movement baseline.
if "session.popupInitialBounds = getBounds(newPopup) || bounds;" not in text:
    text = replace_once(
        text,
        '''    if (newPopup?.id == null) throw new Error("선택한 탭의 Clean Window을 만들지 못했습니다.");
    await chrome.windows.update(source.id, { state: "minimized" });
''',
        '''    if (newPopup?.id == null) throw new Error("선택한 탭의 Clean Window을 만들지 못했습니다.");
    session.popupInitialBounds = getBounds(newPopup) || bounds;
    await chrome.windows.update(source.id, { state: "minimized" });
''',
        "tab switch popup bounds",
    )

# Keep the local behavior that does not fight a user who deliberately restores
# the parked source while the Clean popup is open. Anchor still keeps it alive.
text = text.replace(
    '''    } else if (!source && session.sourceWindowId != null) {
      session.sourceWindowId = null;
      changed = true;
    } else if (source && source.state !== "minimized") {
      await chrome.windows.update(source.id, { state: "minimized" }).catch(() => {});
    }
''',
    '''    } else if (!source && session.sourceWindowId != null) {
      session.sourceWindowId = null;
      changed = true;
    }
''',
    1,
)

fullscreen_helpers = r'''async function materializeFullscreenMode(windowId) {
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
    materializeFullscreenMode(windowId).catch(console.error);
  }, 75);
  fullscreenMaterializeTimers.set(windowId, timer);
}

'''
if "async function materializeFullscreenMode(" not in text:
    text = replace_once(
        text,
        "async function toggleCleanWindow(preferredWindowId, preferredTabId) {",
        fullscreen_helpers + "async function toggleCleanWindow(preferredWindowId, preferredTabId) {",
        "fullscreen materialize helpers",
    )

# Native Chrome fullscreen state: queue the intended Clean Window mode, exit
# native fullscreen, then materialize after the window is normal again.
if "const fullscreenPending = await getFullscreenPending();" not in text:
    text = replace_once(
        text,
        '''    const sessions = await recoverSessions();
    const session = sessions[String(window.id)];
    if (!session) {
''',
        '''    const sessions = await recoverSessions();
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
''',
        "fullscreen toggle path",
    )

# Re-publish shell after loads and reapply contained fullscreen on a reloaded popup.
old_updated = '''chrome.tabs.onUpdated.addListener(async (_tabId, changeInfo, tab) => {
  if (!changeInfo.title) return;
  const sessions = await getSessions();
  for (const [popupKey, session] of Object.entries(sessions)) {
    if (tab.windowId === Number(popupKey) || tab.windowId === session.sourceWindowId) {
      await publishSessionState(Number(popupKey), session).catch(() => {});
    }
  }
});
'''
new_updated = '''chrome.tabs.onUpdated.addListener(async (_tabId, changeInfo, tab) => {
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
if old_updated in text:
    text = text.replace(old_updated, new_updated, 1)

if "chrome.windows.onBoundsChanged.addListener" not in text:
    text = replace_once(
        text,
        "\nrecoverSessions().catch(console.error);\n",
        '''
chrome.windows.onBoundsChanged.addListener((window) => {
  if (!Number.isInteger(window?.id)) return;
  scheduleFullscreenMaterialize(window.id);
});

recoverSessions().catch(console.error);
''',
        "onBoundsChanged",
    )

path.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# windowed_fullscreen.js: preserve the local explicit gold border overlay.
# ---------------------------------------------------------------------------
path = ROOT / "windowed_fullscreen.js"
text = path.read_text(encoding="utf-8")
if 'const BORDER_ID = "clean-window-gold-border";' not in text:
    text = replace_once(
        text,
        'const TAB_STRIP_ID = "clean-window-tab-strip";\n',
        'const TAB_STRIP_ID = "clean-window-tab-strip";\nconst BORDER_ID = "clean-window-gold-border";\n',
        "border id",
    )

    text = replace_once(
        text,
        '''    #${TAB_STRIP_ID},
    #${TAB_STRIP_ID} * {
      visibility: visible !important;
      box-sizing: border-box !important;
    }

    #${TAB_STRIP_ID} {
''',
        '''    #${TAB_STRIP_ID},
    #${TAB_STRIP_ID} *,
    #${BORDER_ID} {
      visibility: visible !important;
      box-sizing: border-box !important;
    }

    #${BORDER_ID} {
      position: fixed !important;
      inset: 0 !important;
      display: block !important;
      border: 2px solid #d9b84f !important;
      box-shadow: inset 0 0 4px rgba(217, 184, 79, 0.32) !important;
      pointer-events: none !important;
      z-index: 2147483647 !important;
    }

    #${TAB_STRIP_ID} {
''',
        "border css",
    )

    text = replace_once(
        text,
        "function renderTabStrip(state) {",
        '''function renderGoldBorder(active) {
  document.getElementById(BORDER_ID)?.remove();
  if (!active) return;
  const border = document.createElement("div");
  border.id = BORDER_ID;
  border.setAttribute("aria-hidden", "true");
  document.documentElement.append(border);
}

function renderTabStrip(state) {''',
        "renderGoldBorder",
    )

    text = replace_once(
        text,
        '''  if (!state?.active) {
    document.documentElement.removeAttribute(ACTIVE_ATTRIBUTE);''',
        '''  if (!state?.active) {
    renderGoldBorder(false);
    document.documentElement.removeAttribute(ACTIVE_ATTRIBUTE);''',
        "border shell off",
    )

    text = replace_once(
        text,
        '''  document.documentElement.setAttribute(MODE_ATTRIBUTE, state.mode || "clean");
  installStyles();
''',
        '''  document.documentElement.setAttribute(MODE_ATTRIBUTE, state.mode || "clean");
  installStyles();
  renderGoldBorder(state.mode === "windowed-fullscreen");
''',
        "border shell mode",
    )

    text = replace_once(
        text,
        '''function setWindowedFullscreen(enabled) {
  if (!enabled) {
    document.documentElement.removeAttribute(ROOT_ATTRIBUTE);''',
        '''function setWindowedFullscreen(enabled) {
  if (!enabled) {
    renderGoldBorder(false);
    document.documentElement.removeAttribute(ROOT_ATTRIBUTE);''',
        "border fullscreen off",
    )

    text = replace_once(
        text,
        '''  document.documentElement.setAttribute(ROOT_ATTRIBUTE, "");
  fullscreenTarget.setAttribute(TARGET_ATTRIBUTE, "");
  window.scrollTo(0, 0);''',
        '''  document.documentElement.setAttribute(ROOT_ATTRIBUTE, "");
  fullscreenTarget.setAttribute(TARGET_ATTRIBUTE, "");
  renderGoldBorder(true);
  window.scrollTo(0, 0);''',
        "border fullscreen on",
    )

path.write_text(text, encoding="utf-8")

# README: retain Anchor note and document compatibility improvements succinctly.
readme_path = ROOT / "README.md"
readme = readme_path.read_text(encoding="utf-8")
anchor_line = "- 탭이 하나뿐인 창에서도 임시 Anchor 탭으로 원래 Chrome 창 자체를 살려 두어 복귀 안정성 향상\n"
extra_line = "- popup을 실제로 옮겼을 때만 복귀 좌표를 갱신하고, Chrome 전체화면 전환도 안전하게 이어서 처리\n"
if anchor_line in readme and extra_line not in readme:
    readme = readme.replace(anchor_line, anchor_line + extra_line, 1)
readme_path.write_text(readme, encoding="utf-8")

print("Prepared Clean Window 2.3.1 stability merge.")
