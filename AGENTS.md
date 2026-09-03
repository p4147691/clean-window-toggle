# AGENTS.md — Clean Window Map

Clean Window is a Windows-focused Chrome extension for switching/cleaning browser window chrome and coordinating with DesktopWindow when needed.

## Read in this order

1. `PROJECT_HANDOFF.md` when present; until migrated, use the central Registry Drive fallback
2. Relevant extension/workflow files only
3. DesktopWindow integration docs only when the task crosses that boundary
4. Central shared rules as needed: `p4147691/BOOTSTRAP/AI_SHARED_CORE.md`

## Source of Truth

- Repo: `p4147691/clean-window-toggle`
- Branch: `main`
- Local project: `D:\ChromeExtensions\CleanWindow`

Fresh-check current code, workflow triggers, and local-sync status rather than trusting old SHAs.

## Must preserve

- Windows user environment assumptions
- DesktopWindow integration allowlists and fixed extension/origin security boundaries
- unexpected dirty local changes; never erase them with force/reset
- existing safe sync/test behavior

## Validation

Distinguish source-level success from actual Chrome/window behavior. For focus, titlebar, window-mode, or hotkey issues, prefer isolated real-execution testing where practical before repeated manual user checks.
