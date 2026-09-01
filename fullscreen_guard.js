(() => {
  if (window.__cleanWindowFullscreenGuardInstalled) return;
  window.__cleanWindowFullscreenGuardInstalled = true;

  // 진짜 전체화면 요청을 가로채지 않는다. YouTube의 F 단축키와
  // 플레이어 전체화면 버튼이 기본 동작을 수행하도록 의도적으로 비워 둔다.
})();
