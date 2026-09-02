from pathlib import Path
import json

wf_path = Path('windowed_fullscreen.js')
bg_path = Path('background.js')
manifest_path = Path('manifest.json')

wf = wf_path.read_text(encoding='utf-8')
bg = bg_path.read_text(encoding='utf-8')
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

if manifest.get('version') != '2.3.8':
    raise SystemExit(f"unexpected base version: {manifest.get('version')}")
if 'const RUNTIME_VERSION = "2.3.9";' in wf:
    raise SystemExit('window runtime already patched')

# 1) Make the content script safely reinjectable from 2.3.9 onward.
prefix = '''(() => {\nconst RUNTIME_VERSION = "2.3.9";\nconst RUNTIME_KEY = "__cleanWindowRuntimeV1";\nconst MESSAGE_BRIDGE_KEY = "__cleanWindowRuntimeMessageBridgeV1";\nconst previousRuntime = globalThis[RUNTIME_KEY];\nconst previousSnapshot = previousRuntime?.hotReload === true && typeof previousRuntime.snapshot === "function"\n  ? previousRuntime.snapshot()\n  : null;\nif (previousRuntime?.hotReload === true && typeof previousRuntime.dispose === "function") {\n  previousRuntime.dispose();\n}\nconst runtimeAbort = new AbortController();\n\n'''
wf = prefix + wf
wf = wf.replace('let fullscreenTarget = null;', 'let fullscreenTarget = previousSnapshot?.fullscreenTarget?.isConnected\n  ? previousSnapshot.fullscreenTarget\n  : document.querySelector(`[${TARGET_ATTRIBUTE}]`);', 1)
wf = wf.replace('let savedScrollX = 0;', 'let savedScrollX = Number(previousSnapshot?.savedScrollX) || 0;', 1)
wf = wf.replace('let savedScrollY = 0;', 'let savedScrollY = Number(previousSnapshot?.savedScrollY) || 0;', 1)
wf = wf.replace('const pausedMedia = new Set();', 'const pausedMedia = new Set(previousSnapshot?.pausedMedia || []);', 1)

listener_replacements = {
    'document.addEventListener("yt-navigate-finish", () => scheduleFullscreenRepair(40), true);': 'document.addEventListener("yt-navigate-finish", () => scheduleFullscreenRepair(40), { capture: true, signal: runtimeAbort.signal });',
    'window.addEventListener("popstate", () => scheduleFullscreenRepair(40), true);': 'window.addEventListener("popstate", () => scheduleFullscreenRepair(40), { capture: true, signal: runtimeAbort.signal });',
    'window.addEventListener("hashchange", () => scheduleFullscreenRepair(40), true);': 'window.addEventListener("hashchange", () => scheduleFullscreenRepair(40), { capture: true, signal: runtimeAbort.signal });',
    'window.addEventListener("pageshow", () => scheduleFullscreenRepair(40), true);': 'window.addEventListener("pageshow", () => scheduleFullscreenRepair(40), { capture: true, signal: runtimeAbort.signal });',
    'window.addEventListener("pageshow", () => setTimeout(refreshCleanWindowShellState, 0), true);': 'window.addEventListener("pageshow", () => setTimeout(refreshCleanWindowShellState, 0), { capture: true, signal: runtimeAbort.signal });',
    '}, true);\n\nfunction isContainedFullscreenActive()': '}, { capture: true, signal: runtimeAbort.signal });\n\nfunction isContainedFullscreenActive()'
}
for old, new in listener_replacements.items():
    if old not in wf:
        raise SystemExit(f'missing listener pattern: {old[:80]}')
    wf = wf.replace(old, new, 1)

# The final keydown listener is the last capture=true listener in the file.
needle = '  chrome.runtime.sendMessage({ type: "toggle-clean-window-request" });\n}, true);'
replacement = '  chrome.runtime.sendMessage({ type: "toggle-clean-window-request" });\n}, { capture: true, signal: runtimeAbort.signal });'
if needle not in wf:
    raise SystemExit('keydown listener tail not found')
wf = wf.replace(needle, replacement, 1)

# Convert the per-runtime Chrome message listener into a stable global bridge.
start_marker = 'chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {'
end_marker = '\n});\n\nfunction refreshCleanWindowShellState()'
start = wf.index(start_marker)
end = wf.index(end_marker, start)
body = wf[start + len(start_marker):end]
handler = '''function handleRuntimeMessage(message, _sender, sendResponse) {\n  if (message?.type === "clean-window-runtime-probe") {\n    sendResponse({ ok: true, version: RUNTIME_VERSION, hotReload: true });\n    return false;\n  }''' + body + '''\n}\n\nfunction snapshotRuntimeState() {\n  return {\n    savedScrollX,\n    savedScrollY,\n    fullscreenTarget: fullscreenTarget?.isConnected ? fullscreenTarget : null,\n    pausedMedia: [...pausedMedia]\n  };\n}\n\nfunction disposeRuntime() {\n  runtimeAbort.abort();\n  stopFullscreenRepairWatch();\n}\n\nconst runtimeApi = {\n  version: RUNTIME_VERSION,\n  hotReload: true,\n  snapshot: snapshotRuntimeState,\n  dispose: disposeRuntime,\n  handleMessage: handleRuntimeMessage\n};\nglobalThis[RUNTIME_KEY] = runtimeApi;\n\nif (!globalThis[MESSAGE_BRIDGE_KEY]) {\n  const bridge = (message, sender, sendResponse) => {\n    const current = globalThis[RUNTIME_KEY];\n    if (!current || typeof current.handleMessage !== "function") return false;\n    return current.handleMessage(message, sender, sendResponse);\n  };\n  chrome.runtime.onMessage.addListener(bridge);\n  globalThis[MESSAGE_BRIDGE_KEY] = bridge;\n}\n\nfunction refreshCleanWindowShellState()'''
wf = wf[:start] + handler + wf[end + len(end_marker):]

# If hot-reloaded while stage 3 is already active, reconnect the observer seamlessly.
wf += '''\n\nif (document.documentElement.hasAttribute(ROOT_ATTRIBUTE)) {\n  fullscreenTarget ||= document.querySelector(`[${TARGET_ATTRIBUTE}]`);\n  startFullscreenRepairWatch();\n}\n})();\n'''

# 2) Background: probe supported runtimes and hot-inject only when the old runtime explicitly supports it.
insert_after = '''function sendTabMessage(tabId, message) {\n  return new Promise((resolve) => {\n    chrome.tabs.sendMessage(tabId, message, (response) => {\n      if (chrome.runtime.lastError) {\n        resolve({ ok: false, error: chrome.runtime.lastError.message });\n        return;\n      }\n      resolve(response || { ok: false });\n    });\n  });\n}\n'''
if insert_after not in bg:
    raise SystemExit('sendTabMessage block not found')
hot_runtime = insert_after + '''\nconst CONTENT_RUNTIME_VERSION = chrome.runtime.getManifest().version;\n\nasync function ensureContentRuntimeCurrent(tabId) {\n  if (!Number.isInteger(tabId)) return { ok: false, error: "invalid-tab" };\n  let probe = await sendTabMessage(tabId, { type: "clean-window-runtime-probe" });\n\n  // 2.3.8 and older tabs do not understand the probe. Never force-inject over\n  // those pages because their anonymous listeners cannot be safely detached.\n  if (!probe?.ok || probe.hotReload !== true) {\n    return { ok: true, legacy: true, version: probe?.version || null };\n  }\n  if (probe.version === CONTENT_RUNTIME_VERSION) return probe;\n\n  try {\n    await chrome.scripting.executeScript({\n      target: { tabId },\n      files: ["windowed_fullscreen.js"]\n    });\n  } catch (error) {\n    return { ok: false, error: error?.message || String(error) };\n  }\n\n  probe = await sendTabMessage(tabId, { type: "clean-window-runtime-probe" });\n  if (!probe?.ok || probe.version !== CONTENT_RUNTIME_VERSION) {\n    return { ok: false, error: "runtime-hot-reload-verification-failed" };\n  }\n  return probe;\n}\n'''
bg = bg.replace(insert_after, hot_runtime, 1)

# Make stage-3 reapply and each user toggle refresh a compatible old runtime first.
old_sf = 'async function sendFullscreenMessage(tabId, enabled) {\n  if (enabled) {'
new_sf = 'async function sendFullscreenMessage(tabId, enabled) {\n  await ensureContentRuntimeCurrent(tabId).catch(() => {});\n  if (enabled) {'
if old_sf not in bg:
    raise SystemExit('sendFullscreenMessage marker not found')
bg = bg.replace(old_sf, new_sf, 1)

old_toggle = '''    const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);\n    if (!window || window.id == null || !tab || tab.id == null) return;\n    const sessions = await recoverSessions();'''
new_toggle = '''    const { window, tab } = await getFocusedContext(preferredWindowId, preferredTabId);\n    if (!window || window.id == null || !tab || tab.id == null) return;\n    await ensureContentRuntimeCurrent(tab.id).catch(() => {});\n    const sessions = await recoverSessions();'''
if old_toggle not in bg:
    raise SystemExit('toggle runtime insertion point not found')
bg = bg.replace(old_toggle, new_toggle, 1)

# On future extension updates, update only tabs that explicitly advertise hot-reload support.
bg += '''\n\nchrome.runtime.onInstalled.addListener((details) => {\n  if (details.reason !== "update") return;\n  chrome.tabs.query({}).then(async (tabs) => {\n    for (const tab of tabs) {\n      if (!Number.isInteger(tab.id)) continue;\n      if (!/^https?:/i.test(tab.url || "")) continue;\n      await ensureContentRuntimeCurrent(tab.id).catch(() => {});\n    }\n  }).catch(() => {});\n});\n'''

wf_path.write_text(wf, encoding='utf-8')
bg_path.write_text(bg, encoding='utf-8')
manifest['version'] = '2.3.9'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('PATCH_239_HOT_RUNTIME_OK')
