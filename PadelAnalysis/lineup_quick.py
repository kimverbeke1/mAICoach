from __future__ import annotations
import re
from typing import Optional
import pandas as pd
import player_inline_actions as pia
# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default
def _winrate_num(wins: int, losses: int) -> Optional[float]:
    known = wins + losses
    if known <= 0:
        return None
    return wins / known
def _pct(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{round(value * 100, 1)}%"
def _winrate_str(wins: int, losses: int) -> str:
    return _pct(_winrate_num(wins, losses))
def _parse_rank(value) -> Optional[int]:
    """Parse P100/P200/... to int.
    PADEL_ANALYSIS_RANK_DIRECTION_FIX_2026-09-14 (kritieke bugfix):
    BUG (opgelost): de docstring stond hier voorheen "Lower number means
    stronger ranking" - dat is het TEGENOVERGESTELDE van de projectbrede,
    bevestigde conventie (zie opponent_dossier.py: "HOE HOGER HET GETAL, HOE
    BETER"; lineup_lab.matchup_edge() kreeg exact dezelfde bugfix eerder al).
    Correct: HOGER GETAL = STERKER."""
    if value is None:
        return None
    m = re.search(r"(\d+)", str(value))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None
def _format_rank(avg_rank: Optional[float]) -> str:
    if avg_rank is None:
        return "-"
    return f"P{int(round(avg_rank / 50) * 50)}"
# PADEL_ANALYSIS_DATE_PARSE_FIX
# Zelfde robuuste datum-parser als in dashboard.py (elk bestand houdt zijn
# eigen kleine kopie, geen extra gedeelde module nodig voor deze ene
# helper-functie). Nodig omdat een platte string-sort op "match_date"
# datums door elkaar zet zodra het formaat niet toevallig ISO is (bv.
# dd/mm/jjjj: "01/12/2026" komt string-alfabetisch VOOR "15/01/2026",
# terwijl december net de meest recente maand is).
_DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}
def _parse_match_date(text) -> Optional[tuple]:
    if not text:
        return None
    text = str(text).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (y, mo, d)
    m = re.search(r"(\d{1,2})\s+([a-zA-Zàéè]+)\s+(\d{4})", text.lower())
    if m:
        mo = _DUTCH_MONTHS.get(m.group(2))
        if mo:
            return (int(m.group(3)), mo, int(m.group(1)))
    return None
def _match_date_key(m: dict) -> str:
    return str(m.get("match_date") or m.get("tournament_date_start") or "")
def _dedupe_match_key(m: dict) -> str:
    """Dedupe only within the selected player's own document.
    PADEL_ANALYSIS_MIXED_SAME_MATCH_ID_FIX_2026-09-12:
    BUG (opgelost): bij een mixed-interclubwedstrijd blijkt de scraper voor
    ÉÉN en dezelfde 'match_id' twee aparte matchrecords op te slaan - één met
    de ene partner (bv. 'Ide Carl') en één met de andere (bv. 'Gallant
    Anneleen') - beide met exact hetzelfde match_id en dezelfde datum. Dat is
    functioneel GEEN duplicaat (het zijn twee verschillende, geldige
    partner-registraties van dezelfde ontmoeting), maar de oude dedupe-sleutel
    gebruikte ENKEL match_id. Zodra het ene record (toevallig) eerder in de
    matchlijst stond, werd het andere - met een andere partner - foutief als
    duplicaat overgeslagen. Gevolg: die partner miste in de partneranalyse
    exact de matches waar dit gebeurde, wat een verkeerde (soms 0%) winrate
    opleverde ondanks correcte brondata.
    Fix: de partner (user_id, of anders naam) wordt mee opgenomen in de
    dedupe-sleutel. Zo blijven twee records met hetzelfde match_id maar een
    verschillende partner allebei behouden; enkel écht identieke records
    (zelfde match_id ÉN zelfde partner) worden nog gededupliceerd - bv. als
    een matchrecord ooit per ongeluk twee keer zou worden opgeslagen."""
    match_id = m.get("match_id")
    partner_key = m.get("partner_user_id") or m.get("partner_name") or ""
    if match_id:
        return f"match_id:{match_id}|partner:{partner_key}"
    parts = [
        m.get("match_date") or m.get("tournament_date_start") or "",
        m.get("period_label") or "",
        m.get("reeks_name") or "",
        m.get("round_text") or "",
        partner_key,
        m.get("opp1_name") or "",
        m.get("opp2_name") or "",
        m.get("score") or "",
    ]
    return "fallback:" + "|".join(str(x) for x in parts)
def _partner_general_wr(partner_pid: str, docs: dict) -> tuple[Optional[float], int, int, int]:
    """Return partner's overall winrate from scraped partner document, if available."""
    if not partner_pid:
        return None, 0, 0, 0
    doc = docs.get(str(partner_pid)) or {}
    matches = doc.get("matches", []) or []
    stats = doc.get("stats", {}) or {}
    total = _safe_int(stats.get("total_matches"), len(matches))
    if total <= 0 and len(matches) <= 0:
        return None, 0, 0, 0
    wins = _safe_int(stats.get("wins"))
    losses = _safe_int(stats.get("losses"))
    wr = _winrate_num(wins, losses)
    return wr, total or len(matches), wins, losses
# -----------------------------------------------------------------------------
# Kernlogica partneranalyse
# PADEL_ANALYSIS_MOVE_PARTNER_ANALYSIS_2026-09-10: Sectie 1 ("Snelle analyse"/
# Beschikbare spelersdata), Sectie 2 ("Recente interclub van <speler>") en de
# vroegere render_lineup_quick_results-wrapper zijn verwijderd: geen directe
# meerwaarde t.o.v. de rest van de app. De partneranalyse hieronder wordt nu
# via build_partner_analysis_df() aangeroepen vanuit het gedeelde
# spelersprofiel (dashboard._render_player_dashboard, tab 'Partners'),
# zichtbaar voor elke speler i.p.v. enkel bij Opstelling-analyse.
# -----------------------------------------------------------------------------
def _collect_partner_analysis_from_selected_doc(
    sel_doc: dict,
    docs: dict,
    profiles_lookup: Optional[dict] = None,
    match_type_filter: str = "Alle",
) -> pd.DataFrame:
    """
    Partner analysis based on selected player's own match list, enriched with
    scraped partner stats.
    PADEL_ANALYSIS_PARTNER_GROUPING_FIX (eerdere poging, onvolledig):
    Groepeerde op partner_user_id ALS die aanwezig was in het match-record,
    anders op de (genormaliseerde) naam - via resolve_player_id() PER MATCH
    aangeroepen. Dat loste het probleem niet volledig op.
    PADEL_ANALYSIS_PARTNER_GROUPING_FIX_V2_2026-09-12:
    Niet elk match-record van dezelfde partner heeft consequent een
    partner_user_id ingevuld. Als resolve_player_id() PER MATCH wordt
    aangeroepen, en de partner bovendien geen eigen player_profile heeft, dan
    kon dezelfde partner in TWEE aparte groepen terechtkomen ("id:..." vs
    "name:..."). Fix: EERST één canoniek ID per genormaliseerde partnernaam
    bepalen, PAS DAARNA groeperen.
    PADEL_ANALYSIS_MIXED_SAME_MATCH_ID_FIX_2026-09-12 (echte oorzaak van de
    aanhoudende 0%-winrate, ook na de vorige twee fixes):
    Bij mixed-interclubwedstrijden slaat de scraper voor ÉÉN match_id soms
    TWEE matchrecords op - één per partner. Deze functie dedupliceert matches
    via _dedupe_match_key() om te vermijden dat een tegenstander-scout-flow
    dezelfde match dubbel telt. Die sleutel gebruikte voorheen ENKEL
    match_id, dus het tweede record (andere partner, zelfde match_id) werd
    hier foutief als duplicaat overgeslagen. _dedupe_match_key() is gefixt om
    de partner mee te nemen in de sleutel (zie aldaar).
    PADEL_ANALYSIS_RANK_DIRECTION_FIX_2026-09-14 (kritieke bugfix, dit was de
    resterende, hardnekkige oorzaak van "Sterkste winst toont altijd P100" en
    een verkeerd-gerichte "W tegen P<=200"-kolom, gemeld door Kim):
    BUG (opgelost): deze functie ging er - net als de oude, foutieve
    parse_ranking-docstring in lineup_lab.py, ondertussen daar al gefixt -
    van uit dat een LAGER klassementsgetal een STERKERE tegenstander
    betekent. Concreet fout, allebei nu gecorrigeerd:
      1. "Sterkste winst" (best_win_rank) hield de LAAGSTE avg_match_rank
         onder de overwinningen bij ("< bucket['best_win_rank']"). Onder de
         correcte conventie (hoger = sterker) betekent dat: de winst tegen de
         ZWAKSTE tegenstander werd getoond als "sterkste winst" - het
         omgekeerde van de bedoeling. Omdat veel tegenstanders rond P100
         clusteren, verklaarde dit waarom deze kolom bijna altijd P100 toonde.
         Fix: nu wordt de HOOGSTE avg_match_rank onder de overwinningen
         bijgehouden ("> bucket['best_win_rank']").
      2. "sterke tegenstander"-drempel (strong_matches/strong_wins, kolom
         "W tegen P<=200") gebruikte "avg_match_rank <= 200" om een
         tegenstander als "sterk" te bestempelen - ook omgekeerd: een LAAG
         getal is een ZWAKKE tegenstander. Fix: drempel omgedraaid naar
         "avg_match_rank >= 200" (kolomlabel hieronder aangepast naar
         "W tegen P>=200" om dit ook zichtbaar te maken).
    "Gem. tegenstand" (avg_rank, gewoon een rekenkundig gemiddelde van alle
    tegenstander-ratings) had GEEN richtingsafhankelijke logica en was dus al
    correct - enkel de twee bovenstaande, expliciet vergelijkende berekeningen
    waren fout.
    """
    profiles_lookup = profiles_lookup or {}
    matches = [
        m for m in (sel_doc or {}).get("matches", []) or []
        if match_type_filter == "Alle" or m.get("match_type") == match_type_filter
    ]
    # Eerste doorloop: één canoniek ID per genormaliseerde partnernaam.
    name_to_canonical_id: dict[str, str] = {}
    for m in matches:
        partner_name = str(m.get("partner_name") or "").strip()
        if not partner_name:
            continue
        norm_name = pia._norm(partner_name)
        if norm_name in name_to_canonical_id:
            continue
        partner_pid_raw = str(m.get("partner_user_id") or "").strip()
        canonical = (
            pia.resolve_player_id(partner_name, profiles_lookup, partner_pid_raw)
            if profiles_lookup else partner_pid_raw
        )
        if canonical:
            name_to_canonical_id[norm_name] = canonical
    acc: dict[str, dict] = {}
    seen = set()
    for m in matches:
        partner_name = str(m.get("partner_name") or "").strip()
        partner_pid_raw = str(m.get("partner_user_id") or "").strip()
        if not partner_name and not partner_pid_raw:
            continue
        key = _dedupe_match_key(m)
        if key in seen:
            continue
        seen.add(key)
        norm_name = pia._norm(partner_name) if partner_name else ""
        # Gebruik het vooraf bepaalde, per-naam-consistente ID i.p.v. een
        # per-match resolutie, zodat groepering nooit meer uit elkaar valt.
        canonical_pid = name_to_canonical_id.get(norm_name) or partner_pid_raw
        partner_group = f"id:{canonical_pid}" if canonical_pid else f"name:{norm_name or partner_pid_raw}"
        bucket = acc.setdefault(partner_group, {
            "Partner": partner_name or canonical_pid or "Onbekende partner",
            "Partner ID": canonical_pid or partner_pid_raw,
            "Matches": 0,
            "W": 0,
            "V": 0,
            "Onbekend": 0,
            "rank_values": [],
            "strong_matches": 0,
            "strong_wins": 0,
            "best_win_rank": None,
            "last_dates": [],
            "last10": [],
            "interclub": 0,
            "tornooi": 0,
        })
        # Naam kan per match licht verschillen in schrijfwijze; bewaar de
        # langste/meest volledige variant als weergavenaam.
        if partner_name and len(partner_name) > len(bucket["Partner"] or ""):
            bucket["Partner"] = partner_name
        bucket["Matches"] += 1
        if m.get("match_type") == "interclub":
            bucket["interclub"] += 1
        elif m.get("match_type") == "tornooi":
            bucket["tornooi"] += 1
        if m.get("won") is True:
            bucket["W"] += 1
            won = True
        elif m.get("won") is False:
            bucket["V"] += 1
            won = False
        else:
            bucket["Onbekend"] += 1
            won = None
        ranks = [_parse_rank(m.get("opp1_ranking")), _parse_rank(m.get("opp2_ranking"))]
        ranks = [r for r in ranks if r is not None]
        if ranks:
            avg_match_rank = sum(ranks) / len(ranks)
            bucket["rank_values"].append(avg_match_rank)
            # PADEL_ANALYSIS_RANK_DIRECTION_FIX_2026-09-14: "sterk" = HOGER
            # getal (>=200), niet lager. Zie functiedocstring hierboven.
            if avg_match_rank >= 200:
                bucket["strong_matches"] += 1
                if won is True:
                    bucket["strong_wins"] += 1
            if won is True:
                # PADEL_ANALYSIS_RANK_DIRECTION_FIX_2026-09-14: "sterkste
                # winst" = winst tegen het HOOGSTE gemiddelde tegenstander-
                # klassement (was voorheen "<", dus het laagste - omgekeerd).
                if bucket["best_win_rank"] is None or avg_match_rank > bucket["best_win_rank"]:
                    bucket["best_win_rank"] = avg_match_rank
        date_key = _match_date_key(m)
        if date_key:
            bucket["last_dates"].append(date_key)
        if won is True:
            bucket["last10"].append((date_key, "W"))
        elif won is False:
            bucket["last10"].append((date_key, "V"))
    rows = []
    for data in acc.values():
        wins = data["W"]
        losses = data["V"]
        with_me_wr = _winrate_num(wins, losses)
        avg_rank = sum(data["rank_values"]) / len(data["rank_values"]) if data["rank_values"] else None
        partner_wr, partner_total, partner_w, partner_v = _partner_general_wr(data.get("Partner ID") or "", docs)
        delta = None
        if with_me_wr is not None and partner_wr is not None:
            delta = with_me_wr - partner_wr
        if data["last10"]:
            # PADEL_ANALYSIS_DATE_SORT_FIX: ook hier recentste-eerst via
            # echte datum-parse i.p.v. string-sort.
            recent = sorted(data["last10"], key=lambda x: _parse_match_date(x[0]) or (0, 0, 0), reverse=True)[:10]
            last10 = "".join(x[1] for x in recent)
        else:
            last10 = "-"
        strong = "-"
        if data["strong_matches"]:
            strong = f"{data['strong_wins']}/{data['strong_matches']}"
        matches_count = data["Matches"]
        reliability = "Laag"
        if matches_count >= 10:
            reliability = "Hoog"
        elif matches_count >= 4:
            reliability = "Middel"
        last_match_sorted = sorted(data["last_dates"], key=lambda d: _parse_match_date(d) or (0, 0, 0), reverse=True)
        rows.append({
            "Partner": data["Partner"],
            "Partner ID": data.get("Partner ID") or "",
            "Matches": matches_count,
            "W": wins,
            "V": losses,
            "Winrate met mij": _pct(with_me_wr),
            "Partner algemeen": _pct(partner_wr),
            "Partner matchen": partner_total if partner_total else "-",
            "Delta": _pct(delta) if delta is not None else "-",
            "Gem. tegenstand": _format_rank(avg_rank),
            "Sterkste winst": _format_rank(data["best_win_rank"]),
            "W tegen P>=200": strong,
            "Laatste 10": last10,
            "Laatste match": last_match_sorted[0] if last_match_sorted else "-",
            "Betrouwbaarheid": reliability,
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["_matches_sort"] = df["Matches"]
    df["_delta_sort"] = df["Delta"].apply(lambda x: float(str(x).replace("%", "")) if str(x).endswith("%") else -999)
    df = df.sort_values(["_matches_sort", "_delta_sort"], ascending=[False, False])
    return df.drop(columns=["_matches_sort", "_delta_sort"])
def build_partner_analysis_df(
    sel_doc: dict,
    docs: dict,
    profiles_lookup: Optional[dict] = None,
    match_type_filter: str = "Alle",
) -> pd.DataFrame:
    """Publieke wrapper rond _collect_partner_analysis_from_selected_doc().
    PADEL_ANALYSIS_MOVE_PARTNER_ANALYSIS_2026-09-10: toegevoegd zodat
    dashboard.py (tab 'Partners', gedeeld door 'Mijn profiel' en 'Spelers')
    dezelfde partneranalyse kan hergebruiken zonder de interne (onderstreepte)
    functienaam rechtstreeks te moeten aanspreken."""
    return _collect_partner_analysis_from_selected_doc(
        sel_doc, docs, profiles_lookup=profiles_lookup, match_type_filter=match_type_filter
    )
