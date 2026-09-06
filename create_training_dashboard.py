from pathlib import Path

dashboard_file = Path(
    "AICoach/pages/training_dashboard.py"
)

dashboard_code = r'''
from pathlib import Path
import json
import subprocess
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]

HISTORY_DIR = ROOT / "data" / "history"

st.set_page_config(
    page_title="MatchFit AI",
    page_icon="🏃",
    layout="wide"
)


@st.cache_data
def load_history():

    files = sorted(
        HISTORY_DIR.glob("*.json")
    )

    rows = []

    *or history_file in files:

       *with open(
            history_fil*,
            "r",
            enc*ding="utf-8",
        ) as handle:*
            rows.append(
        *       json.load(handle)
         *  )

    if not rows:
        retu*n pd.DataFrame()

    df = pd.Data*rame(rows)

    df["date"] = pd.to*datetime(
        df["date"],
    *   errors="coerce"
    )

    nume*ic_columns = [
        "fitness",
        "fatigue",
        "training_load",
        "resting_hr",
        "weight",
    ]

    for column*in numeric_columns:

        if co*umn in df.columns:

            df*column] = pd.to_numeric(
         *      df[column],
                *rrors="coerce"
            )

    *f = df.sort_values("date")

    df*"form"] = (
        df["fitness"]
*       - df["fatigue"]
    )

    *eturn df


st.title("🏃 MatchFit A*")

left, right = st.columns([8, 2])

with right:

    if st.button("*� Data vernieuwen"):

        with*st.spinner(
            "Data verv*rsen..."
        ):

            s*bprocess.run(
                [
                    sys.executable,
                    "-m",
                    "AICoach.refresh_all"
                ]
            )

     *  st.cache_data.clear()
        st*rerun()

df = load_history()

if d*.empty:

    st.error(
        "Ge*n trainingsdata gevonden"
    )

 *  st.stop()

latest = df.iloc[-1]
*st.caption(
    f"Laatste datapunt* {latest['date'].strftime('%d/%m/%*')}"
)

c1, c2, c3, c4, c5 = st.co*umns(5)

c1.metric(
    "Fitness",*    round(float(latest["fitness"])* 1)
)

c2.metric(
    "Fatigue",
 *  round(float(latest["fatigue"]), *)
)

c3.metric(
    "Form",
    ro*nd(float(latest["form"]), 1)
)

c4*metric(
    "Rest HR",
    round(f*oat(latest["resting_hr"]), 1)
)

c*.metric(
    "Weight",
    round(f*oat(latest["weight"]), 1)
)

st.di*ider()

st.subheader(
    "Fitness*/ Fatigue / Form"
)

fig_ffa = px.*ine(
    df,
    x="date",
    y=[
        "fitness",
        "fatigue",
        "form"
    ],
    markers=True
)

st.plotly_chart(
    fig_ffa,
    use_container_width=True
)

st.subheader(
    "Training Load"
)

fig_load = px.bar(
    df,
    x="date",
    y="training_load"
)

st.plotly_chart(
    fig_load,
    use_container_width=True
)

st.subheader(
    "Rusthartslag"
)

fig_hr = px.line(
    df,
    x="date",
    y="resting_hr",
    markers=True
)

st.plotly_chart(
    fig_hr,
    use_container_width=True
)

st.subheader(
    "Gewicht"
)

fig_weight = px.line(
    df,
    x="date",
    y="weight",
    markers=True
)

st.plotly_chart(
    fig_weight,
    use_container_width=True
)

with st.expander(
    "Laatste 20 records"
):

    st.dataframe(
        df.tail(20),
        use_container_width=True
    )
'''

dashboard_file.parent.mkdir(
    parents=True,
    exist_ok=True
)

dashboard_file.write_text(
    dashboard_code,
    encoding="utf-8"
)

print()
print("Dashboard aangemaakt:")
print(dashboard_file)
print()