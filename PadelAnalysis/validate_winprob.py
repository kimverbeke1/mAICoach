"""
validate_winprob.py - toetst de winkans-formule af op ECHT GESPEELDE matchen.

PADEL_ANALYSIS_WINPROB_CALIBRATION_2026-09-22 (op verzoek van Kim: "ik zou de
winstkans formule willen aftoetsen op echt gespeelde matchen. Kan je dat bvb
eens doen voor alle recente matchen. Je mag enkel recente matchen gebruiken
want enkel daar is de padelstat score waarschijnlijk nog redelijk juist.")

WAT DIT SCRIPT DOET
-------------------
1. Leest alle matchen uit de players-collectie in Firestore.
2. Houdt enkel matchen over die (a) recent genoeg zijn (--days, standaard 120)
   en (b) waarvoor ALLE VIER de spelers een gekende sterkte hebben.
3. Berekent voor elke match de VOORSPELDE winkans met EXACT dezelfde functies
   die de app zelf gebruikt (lineup_lab.effective_simulation_rating +
   lineup_lab.estimate_win_probability) - het script dupliceert de formule
   bewust NIET, zodat wat je hier meet ook echt is wat de app doet.
4. Vergelijkt die voorspelling met de WERKELIJKE uitslag en rapporteert:
      - Brier score   (0 = perfect, 0.25 = even goed als altijd 50% gokken)
      - Log loss      (lager = beter)
      - Accuraatheid  (voorspelling >50% == gewonnen?)
      - Kalibratietabel per kansklasse: zegt het model 70%, wordt er dan ook
        ~70% gewonnen? Dit is de belangrijkste tabel.
      - Een geschatte, beter passende steilheid van de logistische curve.
5. Schrijft alle gebruikte matchen weg naar CSV, zodat je die kan doorsturen
   of zelf in Excel kan bekijken.

BELANGRIJK OVER DUBBELTELLING
-----------------------------
Eenzelfde dubbel staat in de database van ELKE speler die erin stond (tot 4x).
Het script ontdubbelt op (datum, set van 4 speler-ID's), zodat een match exact
1x meetelt - anders zou de statistiek er kunstmatig betrouwbaar uitzien.

GEBRUIK (PowerShell, vanuit de PadelAnalysis-map):
    python validate_winprob.py
    python validate_winprob.py --days 90
    python validate_winprob.py --days 180 --csv winprob_180d.csv
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).parent
for _p in [str(_ROOT), str(_ROOT / "scraper")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402
import lineup_lab as ll  # noqa: E402


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _parse_date(text):
    """Geeft een date-object terug, of None bij een onbekend formaat."""
    if not text:
        return None
    text = str(text).strip()
    for pattern, order in (
        (r"^(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"),
        (r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", "dmy"),
    ):
        m = re.match(pattern, text)
        if m:
            a, b, c = (int(m.group(i)) for i in (1, 2, 3))
            y, mo, d = (a, b, c) if order == "ymd" else (c, b, a)
            try:
                return datetime(y, mo, d).date()
            except ValueError:
                return None
    return None


_RATING_CACHE: dict = {}


def _rating(player_id):
    """Sterkte van 1 speler, met exact dezelfde voorrangsregels als de app:
    padelstats.be playing strength, anders het officiele klassement."""
    if not player_id:
        return None
    pid = str(player_id)
    if pid in _RATING_CACHE:
        return _RATING_CACHE[pid]

    padelstat = None
    try:
        cached = fb.get_padelstat_rating(pid)
        if cached and cached.get("rating") is not None:
            padelstat = float(cached["rating"])
    except Exception:
        pass

    official = None
    try:
        snapshot = fb.get_official_klassement_via_padelstat(pid) or {}
        if snapshot.get("klassement") is not None:
            official = float(snapshot["klassement"])
    except Exception:
        pass

    value = ll.effective_simulation_rating(
        pid,
        {pid: padelstat} if padelstat is not None else {},
        {pid: official} if official is not None else {},
    )
    _RATING_CACHE[pid] = value
    return value


def _parse_rank_text(value):
    """'P200' -> 200.0 (klassement van een tegenstander uit het matchrecord)."""
    m = re.search(r"(\d+)", str(value or ""))
    return float(m.group(1)) if m else None


# ─────────────────────────────────────────────
# Matchen verzamelen
# ─────────────────────────────────────────────
def collect_matches(cutoff_date):
    """Alle unieke, bruikbare matchen sinds cutoff_date."""
    try:
        docs = {d.id: (d.to_dict() or {}) for d in fb.db.collection(fb.PLAYERS_COLLECTION).stream()}
    except Exception as exc:
        print(f"Kon de spelersdata niet lezen: {exc}")
        return [], {}

    print(f"{len(docs)} spelersdocument(en) gelezen uit de database.")

    seen = set()
    rows = []
    skipped = defaultdict(int)

    for owner_id, doc in docs.items():
        for match in doc.get("matches") or []:
            if match.get("won") is None:
                skipped["geen uitslag"] += 1
                continue

            date = _parse_date(match.get("match_date"))
            if date is None:
                skipped["geen leesbare datum"] += 1
                continue
            if date < cutoff_date:
                skipped["te oud"] += 1
                continue

            partner_id = match.get("partner_user_id")
            opp1_id = match.get("opp1_user_id")
            opp2_id = match.get("opp2_user_id")
            if not (partner_id and opp1_id and opp2_id):
                skipped["onvolledige spelersgegevens"] += 1
                continue

            key = (str(date), frozenset(str(x) for x in (owner_id, partner_id, opp1_id, opp2_id)))
            if key in seen:
                continue
            seen.add(key)

            our = [_rating(owner_id), _rating(partner_id)]
            their = [_rating(opp1_id), _rating(opp2_id)]

            # Terugval op het klassement zoals het in het matchrecord zelf
            # staat - vaak het enige dat van een tegenstander gekend is.
            if their[0] is None:
                their[0] = _parse_rank_text(match.get("opp1_ranking"))
            if their[1] is None:
                their[1] = _parse_rank_text(match.get("opp2_ranking"))

            if any(v is None for v in our + their):
                skipped["geen sterkte voor alle 4 spelers"] += 1
                continue

            our_avg = sum(our) / 2
            their_avg = sum(their) / 2
            prob = ll.estimate_win_probability(our_avg, their_avg)
            if prob is None:
                skipped["winkans niet berekenbaar"] += 1
                continue

            rows.append({
                "datum": str(date),
                "type": match.get("match_type") or "",
                "speler": owner_id,
                "partner": str(partner_id),
                "tegenstander_1": str(opp1_id),
                "tegenstander_2": str(opp2_id),
                "onze_sterkte": round(our_avg, 1),
                "hun_sterkte": round(their_avg, 1),
                "verschil": round(our_avg - their_avg, 1),
                "voorspelde_winkans": round(prob, 4),
                "gewonnen": 1 if match.get("won") else 0,
                "score": match.get("score") or "",
            })

    return rows, skipped


# ─────────────────────────────────────────────
# Statistiek
# ─────────────────────────────────────────────
def _logistic(diff, scale):
    return 1.0 / (1.0 + math.exp(-diff / scale))


def _fit_scale(rows):
    """Zoekt de steilheid die de log loss minimaliseert. Puur informatief:
    het zegt of de huidige curve te vlak of te steil staat."""
    best_scale, best_loss = None, float("inf")
    for scale in [s / 2 for s in range(2, 401)]:
        loss = 0.0
        for r in rows:
            prob = min(max(_logistic(r["verschil"], scale), 1e-9), 1 - 1e-9)
            loss -= math.log(prob if r["gewonnen"] else 1 - prob)
        loss /= len(rows)
        if loss < best_loss:
            best_scale, best_loss = scale, loss
    return best_scale, best_loss


def report(rows):
    n = len(rows)
    print()
    print("=" * 64)
    print(f"WINKANS-FORMULE GETOETST OP {n} ECHT GESPEELDE MATCH(EN)")
    print("=" * 64)

    if n < 10:
        print("\nTe weinig matchen voor een zinvolle uitspraak (minimum ~10).")
        print("Probeer een ruimere periode, bv. --days 365.")
        return

    brier = sum((r["voorspelde_winkans"] - r["gewonnen"]) ** 2 for r in rows) / n
    logloss = -sum(
        math.log(min(max(r["voorspelde_winkans"], 1e-9), 1 - 1e-9) if r["gewonnen"]
                 else 1 - min(max(r["voorspelde_winkans"], 1e-9), 1 - 1e-9))
        for r in rows
    ) / n
    hits = sum(
        1 for r in rows
        if (r["voorspelde_winkans"] > 0.5) == bool(r["gewonnen"]) or r["voorspelde_winkans"] == 0.5
    )
    gemiddelde_voorspeld = sum(r["voorspelde_winkans"] for r in rows) / n
    werkelijk = sum(r["gewonnen"] for r in rows) / n

    print(f"\nBrier score        : {brier:.4f}   (0 = perfect, 0.25 = zo goed als muntstuk)")
    print(f"Log loss           : {logloss:.4f}   (lager is beter, 0.693 = muntstuk)")
    print(f"Accuraatheid       : {hits}/{n} = {100 * hits / n:.1f}%")
    print(f"Gemiddeld voorspeld: {100 * gemiddelde_voorspeld:.1f}% winkans")
    print(f"Werkelijk gewonnen : {100 * werkelijk:.1f}%")

    bias = gemiddelde_voorspeld - werkelijk
    if abs(bias) > 0.05:
        richting = "TE OPTIMISTISCH" if bias > 0 else "TE PESSIMISTISCH"
        print(f"  -> Het model is systematisch {richting} ({100 * abs(bias):.1f} procentpunt).")
    else:
        print("  -> Geen noemenswaardige systematische over- of onderschatting.")

    print("\nKALIBRATIE PER KANSKLASSE")
    print("Zegt het model 70%, wordt er dan ook ongeveer 70% gewonnen?\n")
    print(f"{'Voorspeld':<14}{'Matchen':>9}{'Gewonnen':>10}{'Werkelijk':>11}{'Afwijking':>11}")
    print("-" * 55)
    for low in range(0, 100, 10):
        high = low + 10
        bucket = [r for r in rows if low <= r["voorspelde_winkans"] * 100 < high]
        if not bucket:
            continue
        won = sum(r["gewonnen"] for r in bucket)
        actual = 100 * won / len(bucket)
        predicted = 100 * sum(r["voorspelde_winkans"] for r in bucket) / len(bucket)
        flag = "  <-- klein" if len(bucket) < 5 else ""
        print(f"{low:>3}-{high:<10}{len(bucket):>9}{won:>10}{actual:>10.0f}%"
              f"{actual - predicted:>+10.0f}pp{flag}")

    scale, fitted_loss = _fit_scale(rows)
    print(f"\nBEST PASSENDE STEILHEID: schaal {scale:.1f} (log loss {fitted_loss:.4f})")
    print("Een LAGERE schaal = uitgesprokener voorspellingen bij eenzelfde")
    print("sterkteverschil; een HOGERE schaal = voorzichtiger, dichter bij 50%.")
    if fitted_loss < logloss - 0.01:
        print(f"-> De huidige curve kan meetbaar beter: {logloss:.4f} -> {fitted_loss:.4f}.")
    else:
        print("-> De huidige curve zit al dicht bij het haalbare optimum.")

    print("\nLET OP: dit meet de formule EN de kwaliteit van de padelstat-cijfers")
    print("samen. Een zwak resultaat kan dus ook aan verouderde sterktes liggen.")


def main():
    parser = argparse.ArgumentParser(description="Toets de winkans-formule aan echte uitslagen.")
    parser.add_argument("--days", type=int, default=120,
                        help="Hoeveel dagen terug (standaard 120).")
    parser.add_argument("--csv", default="winprob_validatie.csv",
                        help="Bestandsnaam voor de CSV-export.")
    args = parser.parse_args()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).date()
    print(f"Matchen vanaf {cutoff} (laatste {args.days} dagen).\n")

    rows, skipped = collect_matches(cutoff)

    if skipped:
        print("\nOvergeslagen matchregels:")
        for reason, count in sorted(skipped.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>6}  {reason}")

    if not rows:
        print("\nGeen bruikbare matchen gevonden. Probeer een ruimere --days.")
        return

    rows.sort(key=lambda r: r["datum"])
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    report(rows)
    print(f"\nAlle {len(rows)} gebruikte matchen weggeschreven naar: {args.csv}")


if __name__ == "__main__":
    main()
