"""premiere: live bridge to a RUNNING Adobe Premiere Pro (25.6+, UXP), macOS and Windows.

    ea (CLI / premiere-mcp)  ──ws /client──►  hub (127.0.0.1:47821)  ◄──ws /premiere──  UXP panel in Premiere
                                                                                       (premiere_uxp/main.js)

- The panel (`premiere_uxp/`, installed once with `ea premiere install`) is a thin shell: it connects
  to the hub, runs requests one at a time and answers. The operations live in `premiere_uxp/lib.js`,
  sent at runtime (op "load") whenever its hash changes, so improving them never needs a reinstall.
- The hub is whichever `ea` process first binds the port (the MCP server while a Claude session is
  open, else the CLI command itself). Other processes connect to it as clients. When the hub process
  exits the panel reconnects to the next one (it retries every 2 s).
- Only this user's processes may drive Premiere: the hub listens on 127.0.0.1, refuses browser
  origins (a web page can reach localhost), and answers only a panel and clients that present the
  token in ~/.editassist/premiere-bridge.token (created 0600; `ea premiere install` writes the same
  value into the panel it packages).
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import secrets
import json
import os
import platform
import shutil
import socket
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

PORT = int(os.environ.get("EA_PREMIERE_PORT", "47821"))
HOST = "127.0.0.1"
PLUGIN_DIR = Path(__file__).parent / "premiere_uxp"
LIB_PATH = PLUGIN_DIR / "lib.js"
PLUGIN_ID = "com.editassist.premiere"
NO_PANEL = ("Premiere is not connected. Open Premiere Pro, then Window > UXP Plugins > editassist "
            "(install once with `uv run ea premiere install`).")


class BridgeError(RuntimeError):
    pass


def token_path() -> Path:
    return Path(os.environ.get("EA_PREMIERE_TOKEN_FILE") or Path.home() / ".editassist" / "premiere-bridge.token")


def token() -> str:
    """The shared secret of this machine's bridge (created on first use, readable by this user only)."""
    p = token_path()
    if p.exists():
        t = p.read_text(encoding="utf-8").strip()
        if t:
            return t
    p.parent.mkdir(parents=True, exist_ok=True)
    t = secrets.token_hex(24)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(t)
    return t


# ---------------------------------------------------------------------------------------------- hub

def browser_origin(origin: str | None) -> bool:
    """True for origins only a web browser sends (http/https pages, sandboxed/file pages = "null")."""
    if not origin:
        return False
    o = origin.strip().lower()
    return o == "null" or o.startswith(("http://", "https://"))


class Hub:
    """Routes client requests to the Premiere panel and the answers back."""

    def __init__(self, secret: str | None = None):
        self.secret = secret or token()
        self.plugin = None
        self.plugin_info: dict = {}
        self.plugin_origin: str | None = None
        self.plugin_ready = threading.Event()
        self.pending: dict[str, tuple[Any, Any]] = {}
        self.lock = threading.Lock()
        self.send_locks: dict[int, threading.Lock] = {}
        self.server = None

    def _send(self, ws, msg: dict) -> None:
        lock = self.send_locks.setdefault(id(ws), threading.Lock())
        with lock:
            ws.send(json.dumps(msg))

    def handler(self, ws) -> None:
        origin = ws.request.headers.get("Origin") if ws.request else None
        if browser_origin(origin):
            ws.close(1008, "browser origins are not allowed")
            return
        path = ws.request.path if ws.request else "/"
        try:
            if path.startswith("/premiere"):
                self._plugin_loop(ws, origin)
            else:
                self._client_loop(ws)
        except Exception:
            pass
        finally:
            self.send_locks.pop(id(ws), None)

    def _authorized(self, msg: dict) -> bool:
        return isinstance(msg.get("token"), str) and hmac.compare_digest(msg["token"], self.secret)

    def _plugin_loop(self, ws, origin) -> None:
        hello = json.loads(ws.recv(timeout=10))
        if hello.get("type") != "hello" or not self._authorized(hello):
            ws.close(1008, "bad token: reinstall the panel with `ea premiere install`")
            return
        self.plugin_info = hello.get("info") or {}
        with self.lock:
            old, self.plugin = self.plugin, ws
            self.plugin_origin = origin
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        self.plugin_ready.set()
        try:
            for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "hello":
                    self.plugin_info = msg.get("info") or {}
                    self.plugin_ready.set()
                    continue
                gid = msg.get("id")
                with self.lock:
                    target = self.pending.get(gid) if msg.get("type") == "event" else self.pending.pop(gid, None)
                if not target:
                    continue
                client, cid = target
                if msg.get("result") and isinstance(msg["result"], dict) and msg["result"].get("lib_hash"):
                    self.plugin_info["lib_hash"] = msg["result"]["lib_hash"]
                try:
                    self._send(client, {**msg, "id": cid})
                except Exception:
                    pass
        finally:
            with self.lock:
                if self.plugin is ws:
                    self.plugin = None
                    self.plugin_ready.clear()
                    lost = [k for k, (c, _) in self.pending.items()]
                    orphans = [self.pending.pop(k) for k in lost]
                else:
                    orphans = []
            for client, cid in orphans:
                try:
                    self._send(client, {"id": cid, "ok": False, "error": "Premiere disconnected during the request"})
                except Exception:
                    pass

    def status(self) -> dict:
        return {"hub_pid": os.getpid(), "port": PORT, "connected": self.plugin is not None,
                "premiere": self.plugin_info if self.plugin is not None else None,
                "plugin_origin": self.plugin_origin}

    def _client_loop(self, ws) -> None:
        for raw in ws:
            msg = json.loads(raw)
            cid = msg.get("id")
            if not self._authorized(msg):
                self._send(ws, {"id": cid, "ok": False, "code": "AUTH", "error": "bad or missing token"})
                continue
            msg.pop("token", None)
            if msg.get("op") == "_status":
                self._send(ws, {"id": cid, "ok": True, "result": self.status()})
                continue
            wait = float(msg.pop("wait", 0) or 0)
            if self.plugin is None and wait > 0:
                self.plugin_ready.wait(wait)
            plugin = self.plugin
            if plugin is None:
                self._send(ws, {"id": cid, "ok": False, "code": "NO_PANEL", "error": NO_PANEL})
                continue
            gid = uuid.uuid4().hex
            with self.lock:
                self.pending[gid] = (ws, cid)
            try:
                self._send(plugin, {**msg, "id": gid})
            except Exception as e:
                with self.lock:
                    self.pending.pop(gid, None)
                self._send(ws, {"id": cid, "ok": False, "error": f"could not reach Premiere: {e}"})

    def start(self) -> bool:
        """Bind the port in a daemon thread; False when another process already holds it."""
        from websockets.sync.server import serve
        try:
            self.server = serve(self.handler, HOST, PORT, max_size=64 * 2**20, ping_interval=20,
                                ping_timeout=60)
        except OSError:
            return False
        threading.Thread(target=self.server.serve_forever, daemon=True, name="premiere-hub").start()
        return True


_hub: Hub | None = None
_hub_lock = threading.Lock()


def port_open(timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_hub() -> Hub | None:
    """Start a hub in this process unless one already runs (here or in another process)."""
    global _hub
    with _hub_lock:
        if _hub is not None:
            return _hub
        if port_open():
            return None
        hub = Hub()
        if hub.start():
            _hub = hub
            return hub
        return None  # lost the race: someone else bound it


# ------------------------------------------------------------------------------------------- client

def lib_source() -> tuple[str, str]:
    src = LIB_PATH.read_text(encoding="utf-8")
    return src, hashlib.sha256(src.encode()).hexdigest()[:16]


_ids = itertools.count(1)


def _request(msg: dict, timeout: float, on_event: Callable[[dict], None] | None) -> dict:
    from websockets.sync.client import connect
    ensure_hub()
    msg = {**msg, "id": f"c{os.getpid()}-{next(_ids)}", "token": token()}
    try:
        ws = connect(f"ws://{HOST}:{PORT}/client", max_size=64 * 2**20, open_timeout=5,
                     ping_interval=None)
    except OSError as e:
        raise BridgeError(f"cannot reach the premiere hub on {HOST}:{PORT}: {e}") from e
    with ws:
        ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise BridgeError(f"Premiere did not answer '{msg.get('op')}' within {timeout:.0f} s "
                                  "(it may still be working; check the editassist panel)")
            try:
                reply = json.loads(ws.recv(timeout=left))
            except TimeoutError:
                continue
            if reply.get("type") == "event":
                if on_event:
                    on_event(reply)
                continue
            if reply.get("id") == msg["id"]:
                return reply


def status(wait: float = 0) -> dict:
    reply = _request({"op": "_status"}, 10, None)
    st = reply["result"]
    if not st["connected"] and wait > 0:
        try:
            st["premiere"] = call("ping", wait=wait, timeout=wait + 10)
            st["connected"] = True
        except BridgeError:
            pass
    return st


def call(op: str, args: dict | None = None, *, timeout: float = 300, wait: float = 15,
         on_event: Callable[[dict], None] | None = None) -> Any:
    """Run one operation in Premiere and return its result (raises BridgeError on failure)."""
    src, h = lib_source() if LIB_PATH.exists() else ("", None)
    msg = {"op": op, "args": args or {}, "lib_hash": h, "wait": wait}
    for _ in range(2):
        reply = _request(msg, timeout, on_event)
        if reply.get("ok"):
            return reply.get("result")
        if reply.get("code") == "NEED_LIB" and src:
            loaded = _request({"op": "load", "args": {"source": src, "hash": h}, "wait": wait}, 60, None)
            if not loaded.get("ok"):
                raise BridgeError("could not load lib.js in Premiere: " + str(loaded.get("error")))
            continue
        raise BridgeError(str(reply.get("error") or reply))
    raise BridgeError("lib.js did not stay loaded in Premiere")


def exec_js(code: str, args: dict | None = None, *, timeout: float = 300) -> Any:
    """Run an async JS function body inside Premiere: `ppro`, `lib`, `args`, `ctx`, `uxp` in scope."""
    return call("exec", {"code": code, "args": args or {}}, timeout=timeout)


def flatten(path: Path) -> Path:
    """Premiere's frame PNGs carry alpha (a fade-in is transparent, not dark): composite over black so
    the picture is what a viewer sees."""
    from PIL import Image

    im = Image.open(path)
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:
        rgba = im.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        Image.alpha_composite(bg, rgba).convert("RGB").save(path)
    return path


def frame(time_s: float, path: Path, width: int = 960, sequence: str | None = None, timeout: float = 30) -> Path:
    """Render the sequence frame at `time_s` to `path` (png). Premiere's exportSequenceFrame returns before
    the file is on disk (26.3): wait until it exists and its size stops changing."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    call("frame", {"time": time_s, "path": str(path), "width": width, "sequence": sequence})
    deadline, last = time.time() + timeout, -1
    while time.time() < deadline:
        hits = [path] if path.exists() else sorted(path.parent.glob(path.stem + "*"))
        if hits:
            size = hits[0].stat().st_size
            if size and size == last:
                return flatten(hits[0])
            last = size
        time.sleep(0.25)
    raise BridgeError(f"Premiere did not write the frame {path.name} within {timeout:.0f} s")


def premiere_dirs() -> list[Path]:
    """Install folders of Premiere Pro (newest first): the .app Contents on macOS, the program folder on Windows."""
    system = platform.system()
    if system == "Darwin":
        found = [Path(p) / "Contents" for p in Path("/Applications").glob("Adobe Premiere Pro*/Adobe Premiere Pro*.app")]
    elif system == "Windows":
        base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Adobe"
        found = list(base.glob("Adobe Premiere Pro*"))
    else:
        found = []
    return sorted(found, key=lambda p: p.as_posix(), reverse=True)


H264 = "4E49434B_48323634"  # Premiere's H.264 system preset folder


def default_preset() -> Path | None:
    """Premiere's own "Match Source - High bitrate" H.264 preset (the File > Export default)."""
    for d in premiere_dirs():
        folder = d / "MediaIO" / "systempresets" / H264
        hits = sorted(folder.glob("*Match Source - High bitrate.epr"))
        if hits:
            return hits[0]
    return None


def export(path: Path, sequence: str | None = None, preset: str | None = None, mode: str = "now",
           timeout: float = 3600) -> dict:
    """Render a sequence to `path` with an encoder preset (.epr; default Match Source - High bitrate H.264).
    mode "now" renders inside Premiere and returns once the file is complete; "queue" / "ame" only queue it."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    epr = Path(preset) if preset else default_preset()
    if not epr or not epr.exists():
        raise BridgeError(f"no export preset {'at ' + str(preset) if preset else 'found'}: pass preset (an .epr from "
                          "File > Export > Media > Preset > Save, or Premiere's MediaIO/systempresets)")
    if mode == "now" and path.exists():
        path.unlink()
    res = call("export", {"sequence": sequence, "path": str(path), "preset": str(epr), "mode": mode},
               timeout=timeout)
    if mode != "now":
        return {**res, "preset": str(epr)}
    deadline, last = time.time() + timeout, -1
    while time.time() < deadline:  # the encoder may still be flushing when the call returns
        if path.exists():
            size = path.stat().st_size
            if size and size == last:
                return {**res, "path": str(path), "bytes": size, "preset": str(epr)}
            last = size
        time.sleep(0.5)
    raise BridgeError(f"Premiere did not finish writing {path.name} within {timeout:.0f} s")


# ------------------------------------------------------------------------------------------ install

def installer_path() -> Path | None:
    system = platform.system()
    if system == "Darwin":
        p = Path("/Library/Application Support/Adobe/Adobe Desktop Common/RemoteComponents/UPI/"
                 "UnifiedPluginInstallerAgent/UnifiedPluginInstallerAgent.app/Contents/MacOS/"
                 "UnifiedPluginInstallerAgent")
    elif system == "Windows":
        base = Path(os.environ.get("CommonProgramFiles", r"C:\Program Files\Common Files"))
        p = base / "Adobe" / "Adobe Desktop Common" / "RemoteComponents" / "UPI" / \
            "UnifiedPluginInstallerAgent" / "UnifiedPluginInstallerAgent.exe"
    else:
        return None
    return p if p.exists() else None


def plugin_version() -> str:
    return json.loads((PLUGIN_DIR / "manifest.json").read_text())["version"]


def build_ccx(out_dir: Path) -> Path:
    """Package the panel as a .ccx (a zip with manifest.json at its root). lib.js is not inside:
    it is sent at runtime."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"editassist-premiere-{plugin_version()}.ccx"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("manifest.json", "index.html", "main.js"):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            data = (PLUGIN_DIR / name).read_bytes()
            if name == "main.js":
                data = data.replace(b"__EA_TOKEN__", token().encode())
                data = data.replace(b"const PORT = 47821;", f"const PORT = {PORT};".encode())
            z.writestr(info, data)
    return out


def install(out_dir: Path) -> dict:
    ccx = build_ccx(out_dir)
    upia = installer_path()
    if not upia:
        return {"installed": False, "ccx": str(ccx),
                "next": "Adobe's plugin installer was not found: double-click the .ccx (Creative Cloud "
                        "installs it), or load the folder in UXP Developer Tool."}
    r = subprocess.run([str(upia), "--install", str(ccx)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    out = (r.stdout + r.stderr).strip()
    ok = r.returncode == 0 and "fail" not in out.lower()
    return {"installed": ok, "ccx": str(ccx), "installer_output": out[-1500:],
            "next": "Restart Premiere Pro, then Window > UXP Plugins > editassist (dock it anywhere)."
            if ok else "Install failed: see installer_output."}


def installed() -> dict:
    upia = installer_path()
    if not upia:
        return {"checked": False}
    r = subprocess.run([str(upia), "--list", "all"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    text = r.stdout + r.stderr
    return {"checked": True, "installed": "editassist" in text or PLUGIN_ID in text}


def doctor() -> dict:
    """Short status for `ea doctor`: never blocks on Premiere."""
    st = {"installer": bool(installer_path()), "hub_running": port_open()}
    if st["hub_running"]:
        try:
            s = status()
            st["connected"] = s["connected"]
            if s.get("premiere"):
                st["premiere_version"] = s["premiere"].get("version")
        except BridgeError:
            pass
    return st


def serve_forever() -> None:
    """`ea premiere hub`: keep a hub alive in the foreground (useful without an MCP session)."""
    hub = ensure_hub()
    if hub is None:
        raise SystemExit(f"a premiere hub is already running on {HOST}:{PORT}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


__all__ = ["call", "exec_js", "export", "default_preset", "status", "install", "installed", "build_ccx", "doctor", "BridgeError",
           "Hub", "browser_origin", "ensure_hub", "serve_forever", "shutil"]
