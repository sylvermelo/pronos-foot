"""
BACKTEST CORNERS — confrontation et handicaps (walk-forward strict).
====================================================================
Marchés évalués, tous relatifs à l'équipe DOMINANTE attendue (celle dont le
nombre de corners espéré est le plus élevé) :

    D = corners(dominante) − corners(adversaire)

    « +2 »        : D ≥ −1   (la dominante peut perdre de 1 corner)
    « +1 / 1X »   : D ≥ 0    (victoire ou nul aux corners)
    « victoire »  : D ≥ 1    (gagne strictement le duel de corners)
    « −1 »        : D ≥ 2
    « −2 »        : D ≥ 3
    « −3 »        : D ≥ 4
    « −4 »        : D ≥ 5

Protocole : identique à backtest_secondaires.py — pour chaque saison testée,
les facteurs émission/réception sont entraînés sur les saisons ANTÉRIEURES
uniquement (walk-forward), loi binomiale négative (dispersion 1.18 mesurée),
indépendance des deux totaux supposée (même approximation que la production).

Sortie : data/backtest_corners.json
    · calibration par famille de barreau × bande de probabilité annoncée
      (annonce moyen vs fréquence réalisée vs n) — c'est elle qui fixe le
      SEUIL de sécurité du coupon et les MARGES appliquées en production ;
    · taux de réussite réels au-delà de 0,90 / 0,95 / 0,97 annoncés.

Usage : python3 backtest_corners.py      (≈1-2 min, 21 divisions)
"""
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

import entraine as E
import modeles_secondaires as MS

RACINE = os.path.dirname(os.path.abspath(__file__))
SAISONS_TEST = ["2324", "2425", "2526"]        # 2627 = en cours, trop mince
FAMILLES = [("+2", -1), ("+1", 0), ("victoire", 1),
            ("-1", 2), ("-2", 3), ("-3", 4), ("-4", 5)]
BORNES = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.93, 0.96, 0.98, 1.01]
KMAX = 40                                       # support de la différence


def bande(p):
    for i in range(len(BORNES) - 1):
        if BORNES[i] <= p < BORNES[i + 1]:
            return f"{BORNES[i]:.2f}-{BORNES[i+1]:.2f}" if BORNES[i+1] <= 1.0 else "0.98-1.00"
    return "0.98-1.00"


def distrib_diff(lam_h, lam_a, disp):
    """P(D = k) pour k ∈ [−KMAX, +KMAX], D = corners(home) − corners(away).
    Retourne un tableau indexé par k + KMAX."""
    ph = np.asarray(MS.pmf_marche(lam_h, disp, kmax=KMAX)[1], dtype=float)
    pa = np.asarray(MS.pmf_marche(lam_a, disp, kmax=KMAX)[1], dtype=float)
    M = np.outer(ph, pa)                        # M[i, j] = P(H=i) P(A=j)
    idx = (np.arange(len(ph))[:, None] - np.arange(len(pa))[None, :]).ravel() + KMAX
    return np.bincount(idx, weights=M.ravel(), minlength=2 * KMAX + 1)


def main():
    print("=" * 78)
    print("BACKTEST CORNERS — confrontation & handicaps (walk-forward)")
    print(f"Saisons : {', '.join(SAISONS_TEST)} — entraînement = saisons antérieures")
    print("=" * 78)

    tout = E.charger()
    tout = tout[tout["season"].astype(str).str.len() == 4]

    cal = defaultdict(list)          # (famille, bande) -> [(annonce, réalisé)]
    haut = defaultdict(list)         # famille -> [(annonce, réalisé)] pour p ≥ 0.90
    n_matches = 0

    for saison in SAISONS_TEST:
        train = tout[tout["season"] < saison]
        test = tout[tout["season"] == saison]
        if len(test) < 50 or len(train) < 500:
            continue
        n_saison = 0
        for div in sorted(test["league"].unique()):
            tr, te = train[train["league"] == div], test[test["league"] == div]
            if len(te) < 20 or len(tr) < 80:
                continue
            teams = sorted(set(tr["home"]) | set(tr["away"]))
            modele = MS.estimer(tr, teams, arbitres=False)
            if not modele.get("base"):
                continue
            base = modele["base"].get("corners")
            disp = modele["base"].get("corners_dispersion", 1.18)
            if not base:
                continue
            E_ = modele["equipes"]

            for _, m in te.iterrows():
                h, a = m["home"], m["away"]
                if h not in E_ or a not in E_:
                    continue
                hc, ac = m.get("HC"), m.get("AC")
                if pd.isna(hc) or pd.isna(ac):
                    continue
                eh = E_[h].get("corners_em"); rh = E_[h].get("corners_rc")
                ea = E_[a].get("corners_em"); ra = E_[a].get("corners_rc")
                if not all(v and np.isfinite(v) for v in (eh, rh, ea, ra)):
                    continue
                lam_h = min(max(base * eh * ra, 0.05), 60)
                lam_a = min(max(base * ea * rh, 0.05), 60)
                dh, da = int(hc), int(ac)
                n_matches += 1
                n_saison += 1

                dom_home = lam_h >= lam_a
                d_reel = (dh - da) if dom_home else (da - dh)
                lam_d, lam_f = (lam_h, lam_a) if dom_home else (lam_a, lam_h)
                pd_ = distrib_diff(lam_d, lam_f, disp)
                # queue supérieure : P(D ≥ t) = somme des positions ≥ t + KMAX
                for nom, t in FAMILLES:
                    annonce = float(pd_[t + KMAX:].sum())
                    annonce = min(max(annonce, 0.0), 1.0)
                    if annonce < 0.5:
                        continue                      # barreau pas du bon côté
                    realise = 1.0 if d_reel >= t else 0.0
                    b = bande(annonce)
                    cal[(nom, b)].append((annonce, realise))
                    if annonce >= 0.90:
                        haut[nom].append((annonce, realise))
        print(f"  saison {saison} : {n_saison} matchs évalués")

    # ---- restitution -------------------------------------------------------
    res = {"protocole": "walk-forward par saison (entraînement = saisons antérieures)",
           "saisons_testees": SAISONS_TEST, "n_matchs": n_matches,
           "familles": [f[0] for f in FAMILLES], "bandes": [], "calibration": {},
           "zone_securite": {}}
    bandes_presentes = []
    for i in range(len(BORNES) - 1):
        b = f"{BORNES[i]:.2f}-{BORNES[i+1]:.2f}" if BORNES[i+1] <= 1.0 else "0.98-1.00"
        if b not in bandes_presentes:
            bandes_presentes.append(b)
    res["bandes"] = bandes_presentes

    print(f"\nTOTAL : {n_matches} matchs × échelle de handicaps\n")
    print(f"{'famille':<10}{'bande':<12}{'n':>7}{'annoncé':>9}{'réalisé':>9}{'écart':>8}")
    print("-" * 55)
    for nom, _ in FAMILLES:
        for b in bandes_presentes:
            v = cal.get((nom, b))
            if not v or len(v) < 25:
                continue
            annonce = float(np.mean([x for x, _ in v]))
            realise = float(np.mean([y for _, y in v]))
            res["calibration"][f"{nom}|{b}"] = {
                "n": len(v), "annonce": round(annonce, 4),
                "realise": round(realise, 4), "ecart": round(realise - annonce, 4)}
            print(f"{nom:<10}{b:<12}{len(v):>7}{annonce:>9.3f}{realise:>9.3f}"
                  f"{realise - annonce:>+8.3f}")

    print(f"\n{'=' * 55}\nZONE DE SÉCURITÉ (annoncé ≥ 0,90) — le cœur du coupon\n{'=' * 55}")
    print(f"{'famille':<10}{'n':>7}{'annoncé':>9}{'réalisé':>9}{'écart':>8}")
    for nom, _ in FAMILLES:
        v = haut.get(nom)
        if not v or len(v) < 25:
            continue
        annonce = float(np.mean([x for x, _ in v]))
        realise = float(np.mean([y for _, y in v]))
        res["zone_securite"][nom] = {
            "n": len(v), "annonce": round(annonce, 4),
            "realise": round(realise, 4), "ecart": round(realise - annonce, 4)}
        print(f"{nom:<10}{len(v):>7}{annonce:>9.3f}{realise:>9.3f}"
              f"{realise - annonce:>+8.3f}")

    chemin = os.path.join(RACINE, "data", "backtest_corners.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"\n→ {chemin}")


if __name__ == "__main__":
    main()
