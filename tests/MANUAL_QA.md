# 2.3.23 Windows virtual-desktop regression check

Automated Chrome-API simulations are in `background-cycle-regression.test.js`.
They exercise the real background listeners, mode transitions, source window IDs,
and anchor lifecycle. They do not prove real Windows/Chrome focus behavior.

## Reported reproduction (manual result pending)

1. Reload the unpacked Clean Window extension and verify version 2.3.23.
2. Open two independent Chrome windows on desktop A.
3. Use Win+Tab to move one window to desktop B.
4. In B, open a video and use Alt+C for `1 → 2 → 3 → 1`.
5. Return to A. Leave the other window on a blank Chrome new tab.
6. Press Alt+C twice: expect `1 → 2 → 1`, with no switch to B.
7. Repeat A/B switching three times; verify both original windows remain distinct.

Also check a multi-tab source (no anchor needed), a normal web page without a
video (`1 → 2 → 1`), a video on both desktops, and rapid repeated Alt+C inputs.
Do not expect mode 3 on a blank new tab. The anchor is an implementation detail;
return targets are chosen from the session's sourceWindowId, not by finding some
other window's anchor.
