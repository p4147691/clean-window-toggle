(() => {
  if (window.__cleanWindowFullscreenGuardInstalled) return;
  window.__cleanWindowFullscreenGuardInstalled = true;

  const rootAttribute = "data-clean-window-fullscreen";
  const methods = [
    [Element.prototype, "requestFullscreen"],
    [Element.prototype, "webkitRequestFullscreen"]
  ];

  for (const [prototype, name] of methods) {
    const original = prototype?.[name];
    if (typeof original !== "function") continue;

    Object.defineProperty(prototype, name, {
      configurable: true,
      writable: true,
      value: function (...args) {
        if (document.documentElement.hasAttribute(rootAttribute)) {
          // CSS 기반 내부 전체화면이 이미 활성화되어 있으므로 실제 OS/모니터
          // 전체화면 요청은 성공한 작업처럼 종료하고 창 경계를 유지한다.
          return Promise.resolve();
        }
        return original.apply(this, args);
      }
    });
  }

  // document_idle 이후에는 YouTube의 단축키 처리기가 먼저 실행될 수 있다.
  // 이 파일을 document_start/Main world에서 불러 window capture 단계에서 선점한다.
  window.addEventListener("keydown", (event) => {
    if (!document.documentElement.hasAttribute(rootAttribute)) return;
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.key.toLowerCase() !== "f") return;

    const target = event.target;
    const isTyping = target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target?.isContentEditable;
    if (isTyping) return;

    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);

  const containUnexpectedFullscreen = () => {
    if (!document.documentElement.hasAttribute(rootAttribute)) return;
    if (!document.fullscreenElement) return;
    document.exitFullscreen().catch(() => {});
  };

  document.addEventListener("fullscreenchange", containUnexpectedFullscreen, true);
  document.addEventListener("webkitfullscreenchange", containUnexpectedFullscreen, true);
})();
