"""
COMBLEMENT RÉTROACTIF (une seule fois) — suivi des pronostics.

Le journal démarre vide ; pour que l'onglet « Pronos vs Résultats » soit
utile immédiatement, on recalcule les sélections conseillées des 3 derniers
jours déjà joués (1-3 septembre 2026) avec le modèle ACTUEL.

Honnêteté : ce n'est pas une triche SI le modèle n'a pas été entraîné sur ces
matchs. Vérification faite le 4 septembre : les fichiers historiques co.uk
(2627_*.csv) ne contiennent encore aucun match des 1-3/09 (mise à jour
hebdomadaire) → le modèle ne les a jamais vus. Les entrées sont marquées
"retro": true et l'interface l'affiche clairement.

Usage : python3 backfill_suivi.py
"""
import datetime
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
os.chdir(RACINE)
sys.path.insert(0, RACINE)
os.environ["PRONOS_SANS_CALENDRIER"] = "1"

import calendrier as CAL
import serveur as S
import suivi

SEUIL = suivi.SEUIL_ARCHIVE
JOURS = ["2026-09-01", "2026-09-02", "2026-09-03"]


def panier(p):
    """Même panier d'options que api_conseils (serveur.py)."""
    o, u = p["over"], p["under"]
    btts = p.get("btts_oui")
    cands = [("1", p["victoire_1"]), ("X", p["nul"]), ("2", p["victoire_2"]),
             ("over 1.5", o.get("1.5")), ("over 2.5", o.get("2.5")),
             ("over 3.5", o.get("3.5")), ("under 1.5", u.get("1.5")),
             ("under 2.5", u.get("2.5")), ("under 3.5", u.get("3.5")),
             ("les deux marquent", btts),
             ("les deux ne marquent pas", round(1 - btts, 4) if btts is not None else None),
             ("double chance 1X", p.get("double_chance_1X")),
             ("double chance 12", p.get("double_chance_12")),
             ("double chance X2", p.get("double_chance_X2"))]
    cands = [(k, v) for k, v in cands if v is not None]
    return max(cands, key=lambda z: z[1]) if cands else (None, None)


def main():
    d = suivi.charger()
    eq = {div: sorted(L["forces"].keys()) for div, L in S.DB.get("ligues", {}).items()}
    map_ = CAL.Mappeur(eq)
    total_sel = total_res = 0
    for date_match in JOURS:
        dm = datetime.date.fromisoformat(date_match)
        jour_prono = (dm - datetime.timedelta(days=1)).isoformat()
        selections = []
        scores = {}
        for div, slug in CAL.ESPN_SLUGS.items():
            lig = S.DB["ligues"].get(div)
            if not lig:
                continue
            for r in CAL.espn_resultats(slug, date_match):
                h = map_.traduire(div, r["home_src"])
                a = map_.traduire(div, r["away_src"])
                if not h or not a or h == a:
                    continue
                scores[(h, a)] = (r["buts_home"], r["buts_away"])
                p = S.pronostic(div, h, a)
                if not p:
                    continue
                opt, proba = panier(p)
                if not opt or proba < SEUIL:
                    continue
                selections.append({
                    "div": div, "ligue": lig["nom"], "pays": lig["pays"],
                    "date": r["date"], "heure": r["heure"], "home": h, "away": a,
                    "option": opt, "p": round(proba, 4),
                    "cote_juste": round(1 / proba, 2), "cote_marche": None,
                    "confiance": p["fiabilite"]["niveau"],
                    "buts": p.get("buts_attendus")})
        d = suivi.archiver({"jours": [{"selections": selections}]}, d=d,
                           jour=jour_prono, retro=True)
        # résolution immédiate : les scores sont déjà connus
        for s in d["jours"][jour_prono]["selections"]:
            sc = scores.get((s["home"], s["away"]))
            if sc:
                bh, ba = sc
                s["resultat"] = {"buts_home": bh, "buts_away": ba,
                                 "touche": suivi.touche(s["option"], bh, ba),
                                 "resolu_le": datetime.date.today().isoformat()}
        res = [s for s in d["jours"][jour_prono]["selections"] if s.get("resultat")]
        tou = [s for s in res if s["resultat"]["touche"]]
        total_sel += len(selections)
        total_res += len(tou)
        print(f"{date_match} : {len(scores)} matchs finis, "
              f"{len(selections)} sélections ≥{int(SEUIL*100)} %, "
              f"{len(tou)}/{len(res)} touchées")
    suivi.sauver(d)
    print(f"archivé sous les veilles (rétro, marqué) : {total_sel} sélections, "
          f"{total_res} touchées → data/suivi.json")


if __name__ == "__main__":
    main()
