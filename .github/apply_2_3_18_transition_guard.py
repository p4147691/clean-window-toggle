from pathlib import Path

bg = Path('background.js')
s = bg.read_text(encoding='utf-8')

old = '''let transitionInProgress = false;\nconst returningPopups = new Set();\n'''
new = '''let transitionInProgress = false;\nlet transitionStartedAt = 0;\nlet transitionRetryRequested = false;\nlet transitionSerial = 0;\nconst TRANSITION_STALE_MS = 2500;\nconst DEBUG_KEY = "cleanWindowTransitionDebugV1";\nconst returningPopups = new Set();\n'''
if old not in s:
    raise SystemExit('transition globals not found')
s = s.replace(old, new, 1)

marker = '''async function getSessions() {\n'''
helper = '''async function recordTransitionDebug(stage, details = {}) {\n  try {\n    await chrome.storage.local.set({\n      [DEBUG_KEY]: {\n        stage,\n        at: Date.now(),\n        transitionSerial,\n        transitionInProgress,\n        transitionStartedAt,\n        ...details\n      }\n    });\n  } catch (_) {}\n}\n\nfunction scheduleQueuedToggle() {\n  if (!transitionRetryRequested || transitionInProgress) return;\n  transitionRetryRequested = false;\n  setTimeout(() => {\n    getActuallyFocusedContext().then(({ window, tab }) => {\n      if (!window || !tab) return;\n      return toggleCleanWindow(window.id, tab.id, "command-retry");\n    }).catch(console.error);\n  }, 60);\n}\n\n'''
if marker not in s:
    raise SystemExit('getSessions marker not found')
s = s.replace(marker, helper + marker, 1)

old = '''  if (inputSource === "content") return;\n\n  if (transitionInProgress) return;\n  transitionInProgress = true;\n  try {\n    await ensureContentRuntimeCurrent(tab.id).catch(() => {});\n    const sessions = await recoverSessions();\n'''
new = '''  if (inputSource === "content") return;\n\n  const now = Date.now();\n  if (transitionInProgress) {\n    if (now - transitionStartedAt < TRANSITION_STALE_MS) {\n      transitionRetryRequested = true;\n      await recordTransitionDebug("queued", { windowId: window.id, tabId: tab.id, inputSource });\n      return;\n    }\n    // A previous transition exceeded the guard interval. Do not leave Alt+C\n    // permanently dead; retire the stale lock and let the freshly focused\n    // command become the new owner. The serial prevents an old finally block\n    // from clearing this newer transition.\n    await recordTransitionDebug("stale-lock-recovered", { windowId: window.id, tabId: tab.id, inputSource });\n    transitionInProgress = false;\n  }\n\n  transitionInProgress = true;\n  transitionStartedAt = Date.now();\n  const mySerial = ++transitionSerial;\n  await recordTransitionDebug("start", { windowId: window.id, tabId: tab.id, inputSource });\n  try {\n    await recordTransitionDebug("ensure-runtime", { windowId: window.id, tabId: tab.id });\n    await ensureContentRuntimeCurrent(tab.id).catch(() => {});\n    await recordTransitionDebug("recover-sessions", { windowId: window.id, tabId: tab.id });\n    const sessions = await recoverSessions();\n'''
if old not in s:
    raise SystemExit('transition entry block not found')
s = s.replace(old, new, 1)

# add stage logs around mode branches
s = s.replace('''      await enterCleanWindow(tab, window, sessions);\n''', '''      await recordTransitionDebug("enter-clean", { windowId: window.id, tabId: tab.id });\n      await enterCleanWindow(tab, window, sessions);\n''', 1)
s = s.replace('''        await returnToNormalWindow(tab, window, session, sessions);\n''', '''        await recordTransitionDebug("clean-to-normal", { windowId: window.id, tabId: tab.id });\n        await returnToNormalWindow(tab, window, session, sessions);\n''', 1)
s = s.replace('''        const entered = await enterWindowedFullscreen(tab, window, session, sessions);\n''', '''        await recordTransitionDebug("clean-to-windowed-fullscreen", { windowId: window.id, tabId: tab.id });\n        const entered = await enterWindowedFullscreen(tab, window, session, sessions);\n''', 1)
s = s.replace('''    else await returnToNormalWindow(tab, window, session, sessions);\n  } finally {\n    transitionInProgress = false;\n  }\n}\n''', '''    else {\n      await recordTransitionDebug("fullscreen-to-normal", { windowId: window.id, tabId: tab.id });\n      await returnToNormalWindow(tab, window, session, sessions);\n    }\n  } finally {\n    // Only the transition that currently owns the serial may release the lock.\n    // This matters when a stale transition finishes after a newer command has\n    // already taken ownership.\n    if (transitionSerial === mySerial) {\n      transitionInProgress = false;\n      transitionStartedAt = 0;\n      await recordTransitionDebug("finish", { windowId: window.id, tabId: tab.id, inputSource });\n      scheduleQueuedToggle();\n    }\n  }\n}\n''', 1)

bg.write_text(s, encoding='utf-8')

wf = Path('windowed_fullscreen.js')
s = wf.read_text(encoding='utf-8')
if 'const RUNTIME_VERSION = "2.3.17";' not in s:
    raise SystemExit('runtime 2.3.17 not found')
wf.write_text(s.replace('const RUNTIME_VERSION = "2.3.17";', 'const RUNTIME_VERSION = "2.3.18";', 1), encoding='utf-8')

mf = Path('manifest.json')
s = mf.read_text(encoding='utf-8')
if '"version": "2.3.17"' not in s:
    raise SystemExit('manifest 2.3.17 not found')
mf.write_text(s.replace('"version": "2.3.17"', '"version": "2.3.18"', 1), encoding='utf-8')
