"""
scrape_klassement.py — TVL padel klassementshistoriek scraper V3 compact
Fixes: periode uit dropdown-label, klassement begin periode, defensieve match-count parser.
"""
from __future__ import annotations
import argparse, json, logging, re, time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19 / hersteld 2026-09-24: LAZY
# Playwright-import.
# ---------------------------------------------------------------------------
# Playwright stond hier vroeger als MODULE-NIVEAU import. Gevolg: elke
# UI-module die dit bestand importeerde (opponent_dossier.py, en via de
# importketen dus ook dashboard_common.py en elke pagina) crashte meteen op
# Streamlit Community Cloud, waar Playwright niet geinstalleerd is. Daardoor
# kon build_klassement_url() hieronder - dat zelf geen browser nodig heeft -
# nergens in de UI gebruikt worden.
#
# Nu wordt Playwright pas geimporteerd binnen scrape_klassement() zelf, op
# het moment dat er ook echt gescrapet wordt. De rest van dit bestand
# (URL-opbouw, parsers, klassement_to_history_summary) is puur tekst- en
# HTML-verwerking en blijft overal veilig importeerbaar.
#
# PlaywrightTimeoutError begint als een onschuldige placeholder en wordt
# door _lazy_playwright() vervangen door de echte klasse. _goto() - de enige
# plek die hem gebruikt - draait uitsluitend binnen scrape_klassement(), dus
# altijd NA die herbinding.
PlaywrightTimeoutError = Exception


def _lazy_playwright():
    """Importeert Playwright pas wanneer er effectief gescrapet wordt, en
    bindt meteen de echte TimeoutError-klasse. Geeft sync_playwright terug."""
    global PlaywrightTimeoutError
    from playwright.sync_api import TimeoutError as _Timeout, sync_playwright as _sync
    PlaywrightTimeoutError = _Timeout
    return _sync


logger=logging.getLogger(__name__)
BASE_URL="https://www.tennisenpadelvlaanderen.be"
KLASSEMENT_PARAMS={"tab":"calcPadel","tspid":"80","tdpid":"80","ppid":"81","tscid":"80","pcid":"81"}
MAX_REASONABLE_MATCHES_PER_LEVEL=250

def _build_url(player_id:str)->str: return f"{BASE_URL}/nl/berekening-klassement?{urlencode({'userId':str(player_id),**KLASSEMENT_PARAMS})}"
def _clean(t:Optional[str])->str: return re.sub(r"\s+"," ",t or "").strip()


# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19 / hersteld 2026-09-24
# ---------------------------------------------------------------------------
def build_klassement_url(player_id) -> str:
    """De URL van de officiele TVL-klassementberekeningspagina van een speler.

    Publieke, PLAYWRIGHT-VRIJE variant van _build_url(). Bewust apart, omdat
    opponent_dossier.klassement_link_url() deze functie op module-niveau
    gebruikt om in de UI een "Bekijk officieel klassement op TVL"-knop te
    tonen. Dankzij de lazy import hierboven kan dat nu ook op Streamlit
    Community Cloud, waar geen Playwright beschikbaar is.

    Altijd exact DEZELFDE URL als de scraper zelf bezoekt, zodat wat je in
    de app ziet en wat er gescrapet werd niet uit elkaar kunnen lopen.
    """
    return _build_url(str(player_id))


# Seizoenswoord -> maand waarin die klassementsperiode begint. TVL berekent
# 2x per jaar; deze maanden zijn een BENADERING, uitsluitend bedoeld om de
# periodes CHRONOLOGISCH te kunnen ordenen. Ze worden nooit als exacte
# officiele datum gepresenteerd.
_PERIOD_START_MONTH = {
    "start": 1, "begin": 1, "winter": 1,
    "lente": 3, "voorjaar": 3,
    "zomer": 7, "summer": 7,
    "najaar": 9, "herfst": 9,
}


def period_start_date(label) -> Optional[str]:
    """Zet een periode-label om naar een ISO-datum ("Zomerklassement 2026"
    -> "2026-07-01"), of None als dat niet betrouwbaar kan.

    PADEL_ANALYSIS_PERIOD_START_DATE_RESTORE_2026-09-24
    ----------------------------------------------------------------------
    Deze functie WERD AL AANGEROEPEN op twee plaatsen (_parse() en
    klassement_to_history_summary()), telkens defensief afgeschermd met

        period_start_date(label)

    maar ze was nergens gedefinieerd. Die check gaf dus ALTIJD None, en het
    veld "datum" bleef in elke historiekrij leeg.

    Waarom dat merkbaar is: opponent_dossier._history_rows() sorteert bij
    voorkeur op die datum en valt zonder datum terug op een tekstuele
    periode-vergelijking. Twee periodes in hetzelfde jaar ("Startklassement
    2026" en "Zomerklassement 2026") krijgen daar dezelfde sorteersleutel en
    worden dan alfabetisch geordend - wat er toevallig juist uitkomt, maar
    op geen enkele inhoudelijke regel berust.

    Er wordt NOOIT een jaartal verzonnen: staat er geen jaar in het label,
    dan is het resultaat None en blijft de bestaande terugval gelden.
    """
    tekst = _clean(label).lower()
    if not tekst:
        return None
    jaar = re.search(r"(20\d{2})", tekst)
    if not jaar:
        return None
    maand = next((m for woord, m in _PERIOD_START_MONTH.items() if woord in tekst), None)
    if maand is None:
        return None
    return f"{jaar.group(1)}-{maand:02d}-01"

def _progress(cb,i,total,label,status):
    if not cb: return
    for args in ((i,total,label,status),(i,total,label),(i,total)):
        try: cb(*args); return
        except TypeError: continue
        except Exception: return
def _safe_attr(loc,n):
    try: return loc.get_attribute(n) or ""
    except Exception: return ""
def _safe_text(loc):
    try: return loc.text_content(timeout=1000) or ""
    except Exception: return ""
def _goto(page,url):
    try: page.goto(url,wait_until="commit",timeout=60000)
    except PlaywrightTimeoutError: logger.warning("page.goto timeout; ga verder")
    try: page.wait_for_selector("body",state="attached",timeout=20000)
    except Exception: pass
    page.wait_for_timeout(2500)
def _dismiss_cookies(page):
    for txt in ["Alle cookies accepteren","Cookies accepteren","Accepteren","Akkoord","Accept all cookies","Accept cookies","Accept","OK"]:
        try:
            loc=page.get_by_text(txt,exact=False)
            if loc.count()>0 and loc.first.is_visible(): loc.first.click(timeout=2500); page.wait_for_timeout(1000); return
        except Exception: pass
def _try_activate_padel_tab(page):
    for txt in ["Padel","Berekening padel","Padel klassement","Klassement Padel"]:
        try:
            loc=page.get_by_text(txt,exact=False)
            for i in range(min(loc.count(),5)):
                it=loc.nth(i)
                if it.is_visible(): it.click(timeout=2500); page.wait_for_timeout(1800); return True
        except Exception: pass
    return False
def _wait(page):
    for st in ["domcontentloaded","networkidle"]:
        try: page.wait_for_load_state(st,timeout=6000)
        except Exception: pass
    try: page.wait_for_function("() => !window.PrimeFaces || !PrimeFaces.ajax || !PrimeFaces.ajax.Queue || (typeof PrimeFaces.ajax.Queue.isEmpty === 'function' ? PrimeFaces.ajax.Queue.isEmpty() : true)",timeout=6000)
    except Exception: pass
    page.wait_for_timeout(1000)
def _debug(page):
    print("\n=== DEBUG SELECTORS ===")
    for css in ["select.year-selector","select","form","[id*='Padel']","[id*='Tennis']"]:
        try:
            loc=page.locator(css); print(f"\nCSS: {css} | count={loc.count()}")
            for i in range(min(loc.count(),8)):
                it=loc.nth(i); print(i,_safe_attr(it,"id"),_safe_attr(it,"name"),_safe_attr(it,"onchange")[:200])
        except Exception as e: print(css,e)
def _selects(page):
    out=[]; seen=set()
    for css in ["select.year-selector","select[id*='period' i]","select[name*='period' i]","select"]:
        try:
            loc=page.locator(css)
            for i in range(loc.count()):
                s=loc.nth(i); key=(_safe_attr(s,"id"),_safe_attr(s,"name"),i,css)
                if key not in seen: seen.add(key); out.append(s)
        except Exception: pass
    return out
def _score(s):
    h=" ".join([_safe_attr(s,"id"),_safe_attr(s,"name"),_safe_attr(s,"class"),_safe_attr(s,"onchange"),_safe_text(s)]).lower(); sc=0
    if "padel" in h: sc+=100
    if "tennis" in h: sc-=100
    for w,p in [("klassement",30),("startklassement",8),("zomerklassement",8),("winterklassement",5),("voorjaarsklassement",5),("najaarsklassement",5),("period",5),("year-selector",5)]:
        if w in h: sc+=p
    try:
        if s.locator("option").count()>=2: sc+=5
    except Exception: pass
    return sc
def _get_sel(page,debug=False):
    ss=_selects(page)
    if debug: _debug(page)
    if not ss: return None
    scored=sorted([(s,_score(s)) for s in ss],key=lambda x:x[1],reverse=True)
    if debug:
        print("\n=== SELECT SCORE ===")
        for i,(s,sc) in enumerate(scored[:10]): print(i,sc,_safe_attr(s,"id"),_safe_attr(s,"name"))
    return scored[0][0] if scored[0][1]>=20 else None
def _options(sel):
    if sel is None: return []
    try: raw=sel.locator("option").evaluate_all("(opts)=>opts.map(o=>({label:(o.textContent||'').trim(),value:o.value}))")
    except Exception: return []
    out=[]; seen=set()
    for o in raw:
        label=_clean(o.get("label")); value=o.get("value")
        if label and "klassement" in label.lower() and (label,value) not in seen: seen.add((label,value)); out.append({"label":label,"value":value})
    return out
def _select(sel,value,label):
    h=sel.element_handle()
    if h is None: raise RuntimeError(f"Geen element_handle voor {label}")
    h.evaluate("(el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true,cancelable:true}));el.dispatchEvent(new Event('change',{bubbles:true,cancelable:true}));if(typeof el.onchange==='function'){try{el.onchange();}catch(e){}}}",value)
def _pct(t):
    m=re.search(r"(\d+(?:[,.]\d+)?)\s*%",str(t or ""));
    if not m: return None
    try: return float(m.group(1).replace(",","."))
    except Exception: return None
def _smallint(v):
    m=re.search(r"\b\d{1,3}\b",str(v or ""));
    if not m: return None
    n=int(m.group(0)); return n if 0<=n<=MAX_REASONABLE_MATCHES_PER_LEVEL else None
def _first(patterns,text):
    for p in patterns:
        m=re.search(p,text,flags=re.I)
        if m: return _clean(m.group(1))
    return None
def _rank(v):
    m=re.search(r"\bP\s*(\d{2,4})\b",str(v or ""),flags=re.I); return f"P{m.group(1)}" if m else None
def _cnt(cells,row):
    for p in [r"(?:aantal\s*)?(?:matchen|matches|wedstrijden|wedstrijd)\s*[:\-]?\s*(\d{1,3})\b",r"\b(\d{1,3})\s*(?:matchen|matches|wedstrijden|wedstrijd)\b"]:
        m=re.search(p,row,flags=re.I)
        if m:
            n=_smallint(m.group(1))
            if n is not None: return n
    ints=[]
    for c in cells:
        cc=_clean(c)
        if re.fullmatch(r"\d{1,3}",cc):
            n=_smallint(cc)
            if n is not None: ints.append(n)
    return ints[-1] if ints else None


def _padel_form_html(page) -> str | None:
    """Return HTML van enkel de padel-form, zodat tennis/sidebar-teksten niet mee geparsed worden."""
    selectors = [
        "form[id*='playerCompleteResultsFormPadel']",
        "form[name*='playerCompleteResultsFormPadel']",
        "[id*='playerCompleteResultsFormPadel']",
        "[id*='calcPadel']",
    ]
    for css in selectors:
        try:
            loc = page.locator(css)
            if loc.count() > 0:
                html = loc.first.inner_html(timeout=3000)
                if html and len(html) > 100:
                    return html
        except Exception:
            pass
    return None


def _extract_selected_period_klassement_from_text(text: str) -> str | None:
    """
    Haalt het klassement van de GESELECTEERDE periode uit de padel-form.

    Belangrijk: niet 'vorig klassement' en niet willekeurige P-waarden uit winrate-rijen nemen.
    We zoeken expliciet naar labels rond 'geselecteerde periode'.
    """
    clean = _clean(text)

    patterns = [
        r"klassement\s+(?:van\s+de\s+)?geselecteerde\s+periode\s*[:\-]?\s*(P\s*\d{2,4})",
        r"klassement\s+(?:voor\s+de\s+)?geselecteerde\s+periode\s*[:\-]?\s*(P\s*\d{2,4})",
        r"geselecteerde\s+periode\s*[:\-]?\s*(?:klassement)?\s*[:\-]?\s*(P\s*\d{2,4})",
        r"klassement\s+periode\s*[:\-]?\s*(P\s*\d{2,4})",
        r"huidig(?:e)?\s+klassement\s*[:\-]?\s*(P\s*\d{2,4})",
    ]
    for pat in patterns:
        m = re.search(pat, clean, flags=re.I)
        if m:
            return _rank(m.group(1))
    return None


def _label_then_rank(text: str) -> str | None:
    """Zoekt het EERSTE P-getal dat NA het label 'geselecteerde periode'
    komt. Een P-waarde die VOOR het label staat hoort bij iets anders en
    mag nooit meegenomen worden."""
    clean = _clean(text)
    m = re.search(r"geselecteerde\s+periode", clean, flags=re.I)
    if not m:
        return None
    return _rank(clean[m.end():])


def _extract_selected_period_klassement_from_html(html: str) -> str | None:
    """Haalt het klassement van de GESELECTEERDE periode uit de padel-form.

    PADEL_ANALYSIS_SELECTED_PERIOD_WRAPPER_FIX_2026-09-24
    ----------------------------------------------------------------------
    ROOT CAUSE (gereproduceerd, geen vermoeden): de vorige implementatie deed

        for row in soup.find_all(["tr", "li", "div"]):
            if "geselecteerde periode" not in row_text.lower(): continue
            for c in reversed(cells):
                r = _rank(c)
                if r: return r

    Twee eigenschappen daarvan zijn samen fataal:

      1. find_all() levert elementen in DOCUMENTVOLGORDE, en dat betekent bij
         geneste elementen: BUITENSTE EERST. Een grote wrapper-<div> die
         ergens diep vanbinnen de tekst "geselecteerde periode" bevat, matcht
         dus VOOR de kleine tabelrij waar het label echt staat.
      2. reversed(cells) pakt vervolgens de LAATSTE rank-achtige waarde in
         dat hele blok. In zo'n wrapper is dat niet het klassement bij het
         label, maar gewoon de laatste P-waarde die toevallig in dat blok
         voorkomt - in de praktijk een rij uit de niveau-/winratetabel.

    Concreet bewijs: Kim Verbeke (1790766) kreeg P300 terwijl hij officieel
    P200 is en virtueel P100. Die P300 kwam uit zijn niveau-tabel (hij
    speelde 3 matchen op P300-niveau) en stond simpelweg als laatste in de
    wrapper. Bij Baete Evelien (615023) gaf dezelfde fout toevallig wel het
    juiste cijfer - vandaar dat het bij de ene speler klopte en bij de
    andere niet, wat de diagnose lang vertroebeld heeft.

    FIX, drie samenwerkende regels:
      1. Verzamel ALLE elementen met het label en neem het KLEINSTE
         (minste tekens). Dat is per definitie de label-rij zelf en nooit
         een wrapper die de halve pagina omvat.
      2. Neem binnen dat element enkel een P-waarde die NA het label komt
         (_label_then_rank). Een waarde ervoor hoort bij iets anders.
      3. Negeer elementen die duidelijk de niveau-/winratetabel bevatten
         (herkenbaar aan meerdere P-waarden met percentages) - daar staat
         nooit een klassement, enkel tegenstander-niveaus.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        return None

    kandidaten = []
    for el in soup.find_all(["tr", "li", "div", "p", "span"]):
        tekst = _clean(el.get_text(" "))
        if "geselecteerde periode" not in tekst.lower():
            continue
        # Bevat dit element de niveau-/winratetabel? Dan is elke P-waarde
        # erin een tegenstander-niveau, geen klassement.
        if len(re.findall(r"\d+(?:[,.]\d+)?\s*%", tekst)) >= 2:
            continue
        kandidaten.append((len(tekst), el, tekst))

    if kandidaten:
        # Kleinste eerst: de label-rij zelf, niet een omhullende wrapper.
        kandidaten.sort(key=lambda k: k[0])
        for _lengte, el, tekst in kandidaten:
            # Eerst de cellen NA de cel met het label (klassieke
            # label-links/waarde-rechts-opbouw in een tabelrij).
            cellen = [_clean(c.get_text(" ")) for c in el.find_all(["td", "th", "span", "label", "strong"])]
            label_index = next(
                (i for i, c in enumerate(cellen) if "geselecteerde periode" in c.lower()),
                None,
            )
            if label_index is not None:
                for c in cellen[label_index + 1:]:
                    r = _rank(c)
                    if r:
                        return r
            # Anders: het eerste P-getal na het label in de platte tekst.
            r = _label_then_rank(tekst)
            if r:
                return r

    # Tekst-gebaseerde fallback op de volledige padel-form, met dezelfde
    # regel "enkel wat NA het label komt".
    volledige_tekst = _clean(soup.get_text(" "))
    r = _label_then_rank(volledige_tekst)
    if r:
        return r
    return _extract_selected_period_klassement_from_text(volledige_tekst)


def _parse(html, selected_label=None):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = _clean(soup.get_text(" "))
    niveaus = []
    seen = set()

    for row in soup.find_all(["tr", "li", "div", "section", "article"]):
        cells = [_clean(c.get_text(" ")) for c in row.find_all(["td", "th", "span"])]
        rt = _clean(row.get_text(" "))
        nm = re.search(r"\bP\s*(\d{2,4})\b", rt, flags=re.I)
        if not nm:
            continue
        niv = f"P{nm.group(1)}"
        wr = _pct(rt)
        aantal = _cnt(cells, rt)
        if wr is None and aantal is None:
            continue
        key = (niv, wr, aantal)
        if key in seen:
            continue
        seen.add(key)
        niveaus.append({"niveau": niv, "winstratio": wr, "aantal_matchen": aantal})

    selected_period_klassement = _extract_selected_period_klassement_from_html(str(soup))

    vorig = _rank(_first([
        r"vorig(?:e)?\s+klassement\s*[:\-]?\s*(P\s*\d{2,4})",
        r"klassement\s+vorige\s+periode\s*[:\-]?\s*(P\s*\d{2,4})",
        r"vorige\s+periode\s*[:\-]?\s*(P\s*\d{2,4})",
    ], text))
    berekend = _rank(_first([
        r"berekend(?:e)?\s+klassement\s*[:\-]?\s*(P\s*\d{2,4})",
        r"nieuw(?:e)?\s+klassement\s*[:\-]?\s*(P\s*\d{2,4})",
        r"klassement\s+deze\s+periode\s*[:\-]?\s*(P\s*\d{2,4})",
    ], text))

    begin_klassement = selected_period_klassement or vorig or berekend

    return {
        "niveau_data": niveaus,
        "datum": period_start_date(selected_label),
        "begin_klassement": begin_klassement,
        "selected_period_klassement": selected_period_klassement,
        "vorig_klassement": vorig,
        "berekend_klassement": berekend,
        "periodeomschrijving": selected_label,
    }

def scrape_klassement(player_id,max_periods=None,headless=True,delay_between_periods=1.2,progress_callback=None,debug=False):
    url=_build_url(player_id); results=[]
    # PADEL_ANALYSIS_LAZY_PLAYWRIGHT_2026-09-24: hier, en enkel hier, is een
    # echte browser nodig.
    sync_playwright = _lazy_playwright()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=headless); ctx=browser.new_context(viewport={"width":1440,"height":1100},user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page=ctx.new_page(); page.set_default_timeout(15000)
        try:
            _progress(progress_callback,0,0,"Pagina openen","starting"); _goto(page,url); _dismiss_cookies(page); _try_activate_padel_tab(page); _wait(page)
            sel=_get_sel(page,debug); opts=_options(sel)
            if not opts:
                Path(__file__).with_name("klassement_debug.html").write_text(page.content(),encoding="utf-8")
                parsed=_parse(_padel_form_html(page) or page.content(), "Huidige pagina"); return [{"label":"Huidige pagina","value":None,**parsed}]
            if max_periods: opts=opts[:int(max_periods)]
            total=len(opts)
            for i,o in enumerate(opts,start=1):
                label,value=o["label"],o["value"]; _progress(progress_callback,i,total,label,"fetching")
                try:
                    sel=_get_sel(page,False); _select(sel,value,label); _wait(page)
                    if delay_between_periods and delay_between_periods>0: time.sleep(delay_between_periods)
                    results.append({"label":label,"value":value,**_parse(_padel_form_html(page) or page.content(), label)}); _progress(progress_callback,i,total,label,"ok")
                except Exception as e:
                    logger.exception("Selectie mislukt voor %s",label); results.append({"label":label,"value":value,"niveau_data":[],"begin_klassement":None,"vorig_klassement":None,"berekend_klassement":None,"verklaring":None,"periodeomschrijving":label,"error":str(e)}); _progress(progress_callback,i,total,label,"error")
            return results
        finally: ctx.close(); browser.close()
# PADEL_ANALYSIS_DOMINANT_LEVEL_FIX_2026-09-23: versiestempel, zodat in de
# logoutput meteen zichtbaar is of de gefixte versie effectief draait.
KLASSEMENT_PARSER_VERSION = "2026-09-24-wrapper-fix+url+datum"


def klassement_to_history_summary(periods):
    """
    Compacte historiek voor dashboard.py.

    Reconstructie op basis van TVL-output:
    - De nieuwste periode krijgt het OFFICIELE klassement van de geselecteerde
      periode, zoals letterlijk op de TVL-pagina zelf vermeld.
    - Oudere periodes krijgen het vorig_klassement van de eerstvolgende
      nieuwere periode.

    PADEL_ANALYSIS_DOMINANT_LEVEL_FIX_2026-09-23 (op verzoek van Kim: "de
    ganse klassementshistoriek komt niet van padelstat [...] dus daar kan
    brondata ook nog verkeerd zitten" - dat klopt, en dit was de oorzaak)
    ----------------------------------------------------------------------
    ROOT CAUSE: voor de NIEUWSTE periode (i == 0) stond _dominant_level()
    VOORAAN in de or-keten. Die functie geeft echter NIET het klassement
    terug, maar het niveau waarop de speler de MEESTE MATCHEN speelde - een
    frequentietelling over niveau_data. Zolang er ook maar 1 rij in
    niveau_data stond, won die telling het altijd van het echte, uit de
    pagina geparste cijfer (selected_period_klassement), dat pas op de
    TWEEDE plaats in dezelfde keten stond en dus nooit aan bod kwam.

    Concreet bevestigd: Baete Evelien (615023) speelde deze periode het
    vaakst tegen P100-niveau en kreeg daardoor "P100" als klassement,
    terwijl haar officiele klassement P200 is (bevestigd via de padelstat-
    snapshot: "-> P220, officieel klassement P200"). Hetzelfde patroon gold
    voor Kim zelf (P100 i.p.v. P200) en in principe voor ELKE speler - zie
    ook PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19 in
    opponent_dossier.py, waar dit eerder al als "virtueel vs officieel"
    zichtbaar werd maar de oorzaak hier bleef zitten.

    FIX: selected_period_klassement (het cijfer dat de parser letterlijk van
    de pagina leest) komt nu EERST. _dominant_level() blijft bestaan als
    LAATSTE terugval, voor het geval de pagina geen enkel expliciet
    klassementsveld bevat - maar dan wordt "klassement_is_afgeleid" op die
    rij gezet, zodat de app een afgeleide schatting nooit meer als officieel
    cijfer kan tonen.

    Oudere periodes (i > 0) blijven ongewijzigd: die gebruikten al
    vorig_klassement van de eerstvolgende nieuwere periode, een echt
    klassementsveld. Vandaar dat enkel het MEEST RECENTE punt fout was.
    """
    def _dominant_level(period):
        scores = {}
        for nd in period.get("niveau_data", []) or []:
            niv = nd.get("niveau")
            if not niv:
                continue
            cnt = nd.get("aantal_matchen")
            if isinstance(cnt, int) and cnt >= 0:
                scores[niv] = scores.get(niv, 0) + cnt
            else:
                scores[niv] = scores.get(niv, 0) + 1
        if not scores:
            return None
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[0][0]

    out = []
    clean_periods = [p for p in (periods or []) if not p.get("error")]

    for i, p in enumerate(clean_periods):
        label = p.get("label") or p.get("periodeomschrijving")

        afgeleid = False

        if i == 0:
            # PADEL_ANALYSIS_DOMINANT_LEVEL_FIX_2026-09-23: echte, van de
            # pagina geparste klassementsvelden EERST; _dominant_level() is
            # nu enkel nog een laatste redmiddel (zie docstring hierboven).
            klassement = (
                p.get("selected_period_klassement")
                or p.get("begin_klassement")
                or p.get("berekend_klassement")
                or p.get("vorig_klassement")
            )
            if not klassement:
                klassement = _dominant_level(p)
                afgeleid = bool(klassement)
        else:
            newer = clean_periods[i - 1]
            klassement = (
                newer.get("vorig_klassement")
                or p.get("selected_period_klassement")
                or p.get("begin_klassement")
                or p.get("vorig_klassement")
                or p.get("berekend_klassement")
            )

        # PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19:
        # opponent_dossier._history_rows() leest dit veld en toont het apart
        # als "Virtueel klassement", naast (nooit in plaats van) het
        # officiele cijfer. Het dominante niveau is geen klassement, maar
        # wel nog altijd een bruikbare indicatie van het niveau waarop
        # effectief gespeeld werd - dus expliciet als zodanig meegegeven
        # i.p.v. weggegooid.
        # PADEL_ANALYSIS_VIRTUEEL_FROM_BEREKEND_2026-09-24: het VIRTUELE
        # klassement is de voorspelling van TVL voor de eerstvolgende
        # officiele berekening. Dat staat op de pagina onder labels als
        # "berekend klassement" / "nieuw klassement" / "klassement deze
        # periode" - precies wat _parse() al als berekend_klassement
        # opslaat, maar wat tot nu toe nergens gebruikt werd.
        #
        # Voorheen stond hier _dominant_level(): het niveau waarop de speler
        # de meeste matchen speelde. Dat is een frequentietelling over
        # tegenstander-niveaus en heeft niets met een klassement te maken.
        # Bevestiging: Kim is virtueel P100, maar zijn dominante niveau was
        # een heel ander cijfer - die twee vallen alleen bij toeval samen.
        #
        # Het dominante niveau blijft wel apart beschikbaar als
        # "dominant_niveau" (beschrijvend, geen klassement), zodat die
        # informatie niet verloren gaat maar ook nooit meer als klassement
        # gepresenteerd kan worden.
        virtueel = p.get("berekend_klassement") if i == 0 else None
        dominant = _dominant_level(p) if i == 0 else None

        out.append({
            "datum": period_start_date(label) if "period_start_date" in globals() else None,
            "periode": label,
            "klassement": klassement,
            "virtueel_klassement": virtueel if virtueel != klassement else None,
            # Beschrijvend: het niveau waarop deze speler de meeste matchen
            # speelde. Nadrukkelijk GEEN klassement - zie hierboven.
            "dominant_niveau": dominant,
            # True zodra "klassement" hierboven niet van de pagina zelf kwam
            # maar afgeleid is uit een frequentietelling - de app kan dit
            # gebruiken om zo'n cijfer nooit als officieel te presenteren.
            "klassement_is_afgeleid": afgeleid,
        })

    return out

def extract_niveau_winrates(periods):
    acc={}; seen=set()
    for p in periods:
        if p.get("error"): continue
        pk=p.get("label") or p.get("value") or p.get("periodeomschrijving") or "?"
        for nd in p.get("niveau_data",[]) or []:
            niv=nd.get("niveau")
            if not niv: continue
            key=(pk,niv,nd.get("winstratio"),nd.get("aantal_matchen"))
            if key in seen: continue
            seen.add(key); acc.setdefault(niv,{"ratios":[],"total_matchen":0})
            if nd.get("winstratio") is not None: acc[niv]["ratios"].append(float(nd["winstratio"]))
            cnt=nd.get("aantal_matchen")
            if isinstance(cnt,int) and 0<=cnt<=MAX_REASONABLE_MATCHES_PER_LEVEL: acc[niv]["total_matchen"]+=cnt
    return {niv:{"winstratio_avg":round(sum(d["ratios"])/len(d["ratios"]),1) if d["ratios"] else None,"total_matchen":d["total_matchen"]} for niv,d in acc.items()}
if __name__=="__main__":
    logging.basicConfig(level=logging.INFO); ap=argparse.ArgumentParser(); ap.add_argument("player_id"); ap.add_argument("--max-periods",type=int); ap.add_argument("--headless",action="store_true"); ap.add_argument("--debug",action="store_true"); a=ap.parse_args(); print(json.dumps(scrape_klassement(a.player_id,a.max_periods,a.headless,debug=a.debug),indent=2,ensure_ascii=False))
