# Active Plan — Runtime reinjection permission gap

Status: `root-cause narrowed / patch candidate for AI CODE TEAM review`
Updated: 2026-09-05

## Symptom

A live Clean Window transition on an already-open ChatGPT tab produced:
- `Could not establish connection. Receiving end does not exist.`
- fallback reinjection failure: `Extension manifest must request permission to access this host.`

This is distinct from the multi-window/native HWND ownership bug.

## Current code path

`background.js` calls `chrome.scripting.executeScript()` in runtime recovery paths, including reinjection of `windowed_fullscreen.js` and `fullscreen_guard.js`.

Current `manifest.json` declares:
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

## Preferred patch candidate

First candidate for AI CODE TEAM review:
- add `"activeTab"` to `permissions` in `manifest.json`;
- do not add broad `<all_urls>` / persistent `host_permissions` merely to fix reinjection;
- preserve existing declarative content-script matches;
- verify the `Alt+C` command path retains the temporary activeTab grant through the tab/window move sequence used by Clean Window.

This candidate is not yet production-approved until real Chrome validation passes.

## Required validation

1. Load/reload the extension so an already-open normal web tab has a stale/missing runtime receiver.
2. Invoke Clean Window with the actual `Alt+C` command on that tab.
3. Confirm programmatic reinjection succeeds without host-permission error.
4. Confirm mode transitions still behave correctly after the tab moves between normal window and popup.
5. Repeat on YouTube and a non-video HTTPS page.
6. Confirm restricted browser-owned pages still fail safely as unsupported pages rather than producing misleading runtime recovery behavior.

## Efficiency benchmark note

This task is suitable for AI TEAM comparison:
- solo worker found the live failure and narrowed the permission root cause;
- AI CODE TEAM can independently review the least-privilege patch, tests, and regression risk;
- record duplicated analysis versus genuinely parallel saved work.

Do not merge a permission change merely because it is small; verify actual Chrome command/activeTab behavior first.
