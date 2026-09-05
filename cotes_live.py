# -*- coding: utf-8 -*-
"""
Cotes EN DIRECT — The Odds API (compte gratuit, 500 crédits/mois).

Pourquoi : football-data.co.uk publie des cotes MOYENNES mises à jour une fois
par jour. The Odds API donne les cotes de Pinnacle (le bookmaker le plus net du
marché) en direct, pour les matchs d'aujourd'hui et demain — exactement là où
la fraîcheur compte (combinés du jour, comparaison cote juste / cote marché).

Règles de sécurité et de budget (IMPORTANT) :
  · la clé API n'est JAMAIS écrite dans le dépôt : elle vient de la variable
    d'environnement ODDS_API_KEY (secret GitHub Actions dans le CI) ;
  · 500 crédits/mois seulement → une seule vraie mise à jour par jour (cache
    de 20 h), 7 sports maximum par passage (2 crédits par sport : h2h + totals),
    et garde-fou : si le quota restant passe sous la réserve, on s'arrête ;
  · sans clé, sans réseau ou sans quota : aucun crash — les cotes co.uk
    déjà présentes dans le calendrier restent en place.

Sortie : data/cotes_live.json
  {"genere_le": ..., "quota_restant": n, "evenements": [
      {"div": "E0", "debut_utc": "2026-09-05T16:30:00Z",
       "home": "Hull", "away": "Aston Villa",        # noms co.uk (traduits)
       "cote_1": 4.15, "cote_X": 3.74, "cote_2": 1.94,
       "cote_over": 1.89, "cote_under": 2.02, "ligne": 2.5}, ...]}
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

CACHE_HEURES = 20        # une vraie mise à jour par jour au maximum
MAX_SPORTS = 7           # 7 sports × 2 marchés = 14 crédits par passage
RESERVE = 80             # crédits à ne jamais entamer (fin de mois tranquille)


def cle():
    """La clé API vient de l'environnement. Jamais du dépôt."""
    return (os.environ.get("ODDS_API_KEY") or "").strip()


def _curl_json(url):
    """GET via curl (urllib est bloqué par certains filtres TLS ici)."""
    try:
        r = subprocess.run(["curl", "-s", "-D", "-", "--compressed",
                            "--max-time", "40", url],
                           capture_output=True, text=True, timeout=55)
    except Exception:
        return None, {}
    brut = r.stdout or ""
    sep = "\r\n\r\n" if "\r\n\r\n" in brut else "\n\n"
    entetes_txt, _, corps = brut.partition(sep)
    entetes = {}
    for ligne in entetes_txt.splitlines():
        if ":" in ligne:
            k, v = ligne.split(":", 1)
            entetes[k.strip().lower()] = v.strip()
    try:
        return json.loads(corps), entetes
    except Exception:
        return None, entetes


def _quota_restant(k):
    """Interroge /sports (gratuit, 0 crédit) pour lire le quota restant."""
    _, ent = _curl_json(f"{BASE}/sports/?apiKey={k}&all=false")
    try:
        return int(ent.get("x-requests-remaining", -1))
    except (TypeError, ValueError):
        return -1


def _sports_utiles(db):
    """Divisions avec des matchs dans les 48 prochaines heures, triées :
    le plus de matchs d'abord, puis le Big 5 en priorité. Max MAX_SPORTS."""
    fx = (db or {}).get("fixtures") or []
    now = datetime.datetime.now(datetime.timezone.utc)
    fin = now + datetime.timedelta(hours=48)
    compte = {}
    for f in fx:
        div = f.get("div")
        if div not in SPORTS:
            continue
        d = (f.get("date") or "").strip()
        if not d:
            continue
        try:                     # date locale du match, large fenêtre ±2 j
            dj = datetime.datetime.strptime(d, "%Y-%m-%d").replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if now - datetime.timedelta(days=2) <= dj <= fin + datetime.timedelta(days=1):
            compte[div] = compte.get(div, 0) + 1
    # Big 5 d'abord (liquidité Pinnacle maximale, ligues les plus suivies),
    # puis les autres divisions au nombre de matchs. Jamais plus de MAX_SPORTS
    # par passage : 7 sports × 2 crédits = 14/jour, soit ~430 sur un mois de
    # 31 jours — sous les 500 crédits du plan gratuit, réserve comprise.
    ordre = sorted(compte, key=lambda d: (d not in BIG5, -compte[d], d))
    return ordre[:MAX_SPORTS]


def _traduire_noms(db):
    """Mappeur noms API (style ESPN) → noms co.uk, par division."""
    from calendrier import Mappeur
    eq = {}
    for div, L in (db.get("ligues") or {}).items():
        noms = set((L.get("forces") or {}).keys())
        noms.update(L.get("equipes_actuelles") or [])
        eq[div] = sorted(noms)
    return Mappeur(eq)


def telecharger(db, k):
    """Télécharge les cotes Pinnacle (1X2 + over/under 2.5) des sports utiles.
    Renvoie (evenements, quota_restant)."""
    quota = _quota_restant(k)
    if quota == 0:
        raise RuntimeError("quota épuisé (0 crédit restant)")
    if 0 < quota < RESERVE:
        print(f"  cotes live : quota restant {quota} < réserve {RESERVE} — passe")
        return [], quota
    sports = _sports_utiles(db)
    if not sports:
        return [], quota
    mappeur = _traduire_noms(db)
    inv = {v: d for d, v in SPORTS.items()}
    evenements, rates = [], {}
    for div in sports:
        sk = SPORTS[div]
        url = (f"{BASE}/sports/{sk}/odds/?apiKey={k}&regions=eu"
               f"&markets=h2h,totals&oddsFormat=decimal&bookmakers=pinnacle")
        evs, ent = _curl_json(url)
        if ent.get("x-requests-remaining"):
            try:
                quota = int(ent["x-requests-remaining"])
            except ValueError:
                pass
        if not isinstance(evs, list):
            print(f"  cotes live : {div} → réponse invalide, ignoré")
            continue
        for e in evs:
            try:
                def _trad(nom):
                    if nom in MANUEL_COTES:
                        return MANUEL_COTES[nom]
                    return mappeur.traduire(div, nom)
                h = _trad(e["home_team"]) or e["home_team"]
                a = _trad(e["away_team"]) or e["away_team"]
                if not _trad(e["home_team"]):
                    rates[e["home_team"]] = rates.get(e["home_team"], 0) + 1
                if not _trad(e["away_team"]):
                    rates[e["away_team"]] = rates.get(e["away_team"], 0) + 1
                c1 = cX = c2 = cov = cuu = None
                ligne = None
                for bk in e.get("bookmakers") or []:
                    for mk in bk.get("markets") or []:
                        if mk.get("key") == "h2h":
                            for o in mk.get("outcomes") or []:
                                if o["name"] == e["home_team"]:
                                    c1 = o["price"]
                                elif o["name"] == e["away_team"]:
                                    c2 = o["price"]
                                elif o["name"] == "Draw":
                                    cX = o["price"]
                        elif mk.get("key") == "totals":
                            for o in mk.get("outcomes") or []:
                                if o.get("point") != 2.5:
                                    continue
                                ligne = 2.5
                                if o["name"] == "Over":
                                    cov = o["price"]
                                elif o["name"] == "Under":
                                    cuu = o["price"]
                if c1 and c2 and cX:
                    evenements.append({
                        "div": div, "debut_utc": e.get("commence_time"),
                        "home": h, "away": a,
                        "cote_1": c1, "cote_X": cX, "cote_2": c2,
                        "cote_over": cov, "cote_under": cuu, "ligne": ligne})
            except (KeyError, TypeError):
                continue
        if quota >= 0 and quota - 2 < RESERVE:
            print(f"  cotes live : quota {quota}, on s'arrête là (réserve)")
            break
    if rates:
        print("  cotes live : noms non traduits :",
              json.dumps(rates, ensure_ascii=False)[:300])
    return evenements, quota


def rafraichir(db, force=False):
    """Met à jour le cache s'il a plus de CACHE_HEURES. Renvoie le nombre de
    sports effectivement téléchargés (0 = cache encore frais / pas de clé)."""
    k = cle()
    if not k:
        print("  cotes live : clé ODDS_API_KEY absente — passe (cotes co.uk conservées)")
        return 0
    if not force and os.path.exists(CHEMIN):
        age_h = (datetime.datetime.now()
                 - datetime.datetime.fromtimestamp(os.path.getmtime(CHEMIN))
                 ).total_seconds() / 3600.0
        if age_h < CACHE_HEURES:
            return 0
    evs, quota = telecharger(db, k)
    if evs:
        tmp = CHEMIN + ".part"
        with open(tmp, "w") as f:
            json.dump({"genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
                       "quota_restant": quota, "evenements": evs}, f)
        os.replace(tmp, CHEMIN)
    return len({e["div"] for e in evs})


def charger():
    if not os.path.exists(CHEMIN):
        return {"evenements": []}
    try:
        with open(CHEMIN) as f:
            return json.load(f)
    except Exception:
        return {"evenements": []}


def appliquer(db):
    """Écrase les cotes des fixtures avec Pinnacle quand le match est reconnu
    (même division, mêmes équipes, date ± 1 jour). Retourne le nb écrasées.
    Les fixtures sans correspondance gardent leurs cotes co.uk."""
    evs = charger().get("evenements") or []
    if not evs:
        return 0
    # index par (div, home, away, date)
    lut = {}
    for e in evs:
        d = (e.get("debut_utc") or "")[:10]
        if not d:
            continue
        try:
            dj = datetime.datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        for delta in (0, -1, 1):
            lut[(e["div"], e["home"], e["away"],
                 (dj + datetime.timedelta(days=delta)).isoformat())] = e
    n = 0
    for f in (db.get("fixtures") or []):
        e = lut.get((f.get("div"), f.get("home"), f.get("away"), f.get("date")))
        if not e:
            continue
        f["cote_1"] = e["cote_1"]
        f["cote_X"] = e["cote_X"]
        f["cote_2"] = e["cote_2"]
        if e.get("cote_over") and e.get("cote_under"):
            f["cote_over"] = e["cote_over"]
            f["cote_under"] = e["cote_under"]
        f["source_cotes"] = "pinnacle"
        n += 1
    return n


if __name__ == "__main__":
    with open(os.path.join(RACINE, "data", "modeles.json")) as f:
        db = json.load(f)
    ns = rafraichir(db, force="--force" in sys.argv)
    print(f"cotes live : {ns} sport(s) téléchargé(s)")
    n = appliquer(db)
    print(f"cotes live : {n} fixture(s) avec cotes Pinnacle en direct")
