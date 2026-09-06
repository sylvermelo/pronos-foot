"""
ANALYSE CORNERS POUSSÉE — fréquences historiques réelles (football-data.co.uk).

Même démarche que pour les lignes de buts (under 3.5) : on MESURE d'abord ce
qui s'est réellement passé, avant d'afficher la moindre probabilité.

Pour chaque division et chaque ligne (7.5 → 12.5 corners dans le match) :
  · le nombre de matchs avec données corners (colonnes HC/AC) ;
  · la moyenne de corners par match ;
  · la fréquence RÉELLE de l'over (et donc de l'under = complément) ;
  · la même chose sur les 3 dernières saisons complètes (tendance récente).

Sortie : data/analyse_corners.json — lue par l'interface à côté des
probabilités du modèle, pour que l'écart modèle ↔ réalité soit visible.

Limites honnêtes :
  · les corners ne sont PAS dans les sélections conseillées ni les combinés :
    aucune source gratuite ne fournit les corners en direct (ESPN ne donne que
    les buts) — un pari corners archivé resterait « en attente » indéfiniment.
  · co.uk ne publie pas de cotes corners : pas de comparaison au marché.

Usage : python3 analyse_corners.py    (après un téléchargement co.uk)
"""
import csv
import glob
import json
import os
import re

RACINE = os.path.dirname(os.path.abspath(__file__))
LIGNES = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
SAISONS_RECENTES = {"2324", "2425", "2526"}   # 3 dernières saisons complètes


def _entier(x):
    try:
        v = str(x).strip()
        if not v:
            return None
        n = int(v)
        return n if 0 <= n <= 40 else None      # garde-fou valeurs absurdes
    except (TypeError, ValueError):
        return None


def analyser():
    par_div = {}
    for chemin in sorted(glob.glob(os.path.join(RACINE, "data", "*_*.csv"))):
        nom = os.path.basename(chemin)
        m = re.match(r"^(\d{4})_(.+)\.csv$", nom)
        if not m:
            continue
        saison, div = m.group(1), m.group(2)
        n = 0
        totaux = []
        lignes_csv = None
        for enc in ("utf-8-sig", "latin-1"):
            try:
                with open(chemin, encoding=enc, newline="") as f:
                    lignes_csv = list(csv.DictReader(f))
                break
            except (OSError, UnicodeDecodeError):
                continue
        if lignes_csv is None:
            continue
        for r in lignes_csv:
            hc, ac = _entier(r.get("HC")), _entier(r.get("AC"))
            if hc is None or ac is None:
                continue
            n += 1
            totaux.append(hc + ac)
        if n < 30:
            continue
        d = par_div.setdefault(div, {"n": 0, "somme": 0, "saisons": sorted({}),
                                     "over": {str(l): 0 for l in LIGNES},
                                     "n_recent": 0, "somme_recent": 0,
                                     "over_recent": {str(l): 0 for l in LIGNES}})
        d["n"] += n
        d["somme"] += sum(totaux)
        d["saisons"] = sorted(set(d.get("saisons") or []) | {saison})
        for t in totaux:
            for l in LIGNES:
                if t > l:
                    d["over"][str(l)] += 1
        if saison in SAISONS_RECENTES:
            d["n_recent"] += n
            d["somme_recent"] += sum(totaux)
            for t in totaux:
                for l in LIGNES:
                    if t > l:
                        d["over_recent"][str(l)] += 1

    out = {"lignes": LIGNES, "saisons_recentes": sorted(SAISONS_RECENTES),
           "divisions": {}}
    grand_n = grand_somme = 0
    grand_over = {str(l): 0 for l in LIGNES}
    for div, d in sorted(par_div.items()):
        if not d["n"]:
            continue
        grand_n += d["n"]
        grand_somme += d["somme"]
        for l in LIGNES:
            grand_over[str(l)] += d["over"][str(l)]
        out["divisions"][div] = {
            "n": d["n"],
            "saisons": d["saisons"],
            "moyenne": round(d["somme"] / d["n"], 2),
            "over": {str(l): round(d["over"][str(l)] / d["n"], 4) for l in LIGNES},
            "n_recent": d["n_recent"],
            "moyenne_recente": (round(d["somme_recent"] / d["n_recent"], 2)
                                if d["n_recent"] else None),
            "over_recent": ({str(l): round(d["over_recent"][str(l)] / d["n_recent"], 4)
                             for l in LIGNES} if d["n_recent"] else None),
        }
    if grand_n:
        out["toutes_divisions"] = {
            "n": grand_n,
            "moyenne": round(grand_somme / grand_n, 2),
            "over": {str(l): round(grand_over[str(l)] / grand_n, 4) for l in LIGNES},
        }
    return out


if __name__ == "__main__":
    res = analyser()
    chemin = os.path.join(RACINE, "data", "analyse_corners.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    t = res.get("toutes_divisions", {})
    print(f"analyse corners : {len(res['divisions'])} divisions, "
          f"{t.get('n', 0)} matchs, moyenne {t.get('moyenne', '?')} corners/match")
    for l in res["lignes"]:
        print(f"  over {l} : {round(100 * t.get('over', {}).get(str(l), 0), 1)} % "
              f"(toutes divisions confondues)")
    print(f"→ {chemin}")
