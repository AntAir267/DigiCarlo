"""Asking Syncthing how the library is getting to the phone.

Syncthing answers on a small web service on this machine, and its key is in
its config file, which only the user it runs as can read -- the same user
DigiCarlo runs as. From that DigiCarlo finds the Syncthing folder the library
is in, which devices share it, whether each is connected, and how much of the
folder each still needs. After putting pictures in the library it asks
Syncthing to look at the folder straight away, so they go now rather than at
its next scheduled scan.

Nothing here changes Syncthing's settings.
"""

import datetime
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Where Syncthing keeps its config, most specific first: SyncThingy (a
# Flatpak), then Syncthing's own locations, old and new, and the snap.
CONFIGS = [
    "~/.var/app/com.github.zocker_160.SyncThingy/.local/state/syncthing/config.xml",
    "~/.local/state/syncthing/config.xml",
    "~/.config/syncthing/config.xml",
    "~/snap/syncthing/common/.config/syncthing/config.xml",
]
TIMEOUT = 5


class SyncthingError(RuntimeError):
    pass


class Config:
    def __init__(self, path):
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as exc:
            raise SyncthingError("cannot read %s: %s" % (path, exc))
        gui = root.find("gui")
        if gui is None or not gui.findtext("apikey"):
            raise SyncthingError("%s has no GUI address or API key" % path)
        self.path = path
        self.key = gui.findtext("apikey").strip()
        address = (gui.findtext("address") or "127.0.0.1:8384").strip()
        host, _, port = address.rpartition(":")
        if host in ("", "0.0.0.0", "[::]", "::"):
            host = "127.0.0.1"
        tls = (gui.get("tls") or "").lower() == "true"
        self.url = "%s://%s:%s" % ("https" if tls else "http", host, port)
        self.devices = {d.get("id"): d.get("name") or d.get("id")[:7]
                        for d in root.findall("device")}
        self.folders = []
        for f in root.findall("folder"):
            self.folders.append({
                "id": f.get("id"),
                "label": f.get("label") or f.get("id"),
                "path": os.path.abspath(os.path.expanduser(f.get("path") or "")),
                "devices": [d.get("id") for d in f.findall("device")],
            })

    def folder_for(self, path):
        """The shared folder holding `path`, the deepest if they nest."""
        path = os.path.abspath(os.path.expanduser(path))
        best = None
        for f in self.folders:
            if path == f["path"] or path.startswith(f["path"].rstrip(os.sep) + os.sep):
                if best is None or len(f["path"]) > len(best["path"]):
                    best = f
        return best


def find_config(candidates=None):
    for c in candidates or CONFIGS:
        path = os.path.expanduser(c)
        if os.path.isfile(path):
            return Config(path)
    return None


class Client:
    def __init__(self, config):
        self.config = config
        self._ctx = None
        if config.url.startswith("https:"):
            # Syncthing's GUI certificate is self-signed, and this only ever
            # talks to this machine.
            self._ctx = ssl.create_default_context()
            self._ctx.check_hostname = False
            self._ctx.verify_mode = ssl.CERT_NONE

    def _call(self, method, path, params):
        url = self.config.url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method=method,
                                     headers={"X-API-Key": self.config.key})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=self._ctx) as r:
                body = r.read()
        except urllib.error.HTTPError as exc:
            exc.close()
            raise SyncthingError("Syncthing said %s to %s" % (exc.code, path))
        except (urllib.error.URLError, OSError) as exc:
            raise SyncthingError("Syncthing is not answering at %s (%s)"
                                 % (self.config.url, getattr(exc, "reason", exc)))
        return json.loads(body) if body.strip() else None

    def get(self, path, **params):
        return self._call("GET", path, params)

    def post(self, path, **params):
        return self._call("POST", path, params)


class Peer:
    def __init__(self, ident, name):
        self.id = ident
        self.name = name
        self.connected = False
        self.last_seen = None           # datetime, local time
        self.completion = None          # percent of the folder it has
        self.need_items = 0
        self.need_bytes = 0


class Status:
    def __init__(self):
        self.folder = None              # label
        self.path = None
        self.state = None               # idle, scanning, syncing...
        self.files = 0
        self.bytes = 0
        self.errors = 0
        self.peers = []


def _when(text):
    if not text or text.startswith("1970"):
        return None
    try:
        dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone().replace(tzinfo=None)


def library_status(library, config=None, client=None):
    """How the Syncthing folder holding `library` stands; None when
    Syncthing is not set up here, or does not share the library."""
    config = config or find_config()
    if config is None:
        return None
    folder = config.folder_for(library)
    if folder is None:
        return None
    client = client or Client(config)
    st = Status()
    st.folder, st.path = folder["label"], folder["path"]
    me = client.get("/rest/system/status").get("myID")
    fs = client.get("/rest/db/status", folder=folder["id"]) or {}
    st.state = fs.get("state")
    st.files = int(fs.get("localFiles") or 0)
    st.bytes = int(fs.get("localBytes") or 0)
    st.errors = int(fs.get("errors") or 0) + int(fs.get("pullErrors") or 0)
    conns = (client.get("/rest/system/connections") or {}).get("connections", {})
    seen = client.get("/rest/stats/device") or {}
    for dev in folder["devices"]:
        if dev == me:
            continue
        peer = Peer(dev, config.devices.get(dev, dev[:7]))
        peer.connected = bool((conns.get(dev) or {}).get("connected"))
        peer.last_seen = _when((seen.get(dev) or {}).get("lastSeen"))
        comp = client.get("/rest/db/completion", folder=folder["id"], device=dev) or {}
        if "completion" in comp:
            peer.completion = float(comp["completion"])
        peer.need_items = int(comp.get("needItems") or 0)
        peer.need_bytes = int(comp.get("needBytes") or 0)
        st.peers.append(peer)
    return st


def rescan(library, config=None, client=None):
    """Ask Syncthing to look at the library's folder now. Says whether it
    was asked: False when Syncthing does not share the library."""
    config = config or find_config()
    if config is None:
        return False
    folder = config.folder_for(library)
    if folder is None:
        return False
    (client or Client(config)).post("/rest/db/scan", folder=folder["id"])
    return True
