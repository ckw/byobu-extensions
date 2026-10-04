# Ctrl-A then Space, or F12 then Space, with the normal Byobu prefixes.
# This replaces prefix+Space's next-window action; prefix+n still goes next.
# Add --order index to the command below for numeric window order.
bind-key -T prefix Space run-shell -b 'python3 "$HOME/byobu-extensions/bin/window-picker.py" --socket #{q:socket_path} --client #{q:client_name} --session #{q:session_id}'
