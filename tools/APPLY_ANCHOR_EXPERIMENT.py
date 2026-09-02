from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
bg_path = ROOT / 'background.js'
bg = bg_path.read_text(encoding='utf-8')


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f'marker not found: {label}')
    return text.replace(old, new, 1)

# Hide the internal anchor from the Clean Window tab shell.
bg = replace_once(
    bg,
    '''  const order = new Map(session.tabOrder.map((tabId, index) => [tabId, index]));
  return tabs.sort((a, b) => (order.get(a.id) ?? 999999) - (order.get(b.id) ?? 999999));
}''',
    '''  const order = new Map(session.tabOrder.map((tabId, index) => [tabId, index]));
  return tabs
    .filter((tab) => tab.id !== session.anchorTabId)
    .sort((a, b) => (order.get(a.id) ?? 999999) - (order.get(b.id) ?? 999999));
}''',
    'filter anchor from shell'
)

# Insert anchor helpers before enterCleanWindow.
bg = replace_once(
    bg,
    'async function enterCleanWindow(tab, source, sessions) {',
    '''async function createSourceAnchorIfNeeded(source, sourceTabs) {
  if (!Number.isInteger(source?.id) || sourceTabs.length !== 1) return null;
  const anchor = await chrome.tabs.create({
    windowId: source.id,
    url: "about:blank",
    active: false,
    index: sourceTabs.length
  });
  return Number.isInteger(anchor?.id) ? anchor : null;
}

async function removeSourceAnchor(anchorTabId) {
  if (!Number.isInteger(anchorTabId)) return;
  const anchor = await safeGetTab(anchorTabId);
  if (!anchor) return;
  try { await chrome.tabs.remove(anchorTabId); } catch (_) {}
}

async function safeGetTab(tabId) {
  if (!Number.isInteger(tabId)) return null;
  try { return await chrome.tabs.get(tabId); }
  catch (_) { return null; }
}

async function enterCleanWindow(tab, source, sessions) {''',
    'anchor helpers'
)

# Create anchor only for the one-tab edge case, before moving the real tab.
bg = replace_once(
    bg,
    '''  const parkedIds = tabOrder.filter((tabId) => tabId !== tab.id);
  await setMediaPaused(parkedIds, true);

  let popup = null;
  try {
    popup = await chrome.windows.create({''',
    '''  const parkedIds = tabOrder.filter((tabId) => tabId !== tab.id);
  await setMediaPaused(parkedIds, true);

  let popup = null;
  let anchorTab = null;
  try {
    // When the active tab is the only tab, moving it directly into a popup can
    // destroy the original Chrome window. Keep one invisible blank tab parked
    // in that window so its HWND/window identity survives the Clean Window cycle.
    anchorTab = await createSourceAnchorIfNeeded(source, sourceTabs);

    popup = await chrome.windows.create({''',
    'create anchor before popup'
)

# Persist anchor metadata with the session.
bg = replace_once(
    bg,
    '''      mode: "clean",
      tabOrder,
      tabMeta: metadata
    };''',
    '''      mode: "clean",
      tabOrder,
      tabMeta: metadata,
      anchorTabId: anchorTab?.id ?? null,
      sourceHadSingleTab: sourceTabs.length === 1
    };''',
    'persist anchor metadata'
)

# Failure cleanup: restore the real tab first, then remove anchor.
bg = replace_once(
    bg,
    '''      if (sourceExists) {
        try { await movePopupTabBack(tab.id, source.id, metadata[String(tab.id)]); } catch (_) {}
        try { await showWindow(source.id, bounds); } catch (_) {}
      }
      returningPopups.delete(popup.id);
    }
    throw error;''',
    '''      if (sourceExists) {
        try { await movePopupTabBack(tab.id, source.id, metadata[String(tab.id)]); } catch (_) {}
        await removeSourceAnchor(anchorTab?.id);
        try { await showWindow(source.id, bounds); } catch (_) {}
      }
      returningPopups.delete(popup.id);
    } else {
      await removeSourceAnchor(anchorTab?.id);
    }
    throw error;''',
    'anchor failure cleanup'
)

# Normal return: real tab goes back into the original source window, anchor is
# removed while the source is still minimized, then the original window is shown.
bg = replace_once(
    bg,
    '''      await movePopupTabBack(tab.id, source.id, session.tabMeta[String(tab.id)]);
      await chrome.tabs.update(tab.id, { active: true });
      delete sessions[String(popup.id)];''',
    '''      await movePopupTabBack(tab.id, source.id, session.tabMeta[String(tab.id)]);
      await chrome.tabs.update(tab.id, { active: true });
      await removeSourceAnchor(session.anchorTabId);
      delete sessions[String(popup.id)];''',
    'anchor normal return cleanup'
)

# Recovery: if the popup disappeared, an anchor-only source must not be exposed
# as a blank Chrome window. Removing the anchor reproduces the old single-tab
# close behavior; non-anchor sessions keep the previous restore behavior.
bg = replace_once(
    bg,
    '''    if (!popup) {
      if (source) await showWindow(source.id, session.sourceBounds, true).catch(() => {});
      await setMediaPaused(session.tabOrder || [], false);
      delete sessions[popupKey];''',
    '''    if (!popup) {
      if (source && Number.isInteger(session.anchorTabId)) {
        await removeSourceAnchor(session.anchorTabId);
      } else if (source) {
        await showWindow(source.id, session.sourceBounds, true).catch(() => {});
      }
      await setMediaPaused(session.tabOrder || [], false);
      delete sessions[popupKey];''',
    'anchor recovery cleanup'
)

# Direct popup X: with an anchor session, remove the anchor instead of revealing
# a blank source window. Multi-tab sessions preserve the old behavior.
bg = replace_once(
    bg,
    '''    const source = await safeGetWindow(closedPopupSession.sourceWindowId);
    if (source) await showWindow(source.id, closedPopupSession.sourceBounds, true).catch(() => {});
    await setMediaPaused(closedPopupSession.tabOrder || [], false);''',
    '''    const source = await safeGetWindow(closedPopupSession.sourceWindowId);
    if (source && Number.isInteger(closedPopupSession.anchorTabId)) {
      await removeSourceAnchor(closedPopupSession.anchorTabId);
    } else if (source) {
      await showWindow(source.id, closedPopupSession.sourceBounds, true).catch(() => {});
    }
    await setMediaPaused(closedPopupSession.tabOrder || [], false);''',
    'anchor popup close cleanup'
)

bg_path.write_text(bg, encoding='utf-8')

manifest_path = ROOT / 'manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
manifest['version'] = '2.3.0'
manifest['description'] = '원본 Chrome 창 정체성을 보존하는 Anchor 실험이 포함된 Clean Window 테스트 버전입니다.'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

notes = ROOT / 'ANCHOR_EXPERIMENT.md'
notes.write_text('''# Clean Window Anchor experiment\n\nThis branch keeps the original normal Chrome window alive when the active tab is its only tab.\n\n## Hypothesis\nMoving the only tab into a popup can destroy the original normal Chrome window. Returning then requires a newly created normal window, which may feel less stable in Windows Snap/group behavior.\n\n## Experiment\n- Only when the source window has exactly one tab, create one inactive `about:blank` anchor tab.\n- Move the real tab to the Clean Window popup as before.\n- Minimize and preserve the original source window.\n- On the third toggle, move the real tab back to the same source window, remove the anchor while the source remains minimized, then restore/focus the original source window.\n- Multi-tab behavior is unchanged.\n- The anchor is filtered from the Clean Window tab shell.\n- Failure, recovery, popup-X, and source-window-close paths clean up the anchor.\n\nThe experiment intentionally does not change the stable `main` branch.\n''', encoding='utf-8')

print('Applied Clean Window anchor experiment 2.3.0.')
