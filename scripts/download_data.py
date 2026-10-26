"""Download datasets into the git-ignored data/ folder.

Sources and licences are recorded in DATA_SOURCES.md. URLs are resolved at runtime (the
Chinook release asset is looked up from the GitHub API) rather than hardcoded. Downloads are
idempotent: an existing file is left untouched.

Usage:
    python scripts/download_data.py --dataset chinook
    python scripts/download_data.py --dataset spider    # implemented in P5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

CHINOOK_RELEASE_API = "https://api.github.com/repos/lerocha/chinook-database/releases/latest"
CHINOOK_ASSET_NAME = "Chinook_Sqlite.sqlite"
USER_AGENT = "safe-db-mcp-downloader"


_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:  # noqa: S310 (pinned hosts)
        return resp.read()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def download_chinook() -> Path:
    """Fetch the latest Chinook_Sqlite.sqlite release asset. Idempotent."""
    dest = DATA_DIR / "chinook" / CHINOOK_ASSET_NAME
    if dest.exists():
        print(f"chinook: already present at {dest} ({dest.stat().st_size} bytes)")
        return dest

    print(f"chinook: resolving latest release from {CHINOOK_RELEASE_API}")
    release = json.loads(_get(CHINOOK_RELEASE_API))
    tag = release.get("tag_name", "?")
    asset = next((a for a in release["assets"] if a["name"] == CHINOOK_ASSET_NAME), None)
    if asset is None:
        raise SystemExit(f"chinook: asset {CHINOOK_ASSET_NAME!r} not found in release {tag}")

    url = asset["browser_download_url"]
    print(f"chinook: downloading {CHINOOK_ASSET_NAME} from release {tag}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_get(url))
    print(f"chinook: saved {dest} ({dest.stat().st_size} bytes)")
    print(f"chinook: sha256 {_sha256(dest)}")
    return dest


def download_spider() -> None:
    raise SystemExit(
        "spider download is implemented in P5 (Hugging Face mirror xlangai/spider). "
        "See DATA_SOURCES.md and DECISIONS.md."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["chinook", "spider", "all"], default="chinook")
    args = parser.parse_args(argv)

    if args.dataset in ("chinook", "all"):
        download_chinook()
    if args.dataset in ("spider", "all"):
        download_spider()
    return 0


if __name__ == "__main__":
    sys.exit(main())
