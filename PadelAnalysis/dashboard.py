"""
dashboard.py — PadelAnalysis v2 Streamlit dashboard: DUNNE ENTRYPOINT.

PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14 (op verzoek van Kim):
Dit bestand groeide tot ~1800 regels, wat elke aanpassing traag en
foutgevoelig maakte. Opgesplitst in:
  - dashboard_common.py         : gedeelde helpers/imports/CSS-achtige state
  - page_add_player.py          : "➕ Speler toevoegen"
  - page_lineup_lab.py          : "🧩 Opstelling-analyse" (incl. rotatieplanner)
  - player_dashboard_shared.py  : render_player_dashboard() - HERGEBRUIKT
                                   door zowel Mijn profiel als Spelers
  - page_my_profile.py          : "👤 Mijn profiel"
  - page_players.py             : "🔍 Spelers"

dashboard.py zelf doet enkel nog: st.set_page_config, CSS-injectie,
navigatie-knoppen, en de routing naar de juiste page_xxx()-functie.

PADEL_ANALYSIS_SYSPATH_CHICKEN_EGG_FIX_2026-09-14 (kritieke bugfix):
BUG (opgelost): dashboard.py importeerde dashboard_common als ALLERALEERSTE
lokale import, in de veronderstelling dat "het via streamlit_app.py sowieso
wel goed komt". Maar dashboard_common.py bevat zelf de sys.path-setup die
de PadelAnalysis-map toevoegt - een kip-en-ei-probleem: om
dashboard_common.py te kunnen VINDEN en importeren, moet Python al weten dat
er in de PadelAnalysis-map gezocht moet worden, en dat wist het nog niet op
het moment van die import.
Lokaal (via `streamlit run dashboard.py`, uitgevoerd VANUIT de
PadelAnalysis-map) voegt Streamlit de map van het uitgevoerde hoofdscript
zelf automatisch toe aan sys.path - vandaar dat het daar wél werkte. Op de
cloud wordt dashboard.py echter NIET als hoofdscript gestart, maar als
sub-pagina via st.Page("PadelAnalysis/dashboard.py") vanuit het
GECOMBINEERDE hoofdbestand streamlit_app.py (dat in de repo-root staat).
Streamlit voegt dan enkel de map van streamlit_app.py toe aan sys.path -
niet de PadelAnalysis-submap - waardoor "import dashboard_common" faalde
met ModuleNotFoundError, en (omdat beide apps in HETZELFDE proces draaien
via dezelfde st.navigation) ook mAICoach onbruikbaar werd.
In de OUDE, monolithische dashboard.py (vóór de opsplitsing) stond deze
exacte sys.path-toevoeging BOVENAAN dat bestand zelf, VOOR enige lokale
import - vandaar dat die versie altijd werkte, ongeacht hoe ze werd
aangeroepen. Bij de opsplitsing verhuisde die cruciale, EERST-uit-te-voeren
stap per ongeluk naar dashboard_common.py, waardoor de volgorde verloren
ging.
Fix: dezelfde twee regels sys.path-setup staan nu OOK, EERST, hier in
dashboard.py zelf - vóór "import dashboard_common". Dat is een bewuste,
kleine duplicatie (dashboard_common.py behoudt zijn EIGEN kopie voor het
geval een ander bestand dashboard_common rechtstreeks importeert zonder
via dashboard.py te lopen) - maar noodzakelijk om het kip-en-ei-probleem op
te lossen.

--------------------------------------------------------------------------
PERF_TIMING_ROLLOUT_2026-09-29 (op verzoek van Kim: laadtijd-meting over de
hele app)
--------------------------------------------------------------------------
  - De repo-root (mAICoach/) wordt nu OOK op sys.path gezet: perf_timing.py
    is daarheen verhuisd, zodat mAICoach en PadelAnalysis dezelfde helper
    delen. Via streamlit_app.py staat de root er al; dit is nodig voor
    standalone `streamlit run PadelAnalysis/dashboard.py`.
  - Gemeten stappen (zichtbaar onder "pagina: Padel Analysis" in het
    paneel): de imports van dashboard_common + pagina-modules (duur enkel
    bij de EERSTE run na een herstart - daarna zitten ze in sys.modules),
    en de gekozen pagina als geheel ("Padel: <pagina>").
  - Draait dit bestand standalone (zonder streamlit_app.py), dan doen
    perf.reset()/perf.render_panel() hieronder het werk zelf; via
    streamlit_app.py zijn het automatisch no-ops.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PAGE_IN_URL_2026-09-29 (op verzoek van Kim: "F5 springt terug
naar Mijn profiel")
--------------------------------------------------------------------------
ROOT CAUSE: de gekozen pagina stond ENKEL in st.session_state["page"]. Een
F5 start in Streamlit een NIEUWE sessie met een lege session_state, dus viel
de navigatie telkens terug op PAGES[0] ("Mijn profiel"). Extra vervelend
tijdens het meten van laadtijden: elke F5 op Opstelling-analyse vergde
eerst een klik terug naar die pagina.
FIX: de gekozen pagina staat nu OOK in de URL, als ?p=<slug>
(st.query_params). Die overleeft F5, een bladwijzer en een gedeelde link.
  - Bij de EERSTE run van een sessie (F5, nieuwe tab) wordt de pagina uit
    de URL gelezen. Onbekende of ontbrekende waarde -> "Mijn profiel",
    zoals voorheen.
  - Binnen een lopende sessie blijft session_state de bron van waarheid;
    de URL wordt bij ELKE run gelijkgezet met de huidige pagina. Zo volgt
    ook een sprong via dashboard_common._go_to_player() (die enkel
    session_state["page"] zet) automatisch in de URL.
  - De slugs zijn korte ASCII-namen zonder emoji (PAGE_SLUGS hieronder),
    zodat de URL leesbaar blijft.
Via streamlit_app.py (st.navigation) wordt de URL dan bv.
    .../dashboard?p=opstelling
Wisselen naar mAICoach en terug start deze pagina zonder ?p=, dus weer op
"Mijn profiel" - dat is het bestaande gedrag van st.navigation.
"""
import sys
from pathlib import Path

# PADEL_ANALYSIS_SYSPATH_CHICKEN_EGG_FIX_2026-09-14: MOET vóór de
# "import dashboard_common"-regel hieronder staan - zie uitleg hierboven.
_ROOT = Path(__file__).parent
for _p in [str(_ROOT), str(_ROOT / "scraper")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
# PERF_TIMING_ROLLOUT_2026-09-29: repo-root ACHTERAAN toevoegen (append, niet
# insert), zodat een module in PadelAnalysis/ nooit door een gelijknamige in
# de root overschaduwd wordt. Enkel perf_timing.py staat bewust in de root.
if str(_ROOT.parent) not in sys.path:
    sys.path.append(str(_ROOT.parent))

import streamlit as st

try:
    import perf_timing as perf
except Exception:  # noqa: BLE001  pragma: no cover
    class _PerfNoop:
        @staticmethod
        def reset():
            pass

        @staticmethod
        def render_panel(**_kwargs):
            pass

        @staticmethod
        def step(_label):
            from contextlib import nullcontext
            return nullcontext()

    perf = _PerfNoop()

# No-op via streamlit_app.py (centraal beheerd); actief bij standalone gebruik.
perf.reset()

with perf.step("Padel: imports (dashboard_common + pagina-modules)"):
    import dashboard_common as dc  # zorgt (nogmaals, onschadelijk) voor dezelfde path-setup + alle gedeelde imports
    from page_add_player import page_add_player
    from page_lineup_lab import page_lineup_lab
    from page_my_profile import page_my_profile
    from page_players import page_players

try:
    st.set_page_config(page_title="Padel Analysis", page_icon="🎾", layout="wide", initial_sidebar_state="collapsed")
except Exception:
    pass

# ─────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* Clean card-style metric */
[data-testid="stMetric"] {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 12px 16px;
    border-left: 4px solid #1a73e8;
}
[data-testid="stMetricLabel"] { font-size: 0.75rem; color: #666; }
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
/* Tab styling */
.stTabs [data-baseweb="tab"] { font-size: 0.85rem; padding: 6px 14px; }
.stTabs [aria-selected="true"] { border-bottom: 3px solid #1a73e8 !important; }
/* Win badge */
.badge-win  { background:#d4edda; color:#155724; border-radius:4px; padding:2px 8px; font-size:0.8rem; font-weight:600; }
.badge-loss { background:#f8d7da; color:#721c24; border-radius:4px; padding:2px 8px; font-size:0.8rem; font-weight:600; }
/* Section header */
.section-header { font-size:1.1rem; font-weight:700; margin-bottom:8px; color:#1a1a1a; border-bottom:2px solid #e0e0e0; padding-bottom:4px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Navigation
# ─────────────────────────────────────────────
PAGES = ["👤 Mijn profiel", "🔍 Spelers", "➕ Speler toevoegen", "🧩 Opstelling-analyse"]
# PADEL_ANALYSIS_PAGE_IN_URL_2026-09-29: korte URL-namen per pagina (?p=...).
PAGE_SLUGS = {
    "👤 Mijn profiel": "profiel",
    "🔍 Spelers": "spelers",
    "➕ Speler toevoegen": "toevoegen",
    "🧩 Opstelling-analyse": "opstelling",
}
_SLUG_TO_PAGE = {slug: naam for naam, slug in PAGE_SLUGS.items()}


def _page_from_url() -> str:
    """Pagina uit ?p=<slug>, of PAGES[0] als die ontbreekt/onbekend is."""
    try:
        slug = st.query_params.get("p")
    except Exception:  # noqa: BLE001 - URL mag de navigatie nooit breken
        slug = None
    return _SLUG_TO_PAGE.get(str(slug or "").strip().lower(), PAGES[0])


def _sync_page_to_url(page_name: str) -> None:
    """Zet ?p=<slug> gelijk aan de huidige pagina (enkel als die afwijkt)."""
    slug = PAGE_SLUGS.get(page_name)
    if not slug:
        return
    try:
        if st.query_params.get("p") != slug:
            st.query_params["p"] = slug
    except Exception:  # noqa: BLE001
        pass


if "page" not in st.session_state or st.session_state["page"] not in PAGES:
    # Eerste run van deze sessie (bv. na F5): pagina uit de URL.
    st.session_state["page"] = _page_from_url()
nav_col = st.columns(len(PAGES))
for i, p in enumerate(PAGES):
    if nav_col[i].button(p, use_container_width=True,
                          type="primary" if st.session_state["page"] == p else "secondary"):
        st.session_state["page"] = p
        _sync_page_to_url(p)
        st.rerun()
st.divider()
page = st.session_state["page"]
# Ook sprongen via session_state (bv. _go_to_player) komen zo in de URL.
_sync_page_to_url(page)

# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
with perf.step(f"Padel: {page}"):
    if page == "➕ Speler toevoegen":
        page_add_player()
    elif page == "🧩 Opstelling-analyse":
        page_lineup_lab()
    elif page == "👤 Mijn profiel":
        page_my_profile()
    else:
        page_players()

# PERF_TIMING_ROLLOUT_2026-09-29: enkel actief bij standalone gebruik.
perf.render_panel()
