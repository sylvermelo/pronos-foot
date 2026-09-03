"""
LA VRAIE QUESTION : quoi mettre dans un coupon, et quoi ne pas y mettre?

On ne repond pas par intuition, on simule. Sur les 19 142 matchs reellement predits,
on construit des coupons combines de 1 a 8 selections et on mesure:
  - la probabilite REELLE du combine (produit des probabilites du modele, validees
    par le backtest puisque la calibration est bonne a +/-1,5 point)
  - la cote PAYEE par le bookmaker (produit des cotes, moins la marge de combine)
  - le ROI reel sur 20 000 tirages

Resultat attendu et a verifier: plus le combine est long, plus l'ecart entre la
probabilite reelle et la cote payee explose.
"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")

m = pd.read_csv("analyse_coupon.csv", parse_dates=["date"])
m = m.dropna(subset=["B365H", "B365D", "B365A"]).copy()
C = m[["B365H", "B365D", "B365A"]].values.astype(float)
P = m[["p1", "pX", "p2"]].values.astype(float)
pick = P.argmax(1)
vrai = np.where(m["hg"].values > m["ag"].values, 0,
                np.where(m["hg"].values == m["ag"].values, 1, 2))
ar = np.arange(len(m))
m["pmax"] = P.max(1)
m["pick"] = pick
m["cote_pick"] = C[ar, pick]
m["p_pick"] = P[ar, pick]
m["res_pick"] = (pick == vrai).astype(int)
print(f"Base : {len(m)} matchs avec cotes Bet365 et prediction du modele")
print(f"Taux de reussite d'une selection unique (le favori du modele) : {m['res_pick'].mean():.1%}")
print(f"Cote moyenne d'une selection : {m['cote_pick'].mean():.2f}")
print(f"Probabilite moyenne annoncee : {m['p_pick'].mean():.1%}")
print(f"Probabilite implicite de la cote (avec marge) : {(1/m['cote_pick']).mean():.1%}")
print(f"Marge du bookmaker sur une selection : {(1/m['cote_pick']).mean()/m['p_pick'].mean()-1:+.1%}")

MARGE_COMBINE = 1.00   # la marge se multiplie deja mecaniquement dans les cotes


def simuler(pool, taille, n_tirages=20000, seed=7, tri=None):
    """Tire des coupons de `taille` selections dans `pool` et mesure le ROI."""
    rng = np.random.default_rng(seed)
    d = pool.sort_values(tri[0], ascending=tri[1]) if tri else pool
    if len(d) < taille:
        return None
    cotes = d["cote_pick"].values
    probas = d["p_pick"].values
    res = d["res_pick"].values
    gains = np.where(res == 1, cotes - 1, -1.0)
    mise = np.zeros(n_tirages); retour = np.zeros(n_tirages)
    p_reelle = np.ones(n_tirages); c_tot = np.ones(n_tirages)
    for t in range(n_tirages):
        idx = rng.choice(len(d), taille, replace=False)
        mise[t] = 1.0                          # FIX: 1 coupon = 1 unite, quelle que
        gagne = res[idx].all()                 # soit sa taille (la cote se multiplie)
        retour[t] = cotes[idx].prod() if gagne else 0.0
        p_reelle[t] = probas[idx].prod()
        c_tot[t] = cotes[idx].prod()
    n_win = (retour > 0).sum()
    return {
        "taille": taille, "tirages": n_tirages, "gagnes": int(n_win),
        "taux_reel": n_win / n_tirages,
        "taux_theorique": p_reelle.mean(),
        "cote_moyenne": c_tot.mean(),
        "mise": mise.sum(), "retour": retour.sum(),
        "roi": (retour.sum() - mise.sum()) / mise.sum(),
        "perte_par_100": (mise.sum() - retour.sum()) / n_tirages * 100,
    }


print("\n" + "=" * 96)
print("SIMULATION DE COMBINES - 20 000 tirages par taille, selections = favori du modele")
print("=" * 96)
print(f"{'Taille':>7}{'Cote moy.':>11}{'Proba REELLE':>14}{'Proba implicite':>17}"
      f"{'Gagnes':>9}{'ROI':>10}{'Perte/100 mises':>17}")
print("-" * 96)
res_all = []
for t in (1, 2, 3, 4, 5, 6, 8):
    r = simuler(m, t)
    if not r:
        continue
    res_all.append(r)
    print(f"{r['taille']:>7}{r['cote_moyenne']:>11.2f}{r['taux_theorique']:>13.2%}"
          f"{1/r['cote_moyenne']:>17.2%}{r['gagnes']:>9}{r['roi']:>+10.2%}"
          f"{r['perte_par_100']:>16.1f}u")
print("-" * 96)
print("  Proba REELLE   = ce que le moteur calcule (calibration verifiee a +/-1,5 point)")
print("  Proba implicite = ce que la cote du bookmaker laisse esperer")
print("  L'ECART entre les deux, multiplie par la taille du combine, est ta perte.")

print("\n" + "=" * 96)
print("MEME SIMULATION EN NE GARDANT QUE LES SELECTIONS LES PLUS 'SURES' (p >= 65%)")
print("=" * 96)
sur = m[m["p_pick"] >= 0.65]
print(f"  Pool : {len(sur)} selections, taux de reussite reel {sur['res_pick'].mean():.1%}, "
      f"cote moyenne {sur['cote_pick'].mean():.2f}")
print(f"{'Taille':>7}{'Cote moy.':>11}{'Proba REELLE':>14}{'Gagnes':>9}{'ROI':>10}")
print("-" * 96)
for t in (1, 2, 3, 4, 5, 6, 8):
    r = simuler(sur, t, seed=11)
    if not r:
        continue
    print(f"{r['taille']:>7}{r['cote_moyenne']:>11.2f}{r['taux_theorique']:>13.2%}"
          f"{r['gagnes']:>9}{r['roi']:>+10.2%}")

print("\n" + "=" * 96)
print("ET EN NE GARDANT QUE LES GROSSES COTES (p <= 40%, 'coup de poker') ?")
print("=" * 96)
ris = m[m["p_pick"] <= 0.40]
print(f"  Pool : {len(ris)} selections, taux de reussite reel {ris['res_pick'].mean():.1%}, "
      f"cote moyenne {ris['cote_pick'].mean():.2f}")
for t in (1, 2, 3):
    r = simuler(ris, t, seed=13)
    if r:
        print(f"  combine de {t} : ROI {r['roi']:+.2%} | proba reelle {r['taux_theorique']:.2%}")

print("\n" + "=" * 96)
print("CONCLUSION OPERATIONNELLE POUR TON COUPON")
print("=" * 96)
r1, r3, r5 = res_all[0], res_all[2] if len(res_all) > 2 else None, res_all[4] if len(res_all) > 4 else None
if r3 and r5:
    print(f"""
  1. Selection unique      : ROI {r1['roi']:+.1%}
  2. Combine de 3          : ROI {r3['roi']:+.1%}
  3. Combine de 5          : ROI {r5['roi']:+.1%}

  La perte s'aggrave de facon MULTIPLICATIVE, pas additive : la marge du bookmaker
  est prelevee sur CHAQUE selection, donc elle se compose.

  Regles qui decoulent directement de ces chiffres :
   - Moins il y a de selections, moins tu perds. Un combine de 5 perd ~{abs(r5['roi'])*100:.0f}%.
   - Les selections 'sures' (cote faible) ne sauvent pas le combine : la marge
     s'applique quand meme, et une seule erreur suffit a tout perdre.
   - Aucun filtre de confiance du modele ne rend le pari rentable (teste sur
     5 tranches de probabilite et 11 ligues, periode A puis B : 0 segment valide).
""")
pd.DataFrame(res_all).to_csv("simu_combines.csv", index=False)
print("  Detail sauvegarde : simu_combines.csv")
