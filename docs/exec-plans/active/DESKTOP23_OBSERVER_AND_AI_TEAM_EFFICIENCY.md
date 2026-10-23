# Active Plan — Desktop 2/3 observer + AI TEAM efficiency benchmark

Status: `active / observer-chat handoff ready`
Updated: 2026-09-05

## Purpose

Use Windows virtual desktops 2 and 3 as a live Clean Window test workspace while simultaneously measuring whether AI CODE TEAM improves real debugging efficiency versus a single ChatGPT worker.

This is not a synthetic benchmark. The work should produce real Clean Window bug discoveries, fixes, regressions, and product improvements while collecting comparable timing/evidence.

## Workspace boundary — MUST PRESERVE

Allowed GUI workspace:
- Windows virtual desktop 2
- Windows virtual desktop 3

Forbidden / out of scope:
- virtual desktop 1
- virtual desktop 4 or any other desktop not explicitly assigned later
- unrelated project windows
- unrelated user work

Never move, focus, close, minimize, restore, or inspect user windows outside the allowed workspace unless the user explicitly reassigns the boundary.

## Focus protection — highest priority

The user's active focus must never be stolen by background testing.

Before any input-generating GUI action:
1. identify the current foreground HWND;
2. verify that HWND belongs to an explicitly designated Clean Window test window inside desktop 2 or 3;
3. verify the user has not moved focus to unrelated work;
4. if ownership is uncertain, do not send input and continue only with logs/code/GitHub analysis.

SetForegroundWindow, Alt+C injection, window activation, and virtual-desktop switching are forbidden unless the operation is explicitly part of the current desktop-2/3 test and ownership was verified immediately beforehand.

Success target: `user-focus-interference count = 0`.

## Passive dashboard boundary rule — MUST PRESERVE

A `NOACTIVATE` observer window protects foreground focus, but it does **not** by itself guarantee the window is created on an allowed virtual desktop.

Verified failure on 2026-09-05:
- the passive `Clean Window Lab Observer` window did not steal foreground focus;
- however, it appeared on virtual desktop 4, which was outside the assigned 2/3 workspace;
- therefore this counts as a workspace-boundary failure even though focus-interference remained zero.

New rule:
- never create/show an observer GUI unless the current virtual desktop is freshly verified as 2 or 3;
- when current desktop is 1, 4, or any unassigned desktop, remain headless/passive and only update files/logs;
- do not move an observer window from a forbidden desktop back into scope, because doing so would itself manipulate the forbidden desktop;
- observer visibility is optional; workspace isolation is mandatory.

Track separately:
- `user-focus-interference count`
- `workspace-boundary-interference count`

Both success targets are `0` after this rule is adopted.

## Existing observability that is currently useful

Clean Window extension state/log keys:
- `cleanWindowSessionsV8`
- `cleanWindowTransitionDebugV1`
- `cleanWindowLastFailureV1`

DesktopWindow Native helper diagnostics:
- `D:\ChromeExtensions\DesktopWindow\_runtime\window-transition-diagnostics.jsonl`
- records phase, foreground HWND, Chrome HWNDs, process ID, minimized/visible state, frame-style state, monitor and bounds.

These logs are active enough to support incident reconstruction, but there is not yet one unified passive watcher that groups desktop/window/focus/native/extension events into a single incident timeline.

## Observer-chat role

A dedicated chat should own passive observation and evidence collection.

Responsibilities:
- observe only desktops 2 and 3;
- collect foreground HWND, window create/destroy/minimize/restore/move, bounds, desktop membership, and relevant process/title metadata;
- correlate Clean Window transition stages with Native helper diagnostics;
- mark unexpected focus changes and identify the last input/action preceding them;
- capture before/after screenshots only inside the assigned workspace when useful;
- produce short incident records with timestamp, reproduction, expected, actual, affected HWNDs, likely layer, confidence, and next verification;
- never patch product code unless explicitly reassigned to do so.

Prefer passive/read-only observation while the user or another AI worker is actively using the PC.

## Newly verified live findings — 2026-09-05

### A. Mode-3 return / ownership mismatch reproduced on real desktop

A live test on virtual desktop 2 targeted Clean Window HWND `263012` and sent one Alt+C transition after explicitly focusing that test window.

Observed after the transition:
- target HWND `263012` remained alive but became minimized (`-32000,-32000` Windows minimized coordinates);
- a new normal Chrome HWND appeared in the same general workspace;
- visible Chrome layout changed enough to reproduce the user's "windows disappeared" class of symptom;
- DesktopWindow Native diagnostic `restore-after` recorded a different foreground HWND than the transition-start target.

This upgrades the foreground-HWND ownership hazard from code-only hypothesis to a real execution mismatch. It does not yet prove that every reported disappearance has the same cause.

### B. Existing-tab runtime recovery can fail after reload/update

A real transition log on a ChatGPT tab recorded:
- `Could not establish connection. Receiving end does not exist.`
- reinjection failure: `Extension manifest must request permission to access this host.`

Current manifest has `scripting` permission and broad declarative content-script matches, but no `host_permissions`. Therefore runtime hot-recovery through `chrome.scripting.executeScript()` is not guaranteed on an already-open site when the existing content runtime is gone.

Treat this as a separate bug from the multi-window ownership issue.

### C. Passive observer GUI can violate desktop boundary without stealing focus

The first WPF passive dashboard used non-activating display behavior and foreground verification. It successfully preserved the foreground HWND, but the window was later observed on virtual desktop 4.

Lesson:
- focus ownership and virtual-desktop ownership are separate safety dimensions;
- `ShowActivated=false` / no-activate is not sufficient isolation;
- observer GUI creation must be gated by a fresh desktop-index check before creation.

Do not count this as a Clean Window product bug. It is a test-harness/observer bug and must be included when evaluating the multi-desktop test environment itself.

### D. DesktopWindow Chrome-for-Testing window surfaced into the visible workspace

A visible `Google Chrome for Testing` login/onboarding window was observed during normal user activity.

Read-only process inspection identified the exact test instance:
- executable: `D:\AI_TOOLS\ChromeForTesting\152.0.7977.82\chrome-win64\chrome.exe`
- profile: `D:\AI_TOOLS\ChromeProfiles\DesktopWindow-CfT`
- remote debugging port: `9227`
- loaded unpacked extension: `D:\ChromeExtensions\DesktopWindow\extension`
- launcher source: `D:\ChromeExtensions\DesktopWindow\tools\Start-DesktopWindowTestChrome.ps1`

The launcher itself already defaults to `--headless=new`; a visible browser requires its explicit `-Interactive` branch, which verifies a bound virtual-desktop id, starts Chrome minimized, then moves its windows to that bound desktop. Therefore the surfaced window is not evidence that headless mode itself opens UI. It is evidence that an interactive DesktopWindow test instance later became visible in the user's workspace despite the intended isolation.

Classification:
- layer: test harness / DesktopWindow test-browser lifecycle
- Clean Window product bug: no
- workspace-boundary interference: yes
- user-focus interference: not proven from this incident alone
- confidence: high for process/launcher attribution; medium for the exact later restore/visibility trigger

Next verification:
- preserve the current DesktopWindow dirty working files;
- do not launch another interactive test browser while the user is active;
- correlate the process creation time and any later restore/show event with DesktopWindow Native diagnostics and runner logs;
- future unified watcher must record test-browser process identity, desktop membership, visible/minimized state, and the event that first makes a hidden/minimized test window visible.

## AI TEAM efficiency comparison

Compare two modes of work using real Clean Window tasks.

Mode A — single worker:
- one ChatGPT performs reproduction, evidence collection, code analysis, patch design, testing and verification.

Mode B — AI CODE TEAM collaboration:
- observer/test worker gathers live desktop evidence;
- AI CODE TEAM performs parallel code search, hypothesis generation, patch/review/test work;
- observer/test worker performs final live validation.

Track at minimum:
- time to first useful reproduction;
- time to first correct root-cause candidate;
- time to root-cause confirmation;
- time to patch candidate;
- time to validated fix;
- number of wrong hypotheses;
- number of rework cycles;
- user intervention count;
- user-focus-interference count;
- workspace-boundary-interference count;
- bugs found per hour;
- regressions introduced/detected;
- parallel work saved versus duplicated work.

Do not invent percentage improvements. Record actual timestamps/durations first; calculate comparative efficiency only after enough comparable tasks exist.

## Current recommended workflow

1. Observer chat keeps passive records on desktops 2/3.
2. Clean Window debugging chat chooses one incident at a time and requests precise evidence.
3. AI CODE TEAM receives the same evidence packet for parallel analysis/patch work.
4. Final live verification happens only in desktops 2/3 and only when user focus is not being used elsewhere.
5. Observer GUI is created only after the current desktop is freshly verified as 2 or 3; otherwise observer remains headless.
6. VM/VTL is fallback for risky, destructive, or hard-to-isolate reproductions; real-host evidence wins when safely obtainable.

## Safety

- No reboot, logoff, shutdown or destructive host changes without explicit approval.
- Do not touch DesktopWindow dirty working files merely to improve Clean Window diagnostics.
- Do not broaden extension/native allowlists as a shortcut.
- Do not use background automation that can steal foreground focus from unrelated user work.
- Preserve source-anchor and transition/session serialization semantics.

## Handoff target

When starting a new observer chat, run `기깃 Clean Window`, then read this file first after the project handoff. The observer chat should not duplicate product implementation work; its job is to make incidents measurable, attributable, and comparable across solo vs AI TEAM workflows.
