# Byobu Extensions

Small personal extensions for Byobu with the tmux backend. Each extension has
its utility in `bin/` and bindings in `tmux/`; `byobu-extensions.tmux` is the
shared entry point. Future extensions can be added alongside the window picker.

## Window picker

Press **Ctrl-A, then Space** to show a centered menu of every window in the
current session. **F12, then Space** also works when F12 is the alternate prefix.
Press the hint next to a window to close the menu and switch immediately.

- Hints begin `a s d f j k l ; e i r u g h w p t y o`, matching the personal
  `mru-buffer-picker` configuration, then use other letters and digits.
- Most recently visited windows appear toward the bottom of each page, with
  `a` assigned to the most recent other window on that page. Never-visited
  windows follow visited windows in hint priority, ordered by window index.
- The current window is highlighted with `*` and has the hint `0`.
- Escape or `q` cancels; arrow keys and Enter also work through tmux's native menu.
- `[` and `]` change pages when the terminal height or the 62-hint capacity
  requires it. Every window remains reachable. The current window is repeated
  on every page; hints are local to each page.
- A window's displayed number is its actual index, independent of its hint.
  Selection uses stable window IDs, so duplicate names, multi-digit indices,
  and renumbering while the menu is open are supported.

The interaction follows the Vim buffer picker's home-row hint priority and
recent-at-bottom layout. This picker includes the current window and uses
pages instead of two-character hints. Unassigned keys follow tmux's native
menu behavior, rather than Vim's cancel-on-invalid-key behavior.

## Requirements and installation

Tested with tmux 3.5a and Byobu 6.13 on macOS. Python 3.8+ must be on the tmux
server's PATH; no third-party Python packages are used. Tests require a POSIX
system with pseudo-terminal support. This extension is for Byobu's tmux backend.

Keep this repository at `~/byobu-extensions`. Add the following to the active
Byobu `keybindings.tmux` file (on this machine, `~/.byobu/keybindings.tmux`):

```tmux
source-file ~/byobu-extensions/byobu-extensions.tmux
```

Load it in a running Byobu session:

```sh
tmux source-file "$HOME/byobu-extensions/byobu-extensions.tmux"
```

Only prefix+Space is bound. It replaces Byobu's next-window binding on that key;
prefix+n still selects the next window. The extension does not change either
prefix key, and it does not install a prefix+W binding.

To use numeric ordering, append `--order index` to the `run-shell` command in
`tmux/window-picker.tmux`, then reload the entry point. Reload after changing
bindings; script edits take effect the next time the picker opens.

## Implementation and limits

`list-windows` provides the entries; `window_stack_index` provides true visit
order; `display-menu` draws the menu; `select-window` switches to the selected
session/window ID. No custom tracking hooks, background service, or history
file are needed. MRU state belongs to the running tmux session.

The invoking client and tmux socket are passed explicitly. Selection has normal
tmux semantics: other clients sharing the same session follow its active window.
This picker covers windows in the invoking session, not all sessions on the server.

Names are displayed as literal text and never embedded in selection commands.
Long labels are clipped by tmux. A terminal smaller than 30 columns or 8 rows
gets an explanatory status message. The menu is a snapshot: reopen it after
creating or deleting windows or resizing the terminal. If a selected window
was deleted, tmux reports a missing target instead of selecting by a reused index.

## Tests

```sh
make test
```

The interaction test creates its own temporary tmux socket and attached
pseudo-terminal. It checks 28- and 71-window lists, cancellation, hint selection,
unusual names, renumbering, short-terminal paging, and both prefix+Space shortcuts.
Its test server is cleaned up afterward; existing tmux servers are not used.

## Removing the extension

Remove the source line from the Byobu keybindings file. In a running session,
restore the original binding with:

```sh
tmux bind-key -T prefix Space next-window
```

The initial migration saved the earlier keybindings and standalone picker files
in `~/.byobu/backups/byobu-extensions-20261003/`.
