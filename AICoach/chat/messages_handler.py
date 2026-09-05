# AICoach/chat/ai_message_handler.py

import os
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from AICoach.context_builder import build_context

load_dotenv()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)


def load_recent_history():

    history_dir = Path(
        "data/history"
    )

    if not history_dir.exists():
        return []

    files = sorted(
        history_dir.glob("*.json")
    )

    history = []

    for file in files[-30:]:

        try:

            with open(
                file,
                "r",
                encoding="utf-8"
            ) as f:

                history.append(
                    json.load(f)
                )

        except Exception:
            pass

    return history


def build_prompt(
    question: str
) -> str:

    context = build_context()

    recent_history = (
        load_recent_history()
    )

    return f"""
Je bent MatchFitAI.

Je bent een ervaren coach voor:

- hardlopen
- trailrunning
- padel
- uithoudingstraining

Gebruik onderstaande trainingscontext.

CONTEXT
========

{json.dumps(context, indent=2)}

RECENTE TRAININGSDATA
=====================

{json.dumps(recent_history[-10:], indent=2)}

VRAAG GEBRUIKER
=====================

{question}

INSTRUCTIES

- antwoord in het Nederlands
- wees praktisch
- geef concrete inzichten
- gebruik de data
- als de vraag niet expliciet in de data zit,
  redeneer dan op basis van de beschikbare trends
- wees kort maar nuttig
"""


def handle_message(
    question: str
) -> str:

    if not OPENAI_API_KEY:

        return (
            "OPENAI_API_KEY ontbreekt "
            "in .env"
        )

    prompt = build_prompt(
        question
    )

    client = OpenAI(
        api_key=OPENAI_API_KEY
    )

    response = (
        client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
    )

    return response.output_text.strip()