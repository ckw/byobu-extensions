#!/usr/bin/env python3
"""A native tmux window menu; Python 3 standard library only. Tested on tmux 3.5a."""

import argparse
import os
import shlex
import shutil
import string
import subprocess
import sys
from dataclasses import dataclass

# Start with the user's Neovim hint order. Reserve q for cancel and 0 for current.
KEYS = ''.join(dict.fromkeys('asdfjkl;eirughwptyo' + string.ascii_lowercase
                             + '123456789' + string.ascii_uppercase)).replace('q', '')


@dataclass
class Window:
    id: str
    index: int
    active: bool
    rank: int
    name: str


def literal(text):
    """Quote one tmux format pass AND the subsequent style interpretation."""
    # tmux deliberately preserves ##[ through format expansion for style escaping.
    return ''.join(c if c.isprintable() else ' ' for c in text).replace('#', '##')


def make_menu(windows, height, page=0, order='mru'):
    current = next((w for w in windows if w.active), None)
    others = [w for w in windows if not w.active]
    # tmux uses rank 0 for never-visited windows as well as the current window.
    others.sort(key=lambda w: (w.rank or sys.maxsize, w.index)
                if order == 'mru' else (w.index,))
    paged = len(others) > min(len(KEYS), height - 4)
    capacity = min(len(KEYS), height - (7 if paged else 4))
    pages = max(1, (len(others) + capacity - 1) // capacity)
    page = min(max(0, page), pages - 1)
    visible = list(zip(KEYS, others[page * capacity:(page + 1) * capacity]))
    # Match the Vim picker: recent entries toward the bottom; easiest hint is a.
    if order == 'mru':
        visible.reverse()
    entries = [(f'{w.index:>3}  {literal(w.name)}', key, w) for key, w in visible]
    if current:
        entries.append((f'#[fg=cyan,bold]*{current.index:>2}  {literal(current.name)}',
                        '0', current))
    return entries, page, pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    parser.add_argument('--client', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--page', type=int, default=0)
    parser.add_argument('--order', choices=['mru', 'index'], default='mru')
    args = parser.parse_args()
    tmux = [shutil.which('tmux') or 'tmux', '-S', args.socket]

    def call(*command):
        return subprocess.check_output(tmux + list(command), text=True)

    # Resolve dimensions and session from the invoking client, never the default.
    clients = call('list-clients', '-F',
                   '#{client_name}\t#{session_id}\t#{client_width}\t#{client_height}')
    client = next((line.split('\t') for line in clients.splitlines()
                   if line.split('\t')[0] == args.client), None)
    if client is None or client[1] != args.session:
        return
    width, height = map(int, client[2:])
    if width < 30 or height < 8:
        call('display-message', '-c', args.client,
             'Window picker: enlarge terminal to at least 30 columns and 8 rows.')
        return

    # Strip record delimiters within names before parsing; other controls are
    # sanitized for display. Window names are never inserted into commands.
    fmt = ('#{window_id}\t#{window_index}\t#{window_active}\t#{window_stack_index}\t'
           '#{s/[\t\r\n]/ /:window_name}')
    windows = []
    for line in call('list-windows', '-t', args.session, '-F', fmt).rstrip('\n').split('\n'):
        wid, index, active, rank, name = line.split('\t', 4)
        windows.append(Window(wid, int(index), active == '1',
                              int(rank) if rank else int(index), name))
    if not windows:
        return
    entries, page, pages = make_menu(windows, height, args.page, args.order)
    initial = next((i for i, (_, key, _) in enumerate(entries) if key == 'a'), 0)
    command = ['display-menu', '-c', args.client, '-t', args.session + ':',
               '-T', f'Windows {args.order.upper()} {page + 1}/{pages}',
               '-x', 'C', '-y', 'C', '-b', 'rounded', '-C', str(initial)]
    for label, key, window in entries:
        # Session plus immutable window ID survives renumbering and duplicate names.
        target = shlex.quote(args.session + ':' + window.id)
        command.extend([label, key, 'select-window -t ' + target])
    if pages > 1:
        command.append('')
        for label, key, new_page in [('Previous page', '[', page - 1),
                                     ('Next page', ']', page + 1)]:
            if 0 <= new_page < pages:
                shell = shlex.join([sys.executable, os.path.abspath(__file__),
                                    '--socket', args.socket, '--client', args.client,
                                    '--session', args.session, '--order', args.order,
                                    '--page', str(new_page)])
                # The menu and run-shell each expand formats once.
                action = 'run-shell -b ' + shlex.quote(shell.replace('#', '####'))
                command.extend([label, key, action])
            else:
                command.extend(['-' + label, '', ''])
    command.extend(['-Esc/q cancel | * current', '', ''])
    # tmux's argv parser treats even trailing semicolons as command separators.
    call(*(arg[:-1] + r'\;' if arg.endswith(';') else arg for arg in command))


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        print(f'Window picker: {error}', file=sys.stderr)
        sys.exit(1)
