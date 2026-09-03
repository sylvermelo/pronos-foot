"""
Calibration du proxy xG a partir des tirs (gratuit, 30 ans de donnees).

On n'utilise PAS les coefficients theoriques des manuels: on les AJUSTE par
regression sur nos 14 285 matchs reels, separement pour les buts a domicile
et a l'exterieur (l'avantage domicile modifie la conversion).

  buts ~ a * tirs_cadres + b * tirs_non_cadres + c
"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import moteur as M

# recharger avec les colonnes tirs que moteur.load_all ne conserve pas
import os
frames = []
for s in M.ALL_SEASONS:
    for d in M.LIGUES:
        f = f"data/{s}_{d}.csv"
        if os.path.exists(f):
            x = pd.read_csv(f, encoding="latin-1")
            x["league"] = d; x["season"] = s
            frames.append(x)
raw = pd.concat(frames, ignore_index=True)
raw["date"] = pd.to_datetime(raw["Date"], format="mixed", dayfirst=True, errors="coerce")
for c in ["FTHG", "FTAG", "HS", "AS", "HST", "AST", "HC", "AC", "HF", "AF", "HY", "AY"]:
    if c in raw.columns:
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
raw = raw.dropna(subset=["FTHG", "FTAG", "HS", "AS", "HST", "AST", "date"])
raw = raw[(raw["HS"] >= 0) & (raw["AS"] >= 0)]
print(f"Matchs avec statistiques de tirs exploitables : {len(raw)}")

LIGUE_NOMS = M.LIGUES
print("\n=== 1. REALITE OBSERVEE PAR LIGUE ===")
print(f"{'Ligue':<16}{'Buts/m':>8}{'Domic.':>8}{'Ext.':>7}{'Tirs/m':>8}"
      f"{'Cadres/m':>10}{'Conv.cadre':>12}{'Over2.5':>9}")
for lg, nom in LIGUE_NOMS.items():
    z = raw[raw["league"] == lg]
    if len(z) < 200:
        continue
    buts = z["FTHG"] + z["FTAG"]
    tirs = z["HS"] + z["AS"]; cadr = z["HST"] + z["AST"]
    print(f"{nom:<16}{buts.mean():>8.2f}{z['FTHG'].mean():>8.2f}{z['FTAG'].mean():>7.2f}"
          f"{tirs.mean():>8.1f}{cadr.mean():>10.1f}{buts.sum()/max(cadr.sum(),1):>11.1%}"
          f"{(buts>2.5).mean():>9.1%}")

print("\n=== 2. AJUSTEMENT DES COEFFICIENTS DU PROXY xG (moindres carres) ===")
res_coef = {}
for side, (buts, tirs, cadr) in {
    "domicile": ("FTHG", "HS", "HST"),
    "exterieur": ("FTAG", "AS", "AST"),
}.items():
    y = raw[buts].values.astype(float)
    nc = (raw[tirs] - raw[cadr]).values.astype(float)
    c = raw[cadr].values.astype(float)
    X = np.column_stack([c, nc, np.ones(len(y))])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    res_coef[side] = beta
    print(f"  Buts {side:<10} = {beta[0]:.4f} x tirs_cadres "
          f"+ {beta[1]:.4f} x tirs_non_cadres + {beta[2]:.3f}     (R2 = {r2:.3f})")

ch, nh, ih = res_coef["domicile"]
ca, na, ia = res_coef["exterieur"]
raw["xgH"] = ch * raw["HST"] + nh * (raw["HS"] - raw["HST"]) + ih
raw["xgA"] = ca * raw["AST"] + na * (raw["AS"] - raw["AST"]) + ia
raw["xgH"] = raw["xgH"].clip(0.05, 6); raw["xgA"] = raw["xgA"].clip(0.05, 6)

print(f"\n  xG proxy domicile moyen : {raw['xgH'].mean():.3f}  (buts reels {raw['FTHG'].mean():.3f})")
print(f"  xG proxy exterieur moyen: {raw['xgA'].mean():.3f}  (buts reels {raw['FTAG'].mean():.3f})")
print(f"  Ratio domicile/exterieur des xG : {raw['xgH'].mean()/raw['xgA'].mean():.3f}")
print(f"  Ratio domicile/exterieur reels  : {raw['FTHG'].mean()/raw['FTAG'].mean():.3f}")

print("\n=== 3. LE PROXY xG PREDIT-IL MIEUX L'AVENIR QUE LES BUTS PASSES ? ===")
print("  Test: correlation entre la force d'equipe mesuree sur N matchs et les")
print("  buts reels des N matchs SUIVANTS. Plus c'est haut, meilleur est le signal.")
raw = raw.sort_values("date")
for lg in LIGUE_NOMS:
    z = raw[raw["league"] == lg].reset_index(drop=True)
    if len(z) < 800:
        continue
    W = 10
    cor_b, cor_x = [], []
    for i in range(W * 38, len(z) - W, 6):   # pas de 6 pour rester rapide
        pas = z.iloc[i - W * 38:i - W]
        fut = z.iloc[i:i + W]
        for t in set(pas["HomeTeam"]) | set(pas["AwayTeam"]):
            mb = pas["HomeTeam"] == t; ab = pas["AwayTeam"] == t
            if mb.sum() + ab.sum() < 5:
                continue
            bp = (pas.loc[mb, "FTHG"].sum() + pas.loc[ab, "FTAG"].sum()) / (mb.sum() + ab.sum())
            xp = (pas.loc[mb, "xgH"].sum() + pas.loc[ab, "xgA"].sum()) / (mb.sum() + ab.sum())
            mf = fut["HomeTeam"] == t; af = fut["AwayTeam"] == t
            if mf.sum() + af.sum() < 3:
                continue
            bf = (fut.loc[mf, "FTHG"].sum() + fut.loc[af, "FTAG"].sum()) / (mf.sum() + af.sum())
            cor_b.append((bp, bf)); cor_x.append((xp, bf))
    if len(cor_b) > 200:
        rb = np.corrcoef(np.array(cor_b).T)[0, 1]
        rx = np.corrcoef(np.array(cor_x).T)[0, 1]
        mieux = "xG PROXY" if rx > rb else "buts bruts"
        print(f"  {LIGUE_NOMS[lg]:<16} n={len(cor_b):>5}  corr(buts passes)={rb:.4f}"
              f"  corr(xG proxy)={rx:.4f}   -> {mieux} gagne ({rx-rb:+.4f})")

raw.to_csv("data/enrichi.csv", index=False)
print(f"\nFichier enrichi sauvegarde : data/enrichi.csv ({len(raw)} matchs, colonnes xgH/xgA)")
import json
json.dump({"domicile": [float(ch), float(nh), float(ih)],
           "exterieur": [float(ca), float(na), float(ia)]},
          open("data/coef_xg.json", "w"), indent=2)
print("Coefficients sauvegardes : data/coef_xg.json")
