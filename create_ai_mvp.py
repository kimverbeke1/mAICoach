from pathlib import Path

ROOT = Path.cwd()

files = {}

files["AICoach/ai/coach.py"] = r'''
import json
from pathlib import Path

from openai import OpenAI

from AICoach.config import OPENAI_API_KEY


class MatchFitCoach:

    def __init__(self):

        self.client = OpenAI(
            api_key=OPENAI_API_KEY
        )

    def _load_latest_snapshot(self):

        folder = Path(
            "data/history"
        )

        files = sorted(
            folder.glob("*.json")
        )

        if not *iles:
            return {}

     *  latest = files[-1]

        with*open(
            latest,
        *   "r",
            encoding="utf-*"
        ) as f:

            ret*rn json.load(f)

    def ask(self,*question):

        snapshot = (
 *          self._load_latest_snapsh*t()
        )

        prompt = f"*"
Je bent MatchFitAI.

Huidige toe*tand:

{json.dumps(snapshot, inden*=2)}

Vraag gebruiker:

{question}*
Antwoord kort,
praktisch
en coach*nd.
"""

        response = self.c*ient.chat.completions.create(
    *       model="gpt-4o-mini",
      *     messages=[
                {
                    "role": "system",
                    "content": prompt
                }
            ]
        )

        return (
    *       response
            .choic*s[0]
            .message
        *   .content
        )
'''

files["AICoach/ui/app.py"] = r'''
import s*reamlit as st

from AICoach.ai.coa*h import (
    MatchFitCoach
)

st*set_page_config(
    page_title="M*tchFitAI",
    page_icon="🏃"
)

s*.title("🏃 MatchFitAI")

st.captio*(
    "Early MVP"
)

question = st*text_input(
    "Vraag:",
    plac*holder=(
        "Hoe gaat het met*mij vandaag?"
    )
)

if st.butto*("Analyseer"):

    if question:

*       coach = MatchFitCoach()

  *     with st.spinner(
            *Analyseren..."
        ):

       *    answer = coach.ask(
          *     question
            )

     *  st.markdown(answer)
'''

for fil*name, content in files.items():

 *  path = ROOT / filename

    path*parent.mkdir(
        parents=True*
        exist_ok=True
    )

    *ath.write_text(
        content.st*ip() + "\n",
        encoding="utf*8"
    )

    print(
        "writ*en:",
        filename
    )

prin*()
print("✅ AI MVP GENERATED")
pri*t()