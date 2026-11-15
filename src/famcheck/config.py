from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent.parent
FIXTURES_DIR = Path(os.environ.get("FAMCHECK_FIXTURES", REPO_ROOT / "fixtures"))
SAMPLE_INVOICES = FIXTURES_DIR / "invoices"
GOLDEN_DIR = FIXTURES_DIR / "golden"
SEED_REPLAY_DIR = FIXTURES_DIR / "replay"
USER_CACHE_DIR = Path(os.environ.get("FAMCHECK_CACHE", Path.cwd() / ".famcheck_cache" / "replay"))

MODES = ("auto", "replay", "live", "record")


def mode() -> str:
    m = os.environ.get("FAMCHECK_MODE", "auto")
    return m if m in MODES else "auto"


def passes() -> int:
    try:
        return max(1, int(os.environ.get("FAMCHECK_PASSES", "2")))
    except ValueError:
        return 2


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (no extra dependency). Never overrides real env vars."""
    p = path or (Path.cwd() / ".env")
    if not p.exists():
        p = REPO_ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
