"""SÉRIES DU JOUR pour la vitrine (10/09/2026).

Publie data/series_jour.json (copié vers site/ par la CI) : les matchs du
jour avec les 6 probabilités « buts d'affilée » (NON d'abord côté vitrine),
le SAFE du jour séries et le combiné grosse cote séries. MÊMES règles
mesurées que l'onglet « Buts d'affilée » du robot (static/index.html,
tabSeries ; seuils : docs/SPEC-BUTS-AFFILEE.md §8.6) :
  SAFE        : « 2+ match » >= 0.75 (79,3 % mesuré, n=115) ou
                « 2+ domicile » >= 0.70 (75,6 %, n=82) ; Big 5 hors coupes ;
                3 jambes max ; ligues variées ; jamais forcé.
  GROSSE COTE : jambes « 3+ » >= 0.10 ; cote juste = 1/p ; produit cible
                20→50 ; 5 jambes max ; 1 option/match ; SAFE exclus.
Information chiffrée uniquement : aucun marché bookmaker dans nos sources.
"""
import datetime
import json
import math
import os

import serveur
from serveur import pronostic, DB

RACINE = os.path.dirname(os.path.abspath(__file__))
BIG5 = ("E0", "SP1", "I1", "D1", "F1")


def _rows():
    auj = datetime.date.today().isoformat()
    # Source : calendrier.json MULTI-SOURCES (reconstruit à chaque run CI),
    # pas les fixtures de modeles.json (parfois anciennes ou réduites à
    # co.uk en CI — bug du 10/09 : matchs ESPN du jour invisibles).
    # UNION des deux sources : calendrier.json (frais, multi-sources, mais
    # reconstruit tard le soir SANS les matchs déjà commencés) et fixtures
    # de modeles.json (stables toute la journée). Clé = date|home|away.
    fx_source = list(DB.get("fixtures", []))
    vus = {(f.get("date"), f.get("home"), f.get("away")) for f in fx_source}
    cal = os.path.join(RACINE, "data", "calendrier.json")
    if os.path.exists(cal):
        try:
            with open(cal, encoding="utf-8") as f:
                for m in json.load(f).get("matchs", []):
                    k = (m.get("date"), m.get("home"), m.get("away"))
                    if k not in vus:
                        fx_source.append(m)
                        vus.add(k)
        except (ValueError, OSError):
            pass
    out = []
    for fx in fx_source:
        if fx.get("date") != auj:
            continue
        p = pronostic(fx["div"], fx["home"], fx["away"])
        if not p or p.get("serie2") is None:
            continue
        lig = DB["ligues"].get(fx["div"])
        out.append({
            "div": fx["div"], "ligue": lig["nom"] if lig else fx["div"],
            "date": fx["date"], "heure": fx.get("heure") or "",
            "home": fx["home"], "away": fx["away"],
            "coupe": bool(lig and lig.get("coupe")),
            "s2": p["serie2"], "s3": p["serie3"],
            "s2d": p["serie2_dom"], "s3d": p["serie3_dom"],
            "s2e": p["serie2_ext"], "s3e": p["serie3_ext"],
        })
    out.sort(key=lambda m: (-m["s2"], m["home"], m["away"]))
    return out


def construit():
    ms = _rows()
    elig = [m for m in ms if m["div"] in BIG5 and not m["coupe"]]
    # ---- SAFE
    cand = []
    for m in elig:
        opts = [(m["s2"], "2+ match", "79 % mesuré (n=115)") if m["s2"] >= 0.75 else None,
                (m["s2d"], "2+ " + m["home"], "76 % mesuré (n=82)") if m["s2d"] >= 0.70 else None]
        opts = [o for o in opts if o]
        if opts:
            cand.append((max(opts), m))
    cand.sort(key=lambda c: (-c[0][0], c[1]["home"]))
    safe, vues = [], set()
    for diversifie in (True, False):
        safe, ligues = [], set()
        for (p, lib, fiche), m in cand:
            if len(safe) >= 3:
                break
            if diversifie and m["div"] in ligues:
                continue
            safe.append({"home": m["home"], "away": m["away"], "ligue": m["ligue"],
                         "heure": m["heure"], "option": lib, "p": round(p, 4),
                         "fiche": fiche})
            ligues.add(m["div"])
        if len(safe) >= 2:
            break
    exclus = {(l["home"], l["away"]) for l in safe}
    # ---- GROSSE COTE
    opts3 = []
    for m in elig:
        if (m["home"], m["away"]) in exclus:
            continue
        for lib, p in (("3+ match", m["s3"]), ("3+ " + m["home"], m["s3d"]),
                       ("3+ " + m["away"], m["s3e"])):
            if p >= 0.10:
                opts3.append((p, lib, m))
    opts3.sort(key=lambda o: (o[0], o[2]["home"]))
    legs, vus, prod = [], set(), 1.0
    for p, lib, m in opts3:
        if len(legs) >= 5 or prod >= 20:
            break
        k = (m["home"], m["away"])
        if k in vus or prod * (1 / p) > 50:
            continue
        legs.append({"home": m["home"], "away": m["away"], "ligue": m["ligue"],
                     "heure": m["heure"], "option": lib, "p": round(p, 4),
                     "cote_juste": round(1 / p, 2)})
        vus.add(k)
        prod *= 1 / p
    if prod < 20:
        legs, prod = [], 1.0
    return {
        "genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
        "jour": datetime.date.today().isoformat(),
        "matchs": ms,
        "safe": safe,
        "grosse_cote": {"legs": legs,
                        "cote_juste": round(prod, 2) if legs else None,
                        "p_combine": round(math.prod([l["p"] for l in legs]), 4) if legs else None},
        "note": ("Probabilités de séries de buts d'affilée (même équipe, sans but "
                 "adverse entre-temps), biais mesurés puis corrigés sur 2 923 matchs "
                 "réels (2 saisons, Big 5). Information chiffrée, jamais un conseil : "
                 "aucun bookmaker de nos sources ne propose ces marchés."),
    }


if __name__ == "__main__":
    out = construit()
    with open(os.path.join(RACINE, "data", "series_jour.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"series_jour.json : {len(out['matchs'])} matchs du jour, "
          f"safe {len(out['safe'])} jambe(s), grosse cote "
          f"{len(out['grosse_cote']['legs'])} jambe(s)")
