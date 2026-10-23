# Active Plan — Mode 2 Stall / Virtual Desktop Re-verification

Status: `paused / not current primary project`

## Why this remains an active investigation

The 2.3.24 work fixed a real session-state resurrection race and added failure diagnostics, but historical reports around mode-2 stalls and Windows virtual-desktop interactions were not consistently explained by one root cause.

There is also later user evidence that 2.3.24 behaved correctly in actual Chrome for key cycles. Therefore do **not** assume either "still broken" or "fully solved" from old notes. Fresh reproduction comes first.

## Re-entry checklist

1. Fresh-check current `main`, manifest/runtime version, and actual local runtime files.
2. Confirm the running Chrome extension was actually reloaded to that version; distinguish disk sync from live extension reload.
3. Re-run the normal matrix:
   - video `1→2→3→1`
   - unsupported/no-video `1↔2`
   - mode 3 → Back/SPA → mode 2 → normal
   - rapid input
   - multiple Chrome windows
4. Re-run the Windows virtual-desktop scenario with one Chrome window on each desktop.
5. If a stall occurs, inspect preserved diagnostics such as `cleanWindowLastFailureV1`, transition debug, session state, and pending fullscreen state before changing code.

## Important historical evidence

The 2.3.24-era investigation found a concrete read/modify/write race: anchor removal fired asynchronous tab events whose stale full-session snapshot could re-save a session that a successful return had already removed. Serialized session operations fixed that class of bug.

A separate observed mode-2 stall showed command arrival and transition completion without a permanent lock, so not every stall can be explained as missed hotkey input or a stuck transition lock.

## Guardrails

- Do not restore delayed content-keydown fallback as a competing primary input path.
- Do not assume missing/unsupported content and temporary injection/runtime failure are equivalent.
- Do not close user-owned tabs/windows merely because they resemble generated anchors.
- Do not mix a new Windows titlebar/frame-control architecture into an unresolved state-machine bug unless isolation evidence proves it is relevant.
- Keep real site fullscreen separate from contained mode 3.

## Better test direction

This bug class is well suited to isolated real-execution automation:

- persistent Hyper-V VM with two Windows virtual desktops and Chrome state, or
- interactive Windows test agent able to control actual Chrome/focus/keyboard state,
- screenshots + window identity + tab/session logs captured automatically.

Source mocks alone are insufficient for final confidence.

## Completion

When fresh actual-Chrome/OS evidence shows the behavior is consistently solved, move this file to `docs/exec-plans/completed/` with the exact reproduction matrix and proof. If a reproducible remaining failure is found, update this plan with the precise failing transition and evidence before coding.
