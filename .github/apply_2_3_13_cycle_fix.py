from pathlib import Path

bg = Path('background.js')
s = bg.read_text(encoding='utf-8')

old = '''  session.mode = "clean";
  session.contentFullscreen = false;
  session.frameHidden = false;
  sessions[String(popupId)] = session;
'''
new = '''  session.mode = "clean";
  session.contentFullscreen = false;
  session.frameHidden = false;
  // Back/navigation from mode 3 intentionally lands in mode 2. The next
  // toggle should complete the cycle by returning to the normal Chrome window,
  // instead of immediately re-entering mode 3.
  session.returnToNormalNext = true;
  sessions[String(popupId)] = session;
'''
if old not in s:
    raise SystemExit('downgrade state block not found')
s = s.replace(old, new, 1)

old = '''    else if (session.mode === "clean") {
      const entered = await enterWindowedFullscreen(tab, window, session, sessions);
      // A temporary content/runtime miss must never eject the user back to
      // the parked normal Chrome window. Stay in Clean mode and keep focus
      // on the exact popup that emitted Alt+C.
      if (!entered) await publishSessionState(window.id, session).catch(() => {});
    }
'''
new = '''    else if (session.mode === "clean") {
      if (session.returnToNormalNext === true) {
        session.returnToNormalNext = false;
        sessions[String(window.id)] = session;
        await saveSessions(sessions);
        await returnToNormalWindow(tab, window, session, sessions);
      } else {
        const entered = await enterWindowedFullscreen(tab, window, session, sessions);
        // A temporary content/runtime miss must never eject the user back to
        // the parked normal Chrome window. Stay in Clean mode and keep focus
        // on the exact popup that emitted Alt+C.
        if (!entered) await publishSessionState(window.id, session).catch(() => {});
      }
    }
'''
if old not in s:
    raise SystemExit('clean mode toggle block not found')
s = s.replace(old, new, 1)
bg.write_text(s, encoding='utf-8')

wf = Path('windowed_fullscreen.js')
s = wf.read_text(encoding='utf-8')
if 'const RUNTIME_VERSION = "2.3.12";' not in s:
    raise SystemExit('runtime 2.3.12 not found')
wf.write_text(s.replace('const RUNTIME_VERSION = "2.3.12";', 'const RUNTIME_VERSION = "2.3.13";', 1), encoding='utf-8')

mf = Path('manifest.json')
s = mf.read_text(encoding='utf-8')
if '"version": "2.3.12"' not in s:
    raise SystemExit('manifest 2.3.12 not found')
mf.write_text(s.replace('"version": "2.3.12"', '"version": "2.3.13"', 1), encoding='utf-8')
