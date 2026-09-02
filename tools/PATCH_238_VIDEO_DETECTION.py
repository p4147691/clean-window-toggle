from pathlib import Path
import json

wf_path = Path('windowed_fullscreen.js')
manifest_path = Path('manifest.json')

text = wf_path.read_text(encoding='utf-8')

start = text.index('function visibleArea(element) {')
end = text.index('function dispatchFullscreenResize() {', start)
new_detection = r'''function visibleArea(element) {
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

function isYouTubeVideoRoute() {
  const host = location.hostname.toLowerCase();
  if (!(host === "youtube.com" || host.endsWith(".youtube.com"))) return false;
  return location.pathname === "/watch"
    || location.pathname.startsWith("/shorts/")
    || location.pathname.startsWith("/live/")
    || location.pathname.startsWith("/embed/");
}

function findFullscreenTarget() {
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

'''
text = text[:start] + new_detection + text[end:]

old_shell = '''chrome.runtime.sendMessage({ type: "get-clean-window-shell" }, (response) => {
  if (chrome.runtime.lastError || !response?.ok) return;
  renderTabStrip(response);
});
'''
new_shell = '''function refreshCleanWindowShellState() {
  chrome.runtime.sendMessage({ type: "get-clean-window-shell" }, (response) => {
    if (chrome.runtime.lastError || !response?.ok) return;
    renderTabStrip(response);
  });
}

refreshCleanWindowShellState();
window.addEventListener("pageshow", () => setTimeout(refreshCleanWindowShellState, 0), true);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshCleanWindowShellState();
}, true);
'''
if old_shell not in text:
    raise SystemExit('initial shell block not found')
text = text.replace(old_shell, new_shell, 1)

wf_path.write_text(text, encoding='utf-8')

manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
if manifest.get('version') != '2.3.7':
    raise SystemExit(f"unexpected base version: {manifest.get('version')}")
manifest['version'] = '2.3.8'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('PATCH_238_VIDEO_DETECTION_OK')
