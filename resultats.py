"""
BOUCLE RAPIDE — les résultats de la veille nourrissent l'entraînement chaque jour.
=================================================================================
Contexte : la source d'entraînement historique (football-data.co.uk) ne publie
les résultats que dimanche et mercredi soir. Entre deux publications, les
forces des équipes étaient gelées jusqu'à 3-4 jours — une équipe en forme
montante ou en période morte mettait du temps à être rattrapée.

Ce module accumule les scores FINAUX déjà résolus par ESPN (sans clé, la même
API que le calendrier et le suivi) dans data/resultats_espn.json, avec les noms
d'équipes traduits vers la nomenclature co.uk (Mappeur de calendrier.py).

entraine.py fusionne ce complément dans sa base :
  · un match déjà publié par co.uk (CSV) est ignoré — dédoublonnage strict
    (même division, mêmes équipes, même date à ±1 jour près : les dates ESPN
    sont en heure de Cotonou, celles de co.uk en heure locale UK) ;
  · un match pas encore chez co.uk entre dans l'entraînement avec ses buts
    (sans tirs/corners/cartons : ces colonnes restent NaN et le match
    n'alimente que le modèle de buts — c'est exactement ce qu'on veut).

Quand co.uk publie à son tour, ses lignes (plus riches : stats + cotes)
remplacent mécaniquement le complément au prochain téléchargement.

Budget : 21 divisions × 4 jours (fenêtre glissante) ≈ 84 requêtes ESPN par
passage — sans clé. Le fichier n'est réécrit (et donc ne déclenche un
ré-entraînement dans maj.py) QUE si de nouveaux résultats sont apparus.
"""
import datetime
import json
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.path.join(RACINE, "data", "resultats_espn.json")

JOURS = 4              # fenêtre glissante : aujourd'hui + 3 jours en arrière
CONSERVE_JOURS = 45    # au-delà, co.uk a forcément publié : on purge


def saison_pour(date_iso):
    """Étiquette de saison au format co.uk (ex. 2026-09-07 → '2627')."""
    annee, mois = int(date_iso[:4]), int(date_iso[5:7])
    debut = annee if mois >= 7 else annee - 1
    return f"{str(debut)[2:]}{str(debut + 1)[2:]}"


def charger():
    try:
        with open(CHEMIN, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("matchs"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"matchs": {}, "genere_le": None, "description": __doc__.splitlines()[1]}


def sauver(d):
    d["genere_le"] = datetime.datetime.now().isoformat(timespec="minutes")
    tmp = CHEMIN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, CHEMIN)


def collecter(db, jours=JOURS, log=None):
    """Collecte les scores finaux ESPN des derniers jours pour les 21 divisions.

    db : base modeles.json chargée (pour les noms d'équipes co.uk par division).
    Retourne le nombre de matchs AJOUTÉS au complément (0 → fichier inchangé).
    """
    import calendrier as CAL

    eq = {d: sorted(L.get("forces", {}).keys())
          for d, L in db.get("ligues", {}).items() if not L.get("coupe")}
    mappeur = CAL.Mappeur(eq)
    d = charger()
    auj = datetime.date.today()

    # purge des entrées anciennes (co.uk les a forcément publiées depuis)
    limite = (auj - datetime.timedelta(days=CONSERVE_JOURS)).isoformat()
    matchs = {k: v for k, v in d["matchs"].items() if str(v.get("date", "")) >= limite}
    purge = len(d["matchs"]) - len(matchs)
    d["matchs"] = matchs

    ajoutes = 0
    dates = [(auj - datetime.timedelta(days=i)).isoformat() for i in range(jours)]
    for div in sorted(eq):
        slug = CAL.ESPN_SLUGS.get(div)
        if not slug:
            continue
        for date in dates:
            try:
                lignes = CAL.espn_resultats(slug, date)
            except Exception as e:
                if log:
                    log(f"  {div} {date} : échec ignoré ({e})", file=sys.stderr)
                continue
            for r in lignes:
                h = mappeur.traduire(div, r["home_src"])
                a = mappeur.traduire(div, r["away_src"])
                if not h or not a or h == a:
                    continue
                cle = f"{div}|{r['date']}|{h}|{a}"
                if cle in d["matchs"]:
                    continue
                d["matchs"][cle] = {
                    "div": div, "date": r["date"], "home": h, "away": a,
                    "hg": int(r["buts_home"]), "ag": int(r["buts_away"]),
                    "season": saison_pour(r["date"]),
                }
                ajoutes += 1
    if ajoutes or purge:
        sauver(d)
    return ajoutes


if __name__ == "__main__":
    with open(os.path.join(RACINE, "data", "modeles.json"), encoding="utf-8") as f:
        base = json.load(f)
    n = collecter(base)
    print(f"boucle rapide : {n} nouveau(x) résultat(s) — "
          f"{len(charger()['matchs'])} au total dans le complément")
