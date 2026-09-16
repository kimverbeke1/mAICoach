"""
manual_poule_input.py — Streamlit-component om handmatig een poule-URL te
plakken voor een speler waarvoor de automatische afleiding niets vond.

Locatie: PadelAnalysis/manual_poule_input.py
(naast dashboard.py / page_lineup_lab.py, zodat `import manual_poule_input`
werkt zonder extra path-gedoe)

--------------------------------------------------------------------------
WAAROM DIT BESTAAT (en waarom het oude invoerveld niet volstond)
--------------------------------------------------------------------------
page_lineup_lab.py had al een "Poule/tabel-URL (eenmalig)"-veld dat de URL
bewaarde via dashboard_common._save_poule_url(). Dat schrijft naar het
AUTOMATISCHE veld `poule_reeks_url` — exact hetzelfde veld dat
poule_playwright.update_player_poule() bij elke run zelf overschrijft met
de URL die het afleidt uit het meest recente uitslagenblad.

Gevolg: je plakte een URL, het werkte, en na de eerstvolgende dagelijkse
GitHub Actions-run was ze weer weg (of vervangen door een reeks uit een
afgelopen seizoen). "Onthouden" hield dus niet.

Dit component schrijft naar `poule_reeks_url_manual`
(poule_playwright.FIELD_MANUAL_POULE_URL). Dat veld wordt door
update_player_poule() ALS EERSTE gelezen en heeft voorrang op zowel de
gecachete als de afgeleide URL — ook bij force=True. Eenmaal plakken
volstaat dus echt.

--------------------------------------------------------------------------
PADEL_ANALYSIS_MANUAL_URL_ALWAYS_VISIBLE_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): "de manuele poule url moet je idd maar 1 keer geven maar hij
wordt wel niet meer getoond." Oorzaak: de expander gebruikte
    with st.expander(titel, expanded=expanded and not saved):
Zodra saved=True (de URL is al ingesteld), wordt de expander ALTIJD
gecollapsed — ongeacht welke waarde de aanroeper voor `expanded` meegaf. De
bevestiging ("Er staat een handmatige poule-URL op dit profiel" + de URL
zelf) stond dus enkel zichtbaar bij een expliciete klik op de kop, en werd
in de praktijk nooit meer gezien.

Fix: een BEKNOPTE, ALTIJD zichtbare regel (buiten de expander, dus nooit
ingeklapt) toont voortaan meteen of er een handmatige URL actief is en
welke poule/spelgroep die aanwijst. De expander zelf blijft daarnaast
bestaan (nu altijd default ingeklapt bij een reeds ingestelde URL, net als
voorheen) voor de details, het volledige URL-veld en de wijzig-/
verwijderknoppen — maar je hoeft 'm niet meer open te klikken om te
bevestigen dat de URL er nog staat.

--------------------------------------------------------------------------
GEBRUIK
--------------------------------------------------------------------------
    import manual_poule_input
    if not next_match:
        manual_poule_input.render(player_id, player_name=naam)

De component doet zelf de validatie, de opslag én (indien Playwright
beschikbaar is) meteen een verse scrape van de geplakte reeks, zodat de
gebruiker direct ziet of de URL klopt.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import streamlit as st

# --- path setup: scraper/ ligt een niveau dieper ---
_HERE = Path(__file__).parent
for _p in [str(_HERE), str(_HERE / "scraper")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402

BASE_URL = "https://www.tennisenpadelvlaanderen.be"

# Veldnamen komen uit poule_playwright zodat er maar EEN bron van waarheid is.
# Faalt die import (bv. omdat Playwright niet geinstalleerd is op Streamlit
# Cloud), dan vallen we terug op de letterlijke namen: het OPSLAAN van een URL
# heeft immers geen browser nodig.
try:
    import poule_playwright as pp
    FIELD_MANUAL = pp.FIELD_MANUAL_POULE_URL
    FIELD_AUTO = pp.FIELD_POULE_URL
    FIELD_POULE_LABEL = pp.FIELD_POULE_LABEL
    _HAS_PLAYWRIGHT = True
except Exception:  # noqa: BLE001
    pp = None
    FIELD_MANUAL = "poule_reeks_url_manual"
    FIELD_AUTO = "poule_reeks_url"
    FIELD_POULE_LABEL = "poule_label"
    _HAS_PLAYWRIGHT = False


# ---------------------------------------------------------------------------
# Validatie
# ---------------------------------------------------------------------------
def validate_poule_url(url: str) -> tuple[bool, str, dict]:
    """Controleer of dit een bruikbare poule-tabel-URL is.

    Returns (ok, boodschap, ids). Bij ok=False is de boodschap een uitleg die
    rechtstreeks aan de gebruiker getoond kan worden.
    """
    url = (url or "").strip().strip('"').strip("'")
    if not url:
        return False, "Geen URL ingevuld.", {}

    if not url.lower().startswith("http"):
        url = BASE_URL + ("" if url.startswith("/") else "/") + url

    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False, "Dit is geen geldige URL.", {}

    if "tennisenpadelvlaanderen.be" not in (parsed.netloc or "").lower():
        return False, (
            "Deze URL komt niet van tennisenpadelvlaanderen.be. "
            "Open de poule/tabel op de site en kopieer de adresbalk."
        ), {}

    qs = {k.lower(): v[0] for k, v in parse_qs(parsed.query).items() if v}
    ids = {
        "pouleId": qs.get("pouleid"),
        "afdelingId": qs.get("afdelingid"),
        "spelgroepId": qs.get("spelgroepid"),
        "matchId": qs.get("matchid"),
    }

    path = (parsed.path or "").lower()

    # Veelgemaakte vergissing: het uitslagenblad van EEN wedstrijd plakken
    # in plaats van de poule-tabel van de hele reeks.
    if "uitslagenblad" in path:
        return False, (
            "Dit is een **uitslagenblad** van één wedstrijd, niet de poule-tabel. "
            "Klik op de site door naar het overzicht met alle wedstrijden van de "
            "reeks (met de tabs 'Voorronde' en 'Eindronde') en kopieer die URL."
        ), ids

    if "poule" not in path and not ids.get("pouleId"):
        return False, (
            "In deze URL staat geen `pouleId` en het adres verwijst niet naar een "
            "poule-tabel. Controleer of je de juiste pagina gekopieerd hebt."
        ), ids

    if not ids.get("pouleId"):
        return False, (
            "Er ontbreekt een `pouleId` in deze URL. Zonder dat nummer kan de app "
            "niet weten welke poule ze moet inlezen — de pagina bevat er meerdere."
        ), ids

    return True, "", ids


def normalize_poule_url(url: str) -> str:
    url = (url or "").strip().strip('"').strip("'").replace("&amp;", "&")
    if url and not url.lower().startswith("http"):
        url = BASE_URL + ("" if url.startswith("/") else "/") + url
    return url


def _short_url_summary(url: str) -> str:
    """PADEL_ANALYSIS_MANUAL_URL_ALWAYS_VISIBLE_2026-09-16: beknopte,
    herkenbare samenvatting van de URL (pouleId + spelgroepId) voor de
    altijd-zichtbare regel, zodat je niet de hele lange URL hoeft te tonen
    om toch te bevestigen WELKE poule er actief staat."""
    try:
        qs = {k.lower(): v[0] for k, v in parse_qs(urlparse(url).query).items() if v}
    except Exception:  # noqa: BLE001
        return url
    pouleid = qs.get("pouleid")
    spelgroepid = qs.get("spelgroepid")
    if pouleid or spelgroepid:
        onderdelen = []
        if pouleid:
            onderdelen.append(f"pouleId={pouleid}")
        if spelgroepid:
            onderdelen.append(f"spelgroepId={spelgroepid}")
        return ", ".join(onderdelen)
    return url


# ---------------------------------------------------------------------------
# Opslag
# ---------------------------------------------------------------------------
def save_manual_poule_url(player_id: str, url: str) -> None:
    """Bewaar de handmatige poule-URL op het profiel van de speler.

    Schrijft bewust NAAR BEIDE velden:
      - FIELD_MANUAL : de blijvende override (wordt nooit overschreven door
                       de scraper),
      - FIELD_AUTO   : zodat schermen die vandaag enkel het automatische veld
                       lezen (_get_saved_poule_url) meteen werken.
    """
    schoon = normalize_poule_url(url)
    fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
        {FIELD_MANUAL: schoon, FIELD_AUTO: schoon}, merge=True
    )


def clear_manual_poule_url(player_id: str) -> None:
    """Verwijder de handmatige URL, zodat de automatische afleiding het weer
    overneemt."""
    fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
        {FIELD_MANUAL: ""}, merge=True
    )


def get_saved_manual_url(player_id: str) -> Optional[str]:
    try:
        profile = fb.get_player_profile(player_id) or {}
    except Exception:  # noqa: BLE001
        return None
    return (profile.get(FIELD_MANUAL) or "").strip() or None


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def render(
    player_id: str,
    player_name: Optional[str] = None,
    expanded: bool = True,
    key_prefix: str = "manual_poule",
) -> Optional[dict]:
    """Toon het invoerveld voor een handmatige poule-URL.

    Returns het resultaat van de scrape als die net uitgevoerd is, anders None.
    """
    naam = player_name or str(player_id)
    saved = get_saved_manual_url(player_id)
    key = f"{key_prefix}_{player_id}"

    # PADEL_ANALYSIS_MANUAL_URL_ALWAYS_VISIBLE_2026-09-16: deze regel staat
    # ALTIJD zichtbaar, ook als de expander eronder ingeklapt is/blijft.
    if saved:
        st.caption(f"🔗 Handmatige poule-URL actief ({_short_url_summary(saved)})")

    titel = "🔗 Poule-URL handmatig ingesteld" if saved else "🔗 Poule-URL handmatig instellen"
    with st.expander(titel, expanded=expanded and not saved):
        if saved:
            st.success("Er staat een handmatige poule-URL op dit profiel.")
            st.code(saved, language=None)
            st.caption(
                "Deze URL heeft voorrang op de automatische afleiding, ook bij de "
                "dagelijkse update. Verwijder ze om terug automatisch te laten zoeken."
            )
        else:
            st.info(
                f"Voor **{naam}** kon geen poule/tabel gevonden worden. Dat gebeurt "
                "wanneer de laatst gekende match uit een afgelopen seizoen komt, of "
                "wanneer de speler nog geen interclubmatch in de database heeft."
            )

        with st.form(key=f"{key}_form"):
            st.markdown(
                "**Zo vind je de juiste URL**\n\n"
                "1. Open tennisenpadelvlaanderen.be en ga naar de interclubreeks "
                "van deze speler.\n"
                "2. Kies het overzicht met álle wedstrijden van de reeks — daar "
                "staan de tabs *Voorronde* en *Eindronde*.\n"
                "3. Kopieer de volledige URL uit de adresbalk en plak ze hieronder."
            )
            url = st.text_input(
                "Poule-URL",
                value=saved or "",
                placeholder=f"{BASE_URL}/interclub-poule-tabel?afdelingId=…&spelgroepId=…&pouleId=…",
                key=f"{key}_input",
            )

            kolom1, kolom2 = st.columns([3, 1])
            with kolom1:
                opslaan = st.form_submit_button("Opslaan en schema ophalen", type="primary")
            with kolom2:
                verwijderen = st.form_submit_button("Verwijderen", disabled=not saved)

        if verwijderen and saved:
            try:
                clear_manual_poule_url(player_id)
                st.success("Handmatige URL verwijderd. De app zoekt weer automatisch.")
                _rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Verwijderen mislukt: {e}")
            return None

        if not opslaan:
            return None

        ok, boodschap, ids = validate_poule_url(url)
        if not ok:
            st.error(boodschap)
            return None

        schone_url = normalize_poule_url(url)

        try:
            save_manual_poule_url(player_id, schone_url)
        except Exception as e:  # noqa: BLE001
            st.error(f"Opslaan in Firestore mislukt: {e}")
            return None

        st.success(f"URL bewaard (pouleId {ids.get('pouleId')}).")

        # Meteen een verse scrape draaien zodat de gebruiker direct ziet of de
        # reeks klopt. Op Streamlit Cloud is Playwright niet altijd
        # beschikbaar; dan blijft de URL staan voor de volgende Actions-run.
        if not _HAS_PLAYWRIGHT:
            st.info(
                "Het schema wordt opgehaald bij de volgende geplande update. "
                "De URL is bewaard, je hoeft niets meer te doen."
            )
            _rerun()
            return None

        with st.spinner("Schema ophalen uit de opgegeven reeks…"):
            try:
                resultaat = pp.update_player_poule(player_id, headless=True)
            except Exception as e:  # noqa: BLE001
                st.warning(
                    f"De URL is bewaard, maar het schema kon nu niet opgehaald worden: {e}\n\n"
                    "Dat wordt automatisch opnieuw geprobeerd bij de volgende update."
                )
                return None

        if resultaat.get("error"):
            st.warning(f"De URL is bewaard, maar er ging iets mis: {resultaat['error']}")
            return resultaat

        aantal = resultaat.get("fixtures", 0)
        label = resultaat.get(FIELD_POULE_LABEL) or "de opgegeven poule"

        if aantal == 0:
            st.warning(
                f"De URL is bewaard, maar er werden geen wedstrijden gevonden in {label}. "
                "Controleer of je de poule-tabel gekopieerd hebt en niet een ander scherm."
            )
        else:
            st.success(f"{aantal} wedstrijd(en) opgehaald uit {label}.")
            eind = resultaat.get("eindronde", 0)
            if eind:
                st.caption(f"Daarnaast {eind} eindronde-wedstrijd(en) bewaard.")
            _rerun()

        return resultaat


def _rerun() -> None:
    """st.rerun() heet in oudere Streamlit-versies nog experimental_rerun()."""
    for naam in ("rerun", "experimental_rerun"):
        fn = getattr(st, naam, None)
        if callable(fn):
            fn()
            return
