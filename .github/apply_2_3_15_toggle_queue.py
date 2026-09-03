from pathlib import Path

bg = Path('background.js')
s = bg.read_text(encoding='utf-8')

old = '''let transitionInProgress = false;
const returningPopups = new Set();
'''
new = '''let transitionInProgress = false;
let queuedToggleRequest = null;
let lastToggleInput = null;
const returningPopups = new Set();
'''
if old not in s:
    raise SystemExit('global transition block not found')
s = s.replace(old, new, 1)

marker = '''async function toggleCleanWindow(preferredWindowId, preferredTabId, inputSource = "unknown") {
'''
helper = '''function isCrossInputDuplicate(windowId, tabId, inputSource) {
  const now = Date.now();
  const previous = lastToggleInput;
  const isShortcutSource = inputSource === "command" || inputSource === "content";
  const isDuplicate = Boolean(
    isShortcutSource
    && previous
    && (previous.inputSource === "command" || previous.inputSource === "content")
    && previous.inputSource !== inputSource
    && previous.tabId === tabId
    && now - previous.at < 350
  );
  if (!isDuplicate) lastToggleInput = { windowId, tabId, inputSource, at: now };
  return isDuplicate;
}

'''
if marker not in s:
    raise SystemExit('toggle function marker not found')
s = s.replace(marker, helper + marker, 1)

old = '''  const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);
  if (!window || window.id == null || !tab || tab.id == null) return;
  if (transitionInProgress) return;
  transitionInProgress = true;
  try {
'''
new = '''  const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);
  if (!window || window.id == null || !tab || tab.id == null) return;

  // Chrome can deliver one Alt+C through both commands and the content-script
  // fallback. Treat those two deliveries as one gesture, but never discard a
  // genuinely later gesture just because the previous transition is still
  // finishing cleanup.
  if (isCrossInputDuplicate(window.id, tab.id, inputSource)) return;
  if (transitionInProgress) {
    queuedToggleRequest = {
      preferredWindowId: window.id,
      preferredTabId: tab.id,
      inputSource
    };
    return;
  }

  transitionInProgress = true;
  try {
'''
if old not in s:
    raise SystemExit('transition entry block not found')
s = s.replace(old, new, 1)

old = '''  } finally {
    transitionInProgress = false;
  }
}

chrome.action.onClicked.addListener((tab) => {
'''
new = '''  } finally {
    transitionInProgress = false;
    const queued = queuedToggleRequest;
    queuedToggleRequest = null;
    if (queued) {
      setTimeout(() => {
        toggleCleanWindow(
          queued.preferredWindowId,
          queued.preferredTabId,
          queued.inputSource
        ).catch(console.error);
      }, 0);
    }
  }
}

chrome.action.onClicked.addListener((tab) => {
'''
if old not in s:
    raise SystemExit('transition finally block not found')
s = s.replace(old, new, 1)
bg.write_text(s, encoding='utf-8')

wf = Path('windowed_fullscreen.js')
s = wf.read_text(encoding='utf-8')
if 'const RUNTIME_VERSION = "2.3.14";' not in s:
    raise SystemExit('runtime 2.3.14 not found')
wf.write_text(s.replace('const RUNTIME_VERSION = "2.3.14";', 'const RUNTIME_VERSION = "2.3.15";', 1), encoding='utf-8')

mf = Path('manifest.json')
s = mf.read_text(encoding='utf-8')
if '"version": "2.3.14"' not in s:
    raise SystemExit('manifest 2.3.14 not found')
mf.write_text(s.replace('"version": "2.3.14"', '"version": "2.3.15"', 1), encoding='utf-8')
