"""
lineup_retrospective.py - Nabeschouwing: per eerder gespeelde ontmoeting de
voorspelde winkans tegenover de echte uitslag, MET de padelstat-/officiele
klassementwaarden van TOEN (niet de huidige), plus een kalibratieblok over
alle gespeelde matchen samen met een instelbare winkansfactor.
--------------------------------------------------------------------------
(Zie eerdere PADEL_ANALYSIS_RETRO_*-markers in de git-historiek voor de
volledige toelichting bij: brondata-prioriteit padelstat/klassement,
parallelle Firestore-batches, snapshot-cache, persistente winkansfactor,
eindresultaat-vergelijking, "beste alternatief", individuele-vorm-index,
automatische teamgenoten-resolutie, sterkte-gecorrigeerd vorm-model,
vereenvoudigde kalibratie, prefetch-scope-fix, tegenstander-lek-fix,
model-consistentie tussen "Per match" en kalibratie, lazy kalibratie achter
een knop, live voortgangsweergave per stap, teamgenoten-scan-cache.)
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_PERSISTENT_CACHE_RESTORE_2026-10-05 (op verzoek van
Kim, met meting: "zit vandaag over 64k [Firestore-reads]. ik had pay as you
go gedacht maar is raar" + bevestigd: ~10-15x op "Bereken kalibratie"
geklikt vandaag)
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd door de code na te lezen: een eerdere versie van
gather_all_valid_match_data() had een PERSISTENTE Firestore-cache (1 uur
geldig, collectie "app_settings"), zodat de dure scan over ALLE profielen
(in Kim's data: ~2067 unieke tegenstander-/partner-ID's over alle seizoenen
heen - dat aantal is op zich GEEN bug, zie hieronder) maar 1x per uur
werkelijk hoefde te gebeuren. Die cache is bij een latere herbouw van dit
bestand (de overstap naar de "Bereken kalibratie"-knop +
live-voortgangsweergave) VERLOREN gegaan - elke klik op de knop, in elke
sessie, na elke reboot, deed sindsdien de VOLLEDIGE scan opnieuw. Bij
~2067 relevante spelers x 2-3 reads (padelstat + officieel klassement) x
~10-15 klikken vandaag komt dat nauwkeurig overeen met het gemelde
Firestore-verbruik van >64.000 reads op 1 dag.
Over het getal 2067 zelf: dat zijn NIET Kim's 169 clubprofielen, maar ELKE
tegenstander/partner die ooit voorkwam in de interclub-historie van al die
169 profielen, over ALLE seizoenen heen (elk profiel kan tientallen
matchen hebben, elk tegen 2 tegenstanders - dat loopt snel op tot
duizenden unieke, externe TVL-spelers). Dat aantal zelf is dus
verwachting, geen fout - het ONTBREKEN van een cache errond was dat wel.
FIX: _read_all_valid_cache()/_write_all_valid_cache() (teruggebracht, met
dezelfde opzet als voorheen) omwikkelen nu STAP 1 (de duurste:
ll.get_docs_for_players(all_ids)) EN het eindresultaat van gather_all_valid_match_
data() in zijn geheel:
  - VOOR stap 1 wordt eerst de cache gecontroleerd (signatuur = de
    gesorteerde tuple van alle profiel-ID's). Bij een TREFFER toont de
    live-voortgangsweergave dat meteen ("Cache gevonden (opgeslagen op ...,
    X minuten oud) - geen nieuwe Firestore-reads nodig.") en springt de
    functie DIRECT naar het eindresultaat - stappen 1 t/m 6 worden dan
    VOLLEDIG overgeslagen, dus 0 nieuwe Firestore-reads bij een herhaalde
    klik binnen het uur.
  - Bij een MISTREFFER lopen stap 1 t/m 6 zoals voorheen (ONGEWIJZIGD,
    inclusief de live-voortgangsmeldingen per stap), en wordt het resultaat
    NA afloop weggeschreven naar de cache (TTL 1 uur) voor de volgende
    klik/sessie.
  - Enkel de SCHAAL-ONAFHANKELIJKE ruwe rijen worden opgeslagen (our_avg/
    their_avg/actual_won/bron-indicatie e.d. - geen win_probability, die
    hangt af van de actief ingestelde scale/bias/form_weight en wordt nog
    steeds live herberekend door score_raw_at_scale()).
  - Faalt de Firestore-opslag of -lezing om welke reden ook (bv. een
    tijdelijke verbindingsfout), dan valt dit stil terug op "altijd vers
    berekenen" - nooit een crash, enkel het ontbreken van de versnelling.
Dit raakt UITSLUITEND gather_all_valid_match_data() (de kalibratie-knop).
De andere eerdere fixes (teamgenoten-scan-cache in session_state, lazy
calibration achter de knop, model-consistentie) blijven ONGEWIJZIGD - dit
is een AANVULLING op die laatste fix, geen vervanging.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_PREFETCH_DOUBLE_WORK_FIX_2026-10-04 (op verzoek
van Kim, na de meting dat stap 3 (officieel klassement) van 127.60s naar
22.11s gebracht werd via parallellisatie in lineup_scout.py - stap 4
(padelstat-historiek, 76.05s voor dezelfde 2067 spelers) werd daardoor de
grootste resterende kost)
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door de code na te lezen, geen gok): de vorige versie
van _parallel_prefetch_padelstat() haalde WEL al, parallel (ThreadPoolExecutor,
16 workers), fb.get_padelstat_rating(pid) op voor elke speler - maar GOOIDE
dat resultaat METEEN WEG ("pass", geen return-waarde, geen opslag). Het doel
was uitsluitend een cache "warmen" via fb._fs_prefetch - een functie die,
exact zoals bij prefetch_own_player_reads() in lineup_scout.py, NIET bestaat
in firebase_service.py. _load_padelstat_histories() deed daarna ALSNOG een
volledige, SEQUENTIELE tweede doorloop die fb.get_padelstat_rating() gewoon
OPNIEUW aanriep, een voor een, voor elke speler. Dus: 2067 parallelle reads
(nuttig werk, weggegooid) GEVOLGD DOOR 2067 sequentiele reads (hetzelfde
werk, opnieuw, en dit keer wel gebruikt). De sequentiele tweede helft is
vermoedelijk de echte 76.05s-kost.
FIX: _parallel_prefetch_padelstat() geeft nu een dict {pid: data} terug met
de resultaten van de parallelle ophaling zelf, in plaats van ze weg te
gooien. _load_padelstat_histories() gebruikt dat resultaat NU RECHTSTREEKS
i.p.v. een tweede, sequentiele ronde te doen - enkel als de parallelle
ophaling voor een SPECIFIEKE speler toch niets opleverde (lege dict, geen
sleutel aanwezig), valt de code terug op 1 individuele, alsnog sequentiele
poging voor exact DIE speler (defensief, nooit een ontbrekende waarde
stilzwijgend negeren). Het pad via fb._fs_prefetch (als die ooit wel
bestaat) blijft ongewijzigd als eerste, voorkeurs-poging.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MIRRORED_BOARD_FIX_2026-10-05 (op verzoek van Kim, bevestigd
probleem: "Match 05/09. Je toont 5 matchen bij nabeschouwing. Het moeten er
4 zijn." - en apart, bij andere ontmoetingen, te WEINIG borden, zie die
root cause hieronder bij PADEL_ANALYSIS_STALE_PROFILE_BOARD_GAP)
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd met test_board_count_diagnosis.py, geen gok): voor de
ontmoeting van 05/09 bleken 2 van de 6 gereconstrueerde "boards" exacte
SPIEGELBEELDEN van 2 andere boards te zijn - dezelfde 4 spelers, dezelfde
score, maar met "ons koppel" en "tegenstander" OMGEWISSELD. Oorzaak:
_resolve_encounter_teammates() bepaalt exclude_ids UITSLUITEND uit
sel_player_id's EIGEN 2 borden (_known_opponent_ids(eigen_boards)) - het
houdt geen rekening met de tegenstanders van een TEAMGENOOT die zelf pas
via deze functie wordt toegevoegd. Bij een ontmoeting met meer dan 2 eigen
borden (bv. 4, over 2 rotaties) kan zo'n teamgenoot (bv. Van Eetvelde
Michael, Carl Ide's tegenstander in een bord waarin sel_player_id zelf niet
speelde) worden toegevoegd als "teamgenoot" - zijn eigen matchdocument
bevat dan een board waarin hij/zij en zijn/haar partner als "ons koppel"
staan en de ECHTE teamgenoten (Carl Ide/Nico Recour) als "tegenstander" -
het spiegelbeeld van het board dat Carl Ide/Nico Recour's EIGEN document al
correct opleverde.
FIX: _own_side_component() bouwt, via de 'pair'-edges van ALLE
samengevoegde boards (eigen + teamgenoten) van deze ontmoeting, de kleinste
groep spelers die via partnerschappen verbonden is met sel_player_id - dat
IS per definitie het echte, eigen team (een speler partnert nooit met een
tegenstander). render_retrospective_tab() filtert de boards-lijst nu EERST
op "pair ⊆ own_side" (dit vangt de spiegelbeeld-borden op, ongeacht hun
exacte inhoud), VOOR de bestaande known-opponent-filter (die blijft
ongewijzigd bestaan als tweede, onafhankelijke vangnet). own_side_ids (voor
de klassement-/padelstat-ophaling) is nu simpelweg own_side zelf, i.p.v.
een aparte, minder betrouwbare handmatige opbouw uit partner_user_id's.
Een caption toont expliciet hoeveel spiegelbeeld-borden gedropt werden,
zodat dit controleerbaar blijft i.p.v. stilzwijgend te gebeuren.
--------------------------------------------------------------------------
PADEL_ANALYSIS_STALE_PROFILE_BOARD_GAP_2026-10-05 (bevestigd, GEEN
codewijziging - ter info/voor latere herkenning): bij andere ontmoetingen
(19/09, 26/09) toonde "Per match" juist TE WEINIG borden (3 i.p.v. 4, 2
i.p.v. 4). test_board_count_diagnosis.py bevestigde dat de ontbrekende
boards NIET bestonden in het matchdocument van de betrokken teamgenoot
(bv. Joris Verlee, Carl Ide) op het moment van testen - hun profiel was
simpelweg nog niet (opnieuw) gescraped sinds die match gespeeld werd. Dit
bleek een gevolg van een VERLOPEN GitHub fine-grained personal access
token waardoor de nachtelijke scrape-workflow stil faalde voor ~74% van
alle profielen sinds eind september. GEEN actie nodig in dit bestand -
lost zichzelf op zodra het token vernieuwd is en de profielen opnieuw
gescraped zijn. (Aanvulling 2026-10-05: bij Nico Recour bleek een
herscrape niet te helpen door een bug in het MERGE-VANGNET van
scrape_player.py - zie PADEL_ANALYSIS_MERGE_VANGNET_KEEPS_NEW_2026-10-05
in dat bestand.)
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_MATCH_WORDING_SCORE_2026-10-05 (op verzoek van Kim: "Je
spreekt altijd over borden. Vervang borden altijd door 'Matchen' en bord
door Match. Toon ook duidelijk de score 3-1, 4-0 en spreek niet van 1 van
de 4 gewonnen of zoiets.")
--------------------------------------------------------------------------
Enkel ZICHTBARE TEKST gewijzigd (interne variabelen/functienamen met
"board" blijven, om geen regressie te riskeren):
  - overal "bord/borden" -> "match/matchen" in captions, debug-blokken,
    tabelkolom ("Bord" -> "Match") en de live voortgangsmeldingen van de
    kalibratie;
  - de echte uitslag van de ontmoeting wordt nu als SCORE getoond:
    "Echt: gewonnen (3-1)" i.p.v. "3 van 4 borden gewonnen";
  - ontbreken er matchen (oneven of < 2 gekend), dan toont de pagina nu
    toch de score van de GEKENDE matchen, met duidelijk hoeveel er nog
    ontbreken (bv. "Gekende uitslag: 2-1 - 1 match ontbreekt nog in de
    data"), i.p.v. enkel te melden dat er te weinig zijn.
_actual_encounter_result() geeft daarvoor ook n_lost en een score-tekst
terug; de bestaande velden (n_win, n_boards, uitkomst) blijven ongewijzigd.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CALIBRATION_PROPOSAL_2026-10-05 (op verzoek van Kim: "Ik zou
ook graag de kalibratiewaardes zien. Dan bij bereken kalibratie een voorstel
die je al dan niet kan accepteren.")
--------------------------------------------------------------------------
  - Bovenaan de kalibratiesectie staat nu ALTIJD (ook zonder berekening)
    een tabel met de huidige waarden: winkansfactor, bias, vorm-gewicht en
    wanneer ze laatst aangepast werden.
  - "Bereken kalibratie" berekent nu in 1 klik zowel de score van de
    huidige waarden ALS een voorstel (find_best_scale_and_bias - voorheen
    een aparte knop "Zoek beste model"). Het voorstel staat naast de
    huidige waarden in een tabel, met "Voorstel accepteren" (bewaart in
    Firestore) en "Voorstel negeren" (niets wijzigt). Zijn de huidige
    waarden al de beste, dan staat er enkel een bevestiging.
  - De debug-tabel met stap-tijden staat nu ingeklapt onderaan.
"""
import datetime as _dt
import math
import re
from collections import defaultdict
from typing import Dict, List, Optional
import streamlit as st
import lineup_lab as ll
import firebase_service as fb
try:
    import perf_timing as perf
except Exception:  # noqa: BLE001  pragma: no cover
    class _PerfNoop:
        @staticmethod
        def step(_label):
            from contextlib import nullcontext
            return nullcontext()
    perf = _PerfNoop()
SNAPSHOT_COLLECTION = "lineup_snapshots"
_CALIBRATION_SETTINGS_COLLECTION = "app_settings"
_CALIBRATION_SETTINGS_DOC = "retro_calibration"
# PADEL_ANALYSIS_RETRO_PERSISTENT_CACHE_RESTORE_2026-10-05 - zie moduledocstring.
_ALL_VALID_CACHE_DOC = "retro_all_valid_cache"
_ALL_VALID_CACHE_TTL_SECONDS = 3600
_DEFAULT_SCALE = ll.DEFAULT_WIN_PROBABILITY_SCALE
_CALIBRATION_BIN_EDGES = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0]
_SCALE_BIAS_SEARCH_SCALES = list(range(50, 801, 20))
_BIAS_SEARCH_RANGE = list(range(-150, 151, 10))
_FORM_WEIGHT_SEARCH_RANGE = [0.0, 0.25, 0.5, 0.75, 1.0]
# --------------------------------------------------------------- datums
def to_iso_date(date_text) -> Optional[str]:
    """TVL-datumtekst ("26/09/2026", "26-09-2026" of al ISO) -> "YYYY-MM-DD".
    Geeft None terug bij een onherkenbaar formaat (nooit een gok)."""
    if not date_text:
        return None
    s = str(date_text).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None
# ------------------------------------------------- encounter/board-reconstructie
def _encounter_key(m: dict) -> tuple:
    return (m.get("match_date") or "", m.get("encounter") or "")
def _board_dedupe_key(m: dict, fallback_pid: str) -> str:
    mid = m.get("match_id")
    partner = m.get("partner_user_id")
    pair_key = "|".join(sorted([str(fallback_pid), str(partner)]))
    if mid:
        return f"mid:{mid}|pair:{pair_key}"
    return "fb:" + "|".join(str(x) for x in [
        m.get("match_date"), m.get("encounter"), m.get("round_text"),
        m.get("score"), pair_key,
    ])
def build_retro_encounter_index(docs: Dict[str, dict], allowed_player_ids=None) -> Dict[tuple, list]:
    """`allowed_player_ids` is een SET van toegelaten spelers, of None voor
    GEEN filter (alle spelers in `docs` tellen mee)."""
    allowed = {str(p) for p in allowed_player_ids} if allowed_player_ids is not None else None
    index: Dict[tuple, list] = {}
    for pid, doc in docs.items():
        if allowed is not None and str(pid) not in allowed:
            continue
        for m in doc.get("matches", []) or []:
            if m.get("match_type") != "interclub":
                continue
            index.setdefault(_encounter_key(m), []).append((pid, m))
    return index
def list_retro_encounters(index: Dict[tuple, list]) -> List[tuple]:
    """Meest recent eerst, gesorteerd op echte datum (niet de ruwe tekst)."""
    items = []
    for key, entries in index.items():
        date, encounter = key
        reeks = None
        for _pid, m in entries:
            if m.get("reeks_name"):
                reeks = m.get("reeks_name")
                break
        label_parts = [p for p in [date, reeks, encounter] if p]
        label = " \u2014 ".join(label_parts) if label_parts else "Onbekende ontmoeting"
        items.append((key, label, date))
    items.sort(key=lambda x: to_iso_date(x[2]) or "", reverse=True)
    return [(k, lbl) for k, lbl, _ in items]
def reconstruct_boards_with_rankings(entries: list) -> List[dict]:
    """Zoals ll.reconstruct_boards(), maar behoudt ook opp1_ranking/
    opp2_ranking (tekst, bv. "P200") en match_date."""
    seen = {}
    for pid, m in entries:
        key = _board_dedupe_key(m, pid)
        if key in seen:
            continue
        partner = m.get("partner_user_id")
        if not partner:
            continue
        seen[key] = {
            "pair": frozenset({str(pid), str(partner)}),
            "match_date": m.get("match_date"),
            "round_text": m.get("round_text"),
            "opp1_name": m.get("opp1_name"), "opp2_name": m.get("opp2_name"),
            "opp1_user_id": m.get("opp1_user_id"), "opp2_user_id": m.get("opp2_user_id"),
            "opp1_ranking": m.get("opp1_ranking"), "opp2_ranking": m.get("opp2_ranking"),
            "score": m.get("score"), "result": m.get("result"), "won": m.get("won"),
            "match_id": m.get("match_id"), "dedupe_key": key,
        }
    return list(seen.values())
def _known_opponent_ids(boards: list) -> set:
    """Verzamelt alle tegenstander-speler-id's uit een lijst borden (zoals
    teruggegeven door reconstruct_boards_with_rankings())."""
    out = set()
    for b in boards:
        for uid in (b.get("opp1_user_id"), b.get("opp2_user_id")):
            if uid:
                out.add(str(uid))
    return out
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_MIRRORED_BOARD_FIX_2026-10-05
# Zie de module-docstring voor de gemeten/bevestigde root cause (5 i.p.v.
# 4 boards bij de ontmoeting van 05/09).
# ─────────────────────────────────────────────
def _own_side_component(sel_player_id: str, boards: list) -> set:
    """Bouwt, via de 'pair'-edges van ALLE samengevoegde boards (eigen +
    teamgenoten) van deze ontmoeting, de kleinste groep spelers die via
    partnerschappen verbonden is met sel_player_id - dat IS per definitie
    het echte, eigen team voor deze ontmoeting (een speler partnert nooit
    met een tegenstander).
    Boards waarvan 'pair' NIET in deze groep valt, zijn spiegelbeeld-boards
    die ontstonden doordat een later toegevoegde 'teamgenoot' in
    werkelijkheid een TEGENSTANDER van een andere, echte teamgenoot was -
    _resolve_encounter_teammates() kon dat niet weten, want haar exclude_ids
    komt enkel uit sel_player_id's EIGEN boards, niet uit de boards van de
    teamgenoten die ze zelf toevoegt. Zulke boards zijn altijd het fysieke
    spiegelbeeld van een board dat al correct, vanuit de eigen kant, in de
    lijst staat - droppen verliest dus geen informatie, enkel de dubbele/
    foutief-georiënteerde kant."""
    adj: Dict[str, set] = defaultdict(set)
    for b in boards:
        p1, p2 = tuple(b["pair"])
        adj[p1].add(p2)
        adj[p2].add(p1)
    seen = {str(sel_player_id)}
    queue = [str(sel_player_id)]
    while queue:
        cur = queue.pop()
        for nxt in adj.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen
def _resolve_encounter_teammates(
    sel_player_id: str, encounter_key: tuple, profiles: list,
    exclude_ids: Optional[set] = None, max_candidates: int = 200,
) -> Dict[str, dict]:
    """Zoekt, UITSLUITEND voor de ENE ontmoeting `encounter_key` (match_date,
    encounter), welke andere profielen een interclub-matchrecord hebben op
    DIEZELFDE sleutel, en geeft hun VOLLEDIGE matchdocument terug.
    `exclude_ids` (zie _known_opponent_ids()) sluit kandidaten uit die REEDS
    bekend zijn als TEGENSTANDER van sel_player_id in deze ontmoeting - zodat
    een tegenstander die toevallig ook een eigen profiel heeft (bv. omdat hij
    voor een andere ploeg speelde) niet ten onrechte als teamgenoot wordt
    aanvaard. LET OP (zie PADEL_ANALYSIS_MIRRORED_BOARD_FIX_2026-10-05): dit
    sluit enkel tegenstanders van sel_player_id's EIGEN boards uit, niet van
    boards van andere teamgenoten - render_retrospective_tab() corrigeert
    dat resterende gat achteraf via _own_side_component().
    Resultaat wordt gecached in st.session_state per (sel_player_id,
    encounter_key) - wisselen tussen weergaven of andere herrenders van
    DEZELFDE ontmoeting doen deze scan dus maar 1x per sessie."""
    cache_key = f"retro_teammates_cache_{sel_player_id}_{encounter_key}"
    debug_key = f"retro_teammates_debug_{sel_player_id}_{encounter_key}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    exclude_ids = {str(x) for x in (exclude_ids or set())}
    other_ids = sorted({
        str(p.get("player_id")) for p in profiles
        if p.get("player_id")
        and str(p.get("player_id")) != str(sel_player_id)
        and str(p.get("player_id")) not in exclude_ids
    })[:max_candidates]
    if not other_ids:
        st.session_state[cache_key] = {}
        st.session_state[debug_key] = {"other_ids_count": 0, "docs_count": 0, "matched_count": 0, "error": None}
        return {}
    error_txt = None
    all_docs = {}
    with perf.step(f"retro: teammate-scan get_docs_for_players ({len(other_ids)} kandidaten)"):
        try:
            all_docs = ll.get_docs_for_players(other_ids)
        except Exception as exc:  # noqa: BLE001
            error_txt = f"{type(exc).__name__}: {exc}"
    gevonden = {}
    if not error_txt:
        for pid, doc in all_docs.items():
            for m in doc.get("matches", []) or []:
                if m.get("match_type") == "interclub" and _encounter_key(m) == encounter_key:
                    gevonden[pid] = doc
                    break
    st.session_state[debug_key] = {
        "other_ids_count": len(other_ids), "docs_count": len(all_docs),
        "matched_count": len(gevonden), "error": error_txt,
        "sample_ids": other_ids[:10],
    }
    st.session_state[cache_key] = gevonden
    return gevonden
# --------------------------------------------------------------- momentopnames
@st.cache_data(ttl=300, show_spinner=False)
def _load_all_snapshots() -> list:
    try:
        docs = fb.db.collection(SNAPSHOT_COLLECTION).limit(500).stream()
        return [doc.to_dict() or {} for doc in docs]
    except Exception:  # noqa: BLE001
        return []
def _find_snapshot_for(date_text, opp_user_ids: set) -> Optional[dict]:
    iso = to_iso_date(date_text)
    if not iso:
        return None
    for data in _load_all_snapshots():
        if to_iso_date(data.get("match_date")) != iso:
            continue
        opp_players = data.get("opponent_players") or {}
        if opp_user_ids and not (set(opp_players.keys()) & {str(u) for u in opp_user_ids if u}):
            continue
        return data
    return None
# --------------------------------------------------------------- padelstat-cache
def _collect_relevant_player_ids(index: dict) -> set:
    ids = set()
    for entries in index.values():
        for pid, m in entries:
            ids.add(str(pid))
            for veld in ("partner_user_id", "opp1_user_id", "opp2_user_id"):
                if m.get(veld):
                    ids.add(str(m[veld]))
    return ids
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_PADELSTAT_PREFETCH_DOUBLE_WORK_FIX_2026-10-04
# Zie de module-docstring voor de gemeten/bevestigde root cause: de vorige
# versie van _parallel_prefetch_padelstat() haalde parallel op maar GOOIDE
# het resultaat WEG, waarna _load_padelstat_histories() ALSNOG een volledige
# sequentiele tweede doorloop deed - dubbel werk, waarvan de sequentiele
# helft de gemeten 76.05s-kost was (2067 spelers).
# ─────────────────────────────────────────────
def _parallel_prefetch_padelstat(player_ids: tuple) -> Dict[str, dict]:
    """Haalt fb.get_padelstat_rating() parallel op (ThreadPoolExecutor, max
    16 workers) voor ALLE player_ids EN geeft de resultaten DIRECT terug als
    {pid: data-or-{}}, zodat de aanroeper dit NIET nog eens sequentieel moet
    herhalen. Faalt een individuele read, dan krijgt die pid gewoon {}
    (zelfde gedrag als voorheen bij een fout).
    Als fb._fs_prefetch bestaat (momenteel niet het geval in
    firebase_service.py), wordt die voorkeurs-weg EERST geprobeerd, als
    pure optimalisatie/warming - de parallelle ThreadPoolExecutor-ophaling
    hieronder gebeurt in dat geval ALSNOG, want enkel die levert de
    daadwerkelijke data op die deze functie moet teruggeven."""
    out: Dict[str, dict] = {}
    if not player_ids:
        return out
    prefetch = getattr(fb, "_fs_prefetch", None)
    if callable(prefetch):
        try:
            prefetch(("get_padelstat_rating",), list(player_ids))
        except Exception:  # noqa: BLE001
            pass
    try:
        from concurrent.futures import ThreadPoolExecutor
        def _fetch(pid):
            try:
                return pid, (fb.get_padelstat_rating(pid) or {})
            except Exception:  # noqa: BLE001
                return pid, {}
        with ThreadPoolExecutor(max_workers=min(16, len(player_ids))) as ex:
            for pid, data in ex.map(_fetch, player_ids):
                out[pid] = data
    except Exception:  # noqa: BLE001
        pass
    return out
@st.cache_data(ttl=300, show_spinner=False)
def _load_padelstat_histories(player_ids: tuple) -> Dict[str, dict]:
    # PADEL_ANALYSIS_PADELSTAT_PREFETCH_DOUBLE_WORK_FIX_2026-10-04: gebruikt
    # nu RECHTSTREEKS het resultaat van de parallelle ophaling - GEEN tweede,
    # sequentiele doorloop meer voor spelers die al een (mogelijk lege)
    # resultaat kregen. Enkel als de parallelle fase voor een SPECIFIEKE
    # speler faalde en geen sleutel opleverde, wordt die ENE speler alsnog
    # individueel (sequentieel) geprobeerd - defensief, nooit stilzwijgend
    # overslaan.
    prefetched = _parallel_prefetch_padelstat(player_ids)
    out: Dict[str, dict] = {}
    for pid in player_ids:
        if pid in prefetched:
            data = prefetched[pid]
        else:
            try:
                data = fb.get_padelstat_rating(pid) or {}
            except Exception:  # noqa: BLE001
                data = {}
        out[pid] = {
            "history": list(data.get("history") or []),
            "flat_rating": data.get("rating"),
            "flat_fetched_at": data.get("fetched_at"),
        }
    return out
def _rating_at_from_history(history: list, moment_iso: str) -> Optional[float]:
    beste = None
    for regel in history:
        t = str(regel.get("fetched_at") or "")
        if t and t[:len(moment_iso)] <= moment_iso and (beste is None or t >= beste[0]):
            beste = (t, regel.get("rating"))
    return beste[1] if beste else None
def _latest_rating_from_history(history: list) -> Optional[float]:
    if not history:
        return None
    beste = max(history, key=lambda r: str(r.get("fetched_at") or ""))
    rating = beste.get("rating")
    return float(rating) if rating is not None else None
def _padelstat_priority_rating(
    pid, date_text, ratings_cache: Dict[str, dict], fallback_value, fallback_label: str,
):
    """GEDEELDE prioriteitsketen voor ZOWEL eigen spelers ALS tegenstanders:
      1. padelstat-historiek OP DATUM (exact);
      2. meest recente padelstat-HISTORIEK-waarde (any datum - "huidig");
      3. het vlakke, niet-gehistoriseerde "rating"-veld;
      4. `fallback_value`/`fallback_label`.
    Geeft (waarde, bron) terug; waarde is None als ECHT niets gekend is."""
    cache_entry = ratings_cache.get(str(pid)) or {}
    history = cache_entry.get("history") or []
    iso = to_iso_date(date_text)
    if iso:
        hist = _rating_at_from_history(history, iso)
        if hist is not None:
            return float(hist), "padelstat-historiek (op datum)"
    latest = _latest_rating_from_history(history)
    if latest is not None:
        return latest, "meest recente padelstat-historiek (geen regel exact op die datum - benadering)"
    flat = cache_entry.get("flat_rating")
    if flat is not None:
        return float(flat), "padelstat (nog geen historiek bijgehouden voor deze speler - huidige waarde)"
    if fallback_value is not None:
        return float(fallback_value), fallback_label
    return None, "onbekend"
# --------------------------------------------------------------- voorspelling
def _own_value_at(player_id, date_text, current_official_ranks: dict, snapshot_own: dict,
                  ratings_cache: Dict[str, dict]):
    pid = str(player_id)
    if snapshot_own and pid in snapshot_own:
        v = snapshot_own[pid]
        if v.get("padelstat") is not None:
            return float(v["padelstat"]), "momentopname (padelstat)"
        if v.get("official_rank") is not None:
            return float(v["official_rank"]), "momentopname (klassement)"
    fallback = (current_official_ranks or {}).get(pid)
    return _padelstat_priority_rating(
        pid, date_text, ratings_cache, fallback,
        "huidig officieel klassement (laatste redmiddel, geen padelstat gekend)",
    )
def _opponent_value_at(user_id, ranking_text, date_text, snapshot_opp: dict,
                       ratings_cache: Dict[str, dict]):
    uid = str(user_id) if user_id else None
    if snapshot_opp and uid and uid in snapshot_opp:
        v = snapshot_opp[uid]
        if v.get("padelstat") is not None:
            return float(v["padelstat"]), "momentopname (padelstat)"
        if v.get("official_rank") is not None:
            return float(v["official_rank"]), "momentopname (klassement)"
    if not uid:
        official = ll.parse_ranking(ranking_text)
        return (float(official), "officieel klassement (van toen, uit het uitslagenblad)") if official is not None else (None, "onbekend")
    official = ll.parse_ranking(ranking_text)
    return _padelstat_priority_rating(
        uid, date_text, ratings_cache, official,
        "officieel klassement (van toen, uit het uitslagenblad - laatste redmiddel, geen padelstat gekend)",
    )
def _effective_win_probability(
    our_avg, their_avg, our_ids, their_ids, scale: float, bias: float = 0.0,
    form_weight: float = 0.0, form_adjustment: Optional[Dict[str, dict]] = None,
) -> Optional[float]:
    """EEN enkele, gedeelde formule - gebruikt door ZOWEL predict_board()
    (per match) ALS score_raw_at_scale() (kalibratie), zodat beide ALTIJD
    hetzelfde model gebruiken. Zonder bias/form_weight is dit IDENTIEK aan
    ll.estimate_win_probability()."""
    if our_avg is None or their_avg is None:
        return None
    effective_bias = bias
    if form_weight and form_adjustment:
        our_res = [form_adjustment[str(p)]["avg_residual"] for p in (our_ids or ()) if p and str(p) in form_adjustment]
        their_res = [form_adjustment[str(p)]["avg_residual"] for p in (their_ids or ()) if p and str(p) in form_adjustment]
        if our_res or their_res:
            our_m = sum(our_res) / len(our_res) if our_res else 0.0
            their_m = sum(their_res) / len(their_res) if their_res else 0.0
            effective_bias = bias + (our_m - their_m) * scale * form_weight
    if effective_bias:
        return _estimate_win_probability_with_bias(our_avg, their_avg, scale=scale, bias=effective_bias)
    return ll.estimate_win_probability(our_avg, their_avg, scale=scale)
def predict_board(
    board: dict, current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, snapshot: Optional[dict] = None,
    bias: float = 0.0, form_weight: float = 0.0, form_adjustment: Optional[Dict[str, dict]] = None,
) -> dict:
    """`bias`/`form_weight`/`form_adjustment` zijn OPTIONEEL - standaard
    0.0/None, dus ONGEWIJZIGD gedrag tenzij expliciet meegegeven."""
    date_text = board.get("match_date")
    p1, p2 = tuple(board["pair"])
    snap_own = (snapshot or {}).get("own_players") or {}
    snap_opp = (snapshot or {}).get("opponent_players") or {}
    our_vals = [_own_value_at(p, date_text, current_official_ranks, snap_own, ratings_cache) for p in (p1, p2)]
    their_vals = [
        _opponent_value_at(board.get("opp1_user_id"), board.get("opp1_ranking"), date_text, snap_opp, ratings_cache),
        _opponent_value_at(board.get("opp2_user_id"), board.get("opp2_ranking"), date_text, snap_opp, ratings_cache),
    ]
    our_known = [v for v, _ in our_vals if v is not None]
    their_known = [v for v, _ in their_vals if v is not None]
    our_avg = sum(our_known) / len(our_known) if our_known else None
    their_avg = sum(their_known) / len(their_known) if their_known else None
    wp = _effective_win_probability(
        our_avg, their_avg, (p1, p2), (board.get("opp1_user_id"), board.get("opp2_user_id")),
        scale=scale, bias=bias, form_weight=form_weight, form_adjustment=form_adjustment,
    )
    return {
        "pair": (p1, p2), "our_avg": our_avg, "their_avg": their_avg,
        "win_probability": wp, "risk_note": ll.risk_note_for_probability(wp),
        "our_sources": [s for _, s in our_vals], "their_sources": [s for _, s in their_vals],
        "actual_won": board.get("won"), "score": board.get("score"),
        "opp1_name": board.get("opp1_name"), "opp2_name": board.get("opp2_name"),
        "opp1_user_id": board.get("opp1_user_id"), "opp2_user_id": board.get("opp2_user_id"),
        "match_date": date_text,
    }
def predict_encounter(
    boards: list, current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, use_snapshot: bool = True,
    bias: float = 0.0, form_weight: float = 0.0, form_adjustment: Optional[Dict[str, dict]] = None,
) -> dict:
    snapshot = None
    if use_snapshot and boards:
        opp_ids = {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards}
        snapshot = _find_snapshot_for(boards[0].get("match_date"), opp_ids)
    predictions = [
        predict_board(
            b, current_official_ranks, ratings_cache, scale=scale, snapshot=snapshot,
            bias=bias, form_weight=form_weight, form_adjustment=form_adjustment,
        )
        for b in boards
    ]
    return {"boards": predictions, "snapshot_used": snapshot is not None}
# ------------------------------------------- volledige-ontmoeting-uitkomst
def _combine_boards_to_point_probs(win_probs: list) -> dict:
    probs = [(0.5 if p is None else max(0.0, min(1.0, float(p)))) for p in win_probs]
    n = len(probs)
    if n == 0:
        return {"p2": 0.0, "p1": 0.0, "p0": 0.0}
    tot = {0: 1.0}
    for p in probs:
        nieuw = {}
        for k, pk in tot.items():
            nieuw[k] = nieuw.get(k, 0.0) + pk * (1.0 - p)
            nieuw[k + 1] = nieuw.get(k + 1, 0.0) + pk * p
        tot = nieuw
    half = n / 2.0
    p2 = sum(p for k, p in tot.items() if k > half)
    p1 = sum(p for k, p in tot.items() if k == half)
    p0 = max(0.0, 1.0 - p2 - p1)
    return {"p2": p2, "p1": p1, "p0": p0}
def _actual_encounter_result(boards: list) -> Optional[dict]:
    """PADEL_ANALYSIS_RETRO_MATCH_WORDING_SCORE_2026-10-05: geeft naast de
    bestaande velden ook n_lost en de score als tekst ("3-1") terug."""
    if not boards:
        return None
    gewonnen = [b.get("won") for b in boards]
    if any(w is None for w in gewonnen):
        return None
    n_win = sum(1 for w in gewonnen if w)
    n_lost = len(boards) - n_win
    half = len(boards) / 2.0
    if n_win > half:
        uitkomst = "gewonnen"
    elif n_win == half:
        uitkomst = "gelijk"
    else:
        uitkomst = "verloren"
    return {
        "n_win": n_win, "n_lost": n_lost, "n_boards": len(boards),
        "uitkomst": uitkomst, "score_txt": f"{n_win}-{n_lost}",
    }
# ------------------------------------------------ schaal-onafhankelijke ruwe data
def gather_raw_match_data(index: dict, current_official_ranks: dict, ratings_cache: Dict[str, dict]) -> list:
    """Verzamelt voor ELK bord van ELKE ontmoeting in `index` de SCHAAL-
    ONAFHANKELIJKE ruwe data (our_avg/their_avg/actual_won)."""
    raw = []
    for entries in index.values():
        boards = reconstruct_boards_with_rankings(entries)
        if not boards:
            continue
        opp_ids = {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards}
        snapshot = _find_snapshot_for(boards[0].get("match_date"), opp_ids)
        snap_own = (snapshot or {}).get("own_players") or {}
        snap_opp = (snapshot or {}).get("opponent_players") or {}
        for board in boards:
            p1, p2 = tuple(board["pair"])
            date_text = board.get("match_date")
            our_vals = [_own_value_at(p, date_text, current_official_ranks, snap_own, ratings_cache) for p in (p1, p2)]
            their_vals = [
                _opponent_value_at(board.get("opp1_user_id"), board.get("opp1_ranking"), date_text, snap_opp, ratings_cache),
                _opponent_value_at(board.get("opp2_user_id"), board.get("opp2_ranking"), date_text, snap_opp, ratings_cache),
            ]
            our_known = [v for v, _ in our_vals if v is not None]
            their_known = [v for v, _ in their_vals if v is not None]
            our_is_padelstat = all(
                s is not None and "klassement" not in s and s != "onbekend" for _, s in our_vals
            ) if our_vals else False
            their_is_padelstat = all(
                s is not None and "klassement" not in s and s != "onbekend" for _, s in their_vals
            ) if their_vals else False
            raw.append({
                "pair": (p1, p2),
                "our_avg": (sum(our_known) / len(our_known)) if our_known else None,
                "their_avg": (sum(their_known) / len(their_known)) if their_known else None,
                "actual_won": board.get("won"), "score": board.get("score"),
                "opp1_name": board.get("opp1_name"), "opp2_name": board.get("opp2_name"),
                "opp1_user_id": board.get("opp1_user_id"), "opp2_user_id": board.get("opp2_user_id"),
                "match_date": date_text,
                "our_is_padelstat": our_is_padelstat, "their_is_padelstat": their_is_padelstat,
            })
    return raw
def compute_individual_form_index(raw_rows: list) -> Dict[str, dict]:
    """Geeft {player_id: {"wins", "losses", "n", "winrate",
    "avg_opp_rating_won", "avg_opp_rating_lost"}} terug. Een tegenstander-
    speler krijgt het SPIEGELBEELD van `actual_won`."""
    tally: Dict[str, dict] = defaultdict(lambda: {
        "wins": 0, "losses": 0, "opp_ratings_won": [], "opp_ratings_lost": [],
    })
    for r in raw_rows:
        won = r.get("actual_won")
        if won is None:
            continue
        their_avg = r.get("their_avg")
        our_avg = r.get("our_avg")
        for pid in r.get("pair") or ():
            if pid is None:
                continue
            entry = tally[str(pid)]
            entry["wins" if won else "losses"] += 1
            if their_avg is not None:
                entry["opp_ratings_won" if won else "opp_ratings_lost"].append(their_avg)
        for uid in (r.get("opp1_user_id"), r.get("opp2_user_id")):
            if uid is None:
                continue
            entry = tally[str(uid)]
            entry["wins" if not won else "losses"] += 1
            if our_avg is not None:
                entry["opp_ratings_won" if not won else "opp_ratings_lost"].append(our_avg)
    out: Dict[str, dict] = {}
    for pid, entry in tally.items():
        wins, losses = entry["wins"], entry["losses"]
        n = wins + losses
        won_list, lost_list = entry["opp_ratings_won"], entry["opp_ratings_lost"]
        out[pid] = {
            "wins": wins, "losses": losses, "n": n, "winrate": (wins / n) if n else None,
            "avg_opp_rating_won": (sum(won_list) / len(won_list)) if won_list else None,
            "avg_opp_rating_lost": (sum(lost_list) / len(lost_list)) if lost_list else None,
        }
    return out
def _format_individual_form(form_index: Dict[str, dict], player_id, name: str) -> Optional[str]:
    """Korte tekst voor 1 speler, inclusief het gemiddelde niveau van wie
    hij versloeg/van wie hij verloor."""
    entry = form_index.get(str(player_id)) if player_id else None
    if not entry or not entry.get("n"):
        return None
    basis = f"{name} ({entry['winrate'] * 100:.0f}% win, {entry['wins']}/{entry['n']})"
    context_delen = []
    if entry.get("avg_opp_rating_won") is not None:
        context_delen.append(f"won tegen gem. {entry['avg_opp_rating_won']:.0f}")
    if entry.get("avg_opp_rating_lost") is not None:
        context_delen.append(f"verloor tegen gem. {entry['avg_opp_rating_lost']:.0f}")
    if context_delen:
        basis += f" - {', '.join(context_delen)}"
    return basis
def compute_form_adjustment(raw_rows: list, scale: float, bias: float = 0.0) -> Dict[str, dict]:
    """Geeft per speler {"n", "avg_residual"} terug: het gemiddelde VERSCHIL
    tussen "werkelijk gewonnen (1/0)" en "verwachte kans volgens rating+
    schaal+bias" over al zijn gekende matchen."""
    tally: Dict[str, List[float]] = defaultdict(list)
    for r in raw_rows:
        won = r.get("actual_won")
        our_avg, their_avg = r.get("our_avg"), r.get("their_avg")
        if won is None or our_avg is None or their_avg is None:
            continue
        wp = _estimate_win_probability_with_bias(our_avg, their_avg, scale=scale, bias=bias)
        if wp is None:
            continue
        residual = (1.0 if won else 0.0) - wp
        for pid in r.get("pair") or ():
            if pid is not None:
                tally[str(pid)].append(residual)
        for uid in (r.get("opp1_user_id"), r.get("opp2_user_id")):
            if uid is not None:
                tally[str(uid)].append(-residual)
    return {pid: {"n": len(vals), "avg_residual": sum(vals) / len(vals)} for pid, vals in tally.items() if vals}
# --------------------------------------------------------------------------
# PADEL_ANALYSIS_RETRO_PERSISTENT_CACHE_RESTORE_2026-10-05 - zie moduledocstring.
# --------------------------------------------------------------------------
def _read_all_valid_cache(player_ids_sig: tuple) -> Optional[dict]:
    """Geeft het opgeslagen resultaat terug ALS de spelerslijst-signatuur
    overeenkomt EN de cache niet verlopen is, anders None. Faalt stil."""
    try:
        doc = fb.db.collection(_CALIBRATION_SETTINGS_COLLECTION).document(_ALL_VALID_CACHE_DOC).get()
        data = doc.to_dict() if doc is not None and getattr(doc, "exists", True) else None
        if not data:
            return None
        if tuple(data.get("player_ids_sig") or []) != player_ids_sig:
            return None
        saved_at_epoch = data.get("saved_at_epoch")
        age_seconds = None
        if saved_at_epoch is not None:
            age_seconds = _dt.datetime.now(_dt.timezone.utc).timestamp() - float(saved_at_epoch)
            if age_seconds > _ALL_VALID_CACHE_TTL_SECONDS:
                return None
        rows = data.get("valid_rows")
        if not isinstance(rows, list):
            return None
        for r in rows:
            r["pair"] = tuple(r.get("pair") or ())
        return {
            "valid_rows": rows,
            "n_total_boards": int(data.get("n_total_boards") or 0),
            "player_ids": list(data.get("player_ids") or []),
            "saved_at": data.get("saved_at"),
            "age_seconds": age_seconds,
        }
    except Exception:  # noqa: BLE001
        return None
def _write_all_valid_cache(player_ids_sig: tuple, player_ids: list, valid_rows: list, n_total_boards: int) -> None:
    """Schrijft de SCHAAL-ONAFHANKELIJKE ruwe rijen weg (geen win_
    probability - die hangt af van de gekozen factor). Faalt stil."""
    try:
        payload = {
            "player_ids_sig": list(player_ids_sig),
            "player_ids": player_ids,
            "valid_rows": [
                {
                    "pair": list(r.get("pair") or ()),
                    "our_avg": r.get("our_avg"), "their_avg": r.get("their_avg"),
                    "actual_won": r.get("actual_won"), "score": r.get("score"),
                    "opp1_name": r.get("opp1_name"), "opp2_name": r.get("opp2_name"),
                    "opp1_user_id": r.get("opp1_user_id"), "opp2_user_id": r.get("opp2_user_id"),
                    "match_date": r.get("match_date"),
                    "our_is_padelstat": r.get("our_is_padelstat"), "their_is_padelstat": r.get("their_is_padelstat"),
                }
                for r in valid_rows
            ],
            "n_total_boards": n_total_boards,
            "saved_at_epoch": _dt.datetime.now(_dt.timezone.utc).timestamp(),
            "saved_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        fb.db.collection(_CALIBRATION_SETTINGS_COLLECTION).document(_ALL_VALID_CACHE_DOC).set(payload)
    except Exception:  # noqa: BLE001
        pass
def gather_all_valid_match_data(
    profiles: list, debug_timings: Optional[list] = None, live_placeholder=None,
) -> dict:
    """Bouwt de SCHAAL-ONAFHANKELIJKE ruwe matchdata over ALLE profielen in
    de database. `full_padelstat_rows` is de subset waarvoor de kalibratie
    ONVOORWAARDELIJK gebruikt wordt.
    PADEL_ANALYSIS_RETRO_PERSISTENT_CACHE_RESTORE_2026-10-05: controleert
    EERST de persistente Firestore-cache (1 uur geldig) - bij een treffer
    worden stap 1 t/m 6 VOLLEDIG overgeslagen (0 nieuwe Firestore-reads).
    Bij een mistreffer lopen alle stappen zoals voorheen, en wordt het
    resultaat NA afloop weggeschreven voor de volgende klik/sessie."""
    import time as _time
    def _mark(label, t0, count=None):
        if debug_timings is not None:
            debug_timings.append({"label": label, "seconds": _time.perf_counter() - t0, "count": count})
    def _live(txt):
        if live_placeholder is not None:
            live_placeholder.markdown(txt)
    all_ids = sorted({str(p.get("player_id")) for p in profiles if p.get("player_id")})
    if not all_ids:
        return {
            "valid_rows": [], "full_padelstat_rows": [], "n_total_boards": 0, "n_valid": 0,
            "n_full_padelstat": 0, "n_fallback": 0, "form_index": {}, "player_ids": [],
        }
    sig = tuple(all_ids)
    t0_cache = _time.perf_counter()
    _live(f"**Cache controleren** voor {len(all_ids)} profielen...")
    cached = _read_all_valid_cache(sig)
    if cached is not None:
        age_min = (cached.get("age_seconds") or 0) / 60.0
        _live(
            f"**Cache gevonden** (opgeslagen op {cached.get('saved_at', '?')}, {age_min:.0f} minuten oud) - "
            "geen nieuwe Firestore-reads nodig. Stap 1 t/m 6 overgeslagen."
        )
        _mark("0. persistente cache gelezen (stap 1-6 overgeslagen)", t0_cache, len(cached["valid_rows"]))
        valid_rows = cached["valid_rows"]
        n_total_boards = cached["n_total_boards"]
    else:
        _live(f"**Geen bruikbare cache** (verlopen, leeg of andere spelerslijst) - volledige berekening start...")
        _mark("0. persistente cache: mistreffer", t0_cache)
        _live(f"**Stap 1/6:** documenten ophalen voor **{len(all_ids)}** profielen - bezig...")
        t0 = _time.perf_counter()
        with perf.step(f"retro: get_docs_for_players (ALLE {len(all_ids)} profielen)"):
            try:
                docs = ll.get_docs_for_players(all_ids)
            except Exception as exc:  # noqa: BLE001
                _live(f"**Stap 1/6 MISLUKT** na {_time.perf_counter() - t0:.1f}s: `{type(exc).__name__}: {exc}`")
                docs = {}
        dt1 = _time.perf_counter() - t0
        _live(f"**Stap 1/6:** documenten ophalen voor {len(all_ids)} profielen - klaar ({dt1:.1f}s), {len(docs)} documenten terug.")
        _mark(f"1. get_docs_for_players ({len(all_ids)} profielen opgevraagd)", t0, len(all_ids))
        t0 = _time.perf_counter()
        index = build_retro_encounter_index(docs, allowed_player_ids=None)
        n_encounters = len(index)
        n_boards_seen = sum(len(v) for v in index.values())
        dt2 = _time.perf_counter() - t0
        _live(f"**Stap 2/6:** encounter-index gebouwd ({dt2:.1f}s) - {n_encounters} ontmoetingen, {n_boards_seen} matchrecords.")
        _mark(f"2. encounter-index bouwen ({n_encounters} ontmoetingen, {n_boards_seen} matchrecords)", t0, n_boards_seen)
        relevant_ids = tuple(sorted(_collect_relevant_player_ids(index)))
        _live(f"**Stap 3/6:** officieel klassement ophalen voor **{len(relevant_ids)}** unieke spelers - bezig...")
        t0 = _time.perf_counter()
        current_official_ranks = {}
        with perf.step(f"retro: officieel klassement (kalibratie, {len(relevant_ids)} spelers)"):
            try:
                from lineup_scout import _build_own_official_ranks_strict, prefetch_own_player_reads
                prefetch_own_player_reads(list(relevant_ids))
                current_official_ranks = _build_own_official_ranks_strict(list(relevant_ids)) or {}
            except Exception as exc:  # noqa: BLE001
                _live(f"**Stap 3/6 fout** (genegeerd, gaat verder): `{type(exc).__name__}: {exc}`")
        dt3 = _time.perf_counter() - t0
        _live(f"**Stap 3/6:** officieel klassement - klaar ({dt3:.1f}s), {len(current_official_ranks)} spelers met een klassement.")
        _mark(f"3. officieel klassement ophalen ({len(relevant_ids)} unieke spelers)", t0, len(relevant_ids))
        _live(f"**Stap 4/6:** padelstat-historiek ophalen voor **{len(relevant_ids)}** unieke spelers - bezig...")
        t0 = _time.perf_counter()
        with perf.step(f"retro: padelstat-historiek (kalibratie, {len(relevant_ids)} spelers)"):
            ratings_cache = _load_padelstat_histories(relevant_ids)
        dt4 = _time.perf_counter() - t0
        _live(f"**Stap 4/6:** padelstat-historiek - klaar ({dt4:.1f}s).")
        _mark(f"4. padelstat-historiek ophalen ({len(relevant_ids)} unieke spelers)", t0, len(relevant_ids))
        _live(f"**Stap 5/6:** winkans per match berekenen voor **{n_boards_seen}** matchrecords - bezig...")
        t0 = _time.perf_counter()
        with perf.step("retro: gather_raw_match_data (per-match-voorspelling, kalibratie)"):
            raw = gather_raw_match_data(index, current_official_ranks, ratings_cache)
        dt5 = _time.perf_counter() - t0
        _live(f"**Stap 5/6:** winkans per match - klaar ({dt5:.1f}s), {len(raw)} matchen berekend.")
        _mark(f"5. per-match voorspelling berekenen ({len(raw)} matchen)", t0, len(raw))
        t0 = _time.perf_counter()
        valid_rows = [r for r in raw if r.get("our_avg") is not None and r.get("their_avg") is not None and r.get("actual_won") is not None]
        n_total_boards = len(raw)
        dt6 = _time.perf_counter() - t0
        _mark("6a. filteren geldige rijen", t0, len(valid_rows))
        t0 = _time.perf_counter()
        _write_all_valid_cache(sig, all_ids, valid_rows, n_total_boards)
        dt_write = _time.perf_counter() - t0
        _live(
            f"**Stap 6/6:** klaar - {len(valid_rows)} geldige matchen gevonden, weggeschreven naar cache "
            f"({dt_write:.1f}s) voor de volgende klik. **Totaal: {dt1+dt2+dt3+dt4+dt5+dt6+dt_write:.1f}s.**"
        )
        _mark("6b. resultaat wegschrijven naar persistente cache", t0)
    n_full_padelstat = sum(1 for r in valid_rows if r.get("our_is_padelstat") and r.get("their_is_padelstat"))
    n_fallback = len(valid_rows) - n_full_padelstat
    full_padelstat_rows = [r for r in valid_rows if r.get("our_is_padelstat") and r.get("their_is_padelstat")]
    form_index = compute_individual_form_index(valid_rows)
    return {
        "valid_rows": valid_rows, "full_padelstat_rows": full_padelstat_rows,
        "n_total_boards": n_total_boards, "n_valid": len(valid_rows),
        "n_full_padelstat": n_full_padelstat, "n_fallback": n_fallback,
        "form_index": form_index, "player_ids": all_ids,
    }
def score_raw_at_scale(raw_rows: list, scale: float, bias: float = 0.0, form_weight: float = 0.0,
                       form_adjustment: Optional[Dict[str, dict]] = None) -> list:
    """Vult elke rij uit gather_raw_match_data() aan met win_probability -
    gebruikt dezelfde gedeelde _effective_win_probability() als
    predict_board()."""
    out = []
    for r in raw_rows:
        wp = _effective_win_probability(
            r["our_avg"], r["their_avg"], r.get("pair"),
            (r.get("opp1_user_id"), r.get("opp2_user_id")),
            scale=scale, bias=bias, form_weight=form_weight, form_adjustment=form_adjustment,
        )
        out.append({**r, "win_probability": wp})
    return out
# --------------------------------------------------------------- kalibratie
def calibration_stats(predictions: list, bin_edges=None) -> Optional[dict]:
    bin_edges = bin_edges or _CALIBRATION_BIN_EDGES
    usable = [p for p in predictions if p.get("win_probability") is not None and p.get("actual_won") is not None]
    n = len(usable)
    if n == 0:
        return None
    brier = sum((p["win_probability"] - (1.0 if p["actual_won"] else 0.0)) ** 2 for p in usable) / n
    eps = 1e-9
    log_loss = -sum(
        (1.0 if p["actual_won"] else 0.0) * math.log(max(p["win_probability"], eps))
        + (0.0 if p["actual_won"] else 1.0) * math.log(max(1.0 - p["win_probability"], eps))
        for p in usable
    ) / n
    accuracy = sum(1 for p in usable if (p["win_probability"] >= 0.5) == bool(p["actual_won"])) / n
    mean_pred = sum(p["win_probability"] for p in usable) / n
    mean_actual = sum(1.0 if p["actual_won"] else 0.0 for p in usable) / n
    bins = []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        grp = [p for p in usable if lo <= p["win_probability"] < hi or (hi == 1.0 and p["win_probability"] == 1.0)]
        if grp:
            bins.append({
                "bereik": f"{lo * 100:.0f}-{hi * 100:.0f}%", "n": len(grp),
                "gem_voorspeld": sum(x["win_probability"] for x in grp) / len(grp) * 100,
                "werkelijk": sum(1 for x in grp if x["actual_won"]) / len(grp) * 100,
            })
    return {
        "n": n, "brier": brier, "log_loss": log_loss, "accuracy": accuracy,
        "mean_predicted": mean_pred, "mean_actual": mean_actual, "bins": bins,
    }
def _estimate_win_probability_with_bias(our_avg, their_avg, scale: float, bias: float = 0.0):
    """PURE, lokale uitbreiding van ll.estimate_win_probability() met een
    extra bias/verschuiving-term op het ratingverschil."""
    if our_avg is None or their_avg is None:
        return None
    diff = (our_avg - their_avg) + bias
    try:
        return 1.0 / (1.0 + math.pow(10.0, -diff / scale))
    except OverflowError:
        return 0.0 if diff < 0 else 1.0
def find_best_scale_and_bias(
    raw_rows: list, scales=None, biases=None, form_weights=None,
) -> dict:
    """Doorzoekt een rooster (scale x bias x form_weight) en geeft de
    combinatie met de laagste Brier-score terug. `form_weights` bevat
    ALTIJD 0.0, dus dit kan NOOIT slechter zijn dan zonder vorm-term."""
    scales = scales or _SCALE_BIAS_SEARCH_SCALES
    biases = biases or _BIAS_SEARCH_RANGE
    form_weights = form_weights if form_weights is not None else _FORM_WEIGHT_SEARCH_RANGE
    if 0.0 not in form_weights:
        form_weights = [0.0] + list(form_weights)
    form_adjustment = compute_form_adjustment(raw_rows, scale=_DEFAULT_SCALE, bias=0.0) if any(form_weights) else {}
    best = None
    curve = []
    for s in scales:
        for b in biases:
            for fw in form_weights:
                scored = score_raw_at_scale(raw_rows, s, bias=b, form_weight=fw, form_adjustment=form_adjustment)
                stats = calibration_stats(scored)
                if stats is None:
                    continue
                curve.append({"scale": s, "bias": b, "form_weight": fw, "brier": stats["brier"], "n": stats["n"]})
                if best is None or stats["brier"] < best["brier"]:
                    best = {"scale": s, "bias": b, "form_weight": fw, "brier": stats["brier"], "n": stats["n"]}
    return {"best": best, "curve": curve, "form_adjustment": form_adjustment}
def logistic_curve(scale: float, diffs=None) -> list:
    diffs = diffs if diffs is not None else list(range(-400, 401, 10))
    return [(d, ll.estimate_win_probability(0.0, -float(d), scale=scale)) for d in diffs]
# --------------------------------------------------------------- winkansfactor opslaan
def _load_saved_scale() -> dict:
    """Leest de laatst opgeslagen winkansfactor, bias EN form_weight uit
    Firestore. Faalt stil."""
    try:
        doc = fb.db.collection(_CALIBRATION_SETTINGS_COLLECTION).document(_CALIBRATION_SETTINGS_DOC).get()
        data = doc.to_dict() if doc is not None and getattr(doc, "exists", True) else None
        if data and data.get("win_probability_scale") is not None:
            return {
                "scale": float(data["win_probability_scale"]),
                "bias": float(data.get("win_probability_bias") or 0.0),
                "form_weight": float(data.get("win_probability_form_weight") or 0.0),
                "saved_at": data.get("saved_at"),
            }
    except Exception:  # noqa: BLE001
        pass
    return {}
def _save_scale_to_firestore(scale: float, bias: float = 0.0, form_weight: float = 0.0) -> None:
    try:
        fb.db.collection(_CALIBRATION_SETTINGS_COLLECTION).document(_CALIBRATION_SETTINGS_DOC).set(
            {
                "win_probability_scale": float(scale),
                "win_probability_bias": float(bias),
                "win_probability_form_weight": float(form_weight),
                "saved_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            },
            merge=True,
        )
    except Exception:  # noqa: BLE001
        pass
# --------------------------------------------------------------- beste alternatief
def best_alternative_for_encounter(
    boards: list, docs: Dict[str, dict], current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, top_n: int = 3,
) -> Optional[dict]:
    debug_boards = [
        {"pair": sorted(b.get("pair") or []), "score": b.get("score"), "match_id": b.get("match_id"),
         "opp1_name": b.get("opp1_name"), "opp2_name": b.get("opp2_name")}
        for b in (boards or [])
    ]
    if not boards:
        return {"top": [], "actual": None, "reason": "too_few_players", "n_players": 0, "debug": {"boards": debug_boards, "players": []}}
    players = sorted({str(p) for b in boards for p in b["pair"]})
    if len(players) < 4:
        return {
            "top": [], "actual": None, "reason": "too_few_players", "n_players": len(players),
            "debug": {"boards": debug_boards, "players": players, "n_boards": len(boards)},
        }
    required = ll.required_counts_from_boards(boards)
    exclude_keys = {b["dedupe_key"] for b in boards}
    synergy = ll.compute_pairwise_synergy(docs, players, exclude_match_keys=exclude_keys)
    synergy_fn = ll.make_pair_score_fn(synergy, docs)
    date_text = boards[0].get("match_date")
    snapshot = _find_snapshot_for(date_text, {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards})
    snap_own = (snapshot or {}).get("own_players") or {}
    snap_opp = (snapshot or {}).get("opponent_players") or {}
    player_ratings = {}
    for pid in players:
        val, _ = _own_value_at(pid, date_text, current_official_ranks, snap_own, ratings_cache)
        if val is not None:
            player_ratings[pid] = val
    opponent_boards = []
    opponent_ratings = {}
    for b in boards:
        pair_info = []
        for idx, uid_key, ranking_key in ((0, "opp1_user_id", "opp1_ranking"), (1, "opp2_user_id", "opp2_ranking")):
            uid = b.get(uid_key)
            val, _ = _opponent_value_at(uid, b.get(ranking_key), date_text, snap_opp, ratings_cache)
            if uid and val is not None:
                opponent_ratings[str(uid)] = val
            pair_info.append({
                "user_id": uid, "name": b.get("opp1_name") if idx == 0 else b.get("opp2_name"),
                "ranking": b.get(ranking_key),
            })
        opponent_boards.append({"opponent_pair": pair_info})
    results, _truncated, _diag = ll.optimize_lineup_vs_scenario(
        players, required, synergy_fn, opponent_boards, player_ratings,
        player_official_ranks=current_official_ranks, opponent_ratings=opponent_ratings,
        top_n=top_n, win_probability_scale=scale,
    )
    if not results:
        return {"top": [], "actual": None, "reason": "no_valid_combinations", "n_players": len(players)}
    actual_key = tuple(sorted(tuple(sorted(b["pair"])) for b in boards))
    actual_result = next(
        (r for r in results if tuple(sorted(tuple(sorted(a["our_pair"])) for a in r["assignment"])) == actual_key),
        None,
    )
    return {"top": results, "actual": actual_result, "reason": None, "n_players": len(players)}
# --------------------------------------------------------------------------
# Streamlit-weergave
# --------------------------------------------------------------------------
def _pct(v) -> str:
    return f"{v * 100:.0f}%" if v is not None else "onbekend"
def _outcome_color(predicted_wp, actual_won) -> str:
    if predicted_wp is None or actual_won is None:
        return "gray"
    correct = (predicted_wp >= 0.5) == bool(actual_won)
    return "green" if correct else "red"
def _source_is_padelstat(sources) -> bool:
    return all(s is not None and "klassement" not in s and s != "onbekend" for s in (sources or []))
def _render_board_row(bp: dict, name_lookup: dict, form_index: Optional[Dict[str, dict]] = None) -> None:
    p1, p2 = bp["pair"]
    ons = f"{name_lookup.get(p1, p1)} / {name_lookup.get(p2, p2)}"
    hen = f"{bp.get('opp1_name', '?')} / {bp.get('opp2_name', '?')}"
    kleur = _outcome_color(bp["win_probability"], bp["actual_won"])
    uitslag = "gewonnen" if bp["actual_won"] is True else ("verloren" if bp["actual_won"] is False else "onbekend")
    badge = "" if (_source_is_padelstat(bp.get("our_sources")) and _source_is_padelstat(bp.get("their_sources"))) \
        else " \u00b7 :orange[deels klassement]"
    st.markdown(
        f"**{ons}** tegen **{hen}** ({bp.get('score') or '?'}) - "
        f"voorspeld :{kleur}[**{_pct(bp['win_probability'])}**] ({bp['risk_note']}), "
        f"echt **{uitslag}**{badge}"
    )
    with st.expander("Op basis van welke waarden?", expanded=False):
        st.caption(
            (f"Onze spelers: {bp['our_sources'][0]}, {bp['our_sources'][1]} "
             f"(gemiddeld {bp['our_avg']:.0f})") if bp.get("our_avg") is not None else "Onze spelers: onbekend"
        )
        st.caption(
            (f"Tegenstander: {bp['their_sources'][0]}, {bp['their_sources'][1]} "
             f"(gemiddeld {bp['their_avg']:.0f})") if bp.get("their_avg") is not None else "Tegenstander: onbekend"
        )
        if form_index:
            vorm_regels = []
            for pid in (p1, p2):
                txt = _format_individual_form(form_index, pid, name_lookup.get(pid, str(pid)))
                if txt:
                    vorm_regels.append(txt)
            for uid, naam in ((bp.get("opp1_user_id"), bp.get("opp1_name")), (bp.get("opp2_user_id"), bp.get("opp2_name"))):
                txt = _format_individual_form(form_index, uid, naam or "?")
                if txt:
                    vorm_regels.append(txt)
            if vorm_regels:
                st.caption("Individuele vorm (alle bekende interclub-matchen): " + " \u00b7 ".join(vorm_regels))
        else:
            st.caption(
                "Individuele vorm nog niet beschikbaar - klik onderaan de pagina op 'Bereken kalibratie' "
                "om dit (en de modelcontrole) te berekenen."
            )
def _format_saved_at(value) -> str:
    try:
        return _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except Exception:  # noqa: BLE001
        return str(value)
def _apply_scale_callback(new_scale: float, new_bias: float = 0.0, new_form_weight: float = 0.0) -> None:
    st.session_state["retro_scale"] = new_scale
    st.session_state["retro_bias"] = new_bias
    st.session_state["retro_form_weight"] = new_form_weight
    st.session_state.pop("retro_best_scale_bias_result", None)
    st.session_state["retro_scale_saved_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save_scale_to_firestore(new_scale, new_bias, new_form_weight)
def _reject_proposal_callback() -> None:
    """PADEL_ANALYSIS_CALIBRATION_PROPOSAL_2026-10-05: voorstel negeren -
    de huidige instelling blijft ongewijzigd."""
    st.session_state.pop("retro_best_scale_bias_result", None)
def render_retrospective_tab(profiles: list, sel_player_id) -> None:
    st.markdown('<div class="section-header">Nabeschouwing</div>', unsafe_allow_html=True)
    sel_player_id = str(sel_player_id)
    name_lookup = {str(p.get("player_id")): (p.get("display_name") or str(p.get("player_id"))) for p in profiles}
    sel_naam = name_lookup.get(sel_player_id, sel_player_id)
    if "retro_scale" not in st.session_state:
        with perf.step("retro: opgeslagen winkansfactor lezen"):
            saved = _load_saved_scale()
        if saved.get("scale") is not None:
            st.session_state["retro_scale"] = saved["scale"]
            st.session_state["retro_bias"] = saved.get("bias", 0.0)
            st.session_state["retro_form_weight"] = saved.get("form_weight", 0.0)
            st.session_state["retro_scale_saved_at"] = saved.get("saved_at")
    scale = st.session_state.get("retro_scale", _DEFAULT_SCALE)
    bias = st.session_state.get("retro_bias", 0.0)
    form_weight = st.session_state.get("retro_form_weight", 0.0)
    all_data = st.session_state.get("retro_all_valid_data")
    form_index = (all_data or {}).get("form_index") or {}
    form_adjustment = (
        compute_form_adjustment((all_data or {}).get("full_padelstat_rows") or [], scale=_DEFAULT_SCALE, bias=0.0)
        if (form_weight and all_data) else {}
    )
    with perf.step("retro: eigen matchen ophalen"):
        with st.spinner(f"Matchen van {sel_naam} ophalen..."):
            try:
                docs = ll.get_docs_for_players([sel_player_id])
            except Exception as exc:  # noqa: BLE001
                st.error(f"Kon de matchen van {sel_naam} niet ophalen: {type(exc).__name__}: {exc}")
                return
    st.caption(
        f"Vergelijkt, voor **{sel_naam}**, de voorspelde winkans met de echte uitslag van eerder gespeelde "
        "interclub-matchen, MET de padelstat-/klassementwaarden van TOEN (niet de huidige) waar bekend."
    )
    with perf.step("retro: encounter-index bouwen (eigen matchen)"):
        index = build_retro_encounter_index(docs, allowed_player_ids={sel_player_id})
    encounters = list_retro_encounters(index)
    if not encounters:
        st.info(f"Nog geen gespeelde interclub-ontmoetingen gevonden voor {sel_naam}.")
        return
    labels = [lbl for _k, lbl in encounters]
    key_by_label = {lbl: k for k, lbl in encounters}
    gekozen_label = st.selectbox(
        "Kies een eerder gespeelde ontmoeting", labels, key="retro_pick_encounter",
    )
    gekozen_key = key_by_label[gekozen_label]
    eigen_entries = index.get(gekozen_key, [])
    eigen_boards = reconstruct_boards_with_rankings(eigen_entries)
    gekende_tegenstanders = _known_opponent_ids(eigen_boards)
    teammate_docs = _resolve_encounter_teammates(
        sel_player_id, gekozen_key, profiles, exclude_ids=gekende_tegenstanders,
    )
    if teammate_docs:
        st.caption(
            f"{len(teammate_docs)} teamgenoot/teamgenoten van deze ontmoeting automatisch mee opgenomen: "
            + ", ".join(name_lookup.get(pid, pid) for pid in teammate_docs)
        )
    tm_debug_key = f"retro_teammates_debug_{sel_player_id}_{gekozen_key}"
    tm_debug = st.session_state.get(tm_debug_key)
    if tm_debug:
        with st.expander("Debug: teamgenoten-zoekopdracht voor deze ontmoeting", expanded=not teammate_docs):
            if tm_debug.get("error"):
                st.error(f"De zoekopdracht faalde met een fout: {tm_debug['error']}")
            st.caption(
                f"Kandidaten doorzocht: {tm_debug['other_ids_count']} \u00b7 "
                f"documenten teruggekregen: {tm_debug['docs_count']} \u00b7 "
                f"matchend met deze ontmoeting: {tm_debug['matched_count']}"
            )
            if tm_debug["other_ids_count"] > 0 and tm_debug["docs_count"] == 0:
                st.warning(
                    "Er kwamen 0 documenten terug voor alle kandidaten - dit wijst op een probleem met "
                    "`ll.get_docs_for_players()` zelf (een limiet, een batch-grootte-probleem, of een "
                    "foutief geneste call), niet op deze module."
                )
            elif tm_debug["docs_count"] > 0 and tm_debug["matched_count"] == 0:
                st.warning(
                    "Er kwamen wel documenten terug, maar GEEN ENKELE had een interclub-match op exact "
                    "deze (datum, ontmoeting)-combinatie. Mogelijk wijkt het 'encounter'-tekstveld of de "
                    "datum-notatie van de teamgenoot-matchrecords af van die van jouw eigen record."
                )
            st.caption(f"Voorbeeld van doorzochte speler-id's: {', '.join(tm_debug.get('sample_ids', []))}")
    docs_encounter = dict(docs)
    docs_encounter.update(teammate_docs)
    index_encounter = build_retro_encounter_index(
        docs_encounter, allowed_player_ids=set(docs_encounter.keys()),
    )
    entries_encounter = index_encounter.get(gekozen_key, [])
    # PADEL_ANALYSIS_MIRRORED_BOARD_FIX_2026-10-05 - zie moduledocstring voor
    # de volledige, bevestigde root-cause-analyse (05/09: 5 i.p.v. 4 boards).
    boards_all = reconstruct_boards_with_rankings(entries_encounter)
    own_side = _own_side_component(sel_player_id, boards_all)
    boards = [b for b in boards_all if set(b["pair"]) <= own_side]
    n_mirrored_dropped = len(boards_all) - len(boards)
    boards = [b for b in boards if not (set(b["pair"]) & gekende_tegenstanders)]
    if n_mirrored_dropped:
        st.caption(
            f"{n_mirrored_dropped} match(en) genegeerd: dit bleek dezelfde match, maar dan "
            "geregistreerd vanuit het perspectief van de tegenstander (ons/tegenstander omgewisseld)."
        )
    own_side_ids = set(own_side)
    current_official_ranks = {}
    with perf.step(f"retro: officieel klassement terugval ophalen ({len(own_side_ids)} spelers)"):
        try:
            from lineup_scout import _build_own_official_ranks_strict, prefetch_own_player_reads
            with perf.step("retro: klassement - parallel voorophalen"):
                prefetch_own_player_reads(sorted(own_side_ids))
            current_official_ranks = _build_own_official_ranks_strict(sorted(own_side_ids)) or {}
        except Exception:  # noqa: BLE001
            pass
    player_ids = tuple(sorted(_collect_relevant_player_ids(index_encounter)))
    with perf.step(f"retro: padelstat-historiek laden ({len(player_ids)} spelers)"):
        ratings_cache = _load_padelstat_histories(player_ids)
    with perf.step("retro: ontmoeting voorspellen (predict_encounter)"):
        pred = predict_encounter(
            boards, current_official_ranks, ratings_cache, scale=scale,
            bias=bias, form_weight=form_weight, form_adjustment=form_adjustment,
        )
    if pred["snapshot_used"]:
        st.success("Een eerdere momentopname van deze ontmoeting werd gevonden - de waarden van toen zijn exact.")
    st.markdown("#### Per match: voorspeld tegenover echt")
    for bp in pred["boards"]:
        _render_board_row(bp, name_lookup, form_index=form_index)
    st.divider()
    st.markdown("#### Eindresultaat van de ontmoeting: voorspeld tegenover echt")
    n_known_boards = len(boards)
    # PADEL_ANALYSIS_RETRO_MATCH_WORDING_SCORE_2026-10-05: uitslag als score.
    actual = _actual_encounter_result(boards)
    if n_known_boards < 2 or n_known_boards % 2 != 0:
        st.caption(
            f"We kennen {n_known_boards} match(en) van deze ontmoeting - te weinig (of een oneven "
            "aantal, wat altijd op een ontbrekende match wijst) voor een betrouwbaar voorspeld eindresultaat."
        )
        if actual is not None:
            st.markdown(
                f"Gekende uitslag: **{actual['score_txt']}** - minstens 1 match ontbreekt nog in de data "
                "(die speler is nog niet bijgewerkt)."
            )
    else:
        encounter_pp = _combine_boards_to_point_probs([bp["win_probability"] for bp in pred["boards"]])
        st.caption(f"Gebaseerd op alle {n_known_boards} gekende matchen van deze ontmoeting.")
        st.markdown(
            f"Voorspeld: "
            f":green[**{encounter_pp['p2'] * 100:.0f}% winst**] \u00b7 "
            f":orange[**{encounter_pp['p1'] * 100:.0f}% gelijk**] \u00b7 "
            f":red[**{encounter_pp['p0'] * 100:.0f}% verlies**]"
        )
        if actual is None:
            st.caption("De echte uitslag van 1 of meer van deze matchen is niet gekend - geen vergelijking mogelijk.")
        else:
            st.markdown(f"Echt: **{actual['uitkomst']} ({actual['score_txt']})**")
    st.divider()
    st.markdown("#### Beste alternatief (achteraf, met dezelfde waarden van toen)")
    with perf.step("retro: beste alternatief doorrekenen"):
        with st.spinner("Alternatieven doorrekenen..."):
            alt = best_alternative_for_encounter(boards, docs_encounter, current_official_ranks, ratings_cache, scale=scale)
    if alt.get("reason") == "too_few_players":
        st.caption(
            f"Onvoldoende eigen spelers gekend voor deze ontmoeting ({alt.get('n_players', 0)} van de nodige 4)."
        )
        dbg = alt.get("debug") or {}
        with st.expander("Debug: welke matchen/spelers zag deze berekening?", expanded=True):
            st.caption(
                f"Gevonden: {dbg.get('n_boards', len(dbg.get('boards', [])))} match(en), "
                f"{len(dbg.get('players', []))} unieke speler(s): "
                + (", ".join(name_lookup.get(p, p) for p in dbg.get("players", [])) or "(geen)")
            )
            st.dataframe(
                [{"Match": i + 1, "Ons koppel": " / ".join(name_lookup.get(p, p) for p in b["pair"]),
                  "Tegen": f"{b.get('opp1_name', '?')} / {b.get('opp2_name', '?')}", "Score": b.get("score"),
                  "Match-ID": b.get("match_id")}
                 for i, b in enumerate(dbg.get("boards", []))],
                use_container_width=True, hide_index=True,
            )
            st.caption(
                "Als dit minder matchen toont dan de regels hierboven bij 'Per match', dan is dat de "
                "rechtstreekse oorzaak - vergelijk de 2 lijsten."
            )
    elif alt.get("reason") == "no_valid_combinations":
        st.caption(
            f"{alt.get('n_players', 0)} eigen spelers gekend, maar geen enkele reglementair geldige "
            "alternatieve koppelverdeling gevonden voor deze combinatie (bv. door de puntengrens)."
        )
    elif not alt.get("top"):
        st.caption("Geen alternatieven gevonden voor deze ontmoeting.")
    else:
        actual_ebw = alt["actual"]["expected_boards_won"] if alt["actual"] else None
        for rank, r in enumerate(alt["top"], start=1):
            pairs_txt = " \u00b7 ".join(
                f"{name_lookup.get(a['our_pair'][0], a['our_pair'][0])} / {name_lookup.get(a['our_pair'][1], a['our_pair'][1])}"
                for a in r["assignment"]
            )
            is_actual = alt["actual"] is not None and r is alt["actual"]
            label = " (zoals echt gespeeld)" if is_actual else ""
            st.write(f"**#{rank} - verwacht {r['expected_boards_won']:.2f} gewonnen matchen**{label}: {pairs_txt}")
        if actual_ebw is not None and alt["top"] and alt["top"][0]["expected_boards_won"] - actual_ebw >= 0.1:
            st.caption(
                f"Het beste alternatief lag {alt['top'][0]['expected_boards_won'] - actual_ebw:.2f} hoger "
                "dan de effectief gespeelde opstelling (verwachte gewonnen matchen)."
            )
        elif alt["actual"] is not None:
            st.caption("De effectief gespeelde opstelling was (zo goed als) de beste mogelijke keuze.")
    st.divider()
    st.markdown("#### Kalibratie over alle gekende matchen (enkel padelstat)")
    # PADEL_ANALYSIS_CALIBRATION_PROPOSAL_2026-10-05 - zie moduledocstring.
    opgeslagen = st.session_state.get("retro_scale_saved_at")
    st.markdown("**Huidige kalibratiewaarden** (gelden ook voor 'Per match' en 'Beste alternatief' hierboven):")
    st.dataframe(
        [{"Winkansfactor (schaal)": f"{scale:.0f}", "Bias": f"{bias:+.0f}",
          "Vorm-gewicht": f"{form_weight:+.2f}",
          "Laatst aangepast": _format_saved_at(opgeslagen) if opgeslagen else "standaardwaarde (nooit aangepast)"}],
        use_container_width=True, hide_index=True,
    )
    st.caption(
        "'Bereken kalibratie' doorzoekt ALLE interclub-matchen in de database (niet enkel die van "
        f"{sel_naam}), toont hoe goed de huidige waarden scoren en doet een voorstel voor betere waarden, "
        "dat je zelf kan accepteren of negeren. De eerste keer (of na 1 uur) duurt dit even, daarna is "
        "het binnen het uur vrijwel instant dankzij een gedeelde, opgeslagen cache."
    )
    if st.button("Bereken kalibratie (over alle gekende matchen)", key="retro_compute_calibration"):
        import time as _time
        debug_timings: list = []
        live_placeholder = st.empty()
        _t_totaal = _time.perf_counter()
        with perf.step("retro: alle geldige matchdata verzamelen (gather_all_valid_match_data)"):
            st.session_state["retro_all_valid_data"] = gather_all_valid_match_data(
                profiles, debug_timings=debug_timings, live_placeholder=live_placeholder,
            )
        rows_voor_voorstel = st.session_state["retro_all_valid_data"].get("full_padelstat_rows") or []
        if rows_voor_voorstel:
            live_placeholder.markdown("**Voorstel berekenen** (schaal x bias x vorm-gewicht doorrekenen)...")
            t0 = _time.perf_counter()
            with perf.step("retro: voorstel berekenen (find_best_scale_and_bias)"):
                st.session_state["retro_best_scale_bias_result"] = find_best_scale_and_bias(rows_voor_voorstel)
            debug_timings.append({"label": "7. voorstel berekenen", "seconds": _time.perf_counter() - t0, "count": len(rows_voor_voorstel)})
        st.session_state["retro_calibration_debug"] = {
            "steps": debug_timings, "total_seconds": _time.perf_counter() - _t_totaal,
            "n_profiles": len(profiles),
        }
        st.rerun()
    if all_data is None:
        st.info("Nog niet berekend in deze sessie - klik hierboven op de knop.")
        return
    raw_rows = all_data.get("full_padelstat_rows") or []
    if not raw_rows:
        st.info(
            "Nog geen enkele match met echte padelstat-waarden voor alle 4 spelers - de kalibratie kan nog "
            "niet berekend worden."
        )
        return
    with perf.step("retro: kalibratie herberekenen (score_raw_at_scale)"):
        stats = calibration_stats(score_raw_at_scale(raw_rows, scale, bias=bias, form_weight=form_weight, form_adjustment=form_adjustment))
    if not stats:
        st.info("Nog geen matchen met zowel een gekende winkans als een gekende uitslag.")
        return
    st.markdown("##### Hoe goed scoren de huidige waarden?")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Brier-score", f"{stats['brier']:.3f}", help="Lager = beter. 0.25 = niet beter dan een muntstuk.")
    with c2:
        st.metric("Accuraatheid", f"{stats['accuracy'] * 100:.0f}%", help="Hoe vaak de favoriet (>=50%) ook echt won.")
    with c3:
        st.metric("Aantal matchen", f"{stats['n']}")
    st.caption(
        f"Gemiddeld voorspeld: {stats['mean_predicted'] * 100:.0f}% - gemiddeld werkelijk gewonnen: "
        f"{stats['mean_actual'] * 100:.0f}%."
    )
    if stats["bins"]:
        st.dataframe(
            [{"Kansklasse": b["bereik"], "Aantal": b["n"], "Gem. voorspeld": f"{b['gem_voorspeld']:.0f}%",
              "Werkelijk gewonnen": f"{b['werkelijk']:.0f}%"} for b in stats["bins"]],
            use_container_width=True, hide_index=True,
        )
        st.caption("Idealiter liggen 'Gem. voorspeld' en 'Werkelijk gewonnen' per rij dicht bij elkaar.")
    result2 = st.session_state.get("retro_best_scale_bias_result")
    if result2 and result2.get("best"):
        best2 = result2["best"]
        verbetering = stats["brier"] - best2["brier"]
        st.markdown("##### Voorstel")
        st.dataframe(
            [
                {"": "Huidig", "Winkansfactor": f"{scale:.0f}", "Bias": f"{bias:+.0f}",
                 "Vorm-gewicht": f"{form_weight:+.2f}", "Brier-score": f"{stats['brier']:.3f}"},
                {"": "Voorstel", "Winkansfactor": f"{best2['scale']:.0f}", "Bias": f"{best2['bias']:+.0f}",
                 "Vorm-gewicht": f"{best2.get('form_weight', 0.0):+.2f}", "Brier-score": f"{best2['brier']:.3f}"},
            ],
            use_container_width=True, hide_index=True,
        )
        zelfde = (
            float(best2["scale"]) == float(scale) and float(best2["bias"]) == float(bias)
            and float(best2.get("form_weight", 0.0)) == float(form_weight)
        )
        if zelfde or verbetering <= 0:
            st.success("De huidige waarden zijn al de beste - niets aan te passen.")
        else:
            st.caption(
                f"Verbetering van de Brier-score: {verbetering:+.3f} (lager is beter)."
                + (" Kleine verbetering - accepteren is optioneel." if verbetering < 0.005 else "")
            )
            ca, cn = st.columns(2)
            with ca:
                st.button(
                    "Voorstel accepteren", key="retro_accept_proposal", type="primary",
                    on_click=_apply_scale_callback,
                    args=(best2["scale"], best2["bias"], best2.get("form_weight", 0.0)),
                )
            with cn:
                st.button("Voorstel negeren", key="retro_reject_proposal", on_click=_reject_proposal_callback)
    debug_info = st.session_state.get("retro_calibration_debug")
    if debug_info:
        with st.expander(
            f"Debug: laatste berekening duurde {debug_info['total_seconds']:.1f}s "
            f"({debug_info['n_profiles']} profielen in de database)", expanded=False,
        ):
            st.dataframe(
                [{"Stap": s["label"], "Tijd (s)": f"{s['seconds']:.2f}",
                  "Aandeel": f"{(s['seconds'] / debug_info['total_seconds'] * 100):.0f}%" if debug_info["total_seconds"] else "-"}
                 for s in debug_info["steps"]],
                use_container_width=True, hide_index=True,
            )
