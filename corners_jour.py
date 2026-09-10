"""CORNERS DU JOUR — sélections par match pour la vitrine « Choix exotiques ».

Règle utilisateur (11/09) : PLUS DE COUPON montante. Uniquement des
sélections simples, un choix clair par match : le handicap le plus pénalisant
sur la dominante attendue qui tient encore ≥ 60 % de fréquence réelle
(calibré walk-forward, décote intégrée). Affichage vitrine en 3 couleurs :
vert ≥ 85 %, ambre 70–84 %, rouge 60–69 %.

Résolution : colonnes corners (HC/AC) des CSV football-data.co.uk de la
saison courante — la source met 1 à 3 jours à publier les corners d'un match ;
tant qu'ils manquent, le résultat reste honnêtement « en attente ».

Fichiers : archive data/suivi_corners.json (30 jours glissants) ;
vue publiée data/corners_jour.json (10 derniers jours) → site/ via la CI.
"""
import csv
import datetime
import json
import os
import unicodedata

import serveur
from serveur import DB
import modeles_secondaires as MS
import corners as CN

RACINE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(RACINE, "data", "suivi_corners.json")
PUBLIE = os.path.join(RACINE, "data", "corners_jour.json")
GARDE_JOURS = 10
SEUIL_MIN = 0.60        # plancher utilisateur (60 à 100 %)
COTE_PLANCHER = 1.02    # en dessous, le conseil n'a aucune valeur
# seuils D = corners(dominante) − corners(adversaire) par famille (backtest)
SEUILS = {"+2": -1, "+1": 0, "victoire": 1, "-1": 2, "-2": 3, "-3": 4, "-4": 5}


def _source():
    fx = DB.get("fixtures", [])
    cal = os.path.join(RACINE, "data", "calendrier.json")
    if os.path.exists(cal):
        try:
            with open(cal, encoding="utf-8") as f:
                fx = json.load(f).get("matchs", []) or fx
        except (ValueError, OSError):
            pass
    return fx


def pick_corners(m):
    """Le handicap le plus pénalisant qui tient ≥ SEUIL_MIN (calibré)."""
    L = DB["ligues"].get(m["div"])
    if not L or not L.get("secondaires") or m.get("coupe"):
        return None
    cf = MS.confrontation(L["secondaires"], m["home"], m["away"])
    if not cf:
        return None
    dom = m["home"] if cf["dom"] == "home" else m["away"]
    ech_cal = {k: CN.calibrer(k, v) for k, v in (cf.get("echelle") or {}).items()}
    retenu = None
    for fam, _ in CN.FAMILLES:        # du plus sûr (+2) au plus pénalisant (−4)
        pc = ech_cal.get(fam)
        if pc is None or pc < SEUIL_MIN:
            continue
        if 1.0 / pc < COTE_PLANCHER:
            continue
        retenu = (fam, pc, (cf.get("echelle") or {}).get(fam))
    if not retenu:
        return None
    fam, pc, pb = retenu
    return {"dom": dom, "fam": fam, "option": f"{dom} {fam} corners",
            "p": round(pc, 4), "p_brut": round(pb, 4) if pb else None,
            "cote_juste": round(1.0 / pc, 2)}


# ------------------------------------------------------------------ archive
def _charger():
    if os.path.exists(ARCHIVE):
        try:
            with open(ARCHIVE, encoding="utf-8") as f:
                a = json.load(f)
                a.setdefault("jours", {})
                return a
        except (ValueError, OSError):
            pass
    return {"jours": {}}


def archiver(a):
    auj = datetime.date.today().isoformat()
    e = a["jours"].setdefault(auj, {"matchs": []})
    par_cle = {(m["home"], m["away"]): m for m in e["matchs"]}
    n_ajout = n_maj = 0
    for fx in _source():
        if fx.get("date") != auj:
            continue
        pk = pick_corners(fx)
        if pk is None:
            continue
        cle = (fx["home"], fx["away"])
        if cle in par_cle:
            m = par_cle[cle]
            if m.get("resultat") is None:
                m.update(pk)              # état le plus frais avant coup d'envoi
                n_maj += 1
        else:
            lig = DB["ligues"].get(fx["div"])
            row = {"div": fx["div"], "ligue": lig["nom"] if lig else fx["div"],
                   "heure": fx.get("heure") or "", "home": fx["home"],
                   "away": fx["away"], "resultat": None}
            row.update(pk)
            e["matchs"].append(row)
            par_cle[cle] = row
            n_ajout += 1
    e["matchs"].sort(key=lambda m: (m.get("heure") or "99:99", m["home"]))
    return n_ajout, n_maj


# ------------------------------------------------- résolution (co.uk HC/AC)
def _norme(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


def saison_code(jour):
    d = datetime.date.fromisoformat(jour)
    y = d.year if d.month >= 7 else d.year - 1
    return f"{str(y)[2:]}{str(y + 1)[2:]}"


def _date_csv(v):
    v = (v or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def ligne_csv(div, jour, home, away):
    f = os.path.join(RACINE, "data", f"{saison_code(jour)}_{div}.csv")
    if not os.path.exists(f):
        return None
    hn, an = _norme(home), _norme(away)
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                if _date_csv(row.get("Date")) != jour:
                    continue
                if _norme(row.get("HomeTeam")) == hn and \
                   _norme(row.get("AwayTeam")) == an:
                    return row
    except OSError:
        return None
    return None


def resoudre(a):
    n_res = 0
    for jour in sorted(a["jours"]):
        for m in a["jours"][jour]["matchs"]:
            if m.get("resultat") is not None:
                continue
            row = ligne_csv(m["div"], jour, m["home"], m["away"])
            if not row:
                continue
            try:
                hc, ac = int(row.get("HC")), int(row.get("AC"))
            except (TypeError, ValueError):
                continue                    # corners pas encore publiés
            d = hc - ac if m["dom"] == m["home"] else ac - hc
            m["resultat"] = {"hc": hc, "ac": ac, "d": d,
                             "touche": d >= SEUILS.get(m["fam"], 0),
                             "resolu_le": datetime.datetime.now()
                             .isoformat(timespec="minutes")}
            n_res += 1
    return n_res


# ------------------------------------------------------------------ publication
def publier(a):
    jours = sorted(a["jours"])[-GARDE_JOURS:]
    vue = {
        "genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
        "jour": datetime.date.today().isoformat(),
        "jours": {j: a["jours"][j] for j in jours},
        "note": ("Un choix clair par match : le handicap corners le plus "
                 "pénalisant sur la dominante attendue qui tient encore "
                 "≥ 60 % de fréquence réelle mesurée (walk-forward, décote "
                 "intégrée). Résultats via football-data.co.uk (colonnes "
                 "corners) : 1 à 3 jours de délai selon la publication de "
                 "la source — « en attente » tant qu'ils manquent."),
    }
    with open(PUBLIE, "w", encoding="utf-8") as f:
        json.dump(vue, f, ensure_ascii=False)
    return vue


def _nettoie(a):
    cut = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    a["jours"] = {j: e for j, e in a["jours"].items() if j >= cut}


if __name__ == "__main__":
    a = _charger()
    n_ajout, n_maj = archiver(a)
    n_res = resoudre(a)
    _nettoie(a)
    a["maj"] = datetime.datetime.now().isoformat(timespec="minutes")
    with open(ARCHIVE, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False)
    vue = publier(a)
    m_auj = vue["jours"].get(vue["jour"], {}).get("matchs", [])
    att = sum(1 for m in m_auj if m.get("resultat") is None)
    print(f"corners_jour : {len(m_auj)} sélections aujourd'hui "
          f"(+{n_ajout} ajoutées, {n_maj} rafraîchies), {n_res} résolues, "
          f"{att} en attente")
