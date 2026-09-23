"""Fetching a newer DigiCarlo from the GitHub releases.

The same approach as Blinky's: the .deb is checked against the SHA256SUMS
published beside it and refused on any mismatch, because installing a
package is root-level trust.
"""

import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request

from . import __version__

REPO = "AntAir267/DigiCarlo"
RELEASES_API = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES_PAGE = "https://github.com/%s/releases" % REPO


class UpdateError(RuntimeError):
    pass


def version_tuple(text):
    """'1.10-2' -> (1, 10, 2), so 1.10 sorts above 1.9."""
    parts = re.findall(r"\d+", text or "")
    return tuple(int(x) for x in parts) or (0,)


def http_get(url, accept=None, timeout=20, allow_404=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": "digicarlo/%s" % __version__,
        "Accept": accept or "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        # A repository with no releases answers 404; that is a normal state.
        if exc.code == 404 and allow_404:
            return None
        raise UpdateError("%s returned HTTP %s" % (url, exc.code))
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError("could not reach %s: %s"
                          % (url, getattr(exc, "reason", exc)))


def latest():
    """(version, release info) of the newest release, or (None, {})."""
    raw = http_get(RELEASES_API, allow_404=True)
    info = json.loads(raw.decode("utf-8")) if raw else {}
    tag = str(info.get("tag_name") or "").strip()
    return (tag.lstrip("v") or None), info


def newer(version):
    return version is not None and \
        version_tuple(version) > version_tuple(__version__)


def download(info, outdir=None):
    """Fetch the release's .deb, verify it, and return its path."""
    assets = {a.get("name"): a for a in info.get("assets") or []}
    deb = next((n for n in assets if n.endswith(".deb")), None)
    if deb is None:
        raise UpdateError("the release has no .deb attached; see %s"
                          % RELEASES_PAGE)
    data = http_get(assets[deb]["browser_download_url"],
                    accept="application/octet-stream", timeout=120)
    if "SHA256SUMS" not in assets:
        raise UpdateError("the release publishes no SHA256SUMS, so the "
                          "download cannot be verified; not using it")
    sums = http_get(assets["SHA256SUMS"]["browser_download_url"],
                    accept="application/octet-stream").decode("utf-8")
    want = None
    for line in sums.splitlines():
        bits = line.split()
        if len(bits) == 2 and bits[1].lstrip("*") == deb:
            want = bits[0]
    got = hashlib.sha256(data).hexdigest()
    if want is None:
        raise UpdateError("SHA256SUMS does not mention %s; refusing" % deb)
    if want != got:
        raise UpdateError("checksum mismatch for %s (published %s, got %s); "
                          "nothing was installed" % (deb, want, got))
    outdir = os.path.expanduser(outdir) if outdir else \
        tempfile.mkdtemp(prefix="digicarlo-update-")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, deb)
    with open(path + ".part", "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(path + ".part", path)
    return path
