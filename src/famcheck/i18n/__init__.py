"""Bilingual (English / Arabic) strings. All UI and report text comes from these
fixed files - the language model never writes user-facing text."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent
LANGS = ("en", "ar")


@lru_cache
def strings(lang: str) -> dict[str, str]:
    lang = lang if lang in LANGS else "en"
    return json.loads((_DIR / f"{lang}.json").read_text(encoding="utf-8"))


@lru_cache
def _fields() -> dict[str, list[str]]:
    return json.loads((_DIR / "fields.json").read_text(encoding="utf-8"))


def field_label(name: str, lang: str = "en") -> str:
    pair = _fields().get(name)
    if not pair:
        return name
    return pair[1] if lang == "ar" else pair[0]


_NOTES_AR = {
    "verified": "تم التحقق",
    "visual": "مقروءة من صورة",
    "unverified": "لم يُعثر على الدليل في نص المستند",
    "disputed": "تعارضت نتائج الاستخراج",
    "invalid": "لا يمكن تفسير القيمة",
    "absent": "غير موجودة",
}


def status_note_ar(status: str) -> str:
    return _NOTES_AR.get(status, status)
