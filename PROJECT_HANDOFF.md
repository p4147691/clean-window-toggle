# Clean Window — Project Handoff

Stable project contract, state-machine rules, safety boundaries, and validation map only. Current investigations live under `docs/exec-plans/active/`.

Central recovery: `p4147691/BOOTSTRAP/BOOTSTRAP.md` via `기깃`.
Project map: `AGENTS.md`.
Shared rules: `p4147691/BOOTSTRAP/AI_SHARED_CORE.md`.

## Source of Truth

- GitHub: `p4147691/clean-window-toggle`
- Branch: `main`
- Canonical local runtime folder: `D:\ChromeExtensions\CleanWindow`
- Related project: `p4147691/DesktopWindow`
- Related DesktopWindow local folder: `D:\ChromeExtensions\DesktopWindow`

Fresh-check current HEAD, manifest/runtime version, workflow triggers, and actual local deployment state on every new task. Do not treat old SHAs as permanently current.

## Stable Product Model

User-visible modes:

1. normal Chrome window
2. Clean Window popup
3. video-focused contained/windowed-fullscreen inside Clean Window

Expected `Alt+C` cycle:
- video present: `1 → 2 → 3 → 1`
- clear no-video / unsupported browser page: `1 ↔ 2`

Real site fullscreen (for example a site's fullscreen button / `document.fullscreenElement`) is a separate axis from Clean Window mode 3. `fullscreen_guard.js` must not make intercepting real site fullscreen the default design.

## Failure Semantics — MUST PRESERVE

- Clear no-video/unsupported page may skip mode 3 and return toward normal.
- Temporary content/runtime/native failure is not the same as no-video; do not blindly bounce to normal and destroy state.
- If video disappears from mode 3 through Back/SPA navigation, degrade safely to mode 2, then allow the next cycle back to mode 1.
- Do not treat all fullscreen failures as identical.

## Original Chrome Window Identity — MUST PRESERVE

Moving the only tab out of a normal Chrome window can destroy the original window identity. The source-anchor mechanism exists to preserve that relationship.

Rules:
- create an anchor only for the required single-tab case;
- if the user navigates/searches in an anchor tab, promote it to user-owned and stop treating it as disposable;
- if the anchor is moved to another window, treat it as user-owned;
- remove an anchor only after a successful safe return;
- do not remove the anchor architecture as a simplification without proving another identity-preserving mechanism.

## Input / Transition Contract

- Primary `Alt+C` path is `chrome.commands`.
- Do not restore legacy content-keydown as a competing primary path.
- Use the actually focused window/active tab when deciding a transition.
- Preserve transition serialization/queue protections so stale `finally` or old work cannot release/overwrite a newer transition.
- Queued input must not be silently retargeted to a different current tab/window.
- Stale locks must be recoverable rather than permanent.
- Normal-return focus verification should not hold the main transition lock unnecessarily.

## Session Consistency

The 2.3.24-era fix established a key durable lesson: async tab/window events must not re-save an older whole-session snapshot after a newer operation deleted or updated that session.

Preserve serialized/session-operation ownership (`runSessionOperation` or its current equivalent) so late event handlers cannot resurrect completed session state. Do not reintroduce whole-state read/modify/write races.

## Main Files

- `background.js` — session/transition/anchor/window relationships and Native helper requests
- `windowed_fullscreen.js` — mode-3 target/runtime/SPA/video-gone behavior
- `fullscreen_guard.js` — protect real site fullscreen interoperability
- `manifest.json` — extension version/commands/content scripts
- tests including background-cycle regression coverage

## DesktopWindow / Runner Relation

Clean Window may use DesktopWindow helper/frame control and may share its local sync Runner. This does not make the sync Windows Service an interactive GUI-test or Codex-authenticated user-session Runner.

For Runner/Codex details read only when relevant:
`p4147691/BOOTSTRAP/docs/reference/RUNNER_CODEX.md`

Do not broaden fixed extension/origin allowlists when changing the integration.

## Regression Matrix

At minimum preserve these behaviors:

- video cycle repeatedly completes `1→2→3→1` without mode lock
- mode 3 → Back/SPA to non-video → safe mode 2 → `Alt+C` returns to normal
- another tab/window is not contaminated by previous transition/queue state
- unsupported/no-video pages continue `1↔2`
- single-tab source Chrome window identity survives a full cycle
- rapid `Alt+C` does not create duplicate runs, permanent lock, or lost/retargeted queue state
- real site fullscreen enters/exits without corrupting Clean Window session/window return state
- Windows virtual desktops do not cause the operation to jump to another desktop's Chrome window

Automatic tests that mock Chrome/Windows state do not replace actual Chrome/OS evidence for these behaviors.

## Current Active Work

Read `docs/exec-plans/active/` for any live investigation. Historical 2.3.x debugging details should not be loaded by default.

## Handoff Maintenance

- stable state-machine/safety/validation contract → this file
- current bug/reproduction → `docs/exec-plans/active/`
- completed debugging → `docs/exec-plans/completed/`
- durable design decisions → `docs/decisions/`
- important evidence → `docs/evidence/`

Legacy Google Drive `Clean Window 인수인계` remains migration/reference material. Fresh verified GitHub/runtime/user evidence wins on conflict.
