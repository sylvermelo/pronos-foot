"""
xG RÉELS — Understat (gratuit, sans compte, sans clé).

Understat publie les expected goals (xG) de CHAQUE match des 5 grands
championnats : Angleterre (E0), Espagne (SP1), Italie (I1), Allemagne (D1),
France (F1), saisons 2014/15 → aujourd'hui. Endpoint découvert en analysant
la page : https://understat.com/getLeagueData/{ligue}/{saison} (JSON gzippé).

Ce module télécharge les saisons utiles, traduit les noms d'équipes vers la
nomenclature co.uk (celle du moteur) et écrit data/xg_understat.json :

    {"E0": [{"date": "2025-08-15", "home": "Liverpool", "away": "Bournemouth",
             "xg_h": 2.33, "xg_a": 1.57, "hg": 4, "ag": 2}, ...], ...}

Usage :
    python3 xg.py            télécharge (si absent ou vieux > 7 jours)
    python3 xg.py --force    télécharge toujours
"""
import datetime
import json
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.path.join(RACINE, "data", "xg_understat.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Understat → division co.uk du moteur
LIGUES = {"EPL": "E0", "La_liga": "SP1", "Serie_A": "I1",
          "Bundesliga": "D1", "Ligue_1": "F1"}
# saisons Understat (année de début) — alignées sur les 5 saisons du moteur
SAISONS = ["2021", "2022", "2023", "2024", "2025", "2026"]

# noms Understat → noms co.uk (mesurés ; le flou + suffixes complètent)
MANUEL = {
    "Manchester United": "Man United", "Manchester City": "Man City",
    "Newcastle United": "Newcastle", "Wolverhampton Wanderers": "Wolves",
    "Nottingham Forest": "Nottm Forest", "Tottenham": "Tottenham",
    "West Ham": "West Ham", "Brighton": "Brighton",
    "Paris Saint Germain": "Paris SG", "Saint-Etienne": "St Etienne",
    "Atletico Madrid": "Ath Madrid", "Athletic Club": "Ath Bilbao",
    "Real Sociedad": "Sociedad", "Real Betis": "Betis", "Celta Vigo": "Celta",
    "Rayo Vallecano": "Rayo Vallecano", "Deportivo Alaves": "Alaves",
    "Espanyol": "Espanol", "Real Oviedo": "Oviedo", "Elche": "Elche",
    "AC Milan": "Milan", "Inter": "Inter", "Hellas Verona": "Verona",
    "Parma Calcio 1913": "Parma", "Deportivo La Coruna": "La Coruna",
    "Borussia Dortmund": "Dortmund", "Borussia Moenchengladbach": "M'gladbach",
    "Borussia Mönchengladbach": "M'gladbach",
    "Eintracht Frankfurt": "Ein Frankfurt", "1899 Hoffenheim": "Hoffenheim",
    "Mainz 05": "Mainz", "1. FSV Mainz 05": "Mainz",
    "RB Leipzig": "RB Leipzig", "Bayern Munich": "Bayern Munich",
    "Bayer Leverkusen": "Leverkusen", "FC St. Pauli": "St Pauli",
    "1. FC Heidenheim": "Heidenheim", "1. FC Heidenheim 1846": "Heidenheim",
    "1. FC Union Berlin": "Union Berlin", "SC Freiburg": "Freiburg",
    "VfL Wolfsburg": "Wolfsburg", "SV Werder Bremen": "Werder Bremen",
    "FC Augsburg": "Augsburg", "Holstein Kiel": "Holstein Kiel",
    "VfB Stuttgart": "Stuttgart", "FC Cologne": "FC Koln", "1. FC Köln": "FC Koln",
    "FC Koln": "FC Koln", "Arminia Bielefeld": "Bielefeld",
    "Hamburger SV": "Hamburg", "FC Schalke 04": "Schalke 04",
    "Borussia M.Gladbach": "M'gladbach", "RasenBallsport Leipzig": "RB Leipzig",
    "Hertha Berlin": "Hertha", "Greuther Fuerth": "Greuther Furth",
}


def _curl_json(url):
    try:
        p = subprocess.run(["curl", "-s", "-m", "30", "--compressed",
                            "-H", f"User-Agent: {UA}",
                            "-H", "X-Requested-With: XMLHttpRequest", url],
                           capture_output=True, text=True, timeout=40)
        return json.loads(p.stdout) if p.stdout.strip() else None
    except Exception:
        return None


def telecharger():
    """Récupère toutes les ligues/saisons et rend {div: [matchs xG]}."""
    from calendrier import Mappeur, _norme
    import difflib
    # cibles de traduction : équipes actuelles DU MOTEUR + tous les noms vus
    # dans les CSV historiques co.uk (équipes reléguées incluses, ex. Norwich)
    import glob
    import pandas as pd
    with open(os.path.join(RACINE, "data", "modeles.json")) as f:
        db = json.load(f)
    eq = {d: set(L["forces"].keys()) for d, L in db.get("ligues", {}).items()}
    for fcsv in glob.glob(os.path.join(RACINE, "data", "2*_*.csv")):
        base = os.path.basename(fcsv).replace(".csv", "")
        saison, div = base.split("_")
        if div not in LIGUES.values() or saison not in (
                "2122", "2223", "2324", "2425", "2526", "2627"):
            continue
        try:
            x = pd.read_csv(fcsv, encoding="latin-1", usecols=["HomeTeam", "AwayTeam"])
        except Exception:
            continue
        eq.setdefault(div, set()).update(
            x["HomeTeam"].dropna().astype(str))
        eq[div].update(x["AwayTeam"].dropna().astype(str))
    eq = {d: sorted(v) for d, v in eq.items()}
    map_ = Mappeur(eq)

    def traduire(div, nom):
        if nom in MANUEL and MANUEL[nom] in eq.get(div, []):
            return MANUEL[nom]
        return map_.traduire(div, nom)

    out = {d: [] for d in LIGUES.values()}
    rates = {}
    vus = {d: set() for d in LIGUES.values()}
    for slug, div in LIGUES.items():
        for saison in SAISONS:
            d = _curl_json(f"https://understat.com/getLeagueData/{slug}/{saison}")
            if not d or "dates" not in d:
                print(f"  {slug} {saison} : inaccessible (ignoré)")
                continue
            n = 0
            for m in d["dates"]:
                if not m.get("isResult"):
                    continue
                h = traduire(div, m["h"]["title"])
                a = traduire(div, m["a"]["title"])
                if not h or not a:
                    cle = f"{m['h']['title']}|{m['a']['title']}"
                    rates[cle] = rates.get(cle, 0) + 1
                    continue
                date = (m.get("datetime") or "")[:10]
                cle = (date, h, a)
                if cle in vus[div]:
                    continue
                vus[div].add(cle)
                try:
                    xg_h = max(0.05, round(float(m["xG"]["h"]), 3))
                    xg_a = max(0.05, round(float(m["xG"]["a"]), 3))
                except (KeyError, TypeError, ValueError):
                    continue
                out[div].append({"date": date, "home": h, "away": a,
                                 "xg_h": xg_h, "xg_a": xg_a,
                                 "hg": int(m["goals"]["h"]), "ag": int(m["goals"]["a"])})
                n += 1
            print(f"  {slug} {saison} : {n} matchs xG")
    if rates:
        print("  noms non traduits :", json.dumps(rates, ensure_ascii=False)[:500])
    return out


def frais(force=False, jours=7):
    """Télécharge seulement si le cache est absent ou vieux (> jours)."""
    if not force and os.path.exists(CHEMIN):
        age = (datetime.datetime.now()
               - datetime.datetime.fromtimestamp(os.path.getmtime(CHEMIN))).days
        if age < jours:
            with open(CHEMIN) as f:
                return json.load(f)
    data = telecharger()
    if any(data.values()):
        tmp = CHEMIN + ".part"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, CHEMIN)
    return data


def charger():
    """Rend le cache xG s'il existe (sinon {})."""
    try:
        with open(CHEMIN) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


if __name__ == "__main__":
    force = "--force" in sys.argv
    data = frais(force=force)
    tot = sum(len(v) for v in data.values())
    print(f"xG Understat : {tot} matchs "
          f"({', '.join(f'{d}:{len(v)}' for d, v in data.items() if v)}) → {CHEMIN}")
