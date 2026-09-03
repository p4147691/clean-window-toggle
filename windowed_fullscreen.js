(() => {
const RUNTIME_VERSION = "2.3.9";
const RUNTIME_KEY = "__cleanWindowRuntimeV1";
const MESSAGE_BRIDGE_KEY = "__cleanWindowRuntimeMessageBridgeV1";
const previousRuntime = globalThis[RUNTIME_KEY];
const previousSnapshot = previousRuntime?.hotReload === true && typeof previousRuntime.snapshot === "function"
  ? previousRuntime.snapshot()
  : null;
if (previousRuntime?.hotReload === true && typeof previousRuntime.dispose === "function") {
  previousRuntime.dispose();
}
const runtimeAbort = new AbortController();

const ROOT_ATTRIBUTE = "data-clean-window-fullscreen";
const TARGET_ATTRIBUTE = "data-clean-window-fullscreen-target";
const ACTIVE_ATTRIBUTE = "data-clean-window-active";
const MODE_ATTRIBUTE = "data-clean-window-mode";
const TAB_STRIP_ID = "clean-window-tab-strip";
const BORDER_ID = "clean-window-gold-border";
let fullscreenTarget = previousSnapshot?.fullscreenTarget?.isConnected
  ? previousSnapshot.fullscreenTarget
  : document.querySelector(`[${TARGET_ATTRIBUTE}]`);
let savedScrollX = Number(previousSnapshot?.savedScrollX) || 0;
let savedScrollY = Number(previousSnapshot?.savedScrollY) || 0;
let lastToggleRequestAt = 0;
let fullscreenObserver = null;
let fullscreenRepairTimer = null;
const pausedMedia = new Set(previousSnapshot?.pausedMedia || []);

function installStyles() {
  if (document.getElementById("clean-window-fullscreen-style")) return;
  const style = document.createElement("style");
  style.id = "clean-window-fullscreen-style";
  style.textContent = `
    html[${ROOT_ATTRIBUTE}],
    html[${ROOT_ATTRIBUTE}] body {
      overflow: hidden !important;
      background: #000 !important;
    }

    html[${ROOT_ATTRIBUTE}] body * {
      visibility: hidden !important;
    }


    html[${ROOT_ATTRIBUTE}] [${TARGET_ATTRIBUTE}],
    html[${ROOT_ATTRIBUTE}] [${TARGET_ATTRIBUTE}] * {
      visibility: visible !important;
    }

    #${TAB_STRIP_ID},
    #${TAB_STRIP_ID} *,
    #${BORDER_ID} {
      visibility: visible !important;
      box-sizing: border-box !important;
    }

    #${BORDER_ID} {
      position: fixed !important;
      inset: 0 !important;
      display: block !important;
      border: 2px solid #d9b84f !important;
      box-shadow: inset 0 0 4px rgba(217, 184, 79, 0.32) !important;
      pointer-events: none !important;
      z-index: 2147483647 !important;
    }

    #${TAB_STRIP_ID} {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      right: 0 !important;
      height: 34px !important;
      display: flex !important;
      align-items: center !important;
      gap: 4px !important;
      padding: 4px 6px !important;
      overflow-x: auto !important;
      overflow-y: hidden !important;
      background: rgba(18, 18, 20, 0.96) !important;
      border-bottom: 1px solid rgba(217, 184, 79, 0.72) !important;
      box-shadow: 0 3px 12px rgba(0, 0, 0, 0.38) !important;
      transform: translateY(-30px) !important;
      transition: transform 150ms ease-out !important;
      z-index: 2147483647 !important;
      scrollbar-width: none !important;
    }

    #${TAB_STRIP_ID}::-webkit-scrollbar {
      display: none !important;
    }

    #${TAB_STRIP_ID}:hover,
    #${TAB_STRIP_ID}:focus-within {
      transform: translateY(0) !important;
    }

    #${TAB_STRIP_ID} button {
      flex: 0 1 210px !important;
      min-width: 76px !important;
      max-width: 210px !important;
      height: 26px !important;
      padding: 0 10px !important;
      overflow: hidden !important;
      border: 1px solid rgba(255, 255, 255, 0.1) !important;
      border-radius: 6px !important;
      outline: none !important;
      background: rgba(255, 255, 255, 0.07) !important;
      color: rgba(255, 255, 255, 0.76) !important;
      font: 500 12px/24px system-ui, sans-serif !important;
      text-align: left !important;
      text-overflow: ellipsis !important;
      white-space: nowrap !important;
      cursor: pointer !important;
    }

    #${TAB_STRIP_ID} button:hover {
      background: rgba(255, 255, 255, 0.14) !important;
      color: #fff !important;
    }

    #${TAB_STRIP_ID} button[data-active="true"] {
      border-color: rgba(217, 184, 79, 0.8) !important;
      background: rgba(217, 184, 79, 0.18) !important;
      color: #f4dfa0 !important;
    }

    html[${ROOT_ATTRIBUTE}] [${TARGET_ATTRIBUTE}] {
      position: fixed !important;
      inset: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      min-width: 100vw !important;
      min-height: 100vh !important;
      max-width: none !important;
      max-height: none !important;
      margin: 0 !important;
      padding: 0 !important;
      border: 0 !important;
      border-radius: 0 !important;
      transform: none !important;
      z-index: 2147483646 !important;
      background: #000 !important;
    }

    html[${ROOT_ATTRIBUTE}] [${TARGET_ATTRIBUTE}] video {
      position: absolute !important;
      inset: 0 !important;
      width: 100% !important;
      height: 100% !important;
      max-width: none !important;
      max-height: none !important;
      margin: 0 !important;
      object-fit: contain !important;
      object-position: center center !important;
      background: #000 !important;
    }

    html[${ROOT_ATTRIBUTE}] [${TARGET_ATTRIBUTE}].html5-video-player .html5-video-container {
      position: absolute !important;
      inset: 0 !important;
      width: 100% !important;
      height: 100% !important;
    }

    html[${ROOT_ATTRIBUTE}] [${TARGET_ATTRIBUTE}].html5-video-player .ytp-chrome-bottom {
      width: calc(100% - 24px) !important;
      left: 12px !important;
    }

    /* Clean Window에서는 영상 위에 떠서 시야를 가리는 YouTube 추천 카드,
       채널 링크와 워터마크만 숨긴다. 재생 컨트롤은 그대로 유지한다. */
    html[${ACTIVE_ATTRIBUTE}] .ytp-ce-element,
    html[${ACTIVE_ATTRIBUTE}] .ytp-cards-teaser,
    html[${ACTIVE_ATTRIBUTE}] .ytp-cards-button,
    html[${ACTIVE_ATTRIBUTE}] .ytp-paid-content-overlay,
    html[${ACTIVE_ATTRIBUTE}] .annotation,
    html[${ACTIVE_ATTRIBUTE}] .branding-img-container,
    html[${ACTIVE_ATTRIBUTE}] .ytp-title-channel,
    html[${ACTIVE_ATTRIBUTE}] .ytp-title-link {
      display: none !important;
    }
  `;
  (document.head || document.documentElement).append(style);
}

function renderGoldBorder(active) {
  document.getElementById(BORDER_ID)?.remove();
  if (!active) return;
  const border = document.createElement("div");
  border.id = BORDER_ID;
  border.setAttribute("aria-hidden", "true");
  document.documentElement.append(border);
}

function renderTabStrip(state) {
  document.getElementById(TAB_STRIP_ID)?.remove();
  if (!state?.active) {
    clearWindowedFullscreenVisuals(false);
    document.documentElement.removeAttribute(ACTIVE_ATTRIBUTE);
    document.documentElement.removeAttribute(MODE_ATTRIBUTE);
    return;
  }

  if ((state.mode || "clean") !== "windowed-fullscreen") {
    // Background session state is authoritative. If navigation downgraded the
    // session to Clean mode, remove any stale fullscreen DOM state immediately.
    clearWindowedFullscreenVisuals(false);
  }
  document.documentElement.setAttribute(ACTIVE_ATTRIBUTE, "");
  document.documentElement.setAttribute(MODE_ATTRIBUTE, state.mode || "clean");
  installStyles();
  renderGoldBorder(state.mode === "windowed-fullscreen" && document.documentElement.hasAttribute(ROOT_ATTRIBUTE));
  if (!Array.isArray(state.tabs) || state.tabs.length < 2) return;

  const strip = document.createElement("div");
  strip.id = TAB_STRIP_ID;
  strip.setAttribute("role", "tablist");
  strip.dataset.mode = state.mode || "clean";

  for (const tab of state.tabs) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "tab");
    button.dataset.tabId = String(tab.id);
    button.dataset.active = String(Boolean(tab.active));
    button.setAttribute("aria-selected", String(Boolean(tab.active)));
    button.title = tab.title || "새 탭";
    button.textContent = tab.title || "새 탭";
    button.addEventListener("click", () => {
      chrome.runtime.sendMessage({ type: "activate-clean-window-tab", tabId: tab.id }, (response) => {
        if (chrome.runtime.lastError) {
          strip.dataset.lastError = chrome.runtime.lastError.message;
          return;
        }
        if (!response?.ok) strip.dataset.lastError = response?.error || "탭 전환에 실패했습니다.";
      });
    });
    strip.append(button);
  }

  document.documentElement.append(strip);
}

function visibleArea(element) {
  const rect = element.getBoundingClientRect();
  if (rect.width < 80 || rect.height < 45) return 0;
  const style = getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") return 0;
  return rect.width * rect.height;
}

function videoUsableScore(video) {
  if (!(video instanceof HTMLVideoElement)) return 0;
  const rectArea = visibleArea(video);
  const intrinsicArea = Math.max(0, Number(video.videoWidth) || 0) * Math.max(0, Number(video.videoHeight) || 0);
  const clientArea = Math.max(0, Number(video.clientWidth) || 0) * Math.max(0, Number(video.clientHeight) || 0);
  const hasMedia = Boolean(video.currentSrc || video.src || video.readyState >= 1 || intrinsicArea > 0);
  if (!hasMedia && rectArea <= 0) return 0;
  return Math.max(rectArea, intrinsicArea, clientArea);
}

function isYouTubeSite() {
  const host = location.hostname.toLowerCase();
  return host === "youtube.com" || host.endsWith(".youtube.com");
}

function isYouTubeVideoRoute() {
  if (!isYouTubeSite()) return false;
  return location.pathname === "/watch"
    || location.pathname.startsWith("/shorts/")
    || location.pathname.startsWith("/live/")
    || location.pathname.startsWith("/embed/");
}

function findFullscreenTarget() {
  // YouTube keeps #movie_player alive across SPA navigation. Because our
  // fullscreen CSS itself makes that stale player large and visible, checking
  // its geometry first can falsely keep fullscreen alive on Home/Search pages.
  // Route is authoritative on YouTube: outside video routes there is no target.
  if (isYouTubeSite() && !isYouTubeVideoRoute()) return null;

  const youtubePlayer = document.querySelector("#movie_player.html5-video-player, #movie_player");
  if (youtubePlayer) {
    const youtubeVideo = youtubePlayer.querySelector("video");
    if (youtubeVideo && videoUsableScore(youtubeVideo) > 0) return youtubePlayer;
    // YouTube SPA 전환 직후에는 실제 video의 레이아웃 값이 잠깐 0이 될 수 있다.
    // watch/shorts/live/embed 경로에서 player가 살아 있으면 영상 대상으로 인정한다.
    if (isYouTubeVideoRoute() && youtubePlayer.isConnected) return youtubePlayer;
  }

  const videos = [...document.querySelectorAll("video")]
    .map((video) => ({ video, score: videoUsableScore(video) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score);
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

document.addEventListener("yt-navigate-finish", () => scheduleFullscreenRepair(40), { capture: true, signal: runtimeAbort.signal });
window.addEventListener("popstate", () => scheduleFullscreenRepair(40), { capture: true, signal: runtimeAbort.signal });
window.addEventListener("hashchange", () => scheduleFullscreenRepair(40), { capture: true, signal: runtimeAbort.signal });
window.addEventListener("pageshow", () => scheduleFullscreenRepair(40), { capture: true, signal: runtimeAbort.signal });

function handleRuntimeMessage(message, _sender, sendResponse) {
  if (message?.type === "clean-window-runtime-probe") {
    sendResponse({ ok: true, version: RUNTIME_VERSION, hotReload: true });
    return false;
  }
  if (message?.type === "set-windowed-fullscreen") {
    sendResponse(setWindowedFullscreen(Boolean(message.enabled)));
    return false;
  }
  if (message?.type === "set-clean-window-shell") {
    renderTabStrip(message);
    sendResponse({ ok: true });
    return false;
  }
  if (message?.type === "pause-clean-window-media") {
    for (const media of document.querySelectorAll("video, audio")) {
      if (!media.paused && !media.ended) {
        pausedMedia.add(media);
        media.pause();
      }
    }
    sendResponse({ ok: true, paused: pausedMedia.size });
    return false;
  }
  if (message?.type === "resume-clean-window-media") {
    const mediaToResume = [...pausedMedia];
    pausedMedia.clear();
    for (const media of mediaToResume) {
      if (media.isConnected && media.paused && !media.ended) media.play().catch(() => {});
    }
    sendResponse({ ok: true, resumed: mediaToResume.length });
    return false;
  }
  return false;
}

function snapshotRuntimeState() {
  return {
    savedScrollX,
    savedScrollY,
    fullscreenTarget: fullscreenTarget?.isConnected ? fullscreenTarget : null,
    pausedMedia: [...pausedMedia]
  };
}

function disposeRuntime() {
  runtimeAbort.abort();
  stopFullscreenRepairWatch();
}

const runtimeApi = {
  version: RUNTIME_VERSION,
  hotReload: true,
  snapshot: snapshotRuntimeState,
  dispose: disposeRuntime,
  handleMessage: handleRuntimeMessage
};
globalThis[RUNTIME_KEY] = runtimeApi;

if (!globalThis[MESSAGE_BRIDGE_KEY]) {
  const bridge = (message, sender, sendResponse) => {
    const current = globalThis[RUNTIME_KEY];
    if (!current || typeof current.handleMessage !== "function") return false;
    return current.handleMessage(message, sender, sendResponse);
  };
  chrome.runtime.onMessage.addListener(bridge);
  globalThis[MESSAGE_BRIDGE_KEY] = bridge;
}

function refreshCleanWindowShellState() {
  chrome.runtime.sendMessage({ type: "get-clean-window-shell" }, (response) => {
    if (chrome.runtime.lastError || !response?.ok) return;
    renderTabStrip(response);
  });
}

refreshCleanWindowShellState();
window.addEventListener("pageshow", () => setTimeout(refreshCleanWindowShellState, 0), { capture: true, signal: runtimeAbort.signal });
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshCleanWindowShellState();
}, { capture: true, signal: runtimeAbort.signal });

function isContainedFullscreenActive() {
  return document.documentElement.hasAttribute(ROOT_ATTRIBUTE);
}

// 일부 Chrome popup에서 commands 이벤트가 누락될 때 사용하는 보조 입력 경로.
document.addEventListener("keydown", (event) => {
  const target = event.target;
  const isTyping = target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || target?.isContentEditable;

  // 실제 전체화면 중에는 첫 Esc를 Chrome에 맡겨 현재 Clean Window 모드로
  // 돌아오게 한다. 그 밖의 2/3번 모드에서는 Esc로 일반 창까지 복귀한다.
  if (event.key === "Escape"
      && document.documentElement.hasAttribute(ACTIVE_ATTRIBUTE)
      && !document.fullscreenElement
      && !isTyping) {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (!event.repeat) chrome.runtime.sendMessage({ type: "return-clean-window-normal-request" });
    return;
  }

  if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  if (event.key.toLowerCase() !== "c") return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if (event.repeat) return;
  const now = Date.now();
  if (now - lastToggleRequestAt < 500) return;
  lastToggleRequestAt = now;
  chrome.runtime.sendMessage({ type: "toggle-clean-window-request" });
}, { capture: true, signal: runtimeAbort.signal });


if (document.documentElement.hasAttribute(ROOT_ATTRIBUTE)) {
  fullscreenTarget ||= document.querySelector(`[${TARGET_ATTRIBUTE}]`);
  startFullscreenRepairWatch();
}
})();
