# Clean Window Anchor experiment

This branch keeps the original normal Chrome window alive when the active tab is its only tab.

## Hypothesis
Moving the only tab into a popup can destroy the original normal Chrome window. Returning then requires a newly created normal window, which may feel less stable in Windows Snap/group behavior.

## Experiment
- Only when the source window has exactly one tab, create one inactive `about:blank` anchor tab.
- Move the real tab to the Clean Window popup as before.
- Minimize and preserve the original source window.
- On the third toggle, move the real tab back to the same source window, remove the anchor while the source remains minimized, then restore/focus the original source window.
- Multi-tab behavior is unchanged.
- The anchor is filtered from the Clean Window tab shell.
- Failure, recovery, popup-X, and source-window-close paths clean up the anchor.

The experiment intentionally does not change the stable `main` branch.
