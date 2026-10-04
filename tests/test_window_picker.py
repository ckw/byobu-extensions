"""Exercise actual tmux overlays through a disposable pseudo-terminal/server."""
import fcntl
import importlib.util
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'bin/window-picker.py'
spec = importlib.util.spec_from_file_location('picker', SCRIPT)
picker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(picker)
TMP = tempfile.TemporaryDirectory(prefix='byobu-picker-test-')
SOCKET = TMP.name + '/tmux.sock'
TMUX = [shutil.which('tmux') or 'tmux', '-S', SOCKET]
env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
env['TERM'] = 'xterm-256color'
client = None
master = None
processes = []


def tmux(*args):
    return subprocess.check_output(TMUX + list(args), env=env, text=True).strip()


def wait_for(predicate, message):
    limit = time.monotonic() + 4
    while time.monotonic() < limit:
        if predicate():
            return
        time.sleep(.025)
    raise AssertionError(message)


def drain(duration=.15):
    data = b''
    end = time.monotonic() + duration
    while time.monotonic() < end:
        if select.select([master], [], [], max(0, end - time.monotonic()))[0]:
            data += os.read(master, 65536)
    return data


def open_menu(order='mru'):
    drain(.03)
    proc = subprocess.Popen([sys.executable, str(SCRIPT), '--socket', SOCKET,
                             '--client', client_name, '--session', session,
                             '--order', order], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processes.append(proc)
    data = b''
    limit = time.monotonic() + 4
    while time.monotonic() < limit:
        data += drain(.05)
        if b'Windows ' + order.upper().encode() in data:
            return proc, data + drain(.1)
        if proc.poll() is not None and proc.returncode:
            raise AssertionError(proc.communicate())
    raise AssertionError(('No menu drawn', proc.poll(), data))


def active():
    return tmux('display-message', '-p', '-t', session, '#{window_id}')


def choose(proc, key, expected):
    os.write(master, key.encode())
    try:
        wait_for(lambda: active() == expected, 'Wrong selected window: ' + key)
    except AssertionError:
        print('DEBUG expected', expected, 'actual', active(), 'exit', proc.poll())
        print('DEBUG terminal', drain())
        print('DEBUG messages', tmux('show-messages'))
        raise
    proc.wait(timeout=4)
    assert proc.returncode == 0, proc.communicate()
    drain(.1)


def windows():
    result = []
    for row in tmux('list-windows', '-t', session, '-F',
                    '#{window_id}\t#{window_index}\t#{window_active}\t#{window_stack_index}').splitlines():
        wid, index, selected, rank = row.split('\t')
        result.append(picker.Window(wid, int(index), selected == '1', int(rank), 'test'))
    return result


try:
    tmux('-f', '/dev/null', 'new-session', '-d', '-s', 'picker', '-x', '95', '-y', '53',
         'sleep 180')
    session = tmux('display-message', '-p', '-t', 'picker', '#{session_id}')
    tmux('set-option', '-g', 'status', 'off')
    tmux('set-option', '-g', 'escape-time', '0')
    for i in range(1, 28):
        tmux('new-window', '-d', '-t', f'picker:{i}', '-n', f'Window-{i:02}', 'sleep 180')
    tmux('select-window', '-t', 'picker:11')
    recent = active()
    tmux('select-window', '-t', 'picker:0')
    original = active()
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 53, 95, 0, 0))
    client = subprocess.Popen(TMUX + ['attach-session', '-t', 'picker'], env=env,
                              stdin=slave, stdout=slave, stderr=slave,
                              start_new_session=True)
    os.close(slave)
    wait_for(lambda: bool(tmux('list-clients', '-F', '#{client_name}')), 'Client not attached')
    client_name = tmux('list-clients', '-F', '#{client_name}')
    proc, data = open_menu()
    assert b'Window-27' in data and b'Window-01' in data, data
    assert b'(a)' in data and b'(0)' in data, data
    choose(proc, 'a', recent)
    print('PASS: 28 windows visible; one key selects index 11, dismissing menu')

    for key in (';', '0'):
        entries, _, _ = picker.make_menu(windows(), 53)
        expected = next(w.id for _, k, w in entries if k == key)
        proc, _ = open_menu()
        choose(proc, key, expected)
    print('PASS: semicolon hint and current-window hint')

    before = active()
    proc, _ = open_menu()
    os.write(master, b'\x1b')
    proc.wait(timeout=4)
    assert active() == before
    print('PASS: Escape cancels without switching')

    # Exercise both tmux format and style quoting, delimiters, Unicode, and shell text.
    hostile = "literal #{window_id} #[fg=red] #(false) $HOME ' ; 窓\tX\nY"
    tmux('rename-window', '-t', 'picker:27', hostile.replace('#', '##') + r'\;')
    proc, data = open_menu('index')
    assert b'#{window_id}' in data and b'#[fg=red]' in data and b'#(false)' in data, data
    assert '窓'.encode() in data, data
    assert b'Y;' in data, data
    os.write(master, b'q')
    proc.wait(timeout=4)
    print('PASS: literal format/style/shell-like names, Unicode, tabs and newline')

    # Immutable ID selection after renumbering while the menu remains open.
    entries, _, _ = picker.make_menu(windows(), 53, order='index')
    label, key, win = next(e for e in entries if e[2].index == 20)
    proc, _ = open_menu('index')
    tmux('move-window', '-s', session + ':' + win.id, '-t', 'picker:100')
    choose(proc, key, win.id)
    print('PASS: index 100 and renumbering while menu is open')

    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
    os.kill(client.pid, signal.SIGWINCH)
    wait_for(lambda: tmux('list-clients', '-F', '#{client_height}') == '24', 'Resize missing')
    proc, data = open_menu('index')
    assert b'1/2' in data and b'Next page' in data, data
    os.write(master, b']')
    data = drain(.5)
    assert b'2/2' in data and b'Previous page' in data, data
    entries, _, _ = picker.make_menu(windows(), 24, 1, 'index')
    expected = next(w.id for _, k, w in entries if k == 'a')
    os.write(master, b'a')
    wait_for(lambda: active() == expected, 'Page 2 selection failed')
    print('PASS: short terminal pagination and single-key selection on second page')

    for i in range(28, 71):
        tmux('new-window', '-d', '-t', f'picker:{i}', '-n', 'duplicate', 'sleep 180')
    # No omissions, duplicate hints or collisions with navigation/current/cancel.
    items = windows()
    for height in (8, 24, 53, 100):
        seen = []
        _, _, pages = picker.make_menu(items, height)
        for page in range(pages):
            entries, _, _ = picker.make_menu(items, height, page)
            keys = [key for _, key, _ in entries]
            assert len(keys) == len(set(keys))
            assert not set(keys) & set('q[]')
            assert len(entries) + (6 if pages > 1 else 3) <= height
            seen.extend(w.id for _, key, w in entries if key != '0')
        assert len(seen) == len(set(seen)) == len(items) - 1
    proc, data = open_menu()
    assert b'1/5' in data, data
    os.write(master, b'q')
    proc.wait(timeout=4)
    print('PASS: 71 windows, duplicate names, complete paging at 8/24/53/100 rows')

    # Exercise the actual binding; substitute the checkout path for the install path.
    conf = (ROOT / 'tmux/window-picker.tmux').read_text().replace(
        '$HOME/byobu-extensions/bin/window-picker.py', str(SCRIPT))
    subprocess.run(TMUX + ['source-file', '-'], input=conf, text=True, env=env, check=True)
    tmux('set-option', '-g', 'prefix', 'C-a')
    tmux('set-option', '-g', 'prefix2', 'F12')
    drain(.1)
    os.write(master, b'\x01 ')
    data = drain(.5)
    assert b'Windows MRU' in data, data
    os.write(master, b'q')
    drain(.1)
    os.write(master, b'\x1b[24~ ')
    data = drain(.5)
    assert b'Windows MRU' in data, data
    os.write(master, b'q')
    print('PASS: actual config launches via Ctrl-A Space and F12 Space')
finally:
    try:
        tmux('kill-server')
    except subprocess.CalledProcessError:
        pass
    for proc in processes:
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
    if client:
        client.wait(timeout=3)
    if master is not None:
        os.close(master)
    TMP.cleanup()
