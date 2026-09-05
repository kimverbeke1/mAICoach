# -*- coding: utf-8 -*-
"""Wetenschappelijke kennisbank en vaste AI-regels voor mAICoach.

Doel:
- De AI is ALTIJD gebaseerd op een vaste wetenschappelijke grondslag
  (Banister Fitness-Fatigue model) die in data/knowledge/sports_science.md staat.
- De regels staan gescheiden van de code, zodat je ze kunt aanpassen zonder
  Python te wijzigen.

Gebruik in ai_message_handler.py:
    from AICoach.science_knowledge import science_system_block

    prompt = science_system_block() + "\n\n" + BASE_RULES + "\n\n" + <jouw prompt>

Zo krijgt elke AI-call (chat en activiteitvergelijking) dezelfde wetenschappelijke
basis en dezelfde harde regels mee.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_FILE = PROJECT_ROOT / "data" / "knowledge" / "sports_science.md"

# Ingebouwde fallback zodat de AI nooit zonder grondslag draait,
# ook als het markdown-bestand ontbreekt.
_FALLBACK_KNOWLEDGE = """
# Wetenschappelijke basiskennis voor mAICoach

Fitness (CTL) = exponentieel gewogen gemiddelde Load over ~42 dagen, beweegt traag.
Fatigue (ATL) = exponentieel gewogen gemiddelde Load over ~7 dagen, beweegt snel.
Form (TSB) = Fitness - Fatigue.

Form-zones:
- Optimal Training: -10 tot -30 (progressie, supercompensatie).
- Overload/Danger: kouder dan -30 (risico overtraining, blessure, ziekte).
- Freshness/Tapering: +5 tot +25 (fris voor wedstrijd).

Valkuilen: FTP moet correct staan; kwantiteit is niet gelijk aan kwaliteit;
slaap, stress en voeding zitten niet in de Load.
""".strip()

# Harde, niet-onderhandelbare regels voor het model.
AI_RULES = """
## VASTE AI-REGELS (niet-onderhandelbaar)
- Baseer elke analyse op de wetenschappelijke grondslag hierboven; verzin geen
  eigen definities van Fitness, Fatigue of Form.
- Gebruik alleen data die werkelijk is aangeleverd; markeer ontbrekende data als
  onbekend, nooit als nul.
- Correlatie is geen oorzaak; formuleer patronen expliciet als hypotheses.
- Koppel uitspraken over frisheid en belasting aan de Form-zones.
- Vermeld relevante beperkingen (FTP-instelling, kwaliteit vs kwantiteit,
  externe stressoren) wanneer die de interpretatie beinvloeden.
- Padel en Badminton: geen prestatie-oordeel, alleen fysiologische belasting en
  herstelcontext.
- Running en TrailRun: alleen voorzichtige efficientie- en prestatie-uitspraken.
- Antwoord in natuurlijk, vlot Nederlands; zet cijfers en onderbouwing onder
  '### Technische details'.
""".strip()


def load_science_knowledge() -> str:
    """Lees de wetenschappelijke kennisbank; val terug op de ingebouwde versie."""
    try:
        text = KNOWLEDGE_FILE.read_text(encoding="utf-8").strip()
        return text or _FALLBACK_KNOWLEDGE
    except OSError:
        return _FALLBACK_KNOWLEDGE


def science_system_block() -> str:
    """Volledig systeemblok: wetenschappelijke grondslag + vaste regels."""
    return (
        "## WETENSCHAPPELIJKE GRONDSLAG (verplicht)\n"
        f"{load_science_knowledge()}\n\n"
        f"{AI_RULES}"
    )


if __name__ == "__main__":
    print(science_system_block())
