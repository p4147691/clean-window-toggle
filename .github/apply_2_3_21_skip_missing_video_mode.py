from pathlib import Path
import json

bg = Path('background.js')
text = bg.read_text(encoding='utf-8')

old_enter = '''async function enterWindowedFullscreen(tab, popup, session, sessions) {
  const content = await sendFullscreenMessage(tab.id, true);
  if (!content?.ok) return false;
  session.mode = "windowed-fullscreen";
  session.contentFullscreen = true;
  session.frameHidden = false;
  sessions[String(popup.id)] = session;
  await saveSessions(sessions);
  await publishSessionState(popup.id, session);
  return true;
}'''
new_enter = '''async function enterWindowedFullscreen(tab, popup, session, sessions) {
  const content = await sendFullscreenMessage(tab.id, true);
  if (!content?.ok) {
    return {
      ok: false,
      reason: content?.reason || null,
      error: content?.error || null
    };
  }
  session.mode = "windowed-fullscreen";
  session.contentFullscreen = true;
  session.frameHidden = false;
  sessions[String(popup.id)] = session;
  await saveSessions(sessions);
  await publishSessionState(popup.id, session);
  return { ok: true };
}'''
if old_enter in text:
    text = text.replace(old_enter, new_enter, 1)
elif new_enter not in text:
    raise SystemExit('enterWindowedFullscreen marker missing')

old_toggle = '''        const entered = await enterWindowedFullscreen(tab, window, session, sessions);
        // A temporary content/runtime miss must never eject the user back to
        // the parked normal Chrome window. Stay in Clean mode and keep focus
        // on the exact popup that emitted Alt+C.
        if (!entered) await publishSessionState(window.id, session).catch(() => {});'''
new_toggle = '''        const entered = await enterWindowedFullscreen(tab, window, session, sessions);
        if (!entered?.ok && entered?.reason === "no-video") {
          // After browser Back/SPA navigation the video can legitimately be gone.
          // Mode 3 is impossible on that page, so skip it instead of trapping the
          // cycle in mode 2: 1 -> 2 -> (no video) -> 1.
          await recordTransitionDebug("clean-skip-missing-video-to-normal", { windowId: window.id, tabId: tab.id });
          await returnToNormalWindow(tab, window, session, sessions);
        } else if (!entered?.ok) {
          // A temporary runtime/native miss is different from a confirmed
          // no-video page. Preserve Clean mode so a transient failure never
          // ejects the user unexpectedly.
          await publishSessionState(window.id, session).catch(() => {});
        }'''
if old_toggle in text:
    text = text.replace(old_toggle, new_toggle, 1)
elif new_toggle not in text:
    raise SystemExit('toggle enter marker missing')

old_switch = '''      const content = await sendFullscreenMessage(targetTabId, true);
      if (!content?.ok) {
        session.mode = "clean";
        session.contentFullscreen = false;
        session.frameHidden = false;
        await nativeWindowRequest("restoreCleanWindowFrame").catch(() => {});
        sessions[String(newPopup.id)] = session;
        await saveSessions(sessions);
      }'''
# Keep switch behavior as-is; this is only here as an existence guard.
if old_switch not in text:
    raise SystemExit('switch fullscreen fallback marker missing')

manifest = Path('manifest.json')
data = json.loads(manifest.read_text(encoding='utf-8'))
if data.get('version') not in ('2.3.20', '2.3.21'):
    raise SystemExit(f"unexpected manifest version: {data.get('version')}")
data['version'] = '2.3.21'
manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

wf = Path('windowed_fullscreen.js')
wtext = wf.read_text(encoding='utf-8')
wtext = wtext.replace('const RUNTIME_VERSION = "2.3.20";', 'const RUNTIME_VERSION = "2.3.21";', 1)
if 'const RUNTIME_VERSION = "2.3.21";' not in wtext:
    raise SystemExit('runtime version marker missing')
wf.write_text(wtext, encoding='utf-8')

bg.write_text(text, encoding='utf-8')
print('PATCH_2_3_21_OK')
