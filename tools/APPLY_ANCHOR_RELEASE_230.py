from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f'marker not found: {label}')
    return text.replace(old, new, 1)


# manifest.json
manifest_path = ROOT / 'manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
manifest['version'] = '2.3.0'
manifest['description'] = '주소창과 탭바를 숨긴 Clean Window로 전환하고, 한 탭 창에서도 원래 Chrome 창 정체성을 안정적으로 보존합니다.'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

# background.js
path = ROOT / 'background.js'
text = path.read_text(encoding='utf-8')

if 'async function safeGetTab(tabId)' not in text:
    text = replace_once(
        text,
        '''async function safeGetWindow(windowId, populate = false) {
  if (!Number.isInteger(windowId)) return null;
  try { return await chrome.windows.get(windowId, { populate }); }
  catch (_) { return null; }
}
''',
        '''async function safeGetWindow(windowId, populate = false) {
  if (!Number.isInteger(windowId)) return null;
  try { return await chrome.windows.get(windowId, { populate }); }
  catch (_) { return null; }
}

async function safeGetTab(tabId) {
  if (!Number.isInteger(tabId)) return null;
  try { return await chrome.tabs.get(tabId); }
  catch (_) { return null; }
}
''',
        'safeGetTab'
    )

text = replace_once(
    text,
    '''  return tabs.sort((a, b) => (order.get(a.id) ?? 999999) - (order.get(b.id) ?? 999999));
}

async function publishSessionState''',
    '''  return tabs
    .filter((tab) => tab.id !== session.anchorTabId)
    .sort((a, b) => (order.get(a.id) ?? 999999) - (order.get(b.id) ?? 999999));
}

async function publishSessionState''',
    'hide anchor from shell'
)

anchor_helpers = '''
async function createSourceAnchorIfNeeded(source, sourceTabs) {
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

async function removeSourceAnchorAfterReturn(anchorTabId, sourceWindowId, returnedTabId) {
  if (!Number.isInteger(anchorTabId)) return;
  const returnedTab = await safeGetTab(returnedTabId);
  if (!returnedTab || returnedTab.windowId !== sourceWindowId) return;
  await removeSourceAnchor(anchorTabId);
}

'''
if 'async function createSourceAnchorIfNeeded' not in text:
    text = replace_once(text, 'async function enterCleanWindow(tab, source, sessions) {', anchor_helpers + 'async function enterCleanWindow(tab, source, sessions) {', 'anchor helpers')

text = replace_once(
    text,
    '''  let popup = null;
  try {
    popup = await chrome.windows.create({''',
    '''  let popup = null;
  let anchorTab = null;
  try {
    // If the active tab is the only tab, moving it straight into a popup can
    // destroy the original Chrome window. Keep a temporary blank anchor in the
    // source window so its real HWND/window identity survives the whole cycle.
    anchorTab = await createSourceAnchorIfNeeded(source, sourceTabs);

    popup = await chrome.windows.create({''',
    'create anchor before popup'
)

text = replace_once(
    text,
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
    'store anchor session'
)

text = replace_once(
    text,
    '''      if (sourceExists) {
        try { await movePopupTabBack(tab.id, source.id, metadata[String(tab.id)]); } catch (_) {}
        try { await showWindow(source.id, bounds); } catch (_) {}
      }
      returningPopups.delete(popup.id);
    }
    throw error;''',
    '''      if (sourceExists) {
        try { await movePopupTabBack(tab.id, source.id, metadata[String(tab.id)]); } catch (_) {}
        await removeSourceAnchorAfterReturn(anchorTab?.id, source.id, tab.id);
        try { await showWindow(source.id, bounds); } catch (_) {}
      }
      returningPopups.delete(popup.id);
    } else {
      await removeSourceAnchor(anchorTab?.id);
    }
    throw error;''',
    'enter failure cleanup'
)

text = replace_once(
    text,
    '''      await movePopupTabBack(tab.id, source.id, session.tabMeta[String(tab.id)]);
      await chrome.tabs.update(tab.id, { active: true });
      delete sessions[String(popup.id)];''',
    '''      await movePopupTabBack(tab.id, source.id, session.tabMeta[String(tab.id)]);
      await chrome.tabs.update(tab.id, { active: true });
      await removeSourceAnchorAfterReturn(session.anchorTabId, source.id, tab.id);
      delete sessions[String(popup.id)];''',
    'normal return anchor cleanup'
)

text = replace_once(
    text,
    '''      await restoreGroup(tab.id, normal.id, session.tabMeta[String(tab.id)]);
      delete sessions[String(popup.id)];''',
    '''      await restoreGroup(tab.id, normal.id, session.tabMeta[String(tab.id)]);
      await removeSourceAnchor(session.anchorTabId);
      delete sessions[String(popup.id)];''',
    'fallback return anchor cleanup'
)

text = replace_once(
    text,
    '''    if (!popup) {
      if (source) await showWindow(source.id, session.sourceBounds, true).catch(() => {});
      await setMediaPaused(session.tabOrder || [], false);''',
    '''    if (!popup) {
      if (source && Number.isInteger(session.anchorTabId)) {
        // The Clean popup itself is already gone, so its active tab is gone too.
        // Removing the sole anchor preserves the pre-2.3 single-tab close semantics.
        await removeSourceAnchor(session.anchorTabId);
      } else if (source) {
        await showWindow(source.id, session.sourceBounds, true).catch(() => {});
      }
      await setMediaPaused(session.tabOrder || [], false);''',
    'recovery anchor cleanup'
)

text = replace_once(
    text,
    '''    const source = await safeGetWindow(closedPopupSession.sourceWindowId);
    if (source) await showWindow(source.id, closedPopupSession.sourceBounds, true).catch(() => {});
    await setMediaPaused(closedPopupSession.tabOrder || [], false);''',
    '''    const source = await safeGetWindow(closedPopupSession.sourceWindowId);
    if (source && Number.isInteger(closedPopupSession.anchorTabId)) {
      // Closing the Clean popup closes the only real tab. Remove the temporary
      // anchor too so a blank source window is not left behind.
      await removeSourceAnchor(closedPopupSession.anchorTabId);
    } else if (source) {
      await showWindow(source.id, closedPopupSession.sourceBounds, true).catch(() => {});
    }
    await setMediaPaused(closedPopupSession.tabOrder || [], false);''',
    'popup X anchor cleanup'
)

path.write_text(text, encoding='utf-8')

# README
readme_path = ROOT / 'README.md'
readme = readme_path.read_text(encoding='utf-8')
needle = '- 원래 탭, 고정 상태, 탭 그룹과 창 위치 복원\n'
replacement = needle + '- 탭이 하나뿐인 창에서도 임시 Anchor 탭으로 원래 Chrome 창 자체를 살려 두어 복귀 안정성 향상\n'
if '임시 Anchor 탭' not in readme:
    if needle not in readme:
        raise RuntimeError('README feature marker not found')
    readme = readme.replace(needle, replacement, 1)
readme_path.write_text(readme, encoding='utf-8')

print('Prepared Clean Window 2.3.0 anchor release.')
