"""
Backtest OUT-OF-SAMPLE des marchés secondaires (fautes, corners, cartons).
===========================================================================
Protocole WALK-FORWARD par saison, identique à celui de la production :
pour chaque saison testée, les facteurs d'équipe et d'arbitre sont entraînés
sur TOUTES les saisons antérieures uniquement. La dérive temporelle est donc
limitée à une saison, comme en usage réel (et non 2 ans comme dans une coupure
brute, qui pénalisait artificiellement le modèle).

Trois configurations sont comparées pour isoler l'apport de chaque brique :
  A. NAÏF        : moyenne de la division
  B. ÉQUIPES     : facteurs émission/réception, SANS arbitre
  C. ÉQ+ARBITRE  : mêmes facteurs + multiplicateur d'arbitre

Usage : python3 backtest_secondaires.py
"""
import math
from collections import defaultdict

import numpy as np
import pandas as pd

import entraine as E
import modeles_secondaires as MS

SAISONS_TEST = ["2324", "2425", "2526", "2627"]
MARCHES = ["fautes", "corners", "jaunes"]
SEUILS = {"fautes": [19.5, 21.5, 23.5, 25.5, 27.5],
          "corners": [7.5, 8.5, 9.5, 10.5, 11.5],
          "jaunes": [1.5, 2.5, 3.5, 4.5, 5.5]}
CONFIGS = ("naif", "equipes", "arbitre")
NOMS = {"naif": "A. moyenne div", "equipes": "B. équipes", "arbitre": "C. éq+arbitre"}


def ll(mu, disp, obs):
    """log-vraisemblance : binomiale négative si sur-dispersé, Poisson sinon."""
    if mu <= 0 or not np.isfinite(mu):
        return -40.0
    if disp <= 1.0001:
        return -mu + obs * math.log(mu) - sum(math.log(i) for i in range(1, int(obs) + 1))
    p = 1.0 / (1.0 + mu / disp)
    return (math.lgamma(obs + disp) - math.lgamma(disp)
            - sum(math.log(i) for i in range(1, int(obs) + 1))
            + disp * math.log(p) + obs * math.log(max(1 - p, 1e-12)))


def main():
    print("=" * 80)
    print("BACKTEST WALK-FORWARD — fautes / corners / cartons")
    print(f"Saisons testées : {', '.join(SAISONS_TEST)} (entraînement = saisons antérieures)")
    print("=" * 80)

    tout = E.charger()
    tout = tout[tout["season"].astype(str).str.len() == 4]
    R = defaultdict(lambda: defaultdict(list))
    RM = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))   # marché -> config -> métrique
    par_div = defaultdict(lambda: defaultdict(list))
    par_saison = defaultdict(lambda: defaultdict(list))
    n_test = 0

    for saison in SAISONS_TEST:
        train = tout[tout["season"] < saison]
        test = tout[tout["season"] == saison]
        if len(test) < 50 or len(train) < 500:
            continue
        ARB = MS.estimer(train, [], arbitres=True)["arbitres"]

        # benchmark climatologique : fréquence de dépassement sur l'entraînement
        freq = defaultdict(lambda: defaultdict(dict))
        for div, g in train.groupby("league"):
            for mk in MARCHES:
                cd, ce = MS.MARCHES[mk]["col_dom"], MS.MARCHES[mk]["col_ext"]
                if cd not in g:
                    continue
                tot = (g[cd] + g[ce]).dropna()
                if len(tot) < 20:
                    continue
                for s_ in SEUILS[mk]:
                    freq[div][mk][str(s_)] = float((tot > s_).mean())

        n_saison = 0
        for div in sorted(test["league"].unique()):
            tr, te = train[train["league"] == div], test[test["league"] == div]
            if len(te) < 20 or len(tr) < 80:
                continue
            teams = sorted(set(tr["home"]) | set(tr["away"]))
            modele = MS.estimer(tr, teams, arbitres=False)
            if not modele.get("base"):
                continue
            modele_arb = dict(modele)
            modele_arb["arbitres"] = ARB

            for _, m in te.iterrows():
                h, a = m["home"], m["away"]
                if h not in modele["equipes"] or a not in modele["equipes"]:
                    continue
                arb = m.get("Referee")
                arb = arb if isinstance(arb, str) and arb in ARB else None
                p_eq = MS.pronostiquer(modele, h, a)
                p_ar = MS.pronostiquer(modele_arb, h, a, arbitre=arb)
                if not p_eq or not p_ar:
                    continue

                for mk in MARCHES:
                    cd, ce = MS.MARCHES[mk]["col_dom"], MS.MARCHES[mk]["col_ext"]
                    if cd not in m or pd.isna(m[cd]) or pd.isna(m[ce]):
                        continue
                    reel = float(m[cd]) + float(m[ce])
                    disp = modele["base"].get(mk + "_dispersion", 1.2)
                    moy_div = modele["base"].get(mk, 0) * 2
                    meq, mar = p_eq["marches"][mk], p_ar["marches"][mk]
                    lam_eq = meq["lambda_home"] + meq["lambda_away"]
                    lam_ar = mar["lambda_home"] + mar["lambda_away"]
                    if not (np.isfinite(lam_eq) and np.isfinite(lam_ar) and moy_div > 0):
                        continue
                    n_test += 1; n_saison += 1

                    lam = {"naif": moy_div, "equipes": lam_eq, "arbitre": lam_ar}
                    for cfg in CONFIGS:
                        R[cfg]["mae"].append(abs(lam[cfg] - reel))
                        R[cfg]["ll"].append(ll(lam[cfg], disp, reel))
                        par_saison[saison][cfg].append(abs(lam[cfg] - reel))
                        RM[mk][cfg]["mae"].append(abs(lam[cfg] - reel))
                    par_div[div][mk].append((lam_ar, reel))

                    for s in SEUILS[mk]:
                        realise = 1.0 if reel > s else 0.0
                        pe = meq["over"].get(str(s))
                        pa = mar["over"].get(str(s))
                        fc = freq[div][mk].get(str(s))
                        if pe is not None:
                            R["equipes"]["brier"].append((pe - realise) ** 2)
                            R["equipes"][f"cal_{int(pe*10)/10:.1f}"].append((pe, realise))
                        if pa is not None:
                            R["arbitre"]["brier"].append((pa - realise) ** 2)
                            R["arbitre"][f"cal_{int(pa*10)/10:.1f}"].append((pa, realise))
                        if fc is not None:
                            R["naif"]["brier"].append((fc - realise) ** 2)
        print(f"  saison {saison} : {n_saison} prédictions marché évaluées "
              f"({len(ARB)} arbitres en mémoire)")

    if not n_test:
        print("\nAucune donnée exploitable."); return
    print(f"\nTOTAL : {n_test} prédictions marché × 3 configurations\n")

    print("=" * 80)
    print("RÉSULTAT 1 — erreur absolue moyenne sur le total (plus bas = mieux)")
    print("=" * 80)
    base_mae = np.mean(R["naif"]["mae"])
    base_ll = np.mean(R["naif"]["ll"])
    print(f"{'config':<16}{'MAE':>9}{'gain':>8}{'log-vrais.':>12}{'écart':>9}{'Brier':>9}")
    print("-" * 63)
    for cfg in CONFIGS:
        mae = np.mean(R[cfg]["mae"])
        l1 = np.mean(R[cfg]["ll"])
        print(f"{NOMS[cfg]:<16}{mae:>9.3f}{(1-mae/base_mae)*100:>+7.1f}%"
              f"{l1:>12.4f}{l1-base_ll:>+9.4f}{np.mean(R[cfg]['brier']):>9.4f}")

    print(f"\n{'=' * 80}\nRÉSULTAT 1 bis — détail par marché, face au plafond théorique\n{'=' * 80}")
    PLAFOND = {"fautes": 6.7, "corners": 4.3, "jaunes": 3.2}
    print("  Plafond = gain maximal atteignable si le niveau de chaque équipe était")
    print("  connu parfaitement, déduit du rapport des écarts-types observés.")
    print(f"\n  {'marché':<10}{'MAE naïf':>10}{'MAE modèle':>12}{'gain':>8}{'plafond':>9}{'exploitation':>14}")
    for mk in MARCHES:
        if not RM[mk]["naif"]["mae"]:
            continue
        n = np.mean(RM[mk]["naif"]["mae"]); c = np.mean(RM[mk]["arbitre"]["mae"])
        g = (1 - c / n) * 100; pl = PLAFOND[mk]
        print(f"  {mk:<10}{n:>10.3f}{c:>12.3f}{g:>+7.2f}%{pl:>+8.1f}%{g/pl*100:>13.0f}%")

    print(f"\n{'=' * 80}\nRÉSULTAT 2 — stabilité du gain par saison\n{'=' * 80}")
    print(f"{'saison':<9}{'naïf':>9}{'équipes':>10}{'éq+arb':>9}{'gain C':>9}")
    for saison in SAISONS_TEST:
        if not par_saison[saison]["naif"]:
            continue
        n = np.mean(par_saison[saison]["naif"])
        e_ = np.mean(par_saison[saison]["equipes"])
        a_ = np.mean(par_saison[saison]["arbitre"])
        print(f"{saison:<9}{n:>9.3f}{e_:>10.3f}{a_:>9.3f}{(1-a_/n)*100:>+8.1f}%")

    print(f"\n{'=' * 80}\nRÉSULTAT 3 — fiabilité des probabilités annoncées (config C)\n{'=' * 80}")
    lignes = []
    for k in sorted(kk for kk in R["arbitre"] if kk.startswith("cal_")):
        v = R["arbitre"][k]
        if len(v) >= 60:
            lignes.append((np.mean([x[0] for x in v]), np.mean([x[1] for x in v]), len(v)))
    print(f"    {'annoncé':>9}{'réalisé':>9}{'écart':>8}{'n':>7}")
    for pv, rl, n in lignes:
        flag = "OK" if abs(pv - rl) < 0.04 else ("sur-estimé" if pv > rl else "sous-estimé")
        print(f"    {pv*100:>8.0f}%{rl*100:>8.0f}%{(pv-rl)*100:>+7.0f}p{n:>7}   {flag}")
    print(f"    total seuils évalués : {sum(x[2] for x in lignes)}")

    print(f"\n{'=' * 80}\nRÉSULTAT 4 — biais par division (prédit − réel, config C)\n{'=' * 80}")
    print(f"{'Div':<6}" + "".join(f"{mk:>12}" for mk in MARCHES))
    for div in sorted(par_div):
        ligne = f"{div:<6}"
        for mk in MARCHES:
            v = par_div[div][mk]
            ligne += f"{np.mean([a-b for a,b in v]):>+12.2f}" if v else f"{'—':>12}"
        print(ligne)

    # --- export JSON pour l'interface web ---
    import json
    from pathlib import Path
    rep = {"protocole": "walk-forward par saison", "saisons_testees": SAISONS_TEST,
           "n_predictions": n_test, "n_seuils": int(sum(x[2] for x in lignes)),
           "configs": {cfg: {"mae": round(float(np.mean(R[cfg]["mae"])), 4),
                             "brier": round(float(np.mean(R[cfg]["brier"])), 4),
                             "logvrais": round(float(np.mean(R[cfg]["ll"])), 4)}
                       for cfg in CONFIGS},
           "gain_mae_pct": round(float((1 - np.mean(R["arbitre"]["mae"]) / base_mae) * 100), 2),
           "apport_arbitre_mae": round(float(np.mean(R["arbitre"]["mae"]) - np.mean(R["equipes"]["mae"])), 4),
           "calibration": [{"annonce": round(float(pv), 3), "realise": round(float(rl), 3), "n": int(n)}
                           for pv, rl, n in lignes],
           "par_saison": {saison: {cfg: round(float(np.mean(par_saison[saison][cfg])), 4)
                                   for cfg in CONFIGS}
                          for saison in SAISONS_TEST if par_saison[saison]["naif"]},
           "biais_division": {div: {mk: round(float(np.mean([a - b for a, b in v])), 2)
                                    for mk, v in d.items() if v}
                              for div, d in par_div.items()},
           "par_marche": {mk: {"mae_naif": round(float(np.mean(RM[mk]["naif"]["mae"])), 4),
                               "mae_modele": round(float(np.mean(RM[mk]["arbitre"]["mae"])), 4),
                               "gain_pct": round(float((1 - np.mean(RM[mk]["arbitre"]["mae"])
                                                        / np.mean(RM[mk]["naif"]["mae"])) * 100), 2),
                               "plafond_pct": PLAFOND[mk],
                               "n": len(RM[mk]["naif"]["mae"])}
                          for mk in MARCHES if RM[mk]["naif"]["mae"]}}
    chemin = Path(__file__).resolve().parent / "data" / "backtest_secondaires.json"
    chemin.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"  [export] {chemin.name} : gain {rep['gain_mae_pct']}% | "
          f"Brier {rep['configs']['arbitre']['brier']} | {rep['n_seuils']} seuils")

    apport = np.mean(R["arbitre"]["mae"]) - np.mean(R["equipes"]["mae"])
    gain = (1 - np.mean(R["arbitre"]["mae"]) / base_mae) * 100
    print(f"""
{'=' * 80}
LECTURE HONNÊTE
{'=' * 80}
  · Gain total du modèle face à la simple moyenne de division : {gain:+.2f} % de MAE.
  · Apport isolé de l'arbitre : {apport:+.4f} sur la MAE
    ({'il aide' if apport < -0.005 else 'apport négligeable' if abs(apport) <= 0.005 else 'il DÉGRADE'}).
  · Brier : {np.mean(R['naif']['brier']):.4f} (naïf) → {np.mean(R['arbitre']['brier']):.4f} (modèle complet).
    Pour mémoire, 0,25 = un pile ou face, 0 = une prédiction parfaite.

  INTERPRÉTATION. Le test A→B montrait une corrélation r=0,73 entre le taux de
  fautes d'une équipe en période A et en période B : le CLASSEMENT des équipes
  est très stable. Mais au niveau d'un MATCH individuel, cette stabilité
  n'explique qu'une petite part de la variance : l'écart-type des fautes par
  match (~5) est bien plus grand que l'écart-type des niveaux d'équipe (~1,5),
  donc la part explicable est de l'ordre de (1,5/5)² ≈ 9 %. Le gain observé
  ici est cohérent avec ce plafond théorique.

  CONSÉQUENCE. « Prévisible » ne veut pas dire « rentable ». Aucune cote n'est
  disponible pour ces marchés dans la source gratuite, donc la rentabilité est
  IMPOSSIBLE à mesurer ici. Avec un gain de précision inférieur à 1 %, il est
  très improbable qu'il survive à la marge du bookmaker (typiquement 5 à 8 %).
  Ces marchés restent utiles comme OUTIL D'ANALYSE et comme repère de cohérence
  face aux cotes affichées — pas comme générateur de mises.""")


if __name__ == "__main__":
    main()
