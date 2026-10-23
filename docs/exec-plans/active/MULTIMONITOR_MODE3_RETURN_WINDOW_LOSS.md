# Active Plan — Multi-monitor Mode 3 return affects other Chrome windows

Status: `root cause confirmed / source-level patch validated / live Chrome validation pending`
Updated: 2026-09-05

## User-observed symptom

On Windows with multiple Chrome windows / monitors, returning from Clean Window Mode 3 could make unrelated Chrome windows appear to disappear or change state.

The exact visual symptom must still be described precisely per incident (destroyed vs minimized vs moved vs focus/frame mutation), but the foreground-HWND ownership hazard is no longer only a code-inspection hypothesis.

## Confirmed ownership failure

DesktopWindow Native currently chooses the target of Clean Window frame restore from `GetForegroundWindow()` rather than an explicit transition-owned HWND.

A live real-host test on the assigned Clean Window workspace reproduced an ownership mismatch:
- transition target Clean Window HWND: `263012`;
- after Alt+C return, that HWND remained alive but became minimized (`-32000,-32000` placement);
- a new normal Chrome HWND appeared;
- DesktopWindow Native `restore-after` diagnostics recorded a different foreground HWND than the transition-start target.

Therefore a Clean Window transition can reach the foreground-based native restore path after foreground ownership has changed.

This proves the ownership mismatch can occur in real execution. It does not prove every historical window-disappearance report has exactly the same downstream effect.

## Current 2.3.24 code fact

Fresh source inspection found `session.frameHidden` assignments only to `false`; there is no current path that sets `frameHidden = true`.

Yet multiple paths still call `restoreCleanWindowFrame` unconditionally. In current 2.3.24 this means a session that never hid a native frame can still ask the foreground-based helper to restore one.

## Minimal patch candidate

Isolated candidate adds `restoreOwnedFrameIfNeeded(session)`:
- if `session.frameHidden !== true`, native restore is skipped;
- unconditional restore calls in downgrade, return-to-normal, tab-switch, and failed-switch fallback use the ownership gate;
- if a legitimate owned restore succeeds, `frameHidden` is cleared.

This is intentionally fail-closed for current 2.3.24. If native frame hiding is reintroduced later, the long-term protocol should carry explicit HWND/token ownership rather than falling back to foreground targeting.

## Regression proof

A new regression test records Native messages and asserts that Mode 3 return sends zero `restoreCleanWindowFrame` requests when the session never hid a frame.

Control case using unmodified 2.3.24:
- 14 PASS / 1 FAIL;
- the only failure is `mode 3 return does not restore an unowned native frame`;
- original code emits 1 restore message where expected count is 0.

Patched isolated candidate:
- 15 PASS / 0 FAIL;
- `node --check background.js` PASS.

Local isolated ownership commit: `16f94f4`.
Remote experiment branch `fix/owned-frame-restore` contains the `activeTab` candidate and a durable evidence copy of the ownership patch because local Git credential state blocked direct push of the local commit.

## Separate runtime-reinjection issue

Do not conflate this bug with the existing-tab runtime recovery permission failure. That issue is tracked separately in `docs/exec-plans/active/RUNTIME_REINJECTION_PERMISSION_GAP.md` and currently has `activeTab` as the least-privilege candidate.

## Test-harness interference to exclude

A DesktopWindow Chrome-for-Testing interactive instance was also observed surfacing outside its intended workspace. That is tracked as a test-harness isolation problem, not a Clean Window product bug. Do not use it as evidence for or against the ownership patch.

## Safety

- GUI actions are allowed only on explicitly assigned virtual desktops 2 and 3.
- Never steal user foreground focus.
- Do not touch DesktopWindow dirty working files merely to validate Clean Window.
- Do not broaden fixed extension/native allowlists.
- Preserve source-anchor/session serialization and the normal `1→2→3→1` cycle.
- No reboot/logoff/shutdown without explicit approval.

## Next validation — do not redo solved work

VTL reproduction is no longer a prerequisite for confirming the ownership mismatch. Use VTL only as fallback if real-host validation becomes unsafe or cannot isolate a remaining question.

Next required proof:
1. On desktop 2 or 3 only, verify a designated Clean Window test window is foreground-owned immediately before input.
2. Validate the ownership-gated candidate in actual Chrome/Windows behavior without touching unrelated windows.
3. Record before/after HWND, visible/minimized state, bounds, virtual-desktop membership, and Native diagnostics.
4. Confirm unrelated Chrome windows are unchanged.
5. Repeat normal video cycle and multi-window/virtual-desktop variants.
6. Only after live PASS should production/main apply and version bump be considered.

## Completion criteria

- source-level defect and regression proof: **complete**;
- live real-Chrome candidate validation: **pending**;
- unrelated-window non-interference: **pending final candidate validation**;
- production merge/version bump: **not yet approved**.
