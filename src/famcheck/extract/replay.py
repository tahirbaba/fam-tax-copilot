"""Replay cache: stores extractions keyed by the file's SHA-256.

Makes demos deterministic and offline (no API key, no network, same output every
run) and lets the golden-set evaluation be re-run for free. Each entry records
where it came from:

  "claude-opus-5-5"  -> recorded from a real Claude run (`famcheck record`)
  "seed"             -> hand-written ground truth shipped with the sample invoices,
                        so the demo works before an API key is configured
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from famcheck.core.models import ExtractedInvoice


class ReplayStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, sha256: str) -> Path:
        return self.root / f"{sha256}.json"

    def has(self, sha256: str) -> bool:
        return self._path(sha256).exists()

    def get(self, sha256: str) -> Optional[tuple[str, list[ExtractedInvoice]]]:
        p = self._path(sha256)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        passes = [ExtractedInvoice.model_validate(x) for x in data["passes"]]
        return data["source"], passes

    def put(self, sha256: str, source: str, passes: list[ExtractedInvoice], file_name: str = "") -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self._path(sha256)
        payload = {
            "file_name": file_name,
            "source": source,
            "passes": [x.model_dump() for x in passes],
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
