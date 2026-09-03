"""
QUESTIONS: quoi mettre dans un coupon, et quoi ne PAS y mettre?

Methode: on ne devine pas, on mesure. Le backtest existant comparait le modele aux
cotes de CLOTURE de Pinnacle (le bookmaker le plus efficace du monde). Or un parieur
reel joue sur des cotes grand public, moins bien ajustees.

Ce script rejoue les 19 142 matchs deja predits contre 3 niveaux de cotes:
  - B365  : Bet365, bookmaker grand public (le plus proche de la realite d'un parieur)
  - Avg   : moyenne du marche
  - Max   : meilleure cote disponible sur le marche

Et il cherche OU se trouve eventuellement la valeur, par segment.

Protocole anti-surajustement: les regles sont cherchees sur la periode A
(2021/22 -> 2023/24) puis VALIDEES sur la periode B (2024/25 -> 2025/26).
Un edge qui n'existe que sur A est du bruit.
"""
import os, glob, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
NOM2DIV = {"Premier League": "E0", "La Liga": "SP1", "Serie A": "I1",
           "Bundesliga": "D1", "Ligue 1": "F1", "Eredivisie": "N1",
           "Jupiler Pro": "B1", "Liga Portugal": "P1", "Super Lig": "T1",
           "Super League Grece": "G1", "Championship": "E1"}
SEUIL_EDGE = 0.03          # 3% d'avantage minimum pour parier


def charger_cotes():
    cols = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG",
            "B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA",
            "MaxH", "MaxD", "MaxA", "PSCH", "PSCD", "PSCA",
            "B365>2.5", "B365<2.5", "Avg>2.5", "Avg<2.5", "Max>2.5", "Max<2.5"]
    fr = []
    for f in glob.glob("data/2*_*.csv"):
        b = os.path.basename(f).replace(".csv", "")
        if "_" not in b:
            continue
        saison, div = b.split("_")
        try:
            d = pd.read_csv(f, encoding="latin-1")
        except Exception:
            continue
        if not {"HomeTeam", "FTHG"} <= set(d.columns):
            continue
        d = d[[c for c in cols if c in d.columns]].copy()
        d["div"] = div
        d["date"] = pd.to_datetime(d["Date"], format="mixed", dayfirst=True, errors="coerce")
        d = d.dropna(subset=["date"])
        fr.append(d)
    c = pd.concat(fr, ignore_index=True)
    for col in c.columns:
        if col not in ("Div", "HomeTeam", "AwayTeam", "div", "date"):
            c[col] = pd.to_numeric(c[col], errors="coerce")
            if col not in ("FTHG", "FTAG"):
                c.loc[c[col] <= 1.01, col] = np.nan       # cotes invalides
    return c.rename(columns={"HomeTeam": "home", "AwayTeam": "away"})


def devig3(a, b, c):
    v = [a, b, c]
    if any(x is None or not np.isfinite(x) or x <= 1.01 for x in v):
        return (np.nan,) * 3
    inv = np.array([1 / x for x in v])
    return tuple((inv / inv.sum()).tolist())


def jouer(p, cote, res, edge=SEUIL_EDGE):
    """Retourne (pari?, gain). Mise a plat de 1 unite.
    res = 1 si le pari est gagnant, 0 sinon. (BUG corrige: on comparait
    auparavant la probabilite p au resultat binaire res, jamais egaux.)"""
    if not (cote and np.isfinite(cote) and cote > 1.01):
        return False, 0.0
    if p > (1 / cote) * (1 + edge):
        return True, (cote - 1) if res == 1 else -1.0
    return False, 0.0


def main():
    print("Chargement des cotes grand public...")
    cotes = charger_cotes()
    print(f"  {len(cotes)} matchs avec cotes, {cotes['div'].nunique()} divisions")

    print("Chargement des predictions du modele (poids buts = 1.00)...")
    bt = pd.read_csv("backtest_v3.csv", parse_dates=["date"])
    bt = bt[bt["w"] == 1.0][["league", "date", "home", "away", "hg", "ag",
                             "p1", "pX", "p2", "pO25"]].copy()
    bt["div"] = bt["league"].map(NOM2DIV)
    bt = bt.dropna(subset=["div"])
    bt["d"] = bt["date"].dt.date
    cotes["d"] = cotes["date"].dt.date
    m = bt.merge(cotes, on=["div", "d", "home", "away"], how="inner", suffixes=("", "_c"))
    print(f"  Jointure reussie : {len(m)} matchs\n")

    m["res1"] = (m["hg"] > m["ag"]).astype(int)
    m["resX"] = (m["hg"] == m["ag"]).astype(int)
    m["res2"] = (m["hg"] < m["ag"]).astype(int)
    m["resO"] = (m["hg"] + m["ag"] > 2.5).astype(int)
    m["periode"] = np.where(m["date"] < "2024-07-01", "A_apprentissage", "B_validation")

    # ---------------------------------------------------------------- global
    print("=" * 88)
    print("RESULTAT GLOBAL - ROI du modele selon le bookmaker (mise a plat, edge 3%)")
    print("=" * 88)
    print(f"{'BOOKMAKER':<26}{'Paris':>8}{'Reussite':>10}{'ROI':>9}{'P/L':>11}{'CLV vs Pinnacle':>18}")
    print("-" * 88)
    for label, (c1, cX, c2) in {
        "Bet365 (grand public)": ("B365H", "B365D", "B365A"),
        "Moyenne du marche": ("AvgH", "AvgD", "AvgA"),
        "Meilleure cote (Max)": ("MaxH", "MaxD", "MaxA"),
        "Pinnacle cloture": ("PSCH", "PSCD", "PSCA"),
    }.items():
        if c1 not in m.columns:
            continue
        nb = wn = 0; pnl = 0.0
        clv_n = clv_s = 0
        for _, r in m.iterrows():
            for p, res, co, cp in ((r["p1"], r["res1"], r.get(c1), r.get("PSCH")),
                                   (r["pX"], r["resX"], r.get(cX), r.get("PSCD")),
                                   (r["p2"], r["res2"], r.get(c2), r.get("PSCA"))):
                ok, g = jouer(p, co, res)
                if ok:
                    nb += 1; pnl += g; wn += (g > 0)
                    if cp and np.isfinite(cp) and cp > 1.01 and co > 1.01:
                        clv_n += 1
                        clv_s += co / cp - 1.0   # FIX: >0 si on a pris une cote
                                                 # PLUS HAUTE que la cloture Pinnacle
        if nb:
            if wn / nb in (0.0, 1.0):
                print(f"  !! ALERTE {label}: taux de reussite {wn/nb:.0%} = bug probable")
            clv = clv_s / clv_n if clv_n else float("nan")
            print(f"{label:<26}{nb:>8}{wn/nb:>9.1%}{pnl/nb:>+9.2%}{pnl:>+11.1f}"
                  f"{(f'{clv:+.4f}' if clv_n else '-'):>18}")
    print("-" * 88)
    print("  CLV > 0 = on a pris une cote meilleure que la cloture Pinnacle = edge reel.")
    print("  CLV < 0 = le marche a bouge contre nous = pas d'information superieure.")

    # ---------------------------------------------------------------- Over/Under
    print("\n" + "=" * 88)
    print("MARCHE OVER/UNDER 2.5 - ROI selon le bookmaker")
    print("=" * 88)
    print(f"{'BOOKMAKER':<26}{'Paris':>8}{'Reussite':>10}{'ROI':>9}{'P/L':>11}")
    print("-" * 88)
    for label, (co, cu) in {"Bet365": ("B365>2.5", "B365<2.5"),
                            "Moyenne marche": ("Avg>2.5", "Avg<2.5"),
                            "Meilleure cote": ("Max>2.5", "Max<2.5")}.items():
        if co not in m.columns:
            continue
        nb = wn = 0; pnl = 0.0
        for _, r in m.iterrows():
            for p, res, c in ((r["pO25"], r["resO"], r.get(co)),
                              (1 - r["pO25"], 1 - r["resO"], r.get(cu))):
                ok, g = jouer(p, c, res)
                if ok:
                    nb += 1; pnl += g; wn += (g > 0)
        if nb:
            print(f"{label:<26}{nb:>8}{wn/nb:>9.1%}{pnl/nb:>+9.2%}{pnl:>+11.1f}")

    # ---------------------------------------------------------------- segments
    print("\n" + "=" * 88)
    print("OU SE TROUVE LA VALEUR ? Recherche sur periode A, validation sur periode B")
    print("=" * 88)
    print("  Un segment n'est retenu que s'il est rentable sur A ET sur B.")

    def roi(df, c1, cX, c2, edge=SEUIL_EDGE):
        nb = wn = 0; pnl = 0.0
        for _, r in df.iterrows():
            for p, res, co in ((r["p1"], r["res1"], r.get(c1)),
                               (r["pX"], r["resX"], r.get(cX)),
                               (r["p2"], r["res2"], r.get(c2))):
                ok, g = jouer(p, co, res, edge)
                if ok:
                    nb += 1; pnl += g; wn += (g > 0)
        return nb, (wn / nb if nb else 0), (pnl / nb if nb else 0), pnl

    A = m[m["periode"] == "A_apprentissage"]
    B = m[m["periode"] == "B_validation"]
    seg = []
    for div in sorted(m["div"].unique()):
        a = A[A["div"] == div]; b = B[B["div"] == div]
        if len(a) < 150 or len(b) < 100:
            continue
        na, wa, ra, pa = roi(a, "B365H", "B365D", "B365A")
        nb_, wb, rb, pb = roi(b, "B365H", "B365D", "B365A")
        if na < 30 or nb_ < 20:
            continue
        seg.append((NOM2DIV and [k for k, v in NOM2DIV.items() if v == div][0], div,
                    na, wa, ra, pa, nb_, wb, rb, pb))

    print(f"\n{'LIGUE':<20}{'A: paris':>9}{'A: ROI':>9}{'B: paris':>9}{'B: ROI':>9}"
          f"{'  verdict':>12}")
    print("-" * 88)
    for nom, div, na, wa, ra, pa, nb_, wb, rb, pb in sorted(seg, key=lambda x: -(x[4] + x[8])):
        if ra > 0 and rb > 0:
            v = "VALIDE"
        elif ra > 0 or rb > 0:
            v = "instable"
        else:
            v = "a eviter"
        print(f"{nom:<20}{na:>9}{ra:>+9.2%}{nb_:>9}{rb:>+9.2%}{v:>12}")

    # ---------------------------------------------------------------- par confiance
    print("\n" + "=" * 88)
    print("FILTRE PAR NIVEAU DE CONFIACTION DU MODELE (Bet365, 1X2)")
    print("=" * 88)
    print(f"{'Probabilite du modele':<26}{'A: paris':>9}{'A: ROI':>9}{'B: paris':>9}{'B: ROI':>9}")
    print("-" * 88)
    m["pmax"] = m[["p1", "pX", "p2"]].max(axis=1)
    for lo, hi in [(0.30, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 1.01)]:
        A2 = m[(m["periode"] == "A_apprentissage") & (m["pmax"] >= lo) & (m["pmax"] < hi)]
        B2 = m[(m["periode"] == "B_validation") & (m["pmax"] >= lo) & (m["pmax"] < hi)]
        na, wa, ra, pa = roi(A2, "B365H", "B365D", "B365A")
        nb_, wb, rb, pb = roi(B2, "B365H", "B365D", "B365A")
        print(f"{lo:>5.0%} - {min(hi,1):<5.0%}{'':<13}{na:>9}{ra:>+9.2%}{nb_:>9}{rb:>+9.2%}")

    # ---------------------------------------------------------------- regles finales
    print("\n" + "=" * 88)
    print("SYNTHESE : ce que les donnees autorisent a conclure")
    print("=" * 88)
    valides = [s for s in seg if s[4] > 0 and s[8] > 0]
    print(f"  Segments rentables sur A ET B : {len(valides)} / {len(seg)}")
    for nom, div, na, wa, ra, pa, nb_, wb, rb, pb in valides:
        print(f"    - {nom}: ROI A {ra:+.2%} ({na} paris), ROI B {rb:+.2%} ({nb_} paris), "
              f"total {pa+pb:+.1f} unites")
    if not valides:
        print("    Aucun. Le modele ne montre pas d'avantage durable, meme face a Bet365.")
    m.to_csv("analyse_coupon.csv", index=False)
    print(f"\n  Detail sauvegarde : analyse_coupon.csv ({len(m)} matchs)")


if __name__ == "__main__":
    main()
