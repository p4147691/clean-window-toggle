from pathlib import Path
import json

root = Path('.')
bg_path = root / 'background.js'
manifest_path = root / 'manifest.json'

bg = bg_path.read_text(encoding='utf-8')

old_globals = '''let transitionInProgress = false;
const returningPopups = new Set();
const pendingFullscreenTransitions = new Set();
const fullscreenMaterializeTimers = new Map();
'''
new_globals = '''let transitionInProgress = false;
let lastToggleInput = { tabId: null, source: null, at: 0 };
const CROSS_INPUT_DEDUPE_MS = 400;
const returningPopups = new Set();
const pendingFullscreenTransitions = new Set();
const fullscreenMaterializeTimers = new Map();
'''
if old_globals not in bg:
    raise SystemExit('globals block not found')
bg = bg.replace(old_globals, new_globals, 1)

old_focus = '''async function getFocusedContext(preferredWindowId, preferredTabId) {
  const window = Number.isInteger(preferredWindowId)
    ? await chrome.windows.get(preferredWindowId, { populate: true })
    : await chrome.windows.getLastFocused({ populate: true });
  const tab = Number.isInteger(preferredTabId)
    ? window.tabs?.find((candidate) => candidate.id === preferredTabId)
    : window.tabs?.find((candidate) => candidate.active);
  return { window, tab };
}
'''
new_focus = '''async function getFocusedContext(preferredWindowId, preferredTabId) {
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

function isCrossInputDuplicate(tabId, source) {
  const now = Date.now();
  const duplicate = Number.isInteger(tabId)
    && lastToggleInput.tabId === tabId
    && lastToggleInput.source !== source
    && now - lastToggleInput.at < CROSS_INPUT_DEDUPE_MS;
  if (!duplicate) lastToggleInput = { tabId, source, at: now };
  return duplicate;
}
'''
if old_focus not in bg:
    raise SystemExit('focus block not found')
bg = bg.replace(old_focus, new_focus, 1)

old_toggle = '''async function toggleCleanWindow(preferredWindowId, preferredTabId) {
  if (transitionInProgress) return;
  transitionInProgress = true;
  try {
    const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);
    if (!window || window.id == null || !tab || tab.id == null) return;
'''
new_toggle = '''async function toggleCleanWindow(preferredWindowId, preferredTabId, inputSource = "unknown") {
  if (transitionInProgress) return;
  transitionInProgress = true;
  try {
    const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);
    if (!window || window.id == null || !tab || tab.id == null) return;
    if (isCrossInputDuplicate(tab.id, inputSource)) return;
'''
if old_toggle not in bg:
    raise SystemExit('toggle block not found')
bg = bg.replace(old_toggle, new_toggle, 1)

replacements = [
    (
'''chrome.action.onClicked.addListener((tab) => {
  toggleCleanWindow(tab?.windowId, tab?.id).catch(console.error);
});''',
'''chrome.action.onClicked.addListener((tab) => {
  toggleCleanWindow(tab?.windowId, tab?.id, "action").catch(console.error);
});'''
    ),
    (
'''chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "toggle-clean-window") return;
  toggleCleanWindow(tab?.windowId, tab?.id).catch(console.error);
});''',
'''chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "toggle-clean-window") return;
  toggleCleanWindow(tab?.windowId, tab?.id, "command").catch(console.error);
});'''
    ),
    (
'''  if (message?.type === "toggle-clean-window-request") {
    toggleCleanWindow(sender.tab?.windowId, sender.tab?.id).catch(console.error);
    return false;
  }''',
'''  if (message?.type === "toggle-clean-window-request") {
    toggleCleanWindow(sender.tab?.windowId, sender.tab?.id, "content").catch(console.error);
    return false;
  }'''
    )
]
for old, new in replacements:
    if old not in bg:
        raise SystemExit('handler block not found:\n' + old)
    bg = bg.replace(old, new, 1)

bg_path.write_text(bg, encoding='utf-8')

manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
if manifest.get('version') != '2.3.4':
    raise SystemExit(f"unexpected base version: {manifest.get('version')}")
manifest['version'] = '2.3.5'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('PATCH_235_FOCUS_OK')
