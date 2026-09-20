# PadelAnalysis/scraper/Dockerfile
#
# PADEL_ANALYSIS_SLIM_IMAGE_2026-09-21 (op verzoek van Kim: "is die setup job
# en init container effectief noodzakelijk bij al die github actions? is ook
# wel nog wat delay")
#
# --------------------------------------------------------------------------
# BELANGRIJK, EERST TE BEGRIJPEN: GitHub-hosted runners zijn WEGWERP-VM's.
# --------------------------------------------------------------------------
# Elke workflow-run start op een compleet VERSE machine - er bestaat GEEN
# persistente Docker-laag-cache tussen aparte runs. Dat betekent dat het
# "Initialize containers"-stap (het pullen van dit image van GHCR) bij
# ELKE run OPNIEUW volledig gebeurt, ongeacht hoe vaak de workflow al eerder
# gedraaid heeft. We hebben dus niet "installatietijd" geëlimineerd door dit
# image te bouwen, we hebben ze OMGERUILD voor "image-pull-tijd" - of dat een
# netto-winst is, hangt volledig af van hoe GROOT het image is.
#
# PADEL_ANALYSIS_PREBUILT_DOCKER_IMAGE_2026-09-19 gebruikte hiervoor
# mcr.microsoft.com/playwright/python - een basis-image dat STANDAARD ALLE
# DRIE browsers bevat (Chromium, Firefox, WebKit) plus hun volledige
# dependency-sets, ook al gebruiken we ALLEEN Chromium. Dat basisimage alleen
# is doorgaans 2-3GB - en dat werd dus elk UUR opnieuw gepulld voor de
# padelstat-trickle-refresh (2 spelers, ~30-60s eigen werk), waardoor de
# vaste pull-overhead de eigenlijke besparing kon overschrijden.
#
# FIX: dit is een veel SLANKER, zelfgebouwd image - een lichte Python-basis
# (python:3.12-slim, geen Playwright-browsers vooraf aan boord) waarop we
# ZELF enkel Chromium installeren (niet Firefox/WebKit). Dat brengt de
# uiteindelijke image-grootte terug naar typisch een fractie van het vorige
# multi-browser image, en dus ook de pull-tijd bij elke run.
#
# Wat dit NIET oplost (en ook niet kan oplossen): de "Set up job"-stap zelf
# (GitHub Actions' eigen boekhouding: runner toewijzen, workflow-bestand
# inlezen, permissies checken) is GEEN onderdeel van dit Dockerfile en gebeurt
# bij ELKE job, met of zonder container - typisch 3-8s, verwaarloosbaar en
# niet weg te optimaliseren.
#
# BELANGRIJK - versie-koppeling (lees dit bij een toekomstige upgrade):
# In tegenstelling tot de vorige opzet (waar de FROM-tag zelf de
# playwright-versie/browserbinary bepaalde), installeren we hier ZELF
# Chromium via `playwright install --with-deps chromium` binnen ditzelfde
# Dockerfile - de geïnstalleerde browserbinary komt dus ALTIJD automatisch
# overeen met de playwright-Python-package-versie die net ervoor via
# requirements-scraper.txt geïnstalleerd werd (dezelfde RUN-laag). Een
# toekomstige playwright-versie-upgrade in requirements-scraper.txt vereist
# dus GEEN aparte FROM-tag-aanpassing meer, enkel een nieuwe image-build
# (zie .github/workflows/build-scraper-image.yml, triggert automatisch bij
# een wijziging aan dit Dockerfile of requirements-scraper.txt).
FROM python:3.12-slim-bookworm

WORKDIR /app

# Enkel de requirements-bestanden eerst kopiëren (betere Docker-layer-cache
# tijdens het BOUWEN van het image zelf - niet te verwarren met de
# pull-tijd hierboven, dit versnelt enkel herhaalde `docker build`-runs):
# een wijziging in de scraper-Python-code zelf (bv. ci_scrape_all.py) hoeft
# zo geen herinstallatie van dependencies te triggeren bij een volgende
# image-build - enkel een wijziging aan requirements.txt/
# requirements-scraper.txt zelf doet dat.
COPY requirements.txt /app/requirements.txt
COPY PadelAnalysis/scraper/requirements-scraper.txt /app/requirements-scraper.txt

# PADEL_ANALYSIS_SLIM_IMAGE_2026-09-21: alles in ÉÉN RUN-laag (pip install +
# playwright install + apt-cleanup) - dit houdt tussenliggende bestanden
# (apt-cache, pip-cache) NIET in een aparte, blijvende laag hangen, wat de
# uiteindelijke image-grootte verder verkleint t.o.v. losse RUN-instructies.
# `playwright install --with-deps chromium` installeert ZOWEL de
# Chromium-browserbinary ALS de exacte OS-libraries die deze nodig heeft
# (via apt-get, vandaar dat dit als root binnen de container draait) -
# BEWUST ENKEL chromium, NIET firefox/webkit (die gebruiken we nergens),
# wat de grootste besparing t.o.v. het vorige mcr.microsoft.com-basisimage
# oplevert.
RUN pip install --no-cache-dir -r /app/requirements.txt -r /app/requirements-scraper.txt \
    && playwright install --with-deps chromium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache/pip
