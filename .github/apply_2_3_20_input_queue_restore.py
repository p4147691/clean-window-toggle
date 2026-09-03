from pathlib import Path
import json

bg = Path('background.js')
text = bg.read_text(encoding='utf-8')

old_decl = 'let transitionRetryRequested = false;'
new_decl = 'let transitionRetryCount = 0;'
if old_decl in text:
    text = text.replace(old_decl, new_decl, 1)
elif new_decl not in text:
    raise SystemExit('transition retry declaration missing')

old_scheduler = '''function scheduleQueuedToggle() {
  if (!transitionRetryRequested || transitionInProgress) return;
  transitionRetryRequested = false;
  setTimeout(() => {
    getActuallyFocusedContext().then(({ window, tab }) => {
      if (!window || !tab) return;
      return toggleCleanWindow(window.id, tab.id, "command-retry");
    }).catch(console.error);
  }, 60);
}'''
new_scheduler = '''function scheduleQueuedToggle() {
  if (transitionRetryCount <= 0 || transitionInProgress) return;
  transitionRetryCount -= 1;
  setTimeout(() => {
    getActuallyFocusedContext().then(({ window, tab }) => {
      if (!window || !tab) {
        scheduleQueuedToggle();
        return;
      }
      return toggleCleanWindow(window.id, tab.id, "command-retry");
    }).catch(console.error);
  }, 35);
}'''
if old_scheduler in text:
    text = text.replace(old_scheduler, new_scheduler, 1)
elif new_scheduler not in text:
    raise SystemExit('queued toggle scheduler marker missing')

old_queue = '''      transitionRetryRequested = true;
      await recordTransitionDebug("queued", { windowId: window.id, tabId: tab.id, inputSource });'''
new_queue = '''      transitionRetryCount = Math.min(transitionRetryCount + 1, 3);
      await recordTransitionDebug("queued", { windowId: window.id, tabId: tab.id, inputSource, queuedCount: transitionRetryCount });'''
if old_queue in text:
    text = text.replace(old_queue, new_queue, 1)
elif new_queue not in text:
    raise SystemExit('transition queue marker missing')

old_restore_wait = '''      await showWindow(source.id, useChangedBounds ? bounds : session.sourceBounds, true);
      await recordTransitionDebug("normal-restore-wait", { windowId: source.id, tabId: tab.id });
      const restoreStable = await waitForRestoredWindowStable(source.id, tab.id);
      await recordTransitionDebug(restoreStable ? "normal-restore-stable" : "normal-restore-timeout", { windowId: source.id, tabId: tab.id });'''
new_restore_wait = '''      await showWindow(source.id, useChangedBounds ? bounds : session.sourceBounds, true);
      // Focus verification is diagnostic only. Do not hold the global Alt+C
      // transition lock while Chrome settles the restored normal window.
      recordTransitionDebug("normal-restore-wait", { windowId: source.id, tabId: tab.id }).catch(() => {});
      waitForRestoredWindowStable(source.id, tab.id, 420)
        .then((restoreStable) => recordTransitionDebug(
          restoreStable ? "normal-restore-stable" : "normal-restore-timeout",
          { windowId: source.id, tabId: tab.id }
        ))
        .catch(() => {});'''
if old_restore_wait in text:
    text = text.replace(old_restore_wait, new_restore_wait, 1)
elif new_restore_wait not in text:
    raise SystemExit('normal restore wait marker missing')

bg.write_text(text, encoding='utf-8')

manifest = Path('manifest.json')
data = json.loads(manifest.read_text(encoding='utf-8'))
if data.get('version') not in ('2.3.19', '2.3.20'):
    raise SystemExit(f"unexpected manifest version: {data.get('version')}")
data['version'] = '2.3.20'
manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

wf = Path('windowed_fullscreen.js')
wtext = wf.read_text(encoding='utf-8')
wtext = wtext.replace('const RUNTIME_VERSION = "2.3.19";', 'const RUNTIME_VERSION = "2.3.20";', 1)
if 'const RUNTIME_VERSION = "2.3.20";' not in wtext:
    raise SystemExit('runtime version marker missing')
wf.write_text(wtext, encoding='utf-8')

print('PATCH_2_3_20_OK')
