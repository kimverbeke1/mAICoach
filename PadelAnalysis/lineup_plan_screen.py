"""
lineup_plan_screen.py - Planscherm voor een VOLLEDIGE ontmoeting (najaar:
2 rotaties x 2 matchen), aanpasbaar speler per speler.

--------------------------------------------------------------------------
PADEL_ANALYSIS_PLAN_SCREEN_2026-10-03 (op verzoek van Kim: "Je stelt die beter
samen voor met dan meteen ook een eindresultaat van die keuze getoond. Zo zie
je direct de impact van je keuze." + Kim akkoord: "ok met het plan")
--------------------------------------------------------------------------
1. TEGENSTANDER - snelkeuze S1, S2, ... = EXACT de scenario's (en gewichten)
   van de scenario-analyse (st.session_state "scen_matrix_scen_v3_<ploeg>").
   Welke tegenstander telt mee in het resultaat:
     - alle 8 vakjes ingevuld   -> exact die opstelling;
     - enkel rotatie 1 ingevuld -> hun rotatie 2 voorspeld door het model;
     - anders                   -> gewogen over de scenario's S1..Sn.
2. ONZE PLOEG - knoppen "Beste plan" (meeste verwachte punten), "Gespreid"
   (onze 2 zwakste spelers nooit samen), "Opofferen" (onze 2 zwakste samen in
   1 match), "Minstens 1 punt". Daarna speler per speler aanpasbaar.
3. CONTROLES voor BEIDE ploegen: speler 2x in een rotatie, koppel 2x in de
   ontmoeting, puntengrens per rotatie, art. 6.6 (sterkste duo op M1); bij ons
   ook max. matchen per speler. Overtredingen in rood.
4. TIJDENS DE WEDSTRIJD: "Rotatie 1 is gespeeld" + uitslag -> rekent met de
   echte tussenstand; de voorstellen optimaliseren enkel nog rotatie 2.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PLAN_SCREEN_V2_2026-10-03 (feedback Kim: "extra kader rond de
spelers die samen spelen [...] het totaal aantal padelstat punten voor beide
spelers ook best zichtbaar. Best ook matchen van spelers naast elkaar dus A en
B tegen C en D voor elke match", "mss toch wel klein woord uitleg wat dat
scenario is", en de blanco pagina na het toevoegen van een speler)
--------------------------------------------------------------------------
- Per match EEN kader: links onze 2 spelers, rechts hun 2 spelers, daaronder
  "A / B (ps X) tegen C / D (ps Y) - winkans Z%".
- Onder elke S-knop een korte omschrijving van het scenario.
- De hele weergave zit in een try/except: een fout toont een melding met de
  technische details i.p.v. een blanco pagina. Caches hangen aan de huidige
  spelerslijst; een opgeslagen keuze die niet meer geldig is, wordt gewist.
--------------------------------------------------------------------------
PADEL_ANALYSIS_LINEUP_SNAPSHOT_2026-10-03 (Kim: "al gespeelde matchen ook nog
te kunnen analyseren maar dan met de padelstat waardes van toen")
--------------------------------------------------------------------------
Bij elke weergave wordt (max. 1x per sessie per ontmoeting, plus telkens het
plan volledig ingevuld wijzigt) een momentopname bewaard in Firestore,
collectie "lineup_snapshots", document "<ploeg_id>__<datum>": de padelstat-
waarden en officiele klassementen van ALLE spelers op dat moment, de
winkans-schaal, en het laatst ingevulde plan (wij + tegenstander). Basis voor
een latere tab "Nabeschouwing" (voorspeld vs. echte uitslag, kalibratie).
--------------------------------------------------------------------------
PADEL_ANALYSIS_PLAN_SCREEN_V3_2026-10-04 (feedback Kim: "er staat bvb op de
knoppen: S1: 24%: S2:22%. Beter zou zijn om ook kort te tonen wat dat
Scenario is. als je iets koos dan had ik eerst niet gezien dat er effectief
iets geselecteerd was. Als het knoppen zijn dan dat wel tonen dat die knoppen
geselecteerd is (groen?)" + "Ik denk dat het beter is om gewoon die vergelijk
de voorstellen te tonen en dan met een knop bij elke rij 1 van die rijen te
kunnen kiezen (ook tonen dat die knop gekozen is.)" + "in de tabel mag je ook
de beste opstelling tonen voor de speler voor wie we de analyse doen")
--------------------------------------------------------------------------
1. SCENARIO-KNOPPEN: de korte omschrijving stond al als caption ONDER elke
   knop (ongewijzigd) - NIEUW is dat de knop die exact overeenkomt met de
   huidige tegenstander-invulling nu VISUEEL afwijkt: een vinkje in de
   knoptekst EN type="primary" (de gekleurde/opgevulde Streamlit-knopstijl,
   t.o.v. de normale omlijnde knop) i.p.v. een losse caption die je kon
   missen. Daarvoor wordt opp_sel/opp_plan nu AL gelezen VOOR de knoppen
   gerenderd worden (was voorheen pas erna).
2. "ONZE PLOEG - VOORSTELLEN": de aparte knoppenrij met percentages is WEG.
   In de plaats: enkel nog de vergelijkingstabel (niet langer in een
   ingeklapte expander - "gewoon tonen"), met per rij een "Kies"-knop. De
   rij die exact overeenkomt met de huidige invulling krijgt een vinkje,
   vetgedrukte tekst en de knop wordt (uitgeschakeld) "Actief \u2713" i.p.v.
   "Kies". Kolom "Gelijk" blijft (Kim: "net die kolom toont waar het
   verschil in opstelling zit"), naast "Min. 1 punt" (= Winst + Gelijk).
3. NIEUWE RIJ "Beste voor <naam>": de speler voor wie de analyse loopt
   (page_lineup_lab.py's spelerskeuze bovenaan) wordt via st.session_state
   ("viewing_player_id_<ploeg_id>", gezet door page_lineup_lab.py) herkend;
   onder de bestaande 4 voorstellen komt een 5de rij met het plan dat voor
   PRECIES DIE speler de hoogste gemiddelde persoonlijke winkans geeft over
   de match(en) waarin hij/zij voorkomt (tegen de huidige opp_dist) - zelfde
   aanpak als de vroegere "Beste opstelling voor mezelf" in de matchup-tabel
   (die daar nu WEG is, zie lineup_matchup_table.py), maar dan contextueel
   t.o.v. het scenario dat je hier aan het plannen bent.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04 (op verzoek van Kim: "de
teksten wat S1, S2 mogen iets duidelijker en multiline. Je mag ook de
waarom van deze kansen tonen. Eigenlijk komt het er dan op neer dat we
meteen de scenario analyse in die rotatieplanner integreren [...] voorstel
opstellingen rotatieplanner mag in mooiere tabel. Ik zie dat er in alle
plannen verschillende identieke opstellingen zijn [...] je kan dus beter
tonen: Beste plan en dan (opofferen tussen haakjes of toch zeker wat meer
info waarom dat het beste plan is). Minstens 1 punt is trouwens ook dezelfde
opstelling. dus beter dan maar gewoon die 2 opstellingen tonen met uitleg")
--------------------------------------------------------------------------
1. S-KNOPPEN DUIDELIJKER: de caption onder elke knop toont nu de VOLLEDIGE
   scenario-omschrijving (geen afkapping meer op 48 tekens) plus, op een
   aparte regel, de "waarom"-redenen van het model (bv. "Waarom: Roels &
   Logghe speelden al 3x samen"). Die redenen komen nu mee in de gedeelde
   scenario-lijst (zie lineup_scenario_matrix.py, PADEL_ANALYSIS_ROTATION_
   INTEGRATION_2026-10-04) - geen nieuwe modelaanroep hier nodig.
2. SCENARIO-OVERZICHT IN DE PLANNER: een nieuwe, inklapbare tabel ("Scenario-
   overzicht") net onder de S-knoppen toont Scenario/Gewicht/Wat/Rotatie 1/
   Rotatie 2/Waarom voor alle scenario's - dezelfde gegevens als de aparte
   scenario-analyse-sectie, nu ook rechtstreeks in de Rotatieplanner. De
   aparte sectie zelf blijft ONGEWIJZIGD bestaan (Kim: "nog niet direct die
   scenario analyse weglaten") - dit is een AANVULLING, geen vervanging.
3. VOORSTELLEN SAMENVOEGEN: identieke opstellingen (bv. "Beste plan" en
   "Opofferen" die toevallig dezelfde koppelverdeling opleveren) worden niet
   langer als aparte, dubbele rijen getoond. _merge_duplicate_rows() groepeert
   voorstellen op hun EXACTE opstelling (ongeacht rij-volgorde) en toont ze
   als 1 rij met gecombineerde titel ("Beste plan = Opofferen") en
   gecombineerde uitleg ("meeste verwachte punten; onze 2 zwakste spelers
   samen in 1 match") - zo zie je in 1 oogopslag WAAROM een opstelling onder
   meerdere strategieen de beste is, i.p.v. dezelfde rij meermaals te zien.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04 (feedback Kim: "Als ik bij de
rotaties manueel dingen aanpas krijg ik onderaan bvb: Tegenstander rotatie 1:
sterkste duo staat niet op M1 [...] Is beter om gewoon dgans die match in het
rood te tonen." + "je mag toelaten dat je eenzelfde speler kiest die al bvb
in de andere match van de rotatie speelt, maar in dat geval moet je die naam
al tonen in de lijst dat dat zo is" + "De tekst bij tegenstander is helemaal
lichtgrijs en niet zo goed leesbaar" + "Rotatie 1 is gespeeld is nu een
checkbox die wat verloren staat [...] Ik zou dan ook gewoon die dingen bij de
rotatie 1 zelf zetten en niet daarboven")
--------------------------------------------------------------------------
1. ART. 6.6-OVERTREDING INLINE IN HET ROOD: de "sterkste duo staat niet op
   M1"-melding verschijnt niet langer als losse tekstregel onderaan de
   pagina, maar als rode kop ("Match 1" -> ":red[Match 1 - NIET sterkste
   duo (art. 6.6)]") op BEIDE matchkaarten van de betrokken rotatie, voor
   zowel onze als hun opstelling apart gecontroleerd. De overige controles
   (speler 2x in dezelfde rotatie, koppel 2x in de ontmoeting, puntengrens,
   max. matchen per speler) blijven ONGEWIJZIGD als tekstregel onderaan
   staan - dat zijn controles over de HELE rotatie/ontmoeting, niet over 1
   specifieke match, en lenen zich niet tot een inline-kleur op 1 kaart.
2. SPELER AL GEKOZEN IN ANDERE MATCH VAN DEZE ROTATIE: _options_for() sloot
   zulke spelers voorheen volledig uit de keuzelijst. Nu blijven ze gewoon
   kiesbaar (het reglement verbiedt dit niet expliciet op UI-niveau, en Kim
   wil dit "voor de zekerheid" kunnen uitproberen), maar de keuzelijst zelf
   toont het al: "Naam - al bij M<x>" als suffix, dus je ziet VOOR je kiest
   dat die speler al ergens anders in deze rotatie staat. Kiest je hem
   toch, dan markeert _check_rotation() dit (ongewijzigd: "een speler staat
   2x in dezelfde rotatie") als foutregel onderaan.
3. LEESBAARHEID "tegen"-label: de losse <div>-styling tussen de 2 kolommen
   kreeg geen expliciete tekstkleur - op sommige (donkere) Streamlit-thema's
   viel die daardoor terug op een lichtgrijze standaardkleur. Nu expliciet
   "color:inherit" (volgt de normale themakleur, net als de rest van de
   tekst) en iets groter lettertype voor leesbaarheid.
4. "ROTATIE 1 IS GESPEELD": verplaatst van helemaal bovenaan de pagina naar
   ONDER de kop "Rotatie 1" zelf (vlak voor de 2 matchkaarten van rotatie
   1), in een lichte, omkaderde balk - dus niet langer "los" bovenaan,
   maar zichtbaar bij het onderdeel waar het betrekking op heeft.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PLAN_SCREEN_V5_2026-10-04 (feedback Kim: "Als rotatie 1
gespeeld is en je kiest dan de uitslag, dan kan het zijn dat de origineel
gekozen opstelling niet meer de beste is [...] stel dat het 0-2 is (wij
verliezen) dan moet onze strategie aangepast worden om alles op alles te
zetten voor 2-2 wat dan uiteraard geen opofferingsmatch meer mag zijn [...]
moet natuurlijk wel nog mogelijk zijn want als we maar 4 spelers hebben zijn
er niet vele combinaties meer mogelijk" + "Onze ploeg staat nog steeds niet
in mooi kader!")
--------------------------------------------------------------------------
1. HAALBAARHEID NA ROTATIE 1: met de echte tussenstand (0/1/2 gewonnen
   matchen in rotatie 1) ligt het MAXIMAAL haalbare eindresultaat al vast:
     - stand 0 (0-2): zelfs met 2 winsten in rotatie 2 kom je op 2 van de 4
       - dus NOOIT winst (2 ploegpunten), hoogstens gelijk (1 punt) als we
       BEIDE resterende matchen winnen. "Opofferen" is dan zinloos (er is
       geen enkele match meer om bewust prijs te geven - beide MOETEN
       gewonnen worden voor het enige nog haalbare resultaat).
     - stand 2 (2-0): zelfs met 2 verliezen in rotatie 2 blijf je op 2 van
       de 4 - dus NOOIT verlies, hoogstens gelijk. "Gespreid"/"Opofferen"
       zijn dan evenmin zinvol: ELKE geldige rotatie 2 geeft hetzelfde
       gegarandeerde minimum.
     - stand 1 (1-1): het volledige bereik (winst/gelijk/verlies) blijft
       open - hier blijven ALLE 4 presets (incl. Gespreid/Opofferen)
       zinvolle, onderscheiden keuzes.
   _forced_outcome_after_r1() berekent dit (louter telwerk op k en het
   aantal resterende matchen, GEEN kansberekening nodig) en geeft een
   duidelijke banner ("Winst is niet meer mogelijk - enige haalbare resultaat
   is gelijkspel (2-2); beide resterende matchen moeten gewonnen worden.").
   Bij stand 0 of 2 worden de rijen "Gespreid" en "Opofferen" NIET getoond
   (ze zouden sowieso identiek zijn aan "Beste plan"/"Minstens 1 punt" via
   _merge_duplicate_rows, of een nodeloos zwakkere, misleidende rij tonen) -
   "Beste plan" optimaliseert in dat geval vanzelf voor het enige haalbare
   doel (_score() reduceert immers naar "maximaliseer p1" als p2 structureel
   0 is, en naar "p0 structureel 0" bij stand 2). Bij stand 1 verandert er
   niets - alle 4 presets blijven zoals voorheen.
   Met slechts 4 beschikbare spelers kan rotatie 2 maar op 1 (of een
   handvol) manier(en) ingevuld worden - dat is in orde, _own_plans() geeft
   dan gewoon een kortere (of lege) lijst terug; "Geen reglementair geldig
   plan"-melding blijft ongewijzigd bestaan voor dat laatste geval.
2. "ONZE PLOEG - VOORSTELLEN" IN EEN KADER: de volledige tabel (kop + alle
   rijen) staat nu in st.container(border=True) - zelfde kadersstijl als de
   matchkaarten eronder, i.p.v. kale kolommen zonder omlijning.
"""
import datetime as _dt
import traceback

import streamlit as st

from dashboard_common import ll, fb
from lineup_scout import _cached_official_rank, _cached_own_player_rating
from lineup_rotation import (
    _generate_rotation_candidates, _rank_pairs_with_padelstat_tiebreak, _norm_name,
    MATCHES_PER_ROTATION,
)

try:
    import opponent_lineup_model as olm
except Exception:  # noqa: BLE001  pragma: no cover
    olm = None

_N_ROT = 2
_R2_PRED_TOP = 6
_GEEN = "- Kies -"
_SNAPSHOT_COLLECTION = "lineup_snapshots"
_PRESETS = [
    ("best", "Beste plan", "meeste verwachte punten"),
    ("spread", "Gespreid", "onze 2 zwakste spelers nooit samen"),
    ("sacrifice", "Opofferen", "onze 2 zwakste spelers samen in 1 match"),
    ("safe", "Minstens 1 punt", "hoogste kans op winst of gelijk"),
]
_SLOTS = [(r, m, i) for r in range(_N_ROT) for m in range(MATCHES_PER_ROTATION) for i in range(2)]


# ---------------------------------------------------------------- rekenkern
def _wins_dist(a, b) -> list:
    a = 0.5 if a is None else a
    b = 0.5 if b is None else b
    return [(1 - a) * (1 - b), a * (1 - b) + b * (1 - a), a * b]


def _points(dists: list) -> dict:
    tot = {0: 1.0}
    n = 0
    for d in dists:
        nieuw = {}
        for k, pk in tot.items():
            for j, pj in enumerate(d):
                nieuw[k + j] = nieuw.get(k + j, 0.0) + pk * pj
        tot = nieuw
        n += len(d) - 1
    half = n / 2.0
    p2 = sum(p for k, p in tot.items() if k > half)
    p1 = sum(p for k, p in tot.items() if k == half)
    return {"p2": p2, "p1": p1, "p0": max(0.0, 1.0 - p2 - p1)}


def _points_with_offset(d2: list, k: int) -> dict:
    half = (MATCHES_PER_ROTATION * _N_ROT) / 2.0
    p2 = p1 = 0.0
    for j, pj in enumerate(d2):
        t = k + j
        if t > half:
            p2 += pj
        elif t == half:
            p1 += pj
    return {"p2": p2, "p1": p1, "p0": max(0.0, 1.0 - p2 - p1)}


def _forced_outcome_after_r1(played_k):
    """PADEL_ANALYSIS_PLAN_SCREEN_V5_2026-10-04 - zie moduledocstring.
    Geeft (banner_tekst_of_None, toon_spread_en_sacrifice: bool) terug, op
    basis van PUUR TELWERK (geen kans nodig): met `played_k` matchen al
    gewonnen in rotatie 1 en MATCHES_PER_ROTATION matchen nog te spelen in
    rotatie 2, wat is het bereik van het eindtotaal?"""
    if played_k is None:
        return None, True
    half = (MATCHES_PER_ROTATION * _N_ROT) / 2.0
    min_tot = played_k
    max_tot = played_k + MATCHES_PER_ROTATION
    if max_tot <= half:
        return (
            ":red[**Winst is niet meer mogelijk.**] Het enige nog haalbare resultaat is gelijkspel "
            f"({int(half)}-{int(half)}) - dat vereist dat **beide** resterende matchen gewonnen worden. "
            "'Gespreid' en 'Opofferen' zijn hier niet zinvol: er is geen match meer om bewust prijs te geven."
        ), False
    if min_tot >= half:
        return (
            ":green[**Verlies is niet meer mogelijk.**] We staan minstens op gelijkspel, ongeacht de uitslag "
            "van rotatie 2. 'Gespreid' en 'Opofferen' geven hier hetzelfde gegarandeerde minimum als 'Beste "
            "plan' - enkel 'Beste plan' optimaliseert nog voor de volle winst."
        ), False
    return None, True


def _score(kind: str, pp: dict) -> tuple:
    if kind == "safe":
        return (pp["p2"] + pp["p1"], pp["p2"])
    return (2 * pp["p2"] + pp["p1"], pp["p2"])


class _Ctx:
    def __init__(self, player_ratings, official_ranks_strict, opponent_ratings, opp_ranks):
        self.pr = player_ratings or {}
        self.orank = official_ranks_strict or {}
        self.opr = opponent_ratings or {}
        self.opp_ranks = opp_ranks or {}
        self.cache = {}

    def strength(self, uid):
        return ll.effective_simulation_rating(uid, self.pr, self.orank)

    def opp_strength(self, uid):
        r = self.opp_ranks.get(uid)
        return ll.effective_simulation_rating(uid, self.opr, {uid: float(r) if r is not None else None})

    def wp(self, own_pair, opp_pair):
        key = (frozenset(own_pair), frozenset(opp_pair))
        if key not in self.cache:
            ours = [v for v in (self.strength(u) for u in own_pair) if v is not None]
            theirs = [v for v in (self.opp_strength(u) for u in opp_pair) if v is not None]
            self.cache[key] = ll.estimate_win_probability(
                sum(ours) / len(ours) if ours else None,
                sum(theirs) / len(theirs) if theirs else None,
            )
        return self.cache[key]

    def outcome(self, plan, opp_dist, played_k=None):
        acc = {"p2": 0.0, "p1": 0.0, "p0": 0.0}
        tw = sum(w for *_, w in opp_dist) or 1.0
        for o1, o2, w in opp_dist:
            d2 = _wins_dist(self.wp(plan[1][0], o2[0]), self.wp(plan[1][1], o2[1]))
            if played_k is None:
                d1 = _wins_dist(self.wp(plan[0][0], o1[0]), self.wp(plan[0][1], o1[1]))
                pp = _points([d1, d2])
            else:
                pp = _points_with_offset(d2, played_k)
            for k in acc:
                acc[k] += (w / tw) * pp[k]
        return acc

    def match_wp(self, own_pair, r, m, opp_dist):
        tw = sum(w for *_, w in opp_dist) or 1.0
        tot = 0.0
        for o1, o2, w in opp_dist:
            v = self.wp(own_pair, (o1 if r == 0 else o2)[m])
            tot += (w / tw) * (0.5 if v is None else v)
        return tot


def _own_plans(available_ids, synergy_fn, official_ranks_strict, player_ratings, opponent_ratings,
               rules, max_per_player, fixed_r1=None) -> list:
    budget = {str(p): int((max_per_player or {}).get(p, _N_ROT) or 0) for p in available_ids}
    if fixed_r1 is not None:
        r1_opts = [fixed_r1]
    else:
        r1_raw, _, _ = _generate_rotation_candidates(
            available_ids, synergy_fn, official_ranks_strict, set(), opponent_boards=None,
            player_ratings=player_ratings, opponent_ratings=opponent_ratings, max_results=100_000,
            tournament_rules_dict=rules, rotation_number=1, player_budget=budget,
        )
        r1_opts = [c["ordered_pairs"] for c in r1_raw]
    plans = []
    for r1 in r1_opts:
        b2 = dict(budget)
        for p in r1:
            for u in p:
                b2[str(u)] = b2.get(str(u), 0) - 1
        r2_raw, _, _ = _generate_rotation_candidates(
            available_ids, synergy_fn, official_ranks_strict, {frozenset(p) for p in r1},
            opponent_boards=None, player_ratings=player_ratings, opponent_ratings=opponent_ratings,
            max_results=100_000, tournament_rules_dict=rules, rotation_number=2, player_budget=b2,
        )
        for c in r2_raw:
            plans.append([[frozenset(p) for p in r1], [frozenset(p) for p in c["ordered_pairs"]]])
    return plans


def _weakest_two(available_ids, ctx: _Ctx):
    sterk = sorted((ctx.strength(u), u) for u in available_ids if ctx.strength(u) is not None)
    if len(sterk) < 4:
        return None
    return frozenset({sterk[0][1], sterk[1][1]})


def _personal_avg_wp(plan: list, viewing_player_id: str, ctx: "_Ctx", opp_dist: list):
    """PADEL_ANALYSIS_PLAN_SCREEN_V3_2026-10-04: gemiddelde persoonlijke
    winkans van `viewing_player_id` over de match(en) waarin die speler in
    `plan` voorkomt (tegen `opp_dist`). None als die speler nergens in dit
    plan speelt."""
    probs = []
    for r in range(len(plan)):
        for m in range(len(plan[r])):
            pair = plan[r][m]
            if viewing_player_id in pair:
                probs.append(ctx.match_wp(pair, r, m, opp_dist))
    return (sum(probs) / len(probs)) if probs else None


def _pick_presets(plans, opp_dist, ctx, weakest, played_k=None, viewing_player_id=None,
                  include_spread_sacrifice=True) -> dict:
    """PADEL_ANALYSIS_PLAN_SCREEN_V5_2026-10-04: `include_spread_sacrifice`
    laat "Gespreid"/"Opofferen" weg wanneer het eindresultaat na rotatie 1
    al vastligt (zie _forced_outcome_after_r1 / moduledocstring) - die 2
    presets zijn dan niet onderscheidend of zelfs misleidend."""
    out = {}
    scored = [(p, ctx.outcome(p, opp_dist, played_k)) for p in plans]
    for kind, _, _ in _PRESETS:
        if kind in ("spread", "sacrifice") and not include_spread_sacrifice:
            continue
        if kind == "spread":
            pool = [x for x in scored if weakest and all(weakest != pr for rot in x[0] for pr in rot)]
        elif kind == "sacrifice":
            pool = [x for x in scored if weakest and any(weakest == pr for rot in x[0] for pr in rot)]
        else:
            pool = scored
        if pool:
            out[kind] = max(pool, key=lambda x: _score("safe" if kind == "safe" else "best", x[1]))
    # PADEL_ANALYSIS_PLAN_SCREEN_V3_2026-10-04: 5de voorstel - beste voor de
    # specifieke speler voor wie de analyse loopt (zie moduledocstring).
    if viewing_player_id:
        outcome_by_id = {id(p): o for p, o in scored}
        personal = [
            (_personal_avg_wp(p, viewing_player_id, ctx, opp_dist), p) for p in plans
        ]
        personal = [(score, p) for score, p in personal if score is not None]
        if personal:
            _, beste_plan = max(personal, key=lambda x: x[0])
            out["self"] = (beste_plan, outcome_by_id[id(beste_plan)])
    return out


def _canon_plan(plan: list) -> tuple:
    """PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04: canonieke sleutel van
    een plan (ongeacht rotatie-/matchvolgorde) - gebruikt om identieke
    voorstellen te herkennen en samen te voegen."""
    return tuple(sorted(tuple(sorted(tuple(sorted(p)) for p in rot)) for rot in plan))


def _merge_duplicate_rows(rijen: list) -> list:
    """PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04 - zie moduledocstring:
    voegt rijen met EXACT dezelfde opstelling samen tot 1 rij met
    gecombineerde titel ("Beste plan = Opofferen") en gecombineerde,
    ontdubbelde uitleg. Volgorde van eerste voorkomen blijft behouden."""
    merged: dict = {}
    volgorde = []
    for kind, titel, uitleg, plan, pp in rijen:
        ck = _canon_plan(plan)
        if ck not in merged:
            merged[ck] = {"kinds": [], "titels": [], "uitlegs": [], "plan": plan, "pp": pp}
            volgorde.append(ck)
        merged[ck]["kinds"].append(kind)
        merged[ck]["titels"].append(titel)
        merged[ck]["uitlegs"].append(uitleg)
    return [
        (
            merged[ck]["kinds"][0],
            " = ".join(merged[ck]["titels"]),
            "; ".join(dict.fromkeys(merged[ck]["uitlegs"])),
            merged[ck]["plan"], merged[ck]["pp"],
        )
        for ck in volgorde
    ]


def _predict_r2(bundle, roster, r1, opp_ranks, opp_ps, rules):
    if olm is None:
        return []
    stats = olm.build_opponent_stats(bundle, MATCHES_PER_ROTATION)

    def _order(pairs):
        return _rank_pairs_with_padelstat_tiebreak(pairs, opp_ranks, opp_ps)

    pred = olm.predict_rotation_scenarios(
        stats, roster, _order, opp_ranks, rules=rules,
        excluded_pairs={frozenset(p) for p in r1}, top_n=_R2_PRED_TOP,
    )["scenarios"]
    return [([frozenset(p) for p in s["pairs"][0]], s["prob"]) if False else
            (s["pairs"], s["prob"]) for s in pred]


# ------------------------------------------------------------ controles
def _rotation_order_violation(r_pairs, ranks) -> bool:
    """PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: True als het duo op Match 2
    een HOGERE puntensom heeft dan het duo op Match 1 (art. 6.6: sterkste
    duo hoort op Match 1) - enkel bepaalbaar als beide officiele klassementen
    van alle 4 spelers gekend zijn; anders False (niet controleerbaar, geen
    fout tonen op basis van onvolledige data)."""
    if len(r_pairs) != 2:
        return False
    waarden = [ranks.get(u) for p in r_pairs for u in p]
    if any(v is None for v in waarden):
        return False
    s1 = sum(ranks.get(u) or 0 for u in r_pairs[0])
    s2 = sum(ranks.get(u) or 0 for u in r_pairs[1])
    return s2 > s1


def _check_rotation(r_pairs, ranks, rules, wie, r_idx, include_order=True) -> list:
    """PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: `include_order=False` laat
    de art. 6.6-melding hier weg - die wordt elders INLINE (rood op de
    betrokken matchkaart) getoond i.p.v. als losse tekstregel, zie
    moduledocstring. De overige controles (duplicate speler, puntengrens)
    blijven hier ongewijzigd."""
    fouten = []
    spelers = [u for p in r_pairs for u in p]
    if len(set(spelers)) != len(spelers):
        fouten.append(f"{wie} rotatie {r_idx + 1}: een speler staat 2x in dezelfde rotatie.")
    if rules is not None:
        waarden = [ranks.get(u) for u in set(spelers)]
        if all(v is not None for v in waarden):
            tot = sum(waarden)
            lo, hi = rules.get("punten_min"), rules.get("punten_max")
            if (lo is not None and tot < lo) or (hi is not None and tot > hi):
                fouten.append(f"{wie} rotatie {r_idx + 1}: {tot:.0f} punten - buiten de puntengrens ({lo}-{hi}).")
    if include_order and _rotation_order_violation(r_pairs, ranks):
        s1 = sum(ranks.get(u) or 0 for u in r_pairs[0])
        s2 = sum(ranks.get(u) or 0 for u in r_pairs[1])
        fouten.append(f"{wie} rotatie {r_idx + 1}: sterkste duo staat niet op M1 (art. 6.6: {s1:.0f} < {s2:.0f}).")
    return fouten


def _check_encounter(plan, ranks, rules, wie, max_per_player=None) -> list:
    """PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: roept _check_rotation nu
    aan met include_order=False - de art. 6.6-melding wordt apart, inline
    per matchkaart getoond (zie _render_match_card / moduledocstring)."""
    fouten = []
    for r, rot in enumerate(plan):
        if rot:
            fouten += _check_rotation(rot, ranks, rules, wie, r, include_order=False)
    alle = [p for rot in plan for p in rot]
    if len(set(alle)) != len(alle):
        fouten.append(f"{wie}: een koppel speelt 2x samen in de ontmoeting.")
    if max_per_player:
        tel = {}
        for p in alle:
            for u in p:
                tel[u] = tel.get(u, 0) + 1
        for u, n in tel.items():
            if n > int(max_per_player.get(u, _N_ROT) or 0):
                fouten.append(f"{wie}: een speler speelt {n} matchen (max. {max_per_player.get(u)}).")
    return fouten


# ------------------------------------------------------------ selectie
def _read_sel(prefix, label_of) -> dict:
    uid_of = {v: k for k, v in label_of.items()}
    out = {}
    for slot in _SLOTS:
        v = st.session_state.get(f"{prefix}_{slot[0]}{slot[1]}{slot[2]}")
        if v in uid_of:
            out[slot] = uid_of[v]
    return out


def _options_for(slot, sel, volgorde, label_of) -> list:
    """PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: spelers die al in de ANDERE
    match van DEZELFDE rotatie gekozen zijn, worden niet langer uitgesloten
    (Kim: "je mag toelaten dat je eenzelfde speler kiest die al [...] in de
    andere match van de rotatie speelt") - ze krijgen een suffix
    " - al bij M<x>" in de lijst, zodat dat VOOR het kiezen al zichtbaar is.
    Een speler die al de PARTNER is op dit slot (dus zichzelf, voor het
    andere slot van hetzelfde koppel) wordt wel nog steeds overgeslagen -
    anders zou je 1 speler 2x in hetzelfde koppel kunnen zetten.
    Een koppel dat in de ANDERE rotatie al samen speelde, blijft uitgesloten
    (ongewijzigd) - dat is een harde reglementregel (max. 1x samen per
    ontmoeting), geen tactische keuze."""
    r, m, i = slot
    zelfde_match_partner = sel.get((r, m, 1 - i))
    andere_matches_in_rotatie = {
        mm: (sel.get((r, mm, 0)), sel.get((r, mm, 1)))
        for mm in range(MATCHES_PER_ROTATION) if mm != m
    }
    partner = sel.get((r, m, 1 - i))
    andere_rot = set()
    for mm in range(MATCHES_PER_ROTATION):
        a, b = sel.get((1 - r, mm, 0)), sel.get((1 - r, mm, 1))
        if a and b:
            andere_rot.add(frozenset({a, b}))
    opties = [_GEEN]
    for u in volgorde:
        if u == zelfde_match_partner:
            continue
        if partner and frozenset({u, partner}) in andere_rot:
            continue
        suffix = ""
        for mm, (a, b) in andere_matches_in_rotatie.items():
            if u in (a, b):
                suffix = f" - al bij M{mm + 1}"
                break
        opties.append(f"{label_of[u]}{suffix}")
    return opties


def _slot_box(prefix, slot, sel, volgorde, label_of, label_txt):
    key = f"{prefix}_{slot[0]}{slot[1]}{slot[2]}"
    opties = _options_for(slot, sel, volgorde, label_of)
    # PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: de opgeslagen keuze draagt
    # geen " - al bij M<x>"-suffix, maar de optielijst nu soms wel - zoek de
    # bijpassende, eventueel ge-suffixte optie terug i.p.v. die te verliezen.
    huidige = st.session_state.get(key)
    if huidige not in opties:
        match = next((o for o in opties if o == huidige or o.startswith(f"{huidige} - ")), None)
        st.session_state[key] = match or _GEEN
    keuze = st.selectbox(label_txt, opties, key=key)
    uid_of = {v: k for k, v in label_of.items()}
    basis = keuze.split(" - al bij M")[0]
    if keuze != _GEEN:
        sel[slot] = uid_of.get(basis)
    else:
        sel.pop(slot, None)


def _slots_to_plan(sel, rotations=range(_N_ROT)):
    plan = []
    for r in rotations:
        rot = []
        for m in range(MATCHES_PER_ROTATION):
            a, b = sel.get((r, m, 0)), sel.get((r, m, 1))
            if not (a and b):
                return None
            rot.append(frozenset({a, b}))
        plan.append(rot)
    return plan


def _fill(prefix, plan, label_of, rotations=range(_N_ROT)) -> bool:
    waarden = {}
    for r in rotations:
        for m in range(MATCHES_PER_ROTATION):
            pair = sorted(plan[r][m], key=lambda u: label_of.get(u, u))
            for i in range(2):
                if pair[i] not in label_of:
                    return False
                waarden[f"{prefix}_{r}{m}{i}"] = label_of[pair[i]]
    st.session_state.update(waarden)
    return True


def _clear(prefix):
    for slot in _SLOTS:
        st.session_state[f"{prefix}_{slot[0]}{slot[1]}{slot[2]}"] = _GEEN


# ------------------------------------------------------------ weergave
def _pct_md(pp: dict) -> str:
    return (f":green[**{pp['p2'] * 100:.0f}% winst**] \u00b7 :orange[**{pp['p1'] * 100:.0f}% gelijk**] \u00b7 "
            f":red[**{pp['p0'] * 100:.0f}% verlies**]")


def _ps_sum(uids, fn):
    vals = [fn(u) for u in uids]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _plan_txt(plan, names) -> str:
    return "  |  ".join(
        f"R{r + 1}: " + " \u00b7 ".join(" / ".join(names.get(u, u) for u in sorted(p)) for p in rot)
        for r, rot in enumerate(plan)
    )


def _rotation_pairs_text(boards: list) -> tuple:
    """PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04: 'M1 A / B' per match,
    gegroepeerd per rotatie - lokale, minimale kopie van lineup_scenario_
    matrix._rotation_text_opp() (geen import, om koppeling tussen de 2
    modules te vermijden)."""
    rot1 = boards[0:MATCHES_PER_ROTATION]
    rot2 = boards[MATCHES_PER_ROTATION:2 * MATCHES_PER_ROTATION]

    def _fmt(rot):
        return "  \u00b7  ".join(
            f"M{m + 1} " + " / ".join(p.get("name", "?") for p in (b.get("opponent_pair") or []))
            for m, b in enumerate(rot)
        )
    return _fmt(rot1), _fmt(rot2)


def _save_snapshot(ploeg_id, opp_name, available_ids, own_names, own_ranks, own_ps,
                   opp_uids, opp_names, opp_ranks, opp_ps, own_plan, opp_plan) -> None:
    """PADEL_ANALYSIS_LINEUP_SNAPSHOT_2026-10-03 - zie moduledocstring. Faalt altijd stil."""
    try:
        datum = st.session_state.get(f"next_match_date_{ploeg_id}") or "onbekend"
        doc_id = f"{ploeg_id}__{str(datum).replace('/', '-')}"
        plan_sig = (
            tuple(tuple(sorted(p)) for rot in (own_plan or []) for p in rot),
            tuple(tuple(sorted(p)) for rot in (opp_plan or []) for p in rot),
        )
        flag = f"lineup_snapshot_saved_{doc_id}"
        if st.session_state.get(flag) == plan_sig:
            return
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        try:
            import lineup_lab as _llab
            scale = _llab.DEFAULT_WIN_PROBABILITY_SCALE
        except Exception:  # noqa: BLE001
            scale = None
        doc = {
            "ploeg_id": str(ploeg_id), "opponent_name": opp_name or "", "match_date": str(datum),
            "updated_at": now, "win_probability_scale": scale,
            "own_players": {u: {"name": own_names.get(u, u), "official_rank": own_ranks.get(u),
                                "padelstat": own_ps.get(u)} for u in available_ids},
            "opponent_players": {u: {"name": opp_names.get(u, u), "official_rank": opp_ranks.get(u),
                                     "padelstat": opp_ps.get(u)} for u in opp_uids},
        }
        if own_plan:
            doc["own_plan"] = [[sorted(p) for p in rot] for rot in own_plan]
        if opp_plan:
            doc["opponent_plan"] = [[sorted(p) for p in rot] for rot in opp_plan]
        ref = fb.db.collection(_SNAPSHOT_COLLECTION).document(doc_id)
        if st.session_state.get(flag) is None:
            doc["first_saved_at"] = now
        ref.set(doc, merge=True)
        st.session_state[flag] = plan_sig
    except Exception:  # noqa: BLE001
        pass


def render_plan_screen(*args, **kwargs) -> None:
    """Veilige wrapper: een fout toont een melding i.p.v. een blanco pagina."""
    try:
        _render_plan_screen(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        # st.rerun()/st.stop() werken via een (Streamlit-)exceptie - die NIET opvangen.
        if type(exc).__name__ in ("RerunException", "StopException") or any(
            k.__name__ == "ScriptControlException" for k in type(exc).__mro__
        ):
            raise
        st.error(f"Planscherm kon niet getoond worden: {type(exc).__name__}: {exc}")
        with st.expander("Technische details (stuur dit door bij een fout)", expanded=False):
            st.code(traceback.format_exc())


def _render_match_card(
    r, m, own_prefix, opp_prefix, own_sel, opp_sel, own_volgorde, opp_volgorde,
    own_label, opp_label, names_all, ctx, opp_dist, own_ranks, opp_ranks,
    played_k=None,
) -> None:
    """PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: 1 matchkaart. Toont, indien
    van toepassing, een RODE kop ("NIET sterkste duo, art. 6.6") voor onze
    en/of hun kant van DEZE rotatie i.p.v. enkel een tekstregel onderaan de
    pagina - zie moduledocstring."""
    own_rot_pairs = [own_sel.get((r, mm, 0)) and frozenset({own_sel[(r, mm, 0)], own_sel.get((r, mm, 1))})
                     for mm in range(MATCHES_PER_ROTATION)]
    opp_rot_pairs = [opp_sel.get((r, mm, 0)) and frozenset({opp_sel[(r, mm, 0)], opp_sel.get((r, mm, 1))})
                     for mm in range(MATCHES_PER_ROTATION)]
    own_order_bad = (
        None not in own_rot_pairs and _rotation_order_violation(own_rot_pairs, own_ranks)
    )
    opp_order_bad = (
        None not in opp_rot_pairs and _rotation_order_violation(opp_rot_pairs, opp_ranks)
    )
    with st.container(border=True):
        kop = f"**R{r + 1} \u00b7 Match {m + 1}**"
        if own_order_bad:
            kop += "  :red[**- onze volgorde: NIET art. 6.6-conform**]"
        if opp_order_bad:
            kop += "  :red[**- hun volgorde: NIET art. 6.6-conform**]"
        st.markdown(kop)
        c1, c2, c_mid, c3, c4 = st.columns([4, 4, 1, 4, 4])
        with c1:
            _slot_box(own_prefix, (r, m, 0), own_sel, own_volgorde, own_label, "Wij - speler 1")
        with c2:
            _slot_box(own_prefix, (r, m, 1), own_sel, own_volgorde, own_label, "Wij - speler 2")
        with c_mid:
            st.markdown(
                "<div style='text-align:center;padding-top:2rem;font-weight:700;"
                "font-size:1rem;color:inherit'>tegen</div>",
                unsafe_allow_html=True,
            )
        with c3:
            _slot_box(opp_prefix, (r, m, 0), opp_sel, opp_volgorde, opp_label, "Zij - speler 1")
        with c4:
            _slot_box(opp_prefix, (r, m, 1), opp_sel, opp_volgorde, opp_label, "Zij - speler 2")
        ons = [own_sel.get((r, m, i)) for i in range(2)]
        hun = [opp_sel.get((r, m, i)) for i in range(2)]
        delen = []
        if all(ons):
            ps = _ps_sum(ons, ctx.strength)
            delen.append(f"**{' / '.join(names_all.get(u, u) for u in ons)}**"
                         + (f" (ps {ps:.0f})" if ps is not None else ""))
        if all(hun):
            ps = _ps_sum(hun, ctx.opp_strength)
            delen.append(f"**{' / '.join(names_all.get(u, u) for u in hun)}**"
                         + (f" (ps {ps:.0f})" if ps is not None else ""))
        regel = "  tegen  ".join(delen)
        if all(ons) and opp_dist and not (r == 0 and played_k is not None):
            wpv = ctx.match_wp(frozenset(ons), r, m, opp_dist)
            kleur = "green" if wpv >= 0.55 else ("red" if wpv <= 0.45 else "orange")
            extra = "" if all(hun) else " (gemiddeld over de scenario's)"
            regel += f"  \u2192  :{kleur}[**{wpv * 100:.0f}% winkans**]{extra}"
        if regel:
            st.markdown(regel)


def _render_plan_screen(
    available_ids, synergy_fn, official_ranks_strict, name_lookup_global, ploeg_id,
    player_ratings, opponent_ratings, tournament_rules_dict, max_per_player,
    bundle, unique_opp_players,
) -> None:
    rules = tournament_rules_dict
    available_ids = [str(u) for u in available_ids]
    roster_uids = [str(p.get("user_id")) for p in unique_opp_players if p.get("user_id")]
    opp_ranks = {u: _cached_official_rank(u) for u in roster_uids}
    opp_ps = {u: v for u in roster_uids if (v := _cached_own_player_rating(u)) is not None}
    own_ps = {str(k): v for k, v in (player_ratings or {}).items() if v is not None}
    ctx = _Ctx(player_ratings, official_ranks_strict, opponent_ratings, opp_ranks)

    # PADEL_ANALYSIS_PLAN_SCREEN_V3_2026-10-04: de speler voor wie de analyse
    # loopt (gezet door page_lineup_lab.py) - voor de "Beste voor <naam>"-rij.
    viewing_player_id = st.session_state.get(f"viewing_player_id_{ploeg_id}")
    if viewing_player_id is not None:
        viewing_player_id = str(viewing_player_id)
        if viewing_player_id not in available_ids:
            viewing_player_id = None

    def _lbl(naam, rk, ps):
        info = " \u00b7 ".join(x for x in [f"P{int(rk)}" if rk is not None else "P?",
                                      f"ps {int(ps)}" if ps is not None else ""] if x)
        return f"{naam} ({info})"

    opp_names = {str(p.get("user_id")): p.get("name", "?") for p in unique_opp_players if p.get("user_id")}
    own_names = {u: name_lookup_global.get(u, u) for u in available_ids}
    opp_label = {u: _lbl(opp_names[u], opp_ranks.get(u), opp_ps.get(u)) for u in roster_uids}
    own_label = {u: _lbl(own_names[u], official_ranks_strict.get(u), own_ps.get(u)) for u in available_ids}
    names_all = {**own_names, **opp_names}

    # ---- scenario's: EXACT die van de scenario-analyse
    naam_naar_uid = {_norm_name(n): u for u, n in opp_names.items()}

    def _to_uid(p):
        u = str(p.get("user_id") or "")
        return u if u in opp_names else naam_naar_uid.get(_norm_name(p.get("name")))

    scen = []
    for i, s in enumerate(st.session_state.get(f"scen_matrix_scen_v3_{ploeg_id}") or []):
        pairs = []
        for b in s.get("boards") or []:
            ids = [_to_uid(p) for p in (b.get("opponent_pair") or [])]
            if len(ids) == 2 and None not in ids:
                pairs.append(frozenset(ids))
        if len(pairs) == _N_ROT * MATCHES_PER_ROTATION:
            scen.append({
                "name": f"S{i + 1}", "labels": s.get("labels") or [],
                "pairs": [pairs[0:2], pairs[2:4]], "w": s["weight"],
                # PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04: redenen + ruwe
                # boards meegeven, voor de duidelijkere caption en het
                # scenario-overzicht hieronder.
                "reasons": s.get("reasons") or "", "model_prob": s.get("model_prob"),
                "boards": s.get("boards") or [],
            })

    st.markdown('<div class="section-header">Rotatieplanner - plan voor de volledige ontmoeting</div>', unsafe_allow_html=True)
    st.caption(
        "Stel beide rotaties samen, voor de tegenstander en voor ons, speler per speler. Het eindresultaat "
        "onderaan wordt bij elke wijziging meteen herrekend. Gebruik de knoppen als vertrekpunt."
    )

    opp_prefix = f"plan_opp_v2_{ploeg_id}"
    own_prefix = f"plan_own_v2_{ploeg_id}"

    # PADEL_ANALYSIS_PLAN_SCREEN_V3_2026-10-04: opp_sel VOOR de scenario-knoppen
    # lezen (was voorheen pas erna), zodat we meteen kunnen tonen welk scenario
    # (indien van toepassing) al actief/geselecteerd is.
    opp_sel_voor_knoppen = _read_sel(opp_prefix, opp_label)
    opp_plan_voor_knoppen = _slots_to_plan(opp_sel_voor_knoppen)
    active_scenario_name = None
    if opp_plan_voor_knoppen is not None:
        for s in scen:
            if s["pairs"][0] == opp_plan_voor_knoppen[0] and s["pairs"][1] == opp_plan_voor_knoppen[1]:
                active_scenario_name = s["name"]
                break

    # ---- tegenstander snelkeuze
    st.markdown("**Tegenstander - snelkeuze** (zelfde scenario's en gewichten als de scenario-analyse)")
    if scen:
        per_rij = 5
        for start in range(0, len(scen), per_rij):
            cols = st.columns(per_rij)
            for col, s in zip(cols, scen[start:start + per_rij]):
                with col:
                    is_active = (s["name"] == active_scenario_name)
                    # PADEL_ANALYSIS_PLAN_SCREEN_V3_2026-10-04: vinkje + "primary"-stijl
                    # (gevulde knopkleur) voor het actief geselecteerde scenario.
                    btn_label = f"{'\u2713 ' if is_active else ''}{s['name']} \u00b7 {s['w'] * 100:.0f}%"
                    if st.button(
                        btn_label, key=f"{opp_prefix}_use_{s['name']}", use_container_width=True,
                        type=("primary" if is_active else "secondary"),
                    ):
                        if _fill(opp_prefix, s["pairs"], opp_label):
                            st.rerun(scope="fragment")
                        st.warning("Een speler van dit scenario zit niet in de tegenstander-selectie.")
                    # PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04: volledige
                    # omschrijving (geen afkapping meer) + aparte "waarom"-regel.
                    st.caption(" / ".join(s["labels"]))
                    if s.get("reasons"):
                        st.caption(f"*Waarom:* {s['reasons']}")
    else:
        st.caption("Nog geen scenario's - klik eerst op 'Bereken' in de scenario-analyse, of vul de tegenstander zelf in.")

    # PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04: scenario-overzicht
    # rechtstreeks in de planner - zie moduledocstring. Vervangt de losse
    # scenario-analyse-sectie NIET (die blijft ongewijzigd bestaan).
    if scen:
        with st.expander("Scenario-overzicht (uit de scenario-analyse)", expanded=False):
            st.caption(
                "Dezelfde scenario's als in 'Opstelling-scenario's' hierboven, nog eens kort samengevat - "
                "gebruik de S-knoppen hierboven om er een te kiezen."
            )
            rijen_scen = []
            for s in scen:
                r1_txt, r2_txt = _rotation_pairs_text(s.get("boards") or [])
                rijen_scen.append({
                    "Scenario": s["name"], "Gewicht": f"{s['w'] * 100:.0f}%",
                    "Wat": " / ".join(s["labels"]), "Rotatie 1": r1_txt, "Rotatie 2": r2_txt,
                    "Waarom": s.get("reasons") or "",
                })
            st.dataframe(rijen_scen, use_container_width=True, hide_index=True)

    if st.button("Tegenstander leegmaken", key=f"{opp_prefix}_clear"):
        _clear(opp_prefix)
        st.rerun(scope="fragment")

    # ---- huidige keuzes (voor opties, verdeling en voorstellen)
    opp_sel = _read_sel(opp_prefix, opp_label)
    own_sel = _read_sel(own_prefix, own_label)
    opp_plan = _slots_to_plan(opp_sel)
    opp_r1 = _slots_to_plan(opp_sel, rotations=[0])
    if opp_plan is not None:
        opp_dist = [(opp_plan[0], opp_plan[1], 1.0)]
        opp_bron = "de ingevulde tegenstander-opstelling"
    elif opp_r1 is not None:
        opp_dist = [(opp_r1[0], p, w) for p, w in _predict_r2(bundle, unique_opp_players, opp_r1[0],
                                                              opp_ranks, opp_ps, rules)]
        opp_bron = "hun ingevulde rotatie 1 + voorspelde rotatie 2"
    else:
        opp_dist = [(s["pairs"][0], s["pairs"][1], s["w"]) for s in scen]
        opp_bron = f"gewogen over S1-S{len(scen)}" if scen else ""

    # PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: "Rotatie 1 is gespeeld"
    # verplaatst naar bij de Rotatie 1-kop zelf (zie verderop, net voor de 2
    # matchkaarten van rotatie 1) i.p.v. hier, los, bovenaan de pagina.
    played_k = None
    if st.session_state.get(f"plan_r1_played_v2_{ploeg_id}"):
        uitslag_opgeslagen = st.session_state.get(f"plan_r1_score_v2_{ploeg_id}", "2-0")
        played_k = {"2-0": 2, "1-1": 1, "0-2": 0}[uitslag_opgeslagen]

    # PADEL_ANALYSIS_PLAN_SCREEN_V5_2026-10-04: haalbaarheid na rotatie 1 -
    # zie moduledocstring. Puur telwerk, geen kans nodig.
    forced_banner, toon_spread_sacrifice = _forced_outcome_after_r1(played_k)
    if forced_banner:
        st.markdown(forced_banner)

    # ---- onze voorstellen
    fixed_r1 = None
    if played_k is not None:
        r1 = _slots_to_plan(own_sel, rotations=[0])
        fixed_r1 = r1[0] if r1 else None
    plans = []
    if opp_dist and (played_k is None or fixed_r1 is not None):
        sig = (tuple(sorted(available_ids)), tuple(sorted((max_per_player or {}).items())),
               tuple(sorted(official_ranks_strict.items())), tuple(sorted(own_ps.items())),
               tuple(sorted(rules.items())) if rules else None,
               tuple(tuple(sorted(p)) for p in fixed_r1) if fixed_r1 else None)
        pk = f"plan_own_plans_v2_{ploeg_id}"
        if st.session_state.get(pk + "_sig") != sig:
            st.session_state[pk] = _own_plans(available_ids, synergy_fn, official_ranks_strict, player_ratings,
                                              opponent_ratings, rules, max_per_player, fixed_r1=fixed_r1)
            st.session_state[pk + "_sig"] = sig
        plans = st.session_state.get(pk) or []
    weakest = _weakest_two(available_ids, ctx)

    # PADEL_ANALYSIS_PLAN_SCREEN_V3_2026-10-04: huidige invulling - gebruikt om
    # de actieve rij in de voorstellen-tabel te markeren.
    own_plan_now = _slots_to_plan(own_sel)

    # PADEL_ANALYSIS_PLAN_SCREEN_V5_2026-10-04: de volledige voorstellen-
    # sectie (kop + tabel) in 1 kader - zie moduledocstring.
    with st.container(border=True):
        st.markdown("**Onze ploeg - voorstellen**" + (" (enkel rotatie 2)" if played_k is not None else ""))
        if not opp_dist:
            st.caption("Kies eerst een tegenstander-scenario of vul de tegenstander in.")
        elif played_k is not None and fixed_r1 is None:
            st.caption("Vul hieronder onze rotatie 1 in (wie speelde), dan wordt enkel rotatie 2 voorgesteld.")
        elif not plans:
            st.warning("Geen reglementair geldig plan met de huidige spelers, matchen per speler en puntengrens.")
        else:
            presets = _pick_presets(
                plans, opp_dist, ctx, weakest, played_k, viewing_player_id,
                include_spread_sacrifice=toon_spread_sacrifice,
            )
            rijen = []
            for kind, titel, uitleg in _PRESETS:
                if kind in presets:
                    plan, pp = presets[kind]
                    rijen.append((kind, titel, uitleg, plan, pp))
            if "self" in presets:
                plan, pp = presets["self"]
                naam = names_all.get(viewing_player_id, viewing_player_id)
                rijen.append(("self", f"Beste voor {naam}", "hoogste persoonlijke winkans voor deze speler", plan, pp))
            if not rijen:
                st.warning("Geen enkel voorstel kon berekend worden met de huidige instellingen.")
            else:
                # PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04: identieke
                # opstellingen samenvoegen tot 1 rij - zie moduledocstring.
                rijen = _merge_duplicate_rows(rijen)
                # PADEL_ANALYSIS_PLAN_SCREEN_V3_2026-10-04: enkel nog de vergelijkingstabel,
                # NIET langer ingeklapt, met een "Kies"-knop per rij en een duidelijke
                # markering van de rij die al actief is - zie moduledocstring.
                kop = st.columns([1.6, 3.0, 0.7, 0.7, 0.7, 0.9, 0.9])
                for c, h in zip(kop, ["Voorstel", "Plan", "Winst", "Gelijk", "Verlies", "Min. 1p", ""]):
                    c.markdown(f"**{h}**")
                for kind, titel, uitleg, plan, pp in rijen:
                    is_active = own_plan_now is not None and own_plan_now == plan
                    rij = st.columns([1.6, 3.0, 0.7, 0.7, 0.7, 0.9, 0.9])
                    titel_txt = f"\u2713 **{titel}**" if is_active else f"**{titel}**"
                    rij[0].markdown(titel_txt)
                    rij[0].caption(uitleg)
                    rij[1].markdown(_plan_txt(plan, names_all))
                    rij[2].markdown(f":green[**{pp['p2'] * 100:.0f}%**]" if is_active else f"{pp['p2'] * 100:.0f}%")
                    rij[3].markdown(f"{pp['p1'] * 100:.0f}%")
                    rij[4].markdown(f"{pp['p0'] * 100:.0f}%")
                    rij[5].markdown(f"{(pp['p2'] + pp['p1']) * 100:.0f}%")
                    with rij[6]:
                        if is_active:
                            st.button("Actief \u2713", key=f"{own_prefix}_p_{kind}", disabled=True, use_container_width=True)
                        elif st.button("Kies", key=f"{own_prefix}_p_{kind}", use_container_width=True):
                            if _fill(own_prefix, plan, own_label, rotations=[1] if played_k is not None else range(_N_ROT)):
                                st.rerun(scope="fragment")
            if weakest:
                st.caption("Onze 2 zwakste spelers (padelstat, anders klassement): "
                           + " en ".join(names_all.get(u, u) for u in sorted(weakest))
                           + (f". Tegenstander: {opp_bron}." if opp_bron else "."))
    if st.button("Onze ploeg leegmaken", key=f"{own_prefix}_clear"):
        _clear(own_prefix)
        st.rerun(scope="fragment")

    # ---- per rotatie: kop (+ "gespeeld"-balk bij rotatie 1) en de matchkaarten
    own_volgorde = sorted(available_ids, key=lambda u: -(ctx.strength(u) or 0))
    opp_volgorde = sorted(roster_uids, key=lambda u: -(opp_ranks.get(u) or 0))
    for r in range(_N_ROT):
        st.markdown(f"#### Rotatie {r + 1}")
        if r == 0:
            # PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: "Rotatie 1 is
            # gespeeld" nu HIER, bij Rotatie 1 zelf, i.p.v. los bovenaan de
            # hele pagina - zie moduledocstring.
            with st.container(border=True):
                c_g, c_u = st.columns([1, 2])
                with c_g:
                    gespeeld = st.checkbox(
                        "Rotatie 1 is gespeeld", key=f"plan_r1_played_v2_{ploeg_id}",
                    )
                if gespeeld:
                    with c_u:
                        st.radio(
                            "Uitslag rotatie 1 (voor ons)", ["2-0", "1-1", "0-2"], horizontal=True,
                            key=f"plan_r1_score_v2_{ploeg_id}",
                        )
        for m in range(MATCHES_PER_ROTATION):
            _render_match_card(
                r, m, own_prefix, opp_prefix, own_sel, opp_sel, own_volgorde, opp_volgorde,
                own_label, opp_label, names_all, ctx, opp_dist, official_ranks_strict, opp_ranks,
                played_k=played_k,
            )

    # ---- controles + eindresultaat
    # PADEL_ANALYSIS_PLAN_SCREEN_V4_2026-10-04: de art. 6.6-overtreding wordt
    # nu INLINE op de matchkaart getoond (zie _render_match_card hierboven),
    # dus _check_encounter() (include_order=False intern) rapporteert hier
    # enkel nog de overige, ontmoeting-brede controles.
    opp_plan = _slots_to_plan(opp_sel)
    opp_rots = [_slots_to_plan(opp_sel, rotations=[r]) for r in range(_N_ROT)]
    for f in _check_encounter([x[0] if x else [] for x in opp_rots], opp_ranks, rules, "Tegenstander"):
        st.markdown(f":red[{f}]")
    own_plan = _slots_to_plan(own_sel)
    own_rots = [_slots_to_plan(own_sel, rotations=[r]) for r in range(_N_ROT)]
    for f in _check_encounter([x[0] if x else [] for x in own_rots], official_ranks_strict, rules,
                              "Onze ploeg", max_per_player):
        st.markdown(f":red[{f}]")

    _save_snapshot(ploeg_id, (bundle or {}).get("team_name") or "", available_ids, own_names,
                   official_ranks_strict, own_ps, roster_uids, opp_names, opp_ranks, opp_ps, own_plan, opp_plan)

    if own_plan is None:
        st.info("Vul alle 8 vakjes van onze ploeg in (of kies een voorstel) om het eindresultaat te zien.")
        return
    if not opp_dist:
        st.info("Kies een tegenstander-scenario of vul de tegenstander in om het eindresultaat te zien.")
        return
    pp = ctx.outcome(own_plan, opp_dist, played_k)
    st.markdown("### Eindresultaat: " + _pct_md(pp))
    ev = sum(ctx.match_wp(own_plan[1][m], 1, m, opp_dist) for m in range(MATCHES_PER_ROTATION))
    ev += played_k if played_k is not None else sum(
        ctx.match_wp(own_plan[0][m], 0, m, opp_dist) for m in range(MATCHES_PER_ROTATION))
    st.markdown(f"Verwacht **{ev:.1f}** gewonnen matchen op 4 \u00b7 tegenstander: {opp_bron}.")
