from pathlib import Path

bg = Path("background.js")
text = bg.read_text(encoding="utf-8")

old = "const fullscreenMaterializeTimers = new Map();"
new = "const fullscreenMaterializeTimers = new Map();\nconst fullscreenReapplyTimers = new Map();"
assert old in text
text = text.replace(old, new, 1)

old = '''async function downgradeWindowedFullscreenToClean(popupId, session, sessions) {
  if (!session || session.mode !== "windowed-fullscreen") return;
  await nativeWindowRequest("restoreCleanWindowFrame").catch(() => {});
  session.mode = "clean";
  session.contentFullscreen = false;
  session.frameHidden = false;
  sessions[String(popupId)] = session;
  await saveSessions(sessions);
  await publishSessionState(popupId, session).catch(() => {});
}'''
new = '''function cancelFullscreenReapply(popupId) {
  const timer = fullscreenReapplyTimers.get(popupId);
  if (timer) clearTimeout(timer);
  fullscreenReapplyTimers.delete(popupId);
}

function scheduleFullscreenReapply(popupId, tabId) {
  cancelFullscreenReapply(popupId);
  const timer = setTimeout(async () => {
    fullscreenReapplyTimers.delete(popupId);
    const latestSessions = await getSessions();
    const latestSession = latestSessions[String(popupId)];
    if (latestSession?.mode !== "windowed-fullscreen") return;
    const latestTab = await safeGetTab(tabId);
    if (!latestTab || latestTab.windowId !== popupId || latestTab.active !== true) return;
    await sendFullscreenMessage(tabId, true).catch(() => {});
  }, 120);
  fullscreenReapplyTimers.set(popupId, timer);
}

async function downgradeWindowedFullscreenToClean(popupId, session, sessions) {
  if (!session || session.mode !== "windowed-fullscreen") return;
  cancelFullscreenReapply(popupId);
  const popup = await safeGetWindow(popupId, true);
  const activeTab = popup?.tabs?.find((candidate) => candidate.active);
  if (activeTab?.id != null) await sendFullscreenMessage(activeTab.id, false).catch(() => {});
  await nativeWindowRequest("restoreCleanWindowFrame").catch(() => {});
  session.mode = "clean";
  session.contentFullscreen = false;
  session.frameHidden = false;
  sessions[String(popupId)] = session;
  await saveSessions(sessions);
  await publishSessionState(popupId, session).catch(() => {});
}'''
assert old in text
text = text.replace(old, new, 1)

old = '''async function returnToNormalWindow(tab, popup, session, sessions) {
  const bounds = getBounds(popup) || session.sourceBounds;'''
new = '''async function returnToNormalWindow(tab, popup, session, sessions) {
  cancelFullscreenReapply(popup.id);
  const bounds = getBounds(popup) || session.sourceBounds;'''
assert old in text
text = text.replace(old, new, 1)

old = "        setTimeout(() => sendFullscreenMessage(tab.id, true).catch(() => {}), 120);"
new = "        scheduleFullscreenReapply(Number(popupKey), tab.id);"
assert old in text
text = text.replace(old, new, 1)
bg.write_text(text, encoding="utf-8")

wf = Path("windowed_fullscreen.js")
text = wf.read_text(encoding="utf-8")
old = '''  document.documentElement.setAttribute(ACTIVE_ATTRIBUTE, "");
  document.documentElement.setAttribute(MODE_ATTRIBUTE, state.mode || "clean");
  installStyles();'''
new = '''  if ((state.mode || "clean") !== "windowed-fullscreen") {
    // Background session state is authoritative. If navigation downgraded the
    // session to Clean mode, remove any stale fullscreen DOM state immediately.
    clearWindowedFullscreenVisuals(false);
  }
  document.documentElement.setAttribute(ACTIVE_ATTRIBUTE, "");
  document.documentElement.setAttribute(MODE_ATTRIBUTE, state.mode || "clean");
  installStyles();'''
assert old in text
text = text.replace(old, new, 1)
wf.write_text(text, encoding="utf-8")
