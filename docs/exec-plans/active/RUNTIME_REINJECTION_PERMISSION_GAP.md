# Active Plan — Runtime reinjection permission gap

Status: `branch candidate validated at source level / live Chrome verification pending`
Updated: 2026-09-05

## Symptom

A live Clean Window transition on an already-open ChatGPT tab produced:
- `Could not establish connection. Receiving end does not exist.`
- fallback reinjection failure: `Extension manifest must request permission to access this host.`

This is distinct from the multi-window/native HWND ownership bug.

## Current code path

`background.js` calls `chrome.scripting.executeScript()` in runtime recovery paths, including reinjection of `windowed_fullscreen.js` and `fullscreen_guard.js`.

Production `main` manifest currently declares:
- `scripting`
- `tabs`
- `storage`
- `tabGroups`

It does not currently declare either:
- `host_permissions`, or
- `activeTab`.

Therefore a declarative content script may exist on normally loaded pages, but programmatic reinjection can still fail when the old content runtime is missing after extension reload/update.

## Official Chrome evidence

Chrome's official `chrome.scripting` documentation states that programmatic script injection requires the `scripting` permission plus host permission for the target page, supplied either by `host_permissions` or temporary `activeTab` permission.

Chrome's official `activeTab` documentation states that:
- `activeTab` temporarily grants host access to the current tab;
- with `scripting`, it allows `scripting.executeScript()` on that tab;
- executing a keyboard shortcut from the `commands` API is one of the explicit user gestures that enables `activeTab`.

Clean Window's primary user gesture is the `Alt+C` command, so `activeTab` is a narrower permission candidate than broad persistent host permissions.

Official references:
- https://developer.chrome.com/docs/extensions/develop/concepts/activeTab
- https://developer.chrome.com/docs/extensions/reference/api/scripting

## Experimental branch candidate — verified source-level

Branch: `fix/owned-frame-restore`
Candidate commit: `3b4e63ac886c4804c72cac2eec0883cde024c43a`

Change on that branch only:
- add `"activeTab"` to `manifest.json` permissions;
- do not add broad persistent `host_permissions`;
- production `main` remains unchanged.

Local isolated clone validation after adding `activeTab`:
- manifest parse/static check: PASS (`activeTab=true`);
- `node --test tests/background-cycle-regression.test.js`: 15 tests / 15 PASS / 0 FAIL;
- existing ownership regression test `mode 3 return does not restore an unowned native frame` remains PASS in the same isolated clone.

This is source-level validation only. It does not prove real Chrome grants/retains `activeTab` through the exact normal-window → popup → mode-3 lifecycle.

## Preferred patch candidate

First candidate for AI CODE TEAM review:
- retain the branch-only `activeTab` addition;
- do not add broad `<all_urls>` / persistent `host_permissions` merely to fix reinjection;
- preserve existing declarative content-script matches;
- independently review whether the `Alt+C` command's activeTab grant remains usable after the target tab is moved between windows.

Do not merge until live Chrome verification passes.

## Required live validation

1. On an allowed test desktop (2 or 3), load/reload the branch extension so an already-open normal HTTPS tab has a stale/missing runtime receiver.
2. Invoke Clean Window with the actual `Alt+C` command on that tab.
3. Confirm programmatic reinjection succeeds without host-permission error.
4. Confirm mode transitions still behave correctly after the tab moves between normal window and popup.
5. Repeat on YouTube and a non-video HTTPS page.
6. Confirm restricted browser-owned pages still fail safely as unsupported pages rather than producing misleading runtime recovery behavior.
7. Do not perform this live verification while the user's foreground is outside desktops 2/3 or owned by unrelated work.

## Efficiency benchmark note

This task is suitable for AI TEAM comparison:
- solo worker found the live failure, consulted official Chrome docs, narrowed the least-privilege candidate, implemented it in an isolated branch, and ran source-level regression tests;
- AI CODE TEAM should independently review the permission choice, lifecycle assumptions, and any missing regression coverage;
- record duplicated analysis versus genuinely parallel saved work;
- record time to independent confirmation and time to live validated fix.

Do not invent percentage improvements. Use actual timestamps and validated outcomes.
