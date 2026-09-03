# AGENTS.md — Clean Window Map

Clean Window is a Windows-focused Chrome extension for switching/cleaning browser window chrome and coordinating with DesktopWindow when needed.

## Read in this order

1. `PROJECT_HANDOFF.md`
2. Relevant file under `docs/exec-plans/active/`
3. Relevant extension/workflow files only
4. DesktopWindow integration docs only when the task crosses that boundary
5. Central shared rules as needed: `p4147691/BOOTSTRAP/AI_SHARED_CORE.md`

Do not load the legacy Drive handoff or long 2.3.x debugging history by default.

## Source of Truth

- Repo: `p4147691/clean-window-toggle`
- Branch: `main`
- Local project: `D:\ChromeExtensions\CleanWindow`

Fresh-check current code, workflow triggers, live extension version/reload state, and local-sync status rather than trusting old SHAs.

## Must preserve

- Windows user environment assumptions
- original Chrome window identity / source-anchor contract
- transition/session serialization semantics
- DesktopWindow integration allowlists and fixed extension/origin security boundaries
- unexpected dirty local changes; never erase them with force/reset
- existing safe sync/test behavior

## Validation

Distinguish source-level success from actual Chrome/window behavior. For focus, titlebar, virtual-desktop, window-mode, or hotkey issues, prefer isolated real-execution testing where practical before repeated manual user checks.
