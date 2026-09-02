from pathlib import Path
import json

bg_path = Path('background.js')
manifest_path = Path('manifest.json')

bg = bg_path.read_text(encoding='utf-8')

old_focus = '''async function getFocusedContext(preferredWindowId, preferredTabId) {
  // Alt+C must always act on the Chrome window the user is actually looking at.
  // Command/content-script events can arrive after a Clean Window transition has
  // already moved the tab into another window, so never trust stale ids blindly.
  let focusedWindow = null;
  try {
    focusedWindow = await chrome.windows.getLastFocused({ populate: true });
  } catch (_) {
    return { window: null, tab: null };
  }
  if (!focusedWindow || focusedWindow.id == null || focusedWindow.focused === false) {
    return { window: null, tab: null };
  }
  if (Number.isInteger(preferredWindowId) && preferredWindowId !== focusedWindow.id) {
    return { window: null, tab: null };
  }

  const activeTab = focusedWindow.tabs?.find((candidate) => candidate.active);
  if (!activeTab || activeTab.id == null) return { window: null, tab: null };
  if (Number.isInteger(preferredTabId) && preferredTabId !== activeTab.id) {
    return { window: null, tab: null };
  }
  return { window: focusedWindow, tab: activeTab };
}
'''

new_focus = '''async function getFocusedContext(preferredWindowId, preferredTabId, inputSource = "unknown") {
  // The official commands event can carry tab/window ids captured around the
  // instant a Clean Window tab is moved into a popup. For that route, use the
  // browser's *current* focused window as the single source of truth.
  if (inputSource === "command") {
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
    if (!activeTab || activeTab.id == null) return { window: null, tab: null };
    return { window: focusedWindow, tab: activeTab };
  }

  // Content-script/action requests originate from a concrete window. Validate
  // that exact window is still focused, so a delayed request from an older Clean
  // Window can never affect the window the user has since switched away from.
  if (Number.isInteger(preferredWindowId)) {
    const preferredWindow = await safeGetWindow(preferredWindowId, true);
    if (!preferredWindow || preferredWindow.id == null || preferredWindow.focused !== true) {
      return { window: null, tab: null };
    }
    const activeTab = preferredWindow.tabs?.find((candidate) => candidate.active);
    if (!activeTab || activeTab.id == null) return { window: null, tab: null };
    if (Number.isInteger(preferredTabId) && preferredTabId !== activeTab.id) {
      return { window: null, tab: null };
    }
    return { window: preferredWindow, tab: activeTab };
  }

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
'''

if old_focus not in bg:
    raise SystemExit('2.3.5 focus block not found')
bg = bg.replace(old_focus, new_focus, 1)

old_call = 'const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);'
new_call = 'const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId, inputSource);'
if old_call not in bg:
    raise SystemExit('toggle focus call not found')
bg = bg.replace(old_call, new_call, 1)

bg_path.write_text(bg, encoding='utf-8')

manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
if manifest.get('version') != '2.3.5':
    raise SystemExit(f"unexpected base version: {manifest.get('version')}")
manifest['version'] = '2.3.6'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('PATCH_236_FOCUS_CONTEXT_OK')
