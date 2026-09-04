# Active Plan — Multi-monitor Mode 3 return affects other Chrome windows

Status: `investigating / VTL L2 repro required`

Reported: 2026-09-04

## User-observed reproduction

On a multi-monitor Windows desktop:
1. A YouTube tab/window was already in Clean Window Mode 3 on another screen/window.
2. The Mode 3 YouTube window was moved across monitors.
3. `Alt+C` was used to leave Mode 3 / return toward the normal Chrome state.
4. Other Chrome windows unexpectedly disappeared/closed from the user's view.

Treat the exact meaning of "disappeared/closed" as evidence to resolve (actual window destruction vs minimization vs movement/focus/virtual-desktop effect). Do not guess.

## Newly narrowed structural risk — 2026-09-04

Fresh code inspection confirmed that the shared DesktopWindow Native helper currently chooses the frame target from **`GetForegroundWindow()`** for both Clean Window frame hide and restore operations.

In particular:
- `HideCleanWindowFrame(...)` obtains the current foreground HWND and applies `HideFrame(window)`;
- `RestoreCleanWindowFrame()` again obtains the current foreground HWND and applies `RestoreFrame(window)`;
- the Clean Window extension requests `restoreCleanWindowFrame` without passing an explicit transition-owned HWND.

This creates a plausible ownership hazard in asynchronous multi-window/multi-monitor transitions: if foreground focus moves to a different Chrome window before the helper receives the restore request, the helper may mutate an unrelated Chrome frame instead of the Mode-3 popup that owns the transition.

This is a **hypothesis, not yet a proven root cause**. Do not patch production merely from inspection. The exact HWND/foreground sequence must first be reproduced in isolated Windows and correlated with the existing diagnostics.

## Safety

- Do not ask the user to repeat a potentially destructive reproduction on the live desktop until isolated tests are exhausted.
- Do not change production behavior before reproducing or narrowing the fault.
- Preserve source-anchor/session serialization and the normal 1→2→3→1 cycle.
- Other unrelated Chrome windows must never be closed, minimized, moved, or frame-mutated by a transition they do not own.

## Host AutoHotkey reference

The host has external automation capable of affecting Chrome, so it remains an interference layer to distinguish from product behavior. There is no current evidence of a simple direct `Alt+C` registration collision in the reviewed snapshots. Do not assume external automation is inactive without evidence, but do not use it as a catch-all explanation either.

## Investigation order

1. Finish the narrow VTL persistent guest interactive bridge and verify installed Chrome can be controlled in the logged-in guest session.
2. In VTL, create at least two unrelated Chrome windows plus one transition-owned popup and record HWND/window identity before every frame operation.
3. Move/position the owned popup across the available display geometry or equivalent virtual coordinates, then execute return.
4. Compare the helper's foreground HWND at `restoreCleanWindowFrame` with the transition-owned popup HWND.
5. Determine whether any unrelated window was destroyed, minimized, moved, focus-changed, or frame-mutated.
6. Re-run virtual-desktop/rapid-input variants because focus ownership can change there as well.
7. Only after a mismatch is proven, change the protocol so the owner is explicit and validate all existing normal cycles.

## Current code observations

- Clean Window returns Mode 3 through `returnToNormalWindow` / `movePopupTabBack` paths.
- `movePopupTabBack` explicitly removes only its own temporary normal window after target-tab movement.
- Native frame helper ownership is foreground-based rather than explicit-HWND-based.
- Existing mock/background regression tests do not prove actual Windows foreground ownership.

## Completion criteria

- Determine whether the observed effect is close, minimize, move, focus loss, or frame corruption.
- Identify the owning layer: Clean Window state machine, DesktopWindow Native frame helper, host external automation, or OS/Chrome interaction.
- Add a regression test that fails on the proven fault.
- Apply the smallest safe fix and validate unrelated Chrome windows remain unchanged.
