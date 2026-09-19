# PadelAnalysis/scraper/Dockerfile
#
# PADEL_ANALYSIS_PREBUILT_DOCKER_IMAGE_2026-09-19 (op verzoek van Kim: "docker
# image" - performance-item uit de roadmap, prioriteit E).
#
# ROOT CAUSE van het probleem dat dit oplost: elk van de 4 scrape/refresh-
# workflows (scrape-padel.yml, refresh-padelstat.yml, refresh-klassement.yml,
# refresh-klassement-biannual.yml) installeerde tot nu toe ZELF, bij elke run,
# de volledige Python-omgeving EN de Chromium-browserbinary
# (`playwright install --with-deps chromium`, 150-300MB download). Enkel
# scrape-padel.yml had daar ooit een cache-laag voor gekregen (venv-cache +
# Playwright-browsercache); de andere 3 workflows deden dit bij ELKE run
# volledig opnieuw, zonder caching - een vaste, structurele tijdskost
# (~1-2 minuten setup) bovenop het eigenlijke scrapen, en een cache-restore
# is bovendien nooit zo snel als helemaal geen installatie meer nodig hebben.
#
# FIX: dit image bevat de volledige, kant-en-klare omgeving (Python-
# dependencies + Chromium-browserbinary + OS-libraries) EENMALIG voorgebouwd.
# De 4 workflows draaien voortaan gewoon *in* dit image via
# `container: image: ...` (zie .github/workflows/build-scraper-image.yml voor
# de build/publish-stap) - geen enkele installatiestap meer nodig in die
# workflows zelf, enkel `actions/checkout` + het scraper-script draaien.
#
# BELANGRIJK - versie-koppeling (lees dit bij een toekomstige upgrade):
# De basis-image hieronder (mcr.microsoft.com/playwright/python:vX.Y.Z-noble)
# bevat AL de Chromium-browserbinary die EXACT bij Playwright-versie X.Y.Z
# hoort. requirements-scraper.txt hieronder pint `playwright` daarom EXACT op
# diezelfde versie (`==`, nooit `>=`) - anders zou pip een NIEUWERE
# playwright-Python-package kunnen installeren dan de browserbinary die al in
# dit image zit, wat resulteert in een "Executable doesn't exist"-fout zodra
# de scraper een browser probeert te starten.
# Bij een toekomstige upgrade: verhoog de FROM-tag hieronder EN de
# playwright-versie in requirements-scraper.txt ALTIJD SAMEN, nooit apart.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app

# Enkel de requirements-bestanden eerst kopiëren (betere Docker-layer-cache):
# een wijziging in de scraper-Python-code zelf (bv. ci_scrape_all.py) hoeft zo
# geen herinstallatie van dependencies te triggeren bij een volgende
# image-build - enkel een wijziging aan requirements.txt/
# requirements-scraper.txt zelf doet dat.
COPY requirements.txt /app/requirements.txt
COPY PadelAnalysis/scraper/requirements-scraper.txt /app/requirements-scraper.txt

RUN pip install --no-cache-dir -r /app/requirements.txt -r /app/requirements-scraper.txt

# Chromium + de bijhorende OS-libraries zitten AL in de basis-image - er is
# dus GEEN `playwright install`-stap meer nodig, noch hier, noch in de
# workflows die dit image straks gebruiken.
