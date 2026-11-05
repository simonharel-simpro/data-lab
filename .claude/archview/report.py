#!/usr/bin/env python3
"""Summarise .claude/archview/usage.jsonl — ArchView adoption vs grep."""

import collections
import json
import sys
from pathlib import Path

log = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("usage.jsonl"))
if not log.exists():
    sys.exit(f"no usage log at {log} — run `archview enable-logging` first")

rows = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
cat = collections.Counter(r["category"] for r in rows)
arch, miss = cat.get("archview", 0), cat.get("missed", 0)
total = arch + miss
rate = (arch / total * 100) if total else 0.0

print(f"ArchView usage report - {log}  ({len(rows)} events)")
print(f"  archview calls : {arch}")
print(f"  missed (grep)  : {miss}")
print(f"  adoption       : {rate:.0f}%  ({arch}/{total} structural lookups via archview)")
print(f"  by tool        : {dict(collections.Counter(r['tool'] for r in rows))}")

missed = collections.Counter(r["detail"] for r in rows if r["category"] == "missed")
if missed:
    print("  top grep-style searches (candidates to replace with archview):")
    for detail, n in missed.most_common(10):
        print(f"    {n:>3}  {detail[:70]}")
