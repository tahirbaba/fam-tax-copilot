"""Loads YAML rule packs and evaluates them. Rules are data (reviewable by the
tax team without reading code); checks are small pure functions in checks.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from famcheck.core.models import Finding, Impact, Severity
from famcheck.rules.checks import CONDITIONS, REGISTRY, RuleInput

PACK_DIR = Path(__file__).parent / "packs"
PACK_ORDER = ("vat_tax_invoice", "arithmetic", "review_guardrails", "einvoicing_readiness")


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "—"


@dataclass
class Rule:
    id: str
    pack: str
    check: str
    severity: Severity
    impact: Impact
    title_en: str
    title_ar: str
    message_en: str
    message_ar: str
    citation: str | None = None
    params: dict = field(default_factory=dict)
    when: str = "always"
    field: str | None = None

    def make_finding(self, v: dict[str, Any]) -> Finding:
        vars_ = _SafeDict(v)
        return Finding(
            rule_id=self.id,
            pack=self.pack,
            severity=self.severity,
            impact=self.impact,
            title_en=self.title_en,
            title_ar=self.title_ar,
            message_en=self.message_en.format_map(vars_),
            message_ar=self.message_ar.format_map(vars_),
            citation=self.citation,
            field=v.get("field") or self.field,
        )


@dataclass
class Pack:
    pack: str
    title_en: str
    title_ar: str
    version: str
    reviewed_by: str | None
    rules: list[Rule]

    def meta(self) -> dict[str, Any]:
        return {
            "pack": self.pack, "title_en": self.title_en, "title_ar": self.title_ar,
            "version": self.version, "reviewed_by": self.reviewed_by, "rule_count": len(self.rules),
        }


def _load_pack(path: Path) -> Pack:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = []
    for r in data["rules"]:
        if r["check"] not in REGISTRY:
            raise ValueError(f"{path.name}: rule {r['id']} uses unknown check {r['check']!r}")
        if r.get("when", "always") not in CONDITIONS:
            raise ValueError(f"{path.name}: rule {r['id']} uses unknown condition {r.get('when')!r}")
        rules.append(Rule(
            id=r["id"], pack=data["pack"], check=r["check"],
            severity=Severity(r["severity"]), impact=Impact(r["impact"]),
            title_en=r["title_en"], title_ar=r["title_ar"],
            message_en=r["message_en"], message_ar=r["message_ar"],
            citation=r.get("citation"), params=r.get("params") or {},
            when=r.get("when", "always"), field=(r.get("params") or {}).get("field"),
        ))
    return Pack(
        pack=data["pack"], title_en=data["title_en"], title_ar=data["title_ar"],
        version=str(data.get("version", "")), reviewed_by=data.get("reviewed_by"), rules=rules,
    )


@lru_cache
def load_packs() -> tuple[Pack, ...]:
    packs = []
    for name in PACK_ORDER:
        packs.append(_load_pack(PACK_DIR / f"{name}.yaml"))
    ids = [r.id for p in packs for r in p.rules]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate rule ids: {sorted(dupes)}")
    return tuple(packs)


def rule_by_id(rule_id: str) -> Rule:
    for p in load_packs():
        for r in p.rules:
            if r.id == rule_id:
                return r
    raise KeyError(rule_id)


def evaluate(ri: RuleInput) -> list[Finding]:
    findings: list[Finding] = []
    for pack in load_packs():
        for rule in pack.rules:
            if not CONDITIONS[rule.when](ri):
                continue
            for violation in REGISTRY[rule.check](ri, rule.params):
                findings.append(rule.make_finding(violation))
    return findings
