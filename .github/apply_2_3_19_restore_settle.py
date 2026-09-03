from pathlib import Path
import json

bg = Path('background.js')
text = bg.read_text(encoding='utf-8')

marker = 'async function returnToNormalWindow(tab, popup, session, sessions) {'
helper = '''async function waitForRestoredWindowStable(windowId, tabId, timeoutMs = 1200) {\n  const deadline = Date.now() + timeoutMs;\n  let stableHits = 0;\n  while (Date.now() < deadline) {\n    const restored = await safeGetWindow(windowId, true);\n    const activeTab = restored?.tabs?.find((candidate) => candidate.active);\n    const stable = restored\n      && restored.state !== "minimized"\n      && restored.focused === true\n      && activeTab?.id === tabId;\n    if (stable) {\n      stableHits += 1;\n      if (stableHits >= 2) return true;\n    } else {\n      stableHits = 0;\n    }\n    await new Promise((resolve) => setTimeout(resolve, 60));\n  }\n  return false;\n}\n\n'''
if helper.strip() not in text:
    if marker not in text:
        raise SystemExit('returnToNormalWindow marker missing')
    text = text.replace(marker, helper + marker, 1)

old = '      await showWindow(source.id, useChangedBounds ? bounds : session.sourceBounds, true);'
new = '''      await showWindow(source.id, useChangedBounds ? bounds : session.sourceBounds, true);\n      await recordTransitionDebug("normal-restore-wait", { windowId: source.id, tabId: tab.id });\n      const restoreStable = await waitForRestoredWindowStable(source.id, tab.id);\n      await recordTransitionDebug(restoreStable ? "normal-restore-stable" : "normal-restore-timeout", { windowId: source.id, tabId: tab.id });'''
if new not in text:
    if old not in text:
        raise SystemExit('showWindow return target missing')
    text = text.replace(old, new, 1)

bg.write_text(text, encoding='utf-8')

manifest = Path('manifest.json')
data = json.loads(manifest.read_text(encoding='utf-8'))
data['version'] = '2.3.19'
manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

wf = Path('windowed_fullscreen.js')
wtext = wf.read_text(encoding='utf-8')
wtext = wtext.replace('const RUNTIME_VERSION = "2.3.18";', 'const RUNTIME_VERSION = "2.3.19";', 1)
wf.write_text(wtext, encoding='utf-8')

print('PATCH_2_3_19_OK')
