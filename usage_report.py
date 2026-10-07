# -*- coding: utf-8 -*-
"""usage_report.py - lokaal rapport over de verborgen gebruiksstatistieken.

Gebruik (vanuit de repo-root, met firebase-key.json beschikbaar):
    python usage_report.py            # laatste 30 dagen
    python usage_report.py 7          # laatste 7 dagen
"""
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / "PadelAnalysis"))
import firebase_service  # noqa: E402

db = firebase_service.db
days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
since = datetime.now(timezone.utc) - timedelta(days=days)

sessions = [d.to_dict() for d in db.collection("_admin_sessions").where("started_at", ">=", since).stream()]
logs = [d.to_dict() for d in db.collection("_admin_usage_logs").where("timestamp", ">=", since).stream()]

print(f"\n=== Gebruik laatste {days} dagen ===")
print(f"Sessies: {len(sessions)}")
durations = [s.get("duration_sec", 0) for s in sessions]
if durations:
    print(f"Gem. sessieduur: {statistics.mean(durations) / 60:.1f} min | mediaan: {statistics.median(durations) / 60:.1f} min")

per_day = defaultdict(int)
for s in sessions:
    per_day[s["started_at"].astimezone().strftime("%Y-%m-%d")] += 1
print("\nSessies per dag:")
for day in sorted(per_day):
    print(f"  {day}: {per_day[day]}")

print("\nPopulairste pagina's (paginaweergaven):")
for (app, page), n in Counter((l.get("app"), l.get("page")) for l in logs).most_common(15):
    print(f"  {n:5d}  {app} - {page}")
