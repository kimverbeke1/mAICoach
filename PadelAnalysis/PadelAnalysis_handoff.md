# PadelAnalysis — Handoff / vervolg in nieuwe chat

## Context & architectuur
- **PadelAnalysis** = Streamlit-app, onderdeel van de gecombineerde **`mAICoach`** repo.
- Scrapet padeldata van **tennisenpadelvlaanderen.be (TVL)** → **Firestore**.
- **Cloud-deploy** op Streamlit Community Cloud kan **zelf niet scrapen** (geen Playwright/browser).
- Scrapen gebeurt via **GitHub Actions** (`scrape-padel.yml` → `ci_scrape_all.py`), handmatig (`workflow_dispatch`) of via dagelijkse cron.
- De cloud-app **leest enkel uit Firestore**.
- Repo-pad lokaal: `C:\Users\verbekki\OneDrive - Spraying Systems Co\Private\mAICoach`
- GitHub repo: `kimverbeke1/mAICoach`

### Relevante repo-structuur
```
mAICoach/
├── .github/workflows/scrape-padel.yml
├── PadelAnalysis/
│   ├── dashboard.py
│   ├── schedule_scraper.py
│   ├── lineup_quick.py
│   ├── lineup_lab.py
│   ├── opponent_scout.py
│   ├── opponent_dossier.py
│   ├── player_inline_actions.py
│   ├── cloud_helpers.py
│   ├── firebase_service.py
│   └── scraper/
│       ├── scrape_player.py
│       ├── scraper_v2.py
│       ├── fetch_period_playwright.py
│       ├── poule_playwright.py        (NIEUW — Optie B)
│       ├── ci_scrape_all.py
│       └── requirements-scraper.txt
└── requirements.txt
```

## Vaste werkafspraken (belangrijk!)
1. **Altijd volledige bestanden** aanleveren — nooit snippets/patches/diffs.
2. **Altijd de juiste, definitieve bestandsnaam** — nooit `1.py`/`2.py`.
3. **CRLF** line-endings (Windows-repo).
4. Korte, beknopte communicatie.
5. ⚠️ **ALTIJD eerst de huidige versie uit de repo ophalen vóór je een bestand herschrijft.** De repo bevat vaak verder ontwikkelde versies; er is al meermaals functionaliteit overschreven.

## Omgeving / technische noten
- Lokale test-scrape draaide op **Python 3.14** (na `pip install beautifulsoup4`). `py -3.12` bestaat niet op deze machine → gewoon `python` gebruiken.
- Playwright + Chromium werken lokaal. Op cloud niet (bewust).
- Streamlit secret voor de GitHub-trigger (nodig voor de "ververs"-knoppen):
  ```
  [github]
  token = "ghp_..."   # fine-grained token, Actions: read/write op deze repo
  repo  = "kimverbeke1/mAICoach"
  ```

---

## ✅ Opgelost / werkend

### Overzicht & telling
- **Totaaltelling (52 vs 54):** bleek correct = **52**. Dashboard berekent metrics nu **altijd live uit `doc.matches`** (single source of truth) i.p.v. opgeslagen `stats`. Er is ook **self-heal**: als opgeslagen stats afwijken van de live telling, worden ze één keer teruggeschreven naar Firestore. (`_calc_stats_from_matches`, `_persist_stats_if_needed`)
- **Periode-overzicht miste interclubmatchen:** opgelost door `size` i.p.v. `count("won")` (count sloeg `won=None` over). Zelfde fix in Partners/Tegenstanders.
- De matchen vanaf **week 27** verschijnen nu correct in het periode-overzicht.

### Volgende match (Optie B — Playwright rendert de poule-SPA)
Kernprobleem-keten die is opgelost:
1. **Interclubmatchen hadden nooit een `reeks_url`** (alleen tornooimatchen). De oude filter eiste `reeks_url` → volgende match werkte nooit.
2. De **poule/tabel-pagina** (`/nl/clubdashboard/interclub-poule-tabel?afdelingId=…&spelgroepId=…&pouleId=…`) is **WAF-beschermd + SPA** → platte `requests` geeft 403 / lege shell. Playwright (echte Chromium) rendert ze wél.
3. **`played`-detectie fout:** op de clubdashboard-tabel heeft élke rij (ook toekomstige) een `matchId`. `played = bool(match_id)` markeerde alles als gespeeld → nooit een "volgende" match. **Fix: `played` op basis van SCORE** (score ingevuld = gespeeld; lege score = nog te spelen). Bevestigd op echte data (05/09 = gespeeld, 19/09 = nog te spelen).

**Werkende dataflow:**
```
meest recente interclubmatch.uitslagenblad_url
  → Playwright rendert uitslagenblad → vindt poule-tabel-link (afdelingId/pouleId) = reeks_url
  → Playwright rendert poule-tabel → parse fixtures (schedule_scraper.parse_poule_schedule)
  → schrijf {poule_reeks_url, interclub_schedule, interclub_schedule_scraped_at} naar profiel in Firestore
Cloud dashboard leest 'interclub_schedule' uit Firestore → toont volgende match zonder scrapen.
```
- Lokale test bevestigd: `python poule_playwright.py --poule-url "<poule-url>" --dump poule_dump.html --show` → **15 fixtures geparsed**, incl. de match van **19/09**.

### UI-volgorde Opstelling-analyse
- **Volgende match staat nu bovenaan**, met daaronder de "spelers meenemen"-selectie (`_render_opstelling_scenario`), dan de snelle analyse, dan retrospectieve analyse.
- Scenario-blok gebruikt nu `return` i.p.v. `st.stop()` (in aparte functie), zodat een onvolledige invoer niet de hele pagina verbergt.

### Cloud-knop "Schema nu verversen"
- Toegevoegd in de "Volgende match"-sectie, **enkel op cloud** zichtbaar en enkel als het GitHub-token geconfigureerd is.
- Triggert de bestaande GitHub Actions-workflow (die nu ook de poule-stap meepakt). Website scrapet dus nooit zelf; hij geeft het startsein aan GitHub.

### CI
- `ci_scrape_all.py` roept per speler **best-effort** `poule_playwright.update_player_poule()` aan (lazy import, faalt nooit hard, beïnvloedt exit-code niet). Aanstuurbaar via env `POULE_SCRAPE` (default AAN), `POULE_FORCE`.

---

## 📌 Nog te doen / bevestigen na deploy
1. **Push alle Optie-B-bestanden** en **reboot de Streamlit-app**:
   - `PadelAnalysis/dashboard.py`
   - `PadelAnalysis/schedule_scraper.py`
   - `PadelAnalysis/scraper/poule_playwright.py`
   - `PadelAnalysis/scraper/ci_scrape_all.py`
2. **Vul Firestore één keer** (lokaal of via de knop/CI):
   `python poule_playwright.py --player <player_id> --force`  → schrijft `interclub_schedule`.
3. Controleer op cloud: volgende match (19/09) verschijnt **automatisch bovenaan**, geen URL plakken.
4. Bevestig dat de dagelijkse cron het schema vers houdt (venv-cache + Playwright-cache staan al in de workflow voor snelheid).

## 💡 Mogelijke verbeteringen (nog niet gebouwd)
- Knockout-rondes: na de voorronde komen er later tabellen bij (1/16 finale enz.). Parser haalt nu alle tabellen op de pagina op; controleren of nieuwe rondes correct als aparte `poule_label` verschijnen.
- Brede/consistente tabellen ook in Partners/Tegenstanders volledig gelijktrekken met het `lineup_quick` selecteerbare-tabel-patroon (grotendeels gedaan; laatste puntjes optioneel).
- Eventueel: tegenstander-ploeg-analyse (alle vorige matchen + volledige spelerskern met rankings) — eerder besproken concept `next_match_analysis.py`.

## Aanbevolen openingszin voor de nieuwe chat
> "Ik werk verder aan PadelAnalysis (mAICoach repo). Optie B werkt: Playwright rendert de poule-tabel in GitHub Actions en schrijft `interclub_schedule` naar Firestore; het cloud-dashboard leest dat uit. Volgende match (19/09) toont correct. Haal eerst de huidige versie van [bestand] uit mijn repo op vóór je iets wijzigt, en lever altijd volledige CRLF-bestanden met de juiste naam."
