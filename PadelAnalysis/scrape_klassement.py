"""
scrape_klassement.py — TVL padel klassementshistoriek scraper V3 compact
Fixes: periode uit dropdown-label, klassement begin periode, defensieve match-count parser.
"""
from __future__ import annotations
import argparse, json, logging, re, time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
logger=logging.getLogger(__name__)
BASE_URL="https://www.tennisenpadelvlaanderen.be"
KLASSEMENT_PARAMS={"tab":"calcPadel","tspid":"80","tdpid":"80","ppid":"81","tscid":"80","pcid":"81"}
MAX_REASONABLE_MATCHES_PER_LEVEL=250

def _build_url(player_id:str)->str: return f"{BASE_URL}/nl/berekening-klassement?{urlencode({'userId':str(player_id),**KLASSEMENT_PARAMS})}"
def _clean(t:Optional[str])->str: return re.sub(r"\s+"," ",t or "").strip()
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


def _extract_selected_period_klassement_from_html(html: str) -> str | None:
    """Zoekt ook in tabelrijen/cellen naar het label 'geselecteerde periode'."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        return None

    # 1) Rij-gebaseerd: label in één cel, klassement in volgende cel.
    for row in soup.find_all(["tr", "li", "div"]):
        cells = [_clean(c.get_text(" ")) for c in row.find_all(["td", "th", "span", "label", "strong"])]
        row_text = _clean(row.get_text(" "))
        if "geselecteerde periode" not in row_text.lower():
            continue

        # Probeer eerst tegen het einde van de rij, omdat label-links kan staan en waarde rechts.
        for c in reversed(cells):
            r = _rank(c)
            if r:
                return r

        r = _extract_selected_period_klassement_from_text(row_text)
        if r:
            return r

    # 2) Tekst-gebaseerd fallback op de volledige padel-form.
    text = _clean(soup.get_text(" "))
    return _extract_selected_period_klassement_from_text(text)

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
        "datum": period_start_date(selected_label) if "period_start_date" in globals() else None,
        "begin_klassement": begin_klassement,
        "selected_period_klassement": selected_period_klassement,
        "vorig_klassement": vorig,
        "berekend_klassement": berekend,
        "periodeomschrijving": selected_label,
    }

def scrape_klassement(player_id,max_periods=None,headless=True,delay_between_periods=1.2,progress_callback=None,debug=False):
    url=_build_url(player_id); results=[]
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
def klassement_to_history_summary(periods):
    """
    Compacte historiek voor dashboard.py.

    Reconstructie op basis van TVL-output:
    - De nieuwste periode krijgt het dominante niveau uit niveau_data.
    - Oudere periodes krijgen het vorig_klassement van de eerstvolgende nieuwere periode.

    Dit geeft voor de gekende testspeler:
    - Zomerklassement 2026 -> P100
    - Startklassement 2026 -> P200
    - Zomerklassement 2025 -> P50
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

        if i == 0:
            klassement = (
                _dominant_level(p)
                or p.get("selected_period_klassement")
                or p.get("begin_klassement")
                or p.get("vorig_klassement")
                or p.get("berekend_klassement")
            )
        else:
            newer = clean_periods[i - 1]
            klassement = (
                newer.get("vorig_klassement")
                or p.get("selected_period_klassement")
                or p.get("begin_klassement")
                or p.get("vorig_klassement")
                or p.get("berekend_klassement")
            )

        out.append({
            "datum": period_start_date(label) if "period_start_date" in globals() else None,
            "periode": label,
            "klassement": klassement,
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
