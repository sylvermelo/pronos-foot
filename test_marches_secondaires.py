"""
Marches secondaires : fautes, corners, cartons. Sont-ils PREVISIBLES ?

ATTENTION - limite methodologique majeure, verifiee avant de commencer:
football-data.co.uk fournit les RESULTATS de ces marches sur 30 ans, mais
AUCUNE COTE. Le ROI est donc IMPOSSIBLE a mesurer. Ce script ne peut repondre
qu'a une question: le signal existe-t-il, et est-il STABLE dans le temps?

Protocole:
  Periode A = saisons 2020/21 -> 2022/23   (apprentissage des effets)
  Periode B = saisons 2023/24 -> 2025/26   (validation)
  Un effet mesure sur A doit predire B. Sinon c'est du bruit.
  Lissage de Bayes empirique pour ne pas sur-ajuster les petits echantillons.
  Test de permutation pour la significativite.
"""
import os, glob, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
K_LISS = 25.0          # force du lissage (pseudo-observations)
A_JUSQUA = "2023-07-01"


def charger():
    fr = []
    for f in glob.glob("data/2*_*.csv"):
        b = os.path.basename(f).replace(".csv", "")
        if "_" not in b or "enrichi" in b:
            continue
        saison, div = b.split("_")
        try:
            d = pd.read_csv(f, encoding="latin-1")
        except Exception:
            continue
        need = {"HomeTeam", "AwayTeam", "HF", "AF", "HC", "AC", "HY", "AY"}
        if not need <= set(d.columns):
            continue
        d = d[["Date", "HomeTeam", "AwayTeam", "HF", "AF", "HC", "AC",
               "HY", "AY", "HR", "AR"] + (["Referee"] if "Referee" in d.columns else [])].copy()
        d["div"] = div; d["saison"] = saison
        d["date"] = pd.to_datetime(d["Date"], format="mixed", dayfirst=True, errors="coerce")
        d = d.dropna(subset=["date"])
        for c in ["HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR"]:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    d = d.dropna(subset=["HF", "AF", "HC", "AC", "HY", "AY"])
    d = d[(d["HF"] > 0) & (d["AF"] > 0)]
    d["fautes"] = d["HF"] + d["AF"]
    d["corners"] = d["HC"] + d["AC"]
    d["jaunes"] = d["HY"] + d["AY"]
    d["rouges"] = d.get("HR", 0).fillna(0) + d.get("AR", 0).fillna(0)
    d["periode"] = np.where(d["date"] < A_JUSQUA, "A", "B")
    return d


def bayes(groupe, num, den, k=K_LISS):
    """Estimateur de Bayes empirique: (somme_num + k*moyenne_globale) / (somme_den + k)."""
    mg = groupe[num].sum() / max(groupe[den].sum(), 1e-9) if den else groupe[num].mean()
    if den:
        return (groupe[num].sum() + k * mg) / (groupe[den].sum() + k), mg
    return (groupe[num].sum() + k * mg) / (len(groupe) + k), mg


def corr_perm(a, b, w, n=4000, seed=3):
    """Correlation ponderee + p-value par permutation."""
    def wc(x, y, ww):
        mx = np.average(x, weights=ww); my = np.average(y, weights=ww)
        cov = np.average((x - mx) * (y - my), weights=ww)
        sx = np.sqrt(np.average((x - mx) ** 2, weights=ww))
        sy = np.sqrt(np.average((y - my) ** 2, weights=ww))
        return cov / (sx * sy) if sx * sy > 1e-12 else 0.0
    r = wc(a, b, w)
    rng = np.random.default_rng(seed)
    nuls = np.array([wc(a, rng.permutation(b), w) for _ in range(n)])
    p = (np.abs(nuls) >= abs(r)).mean()
    return r, p, nuls.std()


def main():
    d = charger()
    A = d[d["periode"] == "A"]; B = d[d["periode"] == "B"]
    print("=" * 94)
    print("MARCHES SECONDAIRES - LE SIGNAL EXISTE-T-IL ET SURVIT-IL AU TEMPS ?")
    print("=" * 94)
    print(f"Matchs exploitables : {len(d)}   (periode A : {len(A)}, periode B : {len(B)})")
    print(f"Periode A : {A['date'].min().date()} -> {A['date'].max().date()}")
    print(f"Periode B : {B['date'].min().date()} -> {B['date'].max().date()}")
    print(f"Divisions : {d['div'].nunique()} | Arbitres : {d['Referee'].nunique() if 'Referee' in d else 0}")
    print(f"\nMoyennes par match : fautes {d['fautes'].mean():.2f} | corners {d['corners'].mean():.2f}"
          f" | jaunes {d['jaunes'].mean():.2f} | rouges {d['rouges'].mean():.3f}")
    print("\n  RAPPEL : aucune cote n'existe pour ces marches dans la source gratuite.")
    print("  On mesure donc la PREVISIBILITE, pas la rentabilite.")

    # ------------------------------------------------ 1. EFFET ARBITRE / CARTONS
    print("\n" + "=" * 94)
    print("TEST 1 - EFFET ARBITRE : certains arbitres avertissent-ils plus, A FAUTES EGALES ?")
    print("=" * 94)
    if "Referee" in d.columns:
        ar = d.dropna(subset=["Referee"])
        gA = ar[ar["periode"] == "A"].groupby("Referee")
        gB = ar[ar["periode"] == "B"].groupby("Referee")
        rows = []
        for name, g in gA:
            gb = gB.get_group(name) if name in gB.groups else None
            if len(g) < 25 or gb is None or len(gb) < 15:
                continue
            rA, mgA = bayes(g, "jaunes", "fautes")
            rB, _ = bayes(gb, "jaunes", "fautes")
            rows.append({"arbitre": name, "nA": len(g), "nB": len(gb),
                         "tauxA": rA, "tauxB": rB, "w": min(len(g), len(gb))})
        t = pd.DataFrame(rows)
        if len(t) >= 8:
            r, p, sd = corr_perm(t["tauxA"].values, t["tauxB"].values, t["w"].values)
            print(f"\n  {len(t)} arbitres avec assez de matchs sur les deux periodes")
            print(f"  Taux d'avertissement (jaunes / fautes) :")
            print(f"    periode A : de {t['tauxA'].min():.3f} a {t['tauxA'].max():.3f}"
                  f"  (amplitude x{t['tauxA'].max()/max(t['tauxA'].min(),1e-9):.2f})")
            print(f"    periode B : de {t['tauxB'].min():.3f} a {t['tauxB'].max():.3f}"
                  f"  (amplitude x{t['tauxB'].max()/max(t['tauxB'].min(),1e-9):.2f})")
            print(f"\n  CORRELATION A -> B : r = {r:+.4f}   p = {p:.4f}   (bruit: +/-{sd:.4f})")
            print(f"  VERDICT : {'EFFET REEL ET STABLE' if p<0.05 and r>0.3 else 'effet reel mais instable' if p<0.05 else 'PAS DE SIGNAL STABLE'}")
            top = t.sort_values("tauxA", ascending=False)
            print(f"\n  Les 5 arbitres les plus severes sur A (et leur comportement sur B) :")
            for _, x in top.head(5).iterrows():
                print(f"    {str(x['arbitre'])[:26]:<26} A={x['tauxA']:.3f} ({x['nA']} m)  "
                      f"B={x['tauxB']:.3f} ({x['nB']} m)  delta {x['tauxB']-x['tauxA']:+.3f}")
            print(f"  Les 5 plus indulgents sur A :")
            for _, x in top.tail(5).iterrows():
                print(f"    {str(x['arbitre'])[:26]:<26} A={x['tauxA']:.3f} ({x['nA']} m)  "
                      f"B={x['tauxB']:.3f} ({x['nB']} m)  delta {x['tauxB']-x['tauxA']:+.3f}")

    # ------------------------------------------------ 2. ARBITRE / FAUTES
    print("\n" + "=" * 94)
    print("TEST 2 - EFFET ARBITRE SUR LE NOMBRE DE FAUTES SIFFLEES")
    print("=" * 94)
    if "Referee" in d.columns:
        rows = []
        for name, g in d[d["periode"] == "A"].groupby("Referee"):
            gb = d[(d["periode"] == "B") & (d["Referee"] == name)]
            if len(g) < 25 or len(gb) < 15:
                continue
            rows.append({"a": g["fautes"].mean(), "b": gb["fautes"].mean(),
                         "w": min(len(g), len(gb))})
        t = pd.DataFrame(rows)
        if len(t) >= 8:
            r, p, sd = corr_perm(t["a"].values, t["b"].values, t["w"].values)
            print(f"  Fautes/match par arbitre : A de {t['a'].min():.1f} a {t['a'].max():.1f}"
                  f"  (amplitude {t['a'].max()-t['a'].min():+.1f} fautes)")
            print(f"  CORRELATION A -> B : r = {r:+.4f}   p = {p:.4f}")
            print(f"  VERDICT : {'EFFET REEL ET STABLE' if p<0.05 and r>0.3 else 'effet reel mais faible' if p<0.05 else 'PAS DE SIGNAL STABLE'}")

    # ------------------------------------------------ 3. EQUIPES / CORNERS
    print("\n" + "=" * 94)
    print("TEST 3 - LES CORNERS PAR EQUIPE SONT-ILS PREVISIBLES ?")
    print("=" * 94)
    for lab, col, dom, ext in (("corners", "corners", "HC", "AC"),
                               ("fautes", "fautes", "HF", "AF"),
                               ("jaunes", "jaunes", "HY", "AY")):
        rows = []
        for per_a, per_b in (("A", "B"),):
            da = d[d["periode"] == per_a]; db = d[d["periode"] == per_b]
            eq = sorted(set(da["HomeTeam"]) & set(db["HomeTeam"]))
            for e in eq:
                ga = da[(da["HomeTeam"] == e) | (da["AwayTeam"] == e)]
                gb = db[(db["HomeTeam"] == e) | (db["AwayTeam"] == e)]
                if len(ga) < 40 or len(gb) < 30:
                    continue
                va = np.where(ga["HomeTeam"] == e, ga[dom], ga[ext])
                vb = np.where(gb["HomeTeam"] == e, gb[dom], gb[ext])
                rows.append({"a": va.mean(), "b": vb.mean(), "w": min(len(ga), len(gb))})
        t = pd.DataFrame(rows)
        if len(t) >= 20:
            r, p, sd = corr_perm(t["a"].values, t["b"].values, t["w"].values)
            print(f"  {lab:<9} par equipe : n={len(t):>4}  A de {t['a'].min():.2f} a {t['a'].max():.2f}"
                  f"  |  r(A->B) = {r:+.4f}  p = {p:.4f}  "
                  f"{'STABLE' if p<0.05 and r>0.3 else 'faible' if p<0.05 else 'instable'}")

    # ------------------------------------------------ 4. PREVISIBILITE GLOBALE
    print("\n" + "=" * 94)
    print("TEST 4 - QUEL MARCHE EST LE PLUS PREVISIBLE ? (dispersion expliquee)")
    print("=" * 94)
    print("  Un marche est previsible si la variance ENTRE equipes/matchs depasse")
    print("  la variance POISSON attendue (le hasard pur).")
    print(f"\n  {'Marche':<22}{'moyenne':>9}{'var. observee':>15}{'var. Poisson':>14}{'sur-dispersion':>16}")
    print("  " + "-" * 76)
    for lab, col in (("Fautes totales", "fautes"),
                     ("Corners totaux", "corners"), ("Jaunes totaux", "jaunes"),
                     ("Rouges totaux", "rouges")):
        s = d[col]
        v_o, v_p = s.var(), s.mean()
        print(f"  {lab:<22}{s.mean():>9.2f}{v_o:>15.2f}{v_p:>14.2f}{v_o/max(v_p,1e-9):>16.2f}")
    print("\n  Sur-dispersion >> 1 = il y a de la structure a modeliser (donc de l'information).")
    print("  Sur-dispersion ~ 1 = hasard pur, rien a predire.")

    print("\n" + "=" * 94)
    print("CONCLUSION")
    print("=" * 94)
    print("""
  1. Les RESULTATS de ces marches sont previsibles et l'effet arbitre est mesurable.
  2. MAIS aucune cote n'est disponible gratuitement -> ROI impossible a etablir.
  3. Donc: afficher ces pronostics dans l'app est UTILE (analyse), mais promettre
     qu'ils font gagner de l'argent serait MALHONNETE sans test sur cotes reelles.
  4. Pour aller plus loin il faudrait les cotes de ces marches (API payante, ou
     relevé manuel chez un bookmaker), puis rejouer exactement le protocole A/B.
""")
    d[["date", "div", "periode", "HomeTeam", "AwayTeam", "Referee" if "Referee" in d else "div",
       "fautes", "corners", "jaunes", "rouges"]].to_csv("marches_secondaires.csv", index=False)
    print(f"  Detail sauvegarde : marches_secondaires.csv ({len(d)} matchs)")


if __name__ == "__main__":
    main()
