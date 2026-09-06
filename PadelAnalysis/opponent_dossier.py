"""
opponent_dossier.py — Volledig dossier van een individuele tegenstander,
opvraagbaar met één klik vanuit de Opstelling-analyse-pagina.

Toont:
  - Algemene stats (matches, W/V, winrate, tornooi/interclub-verdeling)
  - All-time high (beste ooit gekende) ranking, uit twee mogelijke bronnen:
      1. Als deze speler zelf een klassementshistoriek heeft laten scrapen
         (via de Klassement-tab): het beste (laagste) cijfer uit die
         officiële TVL-historiek.
      2. Anders, opportunistisch: het beste (laagste) cijfer dat ooit door
         ÉÉN van onze eigen spelers als tegenstander-ranking werd
         geregistreerd bij een match tegen deze speler.
  - Interclubmatchen "deze periode": matches van deze speler die tot
    dezelfde poule/schema-pagina behoren als de wedstrijd die je net aan
    het bekijken bent (reeks_url-match) — dus specifiek relevant voor de
    komende ontmoeting, niet zomaar "recente" matches.

LET OP (belangrijk onderscheid, zie ook PROJECT_MAP.md):
Dit bestand is NIET hetzelfde als opponent_scout.py.
  - opponent_scout.py    -> vindt de vorige opstelling van een tegenstander
                            (welke spelers stonden er, via het uitslagenblad)
                            + scrapet ontbrekende tegenstander-spelers.
                            Gebruikt in dashboard.py via `import opponent_scout as osc`.
  - opponent_dossier.py  -> dit bestand. Toont het volledige dossier van
                            ÉÉN specifieke tegenstander-speler (stats,
                            all-time high ranking, matchen deze periode).
                            Gebruikt in dashboard.py via `import opponent_dossier as od`.
Beide bestanden horen naast elkaar te bestaan met hun eigen, verschillende
inhoud -- als een van beide per ongeluk de inhoud van de andere bevat,
zal dashboard.py falen op een ontbrekende functienaam
(bv. AttributeError: module 'opponent_dossier' has no attribute
'render_opponent_dossier_button').
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd
import streamlit as st

import firebase_service as fb


def _parse_rank(value) -> Optional[int]:
    if value is None:
        return None
    m = re.search(r"(\d+)", str(value))
    return int(m.group(1)) if m else None


def _winrate_str(wins: int, losses: int) -> str:
    known = wins + losses
    if known <= 0:
        return "-"
    return f"{round(wins / known * 100, 1)}%"


def _best_rank_from_klassement_history(doc: dict) -> Optional[int]:
    hist = (doc or {}).get("klassement_history") or {}
    history = hist.get("history") or []
    best = None
    for row in history:
        val = _parse_rank(
            row.get("klassement") or row.get("begin_klassement")
            or row.get("vorig") or row.get("vorig_klassement")
        )
        if val is not None and (best is None or val < best):
            best = val
    return best


def _best_rank_opportunistic(player_id: str, all_docs: dict) -> Optional[int]:
    """Doorzoekt ALLE bekende matchlijsten (van al onze gescrapete spelers)
    naar een moment waarop deze speler als tegenstander optrad, en neemt het
    beste (laagste) daar geregistreerde klassementscijfer."""
    best = None
    for doc in all_docs.values():
        for m in (doc or {}).get("matches", []) or []:
            if str(m.get("opp1_user_id")) == str(player_id):
                val = _parse_rank(m.get("opp1_ranking"))
            elif str(m.get("opp2_user_id")) == str(player_id):
                val = _parse_rank(m.get("opp2_ranking"))
            else:
                continue
            if val is not None and (best is None or val < best):
                best = val
    return best


def render_opponent_dossier(
    player_id: str,
    name: str,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    key_prefix: str = "opp_dossier",
) -> None:
    """Rendert het volledige dossier van één tegenstander in een expander."""
    doc = fb.get_player(player_id) or all_docs.get(str(player_id))

    if not doc:
        st.caption(f"Nog geen matchdata gekend voor {name}. Scrape deze speler eerst.")
        return

    matches = doc.get("matches", []) or []
    stats = doc.get("stats", {}) or {}
    wins = int(stats.get("wins", 0))
    losses = int(stats.get("losses", 0))
    total = int(stats.get("total_matches", len(matches)))
    t_count = int(stats.get("tournament_matches", 0))
    ic_count = int(stats.get("interclub_matches", 0))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matches", total)
    c2.metric("Winrate", _winrate_str(wins, losses), f"{wins}W - {losses}V")
    c3.metric("Interclub", ic_count)
    c4.metric("Tornooi", t_count)

    best_own = _best_rank_from_klassement_history(doc)
    source = "eigen klassementshistoriek"
    if best_own is None:
        best_own = _best_rank_opportunistic(player_id, all_docs)
        source = "beste gekende tegenstander-ranking uit onze matches"
    if best_own is not None:
        st.caption(f"🏆 All-time high ranking: **P{best_own}** ({source}).")
    else:
        st.caption("🏆 All-time high ranking: onbekend (nog geen klassementsdata beschikbaar).")

    st.markdown("**Interclubmatchen deze periode**")
    period_matches = []
    if current_reeks_url:
        period_matches = [
            m for m in matches
            if m.get("match_type") == "interclub" and m.get("reeks_url") == current_reeks_url
        ]
    if not period_matches:
        # Fallback: toon de meest recente interclub-periode van deze speler,
        # met duidelijke vermelding dat dit niet noodzakelijk exact dezelfde
        # periode is als de huidige ontmoeting.
        all_interclub = [m for m in matches if m.get("match_type") == "interclub"]
        if all_interclub:
            latest_label = sorted(
                {m.get("period_label") for m in all_interclub if m.get("period_label")},
                reverse=True,
            )
            if latest_label:
                period_matches = [m for m in all_interclub if m.get("period_label") == latest_label[0]]
            st.caption(
                "ℹ️ Geen matches gevonden binnen exact dit schema — onderstaand de meest "
                "recente gekende interclub-periode van deze speler ter referentie."
            )

    if not period_matches:
        st.info("Geen interclubmatches gekend voor deze speler.")
    else:
        rows = []
        for m in sorted(period_matches, key=lambda x: x.get("match_date") or "", reverse=True):
            rows.append({
                "Datum": m.get("match_date") or "",
                "Partner": m.get("partner_name") or "",
                "Tegen": " / ".join(x for x in [m.get("opp1_name"), m.get("opp2_name")] if x),
                "Score": m.get("score") or "",
                "W/V": m.get("result") or ("W" if m.get("won") is True else ("V" if m.get("won") is False else "-")),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(300, 40 + len(rows) * 36))


def render_opponent_dossier_button(
    player_id: str,
    name: str,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    key_prefix: str = "opp_dossier",
) -> None:
    """Klein knopje dat het dossier toont/verbergt (toggle), voor gebruik naast
    elke naam in een lijst van tegenstander-spelers."""
    state_key = f"{key_prefix}_open_{player_id}"
    if st.button("🗂️ Dossier", key=f"{key_prefix}_btn_{player_id}"):
        st.session_state[state_key] = not st.session_state.get(state_key, False)
    if st.session_state.get(state_key):
        with st.container(border=True):
            render_opponent_dossier(
                player_id, name, all_docs,
                current_reeks_url=current_reeks_url,
                key_prefix=f"{key_prefix}_{player_id}",
            )
