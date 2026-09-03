from pathlib import Path

p = Path('windowed_fullscreen.js')
text = p.read_text(encoding='utf-8')
old = '''function isYouTubeVideoRoute() {
  const host = location.hostname.toLowerCase();
  if (!(host === "youtube.com" || host.endsWith(".youtube.com"))) return false;
  return location.pathname === "/watch"
    || location.pathname.startsWith("/shorts/")
    || location.pathname.startsWith("/live/")
    || location.pathname.startsWith("/embed/");
}

function findFullscreenTarget() {
  const youtubePlayer = document.querySelector("#movie_player.html5-video-player, #movie_player");'''
new = '''function isYouTubeSite() {
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

  const youtubePlayer = document.querySelector("#movie_player.html5-video-player, #movie_player");'''
assert old in text, 'target block not found'
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')
