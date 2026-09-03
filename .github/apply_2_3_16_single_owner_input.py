from pathlib import Path

bg = Path('background.js')
s = bg.read_text(encoding='utf-8')

s = s.replace('''let transitionInProgress = false;\nlet queuedToggleRequest = null;\nlet lastToggleInput = null;\nconst returningPopups = new Set();\n''', '''let transitionInProgress = false;\nconst returningPopups = new Set();\n''', 1)

start = s.find('function isCrossInputDuplicate(')
end = s.find('async function toggleCleanWindow(', start)
if start == -1 or end == -1:
    raise SystemExit('duplicate helper block not found')
s = s[:start] + s[end:]

old = '''  // Chrome can deliver one Alt+C through both commands and the content-script\n  // fallback. Treat those two deliveries as one gesture, but never discard a\n  // genuinely later gesture just because the previous transition is still\n  // finishing cleanup.\n  if (isCrossInputDuplicate(window.id, tab.id, inputSource)) return;\n  if (transitionInProgress) {\n    queuedToggleRequest = {\n      preferredWindowId: window.id,\n      preferredTabId: tab.id,\n      inputSource\n    };\n    return;\n  }\n\n  transitionInProgress = true;\n'''
new = '''  // Input ownership is mode-specific: normal Chrome uses commands, while an\n  // active Clean Window popup uses only the content-script keydown path. This\n  // prevents the same Alt+C gesture from racing through two asynchronous paths.\n  const currentSessions = await getSessions();\n  const directSession = currentSessions[String(window.id)];\n  if (inputSource === "command" && directSession) return;\n  if (inputSource === "content" && !directSession) return;\n\n  if (transitionInProgress) return;\n  transitionInProgress = true;\n'''
if old not in s:
    raise SystemExit('queue entry block not found')
s = s.replace(old, new, 1)

old = '''  } finally {\n    transitionInProgress = false;\n    const queued = queuedToggleRequest;\n    queuedToggleRequest = null;\n    if (queued) {\n      setTimeout(() => {\n        toggleCleanWindow(\n          queued.preferredWindowId,\n          queued.preferredTabId,\n          queued.inputSource\n        ).catch(console.error);\n      }, 0);\n    }\n  }\n}\n'''
new = '''  } finally {\n    transitionInProgress = false;\n  }\n}\n'''
if old not in s:
    raise SystemExit('queue finally block not found')
s = s.replace(old, new, 1)

bg.write_text(s, encoding='utf-8')

wf = Path('windowed_fullscreen.js')
s = wf.read_text(encoding='utf-8')
if 'const RUNTIME_VERSION = "2.3.15";' not in s:
    raise SystemExit('runtime 2.3.15 not found')
wf.write_text(s.replace('const RUNTIME_VERSION = "2.3.15";', 'const RUNTIME_VERSION = "2.3.16";', 1), encoding='utf-8')

mf = Path('manifest.json')
s = mf.read_text(encoding='utf-8')
if '"version": "2.3.15"' not in s:
    raise SystemExit('manifest 2.3.15 not found')
mf.write_text(s.replace('"version": "2.3.15"', '"version": "2.3.16"', 1), encoding='utf-8')
