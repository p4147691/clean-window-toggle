from pathlib import Path

bg = Path('background.js')
s = bg.read_text(encoding='utf-8')

marker = '''async function getFocusedContext(preferredWindowId, preferredTabId) {\n'''
helper = '''async function getActuallyFocusedContext() {\n  try {\n    const windows = await chrome.windows.getAll({ populate: true });\n    const focusedWindow = windows.find((candidate) => candidate.focused === true);\n    if (!focusedWindow || focusedWindow.id == null) return { window: null, tab: null };\n    const activeTab = focusedWindow.tabs?.find((candidate) => candidate.active);\n    if (!activeTab || activeTab.id == null) return { window: null, tab: null };\n    return { window: focusedWindow, tab: activeTab };\n  } catch (_) {\n    return { window: null, tab: null };\n  }\n}\n\n'''
if helper not in s:
    if marker not in s:
        raise SystemExit('focused context marker not found')
    s = s.replace(marker, helper + marker, 1)

old = '''  // Input ownership is mode-specific: normal Chrome uses commands, while an\n  // active Clean Window popup uses only the content-script keydown path. This\n  // prevents the same Alt+C gesture from racing through two asynchronous paths.\n  const currentSessions = await getSessions();\n  const directSession = currentSessions[String(window.id)];\n  if (inputSource === "command" && directSession) return;\n  if (inputSource === "content" && !directSession) return;\n\n  if (transitionInProgress) return;\n'''
new = '''  // Alt+C has one owner: chrome.commands. The content-script keydown remains\n  // only as a legacy safety hook and must not race the command path.\n  if (inputSource === "content") return;\n\n  if (transitionInProgress) return;\n'''
if old not in s:
    raise SystemExit('2.3.16 ownership block not found')
s = s.replace(old, new, 1)

old = '''chrome.commands.onCommand.addListener((command, tab) => {\n  if (command !== "toggle-clean-window") return;\n  toggleCleanWindow(tab?.windowId, tab?.id, "command").catch(console.error);\n});\n'''
new = '''chrome.commands.onCommand.addListener((command) => {\n  if (command !== "toggle-clean-window") return;\n  // The tab attached to a commands event can briefly point at the parked or\n  // previously focused window after popup/navigation transitions. Resolve the\n  // window that is actually focused at the moment of the shortcut instead.\n  getActuallyFocusedContext().then(({ window, tab }) => {\n    if (!window || !tab) return;\n    return toggleCleanWindow(window.id, tab.id, "command");\n  }).catch(console.error);\n});\n'''
if old not in s:
    raise SystemExit('command handler block not found')
s = s.replace(old, new, 1)

bg.write_text(s, encoding='utf-8')

wf = Path('windowed_fullscreen.js')
s = wf.read_text(encoding='utf-8')
if 'const RUNTIME_VERSION = "2.3.16";' not in s:
    raise SystemExit('runtime 2.3.16 not found')
wf.write_text(s.replace('const RUNTIME_VERSION = "2.3.16";', 'const RUNTIME_VERSION = "2.3.17";', 1), encoding='utf-8')

mf = Path('manifest.json')
s = mf.read_text(encoding='utf-8')
if '"version": "2.3.16"' not in s:
    raise SystemExit('manifest 2.3.16 not found')
mf.write_text(s.replace('"version": "2.3.16"', '"version": "2.3.17"', 1), encoding='utf-8')
