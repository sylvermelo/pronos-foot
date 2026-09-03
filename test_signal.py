"""
Test decisif: le proxy xG (tirs) est-il un MEILLEUR signal predictif que les buts bruts?

Protocole: on mesure la force offensive d'une equipe sur une fenetre PASSEE de W matchs,
une fois avec les buts reels, une fois avec le proxy xG. On regarde laquelle des deux
corrèle le mieux avec les buts reels marques sur la fenetre SUIVANTE.

Si corr(xG passe, buts futurs) > corr(buts passes, buts futurs), alors l'xG est
moins bruite et doit remplacer les buts dans l'entrainement du modele.
"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")

raw = pd.read_csv("data/enrichi.csv", parse_dates=["date"])
LIGUES = {"E0": "Premier League", "SP1": "La Liga", "I1": "Serie A",
          "D1": "Bundesliga", "F1": "Ligue 1"}

W_PAS = 300      # fenetre passee (~40 matchs par equipe)
W_FUT = 76       # fenetre future (~2 saisons de 38 journees / 10 -> ~4 matchs par equipe)
SEUIL_PAS = 20   # matchs minimum dans la fenetre passee
SEUIL_FUT = 3    # matchs minimum dans la fenetre future

print(f"Fenetre passee : {W_PAS} matchs de ligue | future : {W_FUT} | pas d'echantillonnage : 19")
print(f"Seuils : >= {SEUIL_PAS} matchs passes, >= {SEUIL_FUT} matchs futurs par equipe\n")
print(f"{'Ligue':<16}{'n':>6}{'corr BUTS':>12}{'corr xG':>11}{'ECART':>10}   verdict")
print("-" * 74)

tot_b, tot_x = [], []
for lg, nom in LIGUES.items():
    z = raw[raw["league"] == lg].sort_values("date").reset_index(drop=True)
    if len(z) < W_PAS + W_FUT + 100:
        continue
    pairs = []
    for i in range(W_PAS, len(z) - W_FUT, 19):
        pas = z.iloc[i - W_PAS:i]
        fut = z.iloc[i:i + W_FUT]
        for t in set(pas["HomeTeam"]) | set(pas["AwayTeam"]):
            mb = (pas["HomeTeam"] == t).values
            ab = (pas["AwayTeam"] == t).values
            npas = mb.sum() + ab.sum()
            if npas < SEUIL_PAS:
                continue
            buts_pas = (pas["FTHG"].values * mb + pas["FTAG"].values * ab).sum() / npas
            xg_pas = (pas["xgH"].values * mb + pas["xgA"].values * ab).sum() / npas
            mf = (fut["HomeTeam"] == t).values
            af = (fut["AwayTeam"] == t).values
            nfut = mf.sum() + af.sum()
            if nfut < SEUIL_FUT:
                continue
            buts_fut = (fut["FTHG"].values * mf + fut["FTAG"].values * af).sum() / nfut
            pairs.append((buts_pas, xg_pas, buts_fut))
    if len(pairs) < 100:
        print(f"{nom:<16}{len(pairs):>6}   echantillon trop faible")
        continue
    a = np.array(pairs)
    rb = np.corrcoef(a[:, 0], a[:, 2])[0, 1]
    rx = np.corrcoef(a[:, 1], a[:, 2])[0, 1]
    tot_b.append(a[:, 0]); tot_x.append(a[:, 1])
    v = "xG GAGNE" if rx > rb else "buts bruts"
    print(f"{nom:<16}{len(pairs):>6}{rb:>12.4f}{rx:>11.4f}{rx-rb:>+10.4f}   {v}")

print("-" * 74)
print("\n=== TEST COMPLEMENTAIRE : stabilite (moins de variance = meilleur signal) ===")
print("  Un bon indicateur doit etre STABLE d'une fenetre a l'autre.")
for lg, nom in LIGUES.items():
    z = raw[raw["league"] == lg].sort_values("date").reset_index(drop=True)
    if len(z) < W_PAS + 100:
        continue
    sb, sx = [], []
    for i in range(W_PAS, len(z) - 19, 19):
        pas = z.iloc[i - W_PAS:i]
        for t in set(pas["HomeTeam"]) | set(pas["AwayTeam"]):
            mb = (pas["HomeTeam"] == t).values; ab = (pas["AwayTeam"] == t).values
            n = mb.sum() + ab.sum()
            if n < SEUIL_PAS:
                continue
            sb.append((pas["FTHG"].values * mb + pas["FTAG"].values * ab).sum() / n)
            sx.append((pas["xgH"].values * mb + pas["xgA"].values * ab).sum() / n)
    sb, sx = np.array(sb), np.array(sx)
    if len(sb) > 50:
        print(f"  {nom:<16} ecart-type buts bruts {sb.std():.4f} | proxy xG {sx.std():.4f}"
              f"  -> xG {'MOINS' if sx.std()<sb.std() else 'PLUS'} bruite ({sx.std()-sb.std():+.4f})")

print("\n=== CONCLUSION OPERATIONNELLE ===")
print("  Si corr(xG) > corr(buts) de maniere repetee -> entrainer le modele sur les xG")
print("  Si ecart-type(xG) < ecart-type(buts)        -> le signal est plus stable")
print("  Si les deux sont vrais -> gain attendu reel sur la precision predictive")
