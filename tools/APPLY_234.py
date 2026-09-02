from pathlib import Path
import json

p = Path('windowed_fullscreen.js')
s = p.read_text(encoding='utf-8')
s = s.replace('const PAGE_FULLSCREEN_ATTRIBUTE = "data-clean-window-page-fullscreen";\n', '')
s = s.replace('let fullscreenTargetKind = null;\n', '')
pseudo = '''
    html[${ROOT_ATTRIBUTE}]::after {
      content: "" !important;
      position: fixed !important;
      inset: 0 !important;
      box-sizing: border-box !important;
      border: 2px solid #d9b84f !important;
      box-shadow: inset 0 0 4px rgba(217, 184, 79, 0.32) !important;
      pointer-events: none !important;
      z-index: 2147483647 !important;
    }
'''
s = s.replace(pseudo, '\n')
s = s.replace('html[${ROOT_ATTRIBUTE}]:not([${PAGE_FULLSCREEN_ATTRIBUTE}])', 'html[${ROOT_ATTRIBUTE}]')

start = s.index('function findFullscreenTarget() {')
end = s.index('\nchrome.runtime.onMessage.addListener', start)
replacement = r'''function findFullscreenTarget() {
  const youtubePlayer = document.querySelector("#movie_player.html5-video-player, #movie_player");
  if (youtubePlayer && visibleArea(youtubePlayer) > 0) return youtubePlayer;

  const videos = [...document.querySelectorAll("video")]
    .map((video) => ({ video, area: visibleArea(video) }))
    .filter((item) => item.area > 0)
    .sort((a, b) => b.area - a.area);
  return videos[0]?.video || null;
}

function dispatchFullscreenResize() {
  window.dispatchEvent(new Event("resize"));
  requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  setTimeout(() => window.dispatchEvent(new Event("resize")), 80);
}

function applyFullscreenTarget(target, preserveScroll = false) {
  if (!target) return false;
  fullscreenTarget?.removeAttribute(TARGET_ATTRIBUTE);
  fullscreenTarget = target;
  document.documentElement.setAttribute(ROOT_ATTRIBUTE, "");
  fullscreenTarget.setAttribute(TARGET_ATTRIBUTE, "");
  renderGoldBorder(true);
  if (!preserveScroll) window.scrollTo(0, 0);
  dispatchFullscreenResize();
  return true;
}

function notifyVideoGone() {
  chrome.runtime.sendMessage({ type: "windowed-fullscreen-video-gone" }, () => {
    void chrome.runtime.lastError;
  });
}

function refreshWindowedFullscreenTarget() {
  if (!document.documentElement.hasAttribute(ROOT_ATTRIBUTE)) return;
  const target = findFullscreenTarget();
  if (!target) {
    clearWindowedFullscreenVisuals(true);
    notifyVideoGone();
    return;
  }
  if (fullscreenTarget === target && fullscreenTarget?.isConnected !== false) return;
  applyFullscreenTarget(target, true);
}

function scheduleFullscreenRepair(delay = 80) {
  if (!document.documentElement.hasAttribute(ROOT_ATTRIBUTE)) return;
  if (fullscreenRepairTimer) clearTimeout(fullscreenRepairTimer);
  fullscreenRepairTimer = setTimeout(() => {
    fullscreenRepairTimer = null;
    refreshWindowedFullscreenTarget();
  }, delay);
}

function startFullscreenRepairWatch() {
  if (fullscreenObserver) return;
  fullscreenObserver = new MutationObserver(() => scheduleFullscreenRepair(90));
  fullscreenObserver.observe(document.documentElement, { childList: true, subtree: true });
}

function stopFullscreenRepairWatch() {
  fullscreenObserver?.disconnect();
  fullscreenObserver = null;
  if (fullscreenRepairTimer) clearTimeout(fullscreenRepairTimer);
  fullscreenRepairTimer = null;
}

function clearWindowedFullscreenVisuals(restoreScroll = true) {
  stopFullscreenRepairWatch();
  renderGoldBorder(false);
  document.documentElement.removeAttribute(ROOT_ATTRIBUTE);
  document.documentElement.removeAttribute("data-clean-window-page-fullscreen");
  fullscreenTarget?.removeAttribute(TARGET_ATTRIBUTE);
  for (const element of document.querySelectorAll(`[${TARGET_ATTRIBUTE}]`)) {
    element.removeAttribute(TARGET_ATTRIBUTE);
  }
  fullscreenTarget = null;
  if (restoreScroll) window.scrollTo(savedScrollX, savedScrollY);
  dispatchFullscreenResize();
}

function setWindowedFullscreen(enabled) {
  if (!enabled) {
    clearWindowedFullscreenVisuals(true);
    return { ok: true };
  }
  const target = findFullscreenTarget();
  if (!target) {
    clearWindowedFullscreenVisuals(false);
    return { ok: false, reason: "no-video", error: "이 페이지에는 확대할 영상이 없습니다." };
  }
  installStyles();
  if (!document.documentElement.hasAttribute(ROOT_ATTRIBUTE)) {
    savedScrollX = window.scrollX;
    savedScrollY = window.scrollY;
  }
  applyFullscreenTarget(target, false);
  startFullscreenRepairWatch();
  return { ok: true };
}

document.addEventListener("yt-navigate-finish", () => scheduleFullscreenRepair(40), true);
window.addEventListener("popstate", () => scheduleFullscreenRepair(40), true);
window.addEventListener("hashchange", () => scheduleFullscreenRepair(40), true);
window.addEventListener("pageshow", () => scheduleFullscreenRepair(40), true);
'''
s = s[:start] + replacement + s[end:]
p.write_text(s, encoding='utf-8')

b = Path('background.js')
bg = b.read_text(encoding='utf-8')
old = '''async function enterWindowedFullscreen(tab, popup, session, sessions) {
  const content = await sendFullscreenMessage(tab.id, true);
  const frame = await nativeWindowRequest("hideCleanWindowFrame");
  session.mode = "windowed-fullscreen";
  session.contentFullscreen = Boolean(content?.ok);
  session.frameHidden = Boolean(frame?.ok);
  sessions[String(popup.id)] = session;
  await saveSessions(sessions);
  await publishSessionState(popup.id, session);
}
'''
new = '''async function enterWindowedFullscreen(tab, popup, session, sessions) {
  const content = await sendFullscreenMessage(tab.id, true);
  if (!content?.ok) return false;
  session.mode = "windowed-fullscreen";
  session.contentFullscreen = true;
  session.frameHidden = false;
  sessions[String(popup.id)] = session;
  await saveSessions(sessions);
  await publishSessionState(popup.id, session);
  return true;
}

async function downgradeWindowedFullscreenToClean(popupId, session, sessions) {
  if (!session || session.mode !== "windowed-fullscreen") return;
  await nativeWindowRequest("restoreCleanWindowFrame").catch(() => {});
  session.mode = "clean";
  session.contentFullscreen = false;
  session.frameHidden = false;
  sessions[String(popupId)] = session;
  await saveSessions(sessions);
  await publishSessionState(popupId, session).catch(() => {});
}
'''
if old not in bg:
    raise SystemExit('enterWindowedFullscreen block not found')
bg = bg.replace(old, new)

old = '''    else if (session.mode === "clean") await enterWindowedFullscreen(tab, window, session, sessions);
    else await returnToNormalWindow(tab, window, session, sessions);'''
new = '''    else if (session.mode === "clean") {
      const entered = await enterWindowedFullscreen(tab, window, session, sessions);
      if (!entered) await returnToNormalWindow(tab, window, session, sessions);
    }
    else await returnToNormalWindow(tab, window, session, sessions);'''
if old not in bg:
    raise SystemExit('toggle clean block not found')
bg = bg.replace(old, new)

old = '''    if (session.mode === "windowed-fullscreen") {
      await sendFullscreenMessage(targetTabId, true);
      await nativeWindowRequest("hideCleanWindowFrame");
    }
    await publishSessionState(newPopup.id, session);'''
new = '''    if (session.mode === "windowed-fullscreen") {
      const content = await sendFullscreenMessage(targetTabId, true);
      if (!content?.ok) {
        session.mode = "clean";
        session.contentFullscreen = false;
        session.frameHidden = false;
        await nativeWindowRequest("restoreCleanWindowFrame").catch(() => {});
        sessions[String(newPopup.id)] = session;
        await saveSessions(sessions);
      }
    }
    await publishSessionState(newPopup.id, session);'''
if old not in bg:
    raise SystemExit('switch fullscreen block not found')
bg = bg.replace(old, new)

needle = '''  if (message?.type === "return-clean-window-normal-request") {'''
insert = '''  if (message?.type === "windowed-fullscreen-video-gone") {
    const popupId = sender.tab?.windowId;
    if (Number.isInteger(popupId)) {
      getSessions().then(async (sessions) => {
        const session = sessions[String(popupId)];
        if (session?.mode === "windowed-fullscreen") {
          await downgradeWindowedFullscreenToClean(popupId, session, sessions);
        }
      }).catch(console.error);
    }
    return false;
  }
'''
if needle not in bg:
    raise SystemExit('runtime message insertion point not found')
bg = bg.replace(needle, insert + needle)
b.write_text(bg, encoding='utf-8')

m = Path('manifest.json')
data = json.loads(m.read_text(encoding='utf-8'))
data['version'] = '2.3.4'
m.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
