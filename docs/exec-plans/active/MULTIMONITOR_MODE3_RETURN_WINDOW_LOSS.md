# Active Plan — Multi-monitor Mode 3 return affects other Chrome windows

Status: `investigating`

Reported: 2026-09-04

## User-observed reproduction

On a multi-monitor Windows desktop:
1. A YouTube tab/window was already in Clean Window Mode 3 on another screen/window.
2. The Mode 3 YouTube window was moved across monitors.
3. `Alt+C` was used to leave Mode 3 / return toward the normal Chrome state.
4. Other Chrome windows unexpectedly disappeared/closed from the user's view.

Treat the exact meaning of "disappeared/closed" as evidence to resolve (actual window destruction vs minimization vs movement/focus/virtual-desktop effect). Do not guess.

## Safety

- Do not ask the user to repeat a potentially destructive reproduction on the live desktop until existing diagnostics and isolated tests are exhausted.
- Do not change production behavior before reproducing or narrowing the fault.
- Preserve source-anchor/session serialization and the normal 1→2→3→1 cycle.
- Other unrelated Chrome windows must never be closed, minimized, moved, or frame-mutated by a transition they do not own.

## Host AutoHotkey reference

The user's uploaded AutoHotkey snapshots were reviewed and a shared conflict reference was recorded in BOOTSTRAP at `docs/reference/HOST_AUTOHOTKEY_ENVIRONMENT.md`.

- No direct `Alt+C` hotkey was found in the reviewed AHK snapshots, so there is no current evidence of a simple direct Alt+C registration collision.
- The host does have scripts capable of global hotkey interception, global click handling, browser navigation, and closing the active Chrome window (for example global F3 in the older backup script, ScrollLock-enabled left-click automation, and `Ctrl+Q`). Treat AutoHotkey as a real external interference layer and verify the actually running scripts before ruling it out.
- The newer integrated script intentionally scopes F3/F4 to Explorer/real-desktop contexts; do not assume the older script is inactive without evidence.

## Investigation order

1. Collect existing `DesktopWindow/_runtime/window-transition-diagnostics.jsonl` through the existing Runner; the Native helper records Chrome HWND, monitor, visibility, minimized state, bounds, foreground status, and saved frame-style state around Mode 3 frame operations.
2. Run a deterministic Chrome-API regression simulation with multiple unrelated windows and a Mode 3 popup moved to coordinates representing another physical monitor before `Alt+C` return.
3. Inspect Clean Window `returnToNormalWindow` / temporary-window cleanup / anchor lifecycle.
4. Inspect DesktopWindow Native helper `hideCleanWindowFrame` / `restoreCleanWindowFrame`; these currently target `GetForegroundWindow()`, so focus ownership during cross-monitor transitions must be verified.
5. Verify relevant host AutoHotkey scripts actually running at incident time before attributing any live-desktop close/focus behavior solely to Clean Window.
6. Only if mock logic remains clean, use isolated real Windows/Chrome evidence through VTL/Hyper-V when capable of faithful multi-window/multi-monitor reproduction.

## Current code observations before testing

- Clean Window 2.3.24 returns Mode 3 through `returnToNormalWindow` and `movePopupTabBack`.
- `movePopupTabBack` explicitly removes only the temporary normal window it created after the target tab has moved back to the source window.
- DesktopWindow Native helper frame operations use the current foreground Chrome HWND rather than a passed explicit HWND.
- Existing background regression tests cover unrelated windows/virtual desktops but do not specifically cover moving a Mode 3 popup to another monitor before returning.

## Completion criteria

- Determine whether the observed effect is close, minimize, move, focus loss, or frame corruption.
- Identify the owning layer: Clean Window Chrome state machine, DesktopWindow Native frame helper, host AutoHotkey/external interference, or OS/Chrome interaction.
- Add a regression test that fails on the proven fault.
- Apply the smallest safe fix and validate that unrelated Chrome windows remain unchanged.
