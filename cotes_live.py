# -*- coding: utf-8 -*-
"""Cotes reçues de bookmakers via The Odds API, jamais synthétisées.
Budget gratuit : cinq événements/jour, deux marchés/une région (10 crédits),
réserve 80 crédits, arrêt si quota inconnu. Clé uniquement dans les Secrets CI.
Sans prix exact récent : analyse seule. Aucune substitution par un prix CSV.
"""
import datetime
import json
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
os.chdir(RACINE)
sys.path.insert(0, RACINE)

CHEMIN = os.path.join(RACINE, "data", "cotes_live.json")
BASE = "https://api.the-odds-api.com/v4"

# division co.uk → sport The Odds API (18 des 21 divisions sont couvertes ;
# les divisions écossaises inférieures ne le sont pas)
SPORTS = {
    "E0": "soccer_epl",
    "E1": "soccer_efl_champ",
    "E2": "soccer_england_league1",
    "E3": "soccer_england_league2",
    "SP1": "soccer_spain_la_liga",
    "SP2": "soccer_spain_segunda_division",
    "I1": "soccer_italy_serie_a",
    "I2": "soccer_italy_serie_b",
    "D1": "soccer_germany_bundesliga",
    "D2": "soccer_germany_bundesliga2",
    "F1": "soccer_france_ligue_one",
    "F2": "soccer_france_ligue_two",
    "N1": "soccer_netherlands_eredivisie",
    "B1": "soccer_belgium_first_div",
    "P1": "soccer_portugal_primeira_liga",
    "T1": "soccer_turkey_super_league",
    "G1": "soccer_greece_super_league",
    "SC0": "soccer_spl",
}
BIG5 = ["E0", "SP1", "I1", "D1", "F1"]

# Noms The Odds API qui ne passent pas par le Mappeur d'ESPN (complément).
# Vérifiés contre les CSV co.uk de la saison en cours.
MANUEL_COTES = {
    "Brighton and Hove Albion": "Brighton",
    "Wimbledon": "AFC Wimbledon",
    "Stockport County FC": "Stockport",
    "Stockport County": "Stockport",
    "AD Ceuta FC": "Ceuta",
    "Celta Fortuna": "Celta B",
    "Real Racing Club de Santander": "Santander",
    "Hamburger SV": "Hamburg",
    "FSV Mainz 05": "Mainz",
    "SC Freiburg": "Freiburg",
    "Borussia Monchengladbach": "M'gladbach",
    "Borussia Mönchengladbach": "M'gladbach",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "Paris Saint Germain": "Paris SG",
    "RC Lens": "Lens",
    "Le Mans FC": "Le Mans",
}

RESERVE = 80
MAX_EVENEMENTS_JOUR = 5
BUDGET = os.path.join(RACINE, "data", "odds_budget.json")


def cle():
    return (os.environ.get("ODDS_API_KEY") or "").strip()


def _curl_json(url):
    import tempfile
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        r = subprocess.run(["curl", "-sS", "--fail", "--compressed", "-D", path,
                            "--max-time", "40", url], capture_output=True, text=True, timeout=45)
        ent = {}
        with open(path) as f:
            for ligne in f:
                if ":" in ligne:
                    k, v = ligne.split(":", 1)
                    ent[k.strip().lower()] = v.strip()
        try:
            data = json.loads(r.stdout) if r.returncode == 0 else None
        except ValueError:
            data = None
        return data, ent
    except (OSError, subprocess.TimeoutExpired):
        return None, {}
    finally:
        os.unlink(path)


def charger():
    try:
        with open(CHEMIN) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"evenements": []}


def _sauver(path, d):
    with open(path + ".part", "w") as f:
        json.dump(d, f)
    os.replace(path + ".part", path)


def lire_prix(e, div, home, away, maintenant):
    """Conserve le prix exact, le sens, la ligne et les horodatages reçus."""
    from cotation import option_outcome
    prix = []
    for bk in e.get("bookmakers") or []:
        for mk in bk.get("markets") or []:
            for outcome in mk.get("outcomes") or []:
                opt = option_outcome(mk.get("key"), outcome, e)
                if not opt:
                    continue
                try:
                    cote = float(outcome["price"])
                    if not 1 < cote < 10000:
                        continue
                except (ValueError, TypeError, KeyError):
                    continue
                prix.append({"option": opt, "price": cote, "bookmaker": bk.get("key"),
                             "bookmaker_nom": bk.get("title"), "market": mk.get("key"),
                             "line": outcome.get("point"), "event_id": e.get("id"),
                             "last_update": mk.get("last_update") or bk.get("last_update"),
                             "fetched_at": maintenant, "commence_time": e.get("commence_time")})
    return {"div": div, "home": home, "away": away,
            "debut_utc": e.get("commence_time"), "event_id": e.get("id"), "prix": prix}


def rafraichir(db, force=False):
    """5 événements/jour × 2 marchés : 310 crédits/31 j, réserve 80.
    Même --force ne contourne pas le quota ou le plafond journalier.
    """
    k = cle()
    if not k:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    jour = (now + datetime.timedelta(hours=1)).date().isoformat()
    try:
        with open(BUDGET) as f:
            ledger = json.load(f)
    except (OSError, ValueError):
        ledger = {"jours": {}}
    lot = ledger.setdefault("jours", {}).setdefault(jour, {"tentatives": [], "credits_max": 0})
    if len(lot["tentatives"]) >= MAX_EVENEMENTS_JOUR:
        return 0
    # Interrogation gratuite ; sans en-tête fiable, aucune requête payante.
    _, ent = _curl_json(f"{BASE}/sports/?apiKey={k}&all=false")
    try:
        quota = int(ent["x-requests-remaining"])
    except (KeyError, TypeError, ValueError):
        print("cotes : quota inconnu, collecte payante suspendue")
        return 0
    if quota - 2 < RESERVE:
        return 0
    from calendrier import Mappeur
    mappeur = Mappeur({d: sorted(L.get("forces", {})) for d, L in db["ligues"].items()})
    os.environ["PRONOS_SANS_CALENDRIER"] = "1"
    import serveur
    serveur.DB = db
    analyses = {(m["div"], m["home"], m["away"], m["date"]): m for m in serveur.api_matchs()}
    candidats = []
    divs = sorted({f["div"] for f in db.get("fixtures", []) if f.get("date") == jour and f["div"] in SPORTS},
                  key=lambda d: (d not in BIG5, d))[:5]
    for div in divs:
        events, _ = _curl_json(f"{BASE}/sports/{SPORTS[div]}/events?apiKey={k}")
        if not isinstance(events, list):
            continue
        for e in events:
            try:
                debut = datetime.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
                date = (debut + datetime.timedelta(hours=1)).date().isoformat()
                if debut <= now or date != jour:
                    continue
                h = MANUEL_COTES.get(e["home_team"]) or mappeur.traduire(div, e["home_team"])
                a = MANUEL_COTES.get(e["away_team"]) or mappeur.traduire(div, e["away_team"])
                m = analyses.get((div, h, a, date))
                if not m or not m.get("disponible"):
                    continue
                score = max([m.get("over", {}).get("1.5", 0)] + list(m.get("double_chance", {}).values()))
                if score < (0.85 if div in serveur.DIVS_INSTABLES else 0.75):
                    continue
                candidats.append((score, div, h, a, e))
            except (KeyError, TypeError, ValueError):
                continue
    cache = charger()
    evs = {e["event_id"]: e for e in cache.get("evenements", []) if e.get("event_id")}
    n = 0
    for _, div, h, a, e in sorted(candidats, key=lambda x: (-x[0], x[1], x[2])):
        if len(lot["tentatives"]) >= MAX_EVENEMENTS_JOUR or quota - 2 < RESERVE:
            break
        if e["id"] in lot["tentatives"]:
            continue
        # Réserver AVANT l'appel protège aussi contre une interruption du job.
        lot["tentatives"].append(e["id"])
        lot["credits_max"] += 2
        ledger["quota_restant_observe"] = quota
        _sauver(BUDGET, ledger)
        data, headers = _curl_json(f"{BASE}/sports/{SPORTS[div]}/events/{e['id']}/odds?apiKey={k}"
            "&regions=eu&markets=alternate_totals,double_chance&oddsFormat=decimal")
        quota -= 2
        if isinstance(data, dict) and data.get("id"):
            evs[e["id"]] = lire_prix(data, div, h, a, now.isoformat())
            n += 1
        try:
            quota = int(headers["x-requests-remaining"])
        except (KeyError, ValueError, TypeError):
            break  # coût désormais inconnu, ne pas multiplier les appels
    _sauver(CHEMIN, {"genere_le": now.isoformat(), "quota_restant": quota,
                     "evenements": [e for e in evs.values() if (e.get("debut_utc") or "") >= now.isoformat()[:10]]})
    return n


def appliquer(db):
    """N'expose jamais les anciennes moyennes CSV comme prix bookmaker."""
    from cotation import valide
    evs = charger().get("evenements") or []
    lut = {}
    for e in evs:
        try:
            dt = datetime.datetime.fromisoformat(e["debut_utc"].replace("Z", "+00:00"))
            jour = (dt + datetime.timedelta(hours=1)).date().isoformat()
            lut[e["div"], e["home"], e["away"], jour] = [p for p in e.get("prix", []) if valide(p)]
        except (KeyError, ValueError, TypeError):
            continue
    # Un bookmaker commun au maximum de rencontres : coupons exécutables.
    couverture = {}
    for prix in lut.values():
        for book in {p["bookmaker"] for p in prix}:
            couverture[book] = couverture.get(book, 0) + 1
    book = max(sorted(couverture), key=couverture.get) if couverture else None
    n = 0
    for f in db.get("fixtures", []):
        for champ in ("cote_1", "cote_X", "cote_2", "cote_over", "cote_under",
                      "cote_max_1", "cote_max_X", "cote_max_2"):
            f[champ] = None
        f["cotations"] = {p["option"]: p for p in lut.get((f.get("div"), f.get("home"), f.get("away"), f.get("date")), []) if p["bookmaker"] == book}
        f["source_cotes"] = book if f["cotations"] else None
        for opt, champ in (("1", "cote_1"), ("X", "cote_X"), ("2", "cote_2"), ("over 2.5", "cote_over"), ("under 2.5", "cote_under")):
            f[champ] = f["cotations"].get(opt, {}).get("price")
        n += bool(f["cotations"])
    return n


if __name__ == "__main__":
    with open(os.path.join(RACINE, "data", "modeles.json")) as f:
        db = json.load(f)
    print("cotes :", rafraichir(db), "événements actualisés")
