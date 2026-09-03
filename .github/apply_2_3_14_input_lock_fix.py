from pathlib import Path

bg = Path('background.js')
s = bg.read_text(encoding='utf-8')
old = '''async function toggleCleanWindow(preferredWindowId, preferredTabId, inputSource = "unknown") {
  if (transitionInProgress) return;
  transitionInProgress = true;
  try {
    const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);
    if (!window || window.id == null || !tab || tab.id == null) return;
    await ensureContentRuntimeCurrent(tab.id).catch(() => {});
'''
new = '''async function toggleCleanWindow(preferredWindowId, preferredTabId, inputSource = "unknown") {
  // Resolve the real origin before taking the global transition lock. Chrome can
  // briefly emit a stale command event for the parked/previous window after SPA
  // back navigation. That stale event must not block the valid content-script
  // request coming from the currently focused Clean Window popup.
  const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);
  if (!window || window.id == null || !tab || tab.id == null) return;
  if (transitionInProgress) return;
  transitionInProgress = true;
  try {
    await ensureContentRuntimeCurrent(tab.id).catch(() => {});
'''
if old not in s:
    raise SystemExit('toggle lock block not found')
bg.write_text(s.replace(old, new, 1), encoding='utf-8')

wf = Path('windowed_fullscreen.js')
s = wf.read_text(encoding='utf-8')
if 'const RUNTIME_VERSION = "2.3.13";' not in s:
    raise SystemExit('runtime 2.3.13 not found')
wf.write_text(s.replace('const RUNTIME_VERSION = "2.3.13";', 'const RUNTIME_VERSION = "2.3.14";', 1), encoding='utf-8')

mf = Path('manifest.json')
s = mf.read_text(encoding='utf-8')
if '"version": "2.3.13"' not in s:
    raise SystemExit('manifest 2.3.13 not found')
mf.write_text(s.replace('"version": "2.3.13"', '"version": "2.3.14"', 1), encoding='utf-8')
