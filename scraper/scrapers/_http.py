"""HTTP helper with a disk cache so scrapers are cheap to re-run.

Uses `curl` under the hood instead of `requests` — on some systems the
Python installation can't verify SSL certificates but the system `curl`
does so correctly. This sidesteps the issue without disabling verification.
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{h}.html"


def get(url: str, *, force: bool = False, sleep: float = 0.4, retries: int = 4) -> str:
    """GET with disk cache. Uses `curl` so TLS verification works out of the box.
    Raises on non-200. Retries on transient failures."""
    p = _cache_path(url)
    if p.exists() and not force:
        return p.read_text(encoding="utf-8", errors="replace")
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            res = subprocess.run(
                [
                    "curl",
                    "-sSL",
                    "--max-time", "60",
                    "-A", UA,
                    "-H", "Accept-Language: en-US,en;q=0.9",
                    "-w", "\nHTTPCODE:%{http_code}",
                    url,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            out = res.stdout or ""
            # Extract the trailing "\nHTTPCODE:XXX" we asked curl to append.
            tag = out.rfind("\nHTTPCODE:")
            if tag == -1:
                raise RuntimeError(f"curl failed for {url}: {res.stderr.strip()[:200]}")
            code = out[tag + len("\nHTTPCODE:"):].strip()
            body = out[:tag]
            if code != "200":
                raise RuntimeError(f"HTTP {code} for {url}")
            p.write_text(body, encoding="utf-8")
            if sleep:
                time.sleep(sleep)
            return body
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err  # type: ignore[misc]
