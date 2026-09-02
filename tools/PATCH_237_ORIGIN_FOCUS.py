from pathlib import Path
import json

bg_path = Path('background.js')
manifest_path = Path('manifest.json')

bg = bg_path.read_text(encoding='utf-8')

old_globals = '''let transitionInProgress = false;
let lastToggleInput = { tabId: null, source: null, at: 0 };
const CROSS_INPUT_DEDUPE_MS = 400;
const returningPopups = new Set();
'''
new_globals = '''let transitionInProgress = false;
const returningPopups = new Set();
'''
if old_globals not in bg:
    raise SystemExit('2.3.6 globals block not found')
bg = bg.replace(old_globals, new_globals, 1)

start = bg.index('async function getFocusedContext(')
end = bg.index('\nfunction getBounds(', start)
old_focus_area = bg[start:end]
new_focus_area = '''async function getFocusedContext(preferredWindowId, preferredTabId) {
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
'''
bg = bg[:start] + new_focus_area + bg[end:]

old_call = 'const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId, inputSource);'
new_call = 'const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);'
if old_call not in bg:
    raise SystemExit('2.3.6 focus call not found')
bg = bg.replace(old_call, new_call, 1)

old_dedupe = '''    if (!window || window.id == null || !tab || tab.id == null) return;
    if (isCrossInputDuplicate(tab.id, inputSource)) return;
'''
new_dedupe = '''    if (!window || window.id == null || !tab || tab.id == null) return;
'''
if old_dedupe not in bg:
    raise SystemExit('2.3.6 dedupe call not found')
bg = bg.replace(old_dedupe, new_dedupe, 1)

if 'function isCrossInputDuplicate' in bg or 'CROSS_INPUT_DEDUPE_MS' in bg or 'lastToggleInput' in bg:
    raise SystemExit('dedupe remnants remain')

bg_path.write_text(bg, encoding='utf-8')

manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
if manifest.get('version') != '2.3.6':
    raise SystemExit(f"unexpected base version: {manifest.get('version')}")
manifest['version'] = '2.3.7'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('PATCH_237_ORIGIN_FOCUS_OK')
