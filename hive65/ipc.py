"""Local control channel between the CLI (or Hyprland keybinds) and the running app.

JSON lines over 127.0.0.1. A random token in the settings folder keeps other
local users' processes out.
"""
import json
import secrets
import socket
import socketserver
import threading

from .settings import config_dir

PORT = 47265
TOKEN_FILE = config_dir() / "ipc.token"


def _token(create=False):
    if create:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tok = secrets.token_hex(16)
        TOKEN_FILE.write_text(tok)
        return tok
    try:
        return TOKEN_FILE.read_text().strip()
    except OSError:
        return None


class Server:
    """Runs handler(request_dict) -> response_dict for each client line."""

    def __init__(self, handler):
        token = _token(create=True)

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    try:
                        req = json.loads(line)
                        if req.pop("token", None) != token:
                            resp = {"ok": False, "error": "bad token"}
                        else:
                            resp = handler(req) or {"ok": True}
                    except Exception as e:
                        resp = {"ok": False, "error": str(e)}
                    self.wfile.write((json.dumps(resp) + "\n").encode())

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def send(request, timeout=1.0):
    """Send a request to the running app. Returns the response, or None if not running."""
    token = _token()
    if not token:
        return None
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=timeout) as s:
            s.sendall((json.dumps(dict(request, token=token)) + "\n").encode())
            data = s.makefile().readline()
            return json.loads(data) if data else None
    except OSError:
        return None
