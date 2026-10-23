# Local desktop source authority — CLEAN_WINDOW

The canonical development source is the local Git checkout at D:\ChromeExtensions\CleanWindow-virtual-desktop-fix. GitHub is publication, backup, code review and CI, not an authority that can automatically alter this checkout.

- A remote push must never run a remote-to-local pull, merge, reset or deployment of this local source.
- A local change is developed and tested here, committed to local main, then published to GitHub fast-forward-only with a recorded exact SHA. Remote divergence is a SYNC_CONFLICT; no force updates.
- A runtime/installed copy is a release output, not the source. Validate expected source SHA and expected runtime SHA before deploying; block unexpected differences, protect local data and back up changed files.
- The legacy remote-to-local workflow is preserved for history in docs/retired-remote-sync/pull_local_cleanwindow_once.yml.disabled.txt; it is not a GitHub Actions workflow.
- Current installed extension is at D:\ChromeExtensions\CleanWindow; source must incorporate any installed-only changes before a release.
- Do not restart Chrome, VTL, RCC, Native Host, or self-hosted runners when only changing policy files.
