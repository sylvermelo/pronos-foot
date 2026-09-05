"""
Entrainement des modeles et sauvegarde pour l'application web.

Entrainement UNIQUE ici (lent), puis l'app ne fait plus que des calculs instantanes.
Sortie : data/modeles.json
"""
import os, glob, json, warnings, time
import numpy as np
import pandas as pd
from scipy.stats import poisson

warnings.filterwarnings("ignore")
import moteur_v3 as V
import modeles_secondaires as MS

NOMS = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two",
    "SP1": "La Liga", "SP2": "La Liga 2", "I1": "Serie A", "I2": "Serie B",
    "D1": "Bundesliga", "D2": "Bundesliga 2", "F1": "Ligue 1", "F2": "Ligue 2",
    "N1": "Eredivisie", "B1": "Jupiler Pro League", "P1": "Liga Portugal",
    "T1": "Super Lig", "G1": "Super League Grece",
    "SC0": "Scottish Premiership", "SC1": "Scottish Championship",
    "SC2": "Scottish League One", "SC3": "Scottish League Two",
}
PAYS = {"E": "Angleterre", "SP": "Espagne", "I": "Italie", "D": "Allemagne",
        "F": "France", "N": "Pays-Bas", "B": "Belgique", "P": "Portugal",
        "T": "Turquie", "G": "Grece", "SC": "Ecosse"}
STATS = ["hg", "ag", "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC", "HY", "AY"]

# Divisions couvertes par les xG RÉELS d'Understat (test A/B validé : le modèle
# xG recalé bat le modèle buts seuls, t = -2.6 sur 7 118 matchs, 2022-2026).
XG_REEL_DIVS = {"E0", "SP1", "I1", "D1", "F1"}


def fusionner_xg_reel(df):
    """Joint les xG réels Understat (data/xg_understat.json) sur df, par
    (division, équipes, date ± 1 jour). Colonnes xgRH / xgRA (NaN sinon).
    Aucun échec n'est bloquant : sans le fichier, df revient inchangé."""
    df["xgRH"] = np.nan
    df["xgRA"] = np.nan
    chemin = os.path.join("data", "xg_understat.json")
    if not os.path.exists(chemin):
        return df
    try:
        with open(chemin) as f:
            xg = json.load(f)
    except Exception:
        return df
    lut = {}
    for div, matchs in xg.items():
        for m in matchs:
            try:
                d = pd.Timestamp(m["date"]).normalize()
            except Exception:
                continue
            lut[(div, m["home"], m["away"], d)] = (
                min(max(float(m["xg_h"]), 0.05), 6.0),
                min(max(float(m["xg_a"]), 0.05), 6.0))
    if not lut:
        return df
    cible = df.index[df["league"].isin({k[0] for k in lut})]
    rh = np.full(len(cible), np.nan)
    ra = np.full(len(cible), np.nan)
    for i, row in enumerate(df.loc[cible].itertuples()):
        for dl in (0, -1, 1):
            k = (row.league, row.home, row.away,
                 row.date.normalize() + pd.Timedelta(days=dl))
            if k in lut:
                rh[i], ra[i] = lut[k]
                break
    df.loc[cible, "xgRH"] = rh
    df.loc[cible, "xgRA"] = ra
    return df


def charger():
    """Charge TOUTES les saisons disponibles, toutes divisions."""
    # sorted() est INDISPENSABLE : glob() renvoie les fichiers dans l'ordre du
    # systeme de fichiers, qui change d'une machine a l'autre. Sans tri, les
    # matchs a date egale arrivent dans un ordre different, l'optimisation
    # converge vers un point legerement different, et les probabilites bougent
    # d'environ 1 point d'une execution a l'autre sans aucune raison.
    files = sorted(f for f in glob.glob("data/2*.csv")
                   if "_" in os.path.basename(f) and "enrichi" not in f)
    frames = []
    for f in files:
        b = os.path.basename(f).replace(".csv", "")
        saison, div = b.split("_")
        if div not in NOMS:
            continue
        try:
            x = pd.read_csv(f, encoding="latin-1")
        except Exception:
            continue
        if "HomeTeam" not in x.columns or "FTHG" not in x.columns:
            continue
        x = x.rename(columns={"HomeTeam": "home", "AwayTeam": "away",
                              "FTHG": "hg", "FTAG": "ag"})
        x["date"] = pd.to_datetime(x["Date"], format="mixed", dayfirst=True, errors="coerce")
        x = x.dropna(subset=["date", "home", "away", "hg", "ag"])
        for c in STATS[2:]:
            if c in x.columns:
                x[c] = pd.to_numeric(x[c], errors="coerce")
            else:
                x[c] = np.nan
        x["hg"] = pd.to_numeric(x["hg"], errors="coerce")
        x["ag"] = pd.to_numeric(x["ag"], errors="coerce")
        x = x.dropna(subset=["hg", "ag"])
        x["hg"] = x["hg"].astype(int).clip(0, V.MAXG)
        x["ag"] = x["ag"].astype(int).clip(0, V.MAXG)
        x["league"] = div; x["season"] = saison
        if "Referee" in x.columns:
            x["Referee"] = x["Referee"].astype(str).replace({"nan": None})
        else:
            x["Referee"] = None
        frames.append(x[["date", "league", "season", "home", "away", "hg", "ag", "Referee"] + STATS[2:]])
    df = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["date", "league", "home", "away"])
    df = df.sort_values("date").reset_index(drop=True)
    return fusionner_xg_reel(df)


def stats_equipe(hist, team, jours=400):
    """Statistiques descriptives recentes d'une equipe (pour l'affichage)."""
    cut = hist["date"].max() - pd.Timedelta(days=jours)
    h = hist[hist["date"] >= cut]
    dom = h[h["home"] == team]; ext = h[h["away"] == team]
    n = len(dom) + len(ext)
    if n == 0:
        return None
    marque = dom["hg"].sum() + ext["ag"].sum()
    encaisse = dom["ag"].sum() + ext["hg"].sum()
    v = int((dom["hg"] > dom["ag"]).sum() + (ext["ag"] > ext["hg"]).sum())
    d = int((dom["hg"] == dom["ag"]).sum() + (ext["ag"] == ext["hg"]).sum())
    def moy(col, c1, c2):
        a = dom[c1] if c1 in dom else pd.Series(dtype=float)
        b = ext[c2] if c2 in ext else pd.Series(dtype=float)
        s = pd.concat([a, b]).dropna()
        return round(float(s.mean()), 2) if len(s) else None
    # forme: 5 derniers matchs
    m5 = pd.concat([dom.assign(pts=np.where(dom["hg"] > dom["ag"], 3, np.where(dom["hg"] == dom["ag"], 1, 0))),
                    ext.assign(pts=np.where(ext["ag"] > ext["hg"], 3, np.where(ext["ag"] == ext["hg"], 1, 0)))]
                   ).sort_values("date").tail(5)
    forme = "".join("V" if p == 3 else "N" if p == 1 else "D" for p in m5["pts"])
    # xG réels (Understat) des 400 derniers jours, si disponibles
    xg_pour = xg_contre = None
    if "xgRH" in h.columns:
        sp = pd.concat([dom["xgRH"], ext["xgRA"]]).dropna()
        sc = pd.concat([dom["xgRA"], ext["xgRH"]]).dropna()
        if len(sp):
            xg_pour = round(float(sp.mean()), 2)
        if len(sc):
            xg_contre = round(float(sc.mean()), 2)
    return {
        "xg_pour": xg_pour, "xg_contre": xg_contre,
        "matchs": int(n), "victoires": v, "nuls": d, "defaites": int(n - v - d),
        "marques": round(marque / n, 2), "encaisses": round(encaisse / n, 2),
        "points": int(v * 3 + d), "forme": forme,
        "tirs": moy(None, "HS", "AS"), "tirs_cadres": moy(None, "HST", "AST"),
        "fautes": moy(None, "HF", "AF"), "corners": moy(None, "HC", "AC"),
        "jaunes": moy(None, "HY", "AY"),
    }


def main():
    t0 = time.time()
    df = charger()
    print(f"{len(df)} matchs charges, {df['league'].nunique()} divisions, "
          f"{df['date'].min().date()} -> {df['date'].max().date()}")

    out = {"genere_le": pd.Timestamp.now().isoformat(), "ligues": {}, "meta": {}}
    total_matchs = 0
    for div in sorted(df["league"].unique()):
        # tri canonique : date puis equipes, pour lever toute ambiguite
        sub = (df[df["league"] == div]
               .sort_values(["date", "home", "away"], kind="mergesort")
               .reset_index(drop=True))
        if len(sub) < 150:
            continue
        # entrainement sur les 5 dernieres saisons, avec TOUTES leurs equipes
        # (sinon .map(idx) produit des NaN qui cassent l'indexation)
        saisons = sorted(sub["season"].unique())[-5:]
        hist_fit = sub[sub["season"].isin(saisons)]
        derniere = sub["season"].max()
        rec = sub[sub["season"] == derniere]
        teams_act = sorted(set(rec["home"]) | set(rec["away"]))
        teams_fit = sorted(set(hist_fit["home"]) | set(hist_fit["away"]))
        try:
            mo = V.fit_goals(hist_fit, teams_fit, shrink=20.0)
        except Exception as e:
            print(f"  {div} ECHEC: {e}")
            continue
        # ---- xG RÉELS (Understat) : validé en A/B, uniquement pour les 5 ligues
        # couvertes. Variante REELCAL du test : forces estimées sur les xG réels
        # (w=0), niveau de buts recalé sur les buts RÉELS de la fenêtre (k),
        # rho conservé du modèle Dixon-Coles. Les 16 autres divisions gardent
        # le modèle buts (le proxy tirs y est significativement pire).
        moteur = "Dixon-Coles (buts réels)"
        if div in XG_REEL_DIVS and "xgRH" in hist_fit.columns:
            hr = hist_fit[hist_fit["xgRH"].notna()]
            if len(hr) >= 300:
                hr2 = hr.copy()
                hr2["xgH"] = hr2["xgRH"]
                hr2["xgA"] = hr2["xgRA"]
                try:
                    mx = V.fit_xg(hr2, teams_fit)
                except Exception:
                    mx = None
                if mx is not None:
                    hc = hist_fit[hist_fit["home"].isin(mx["idx"])
                                  & hist_fit["away"].isin(mx["idx"])]
                    hi_ = hc["home"].map(mx["idx"]).values
                    aw_ = hc["away"].map(mx["idx"]).values
                    pred = (mx["gh"] * mx["att"][hi_] * mx["dfn"][aw_]
                            + mx["ga"] * mx["att"][aw_] * mx["dfn"][hi_])
                    if len(pred) >= 200 and pred.mean() > 0:
                        k = float((hc["hg"].values + hc["ag"].values).mean()
                                  / pred.mean())
                        mo = dict(V.combine(mo, mx, 0.0))
                        mo["gamma"] = mo["gamma"] * k
                        mo["s"] = mo["s"] * k
                        moteur = (f"xG réels Understat recalés (k={k:.3f}, "
                                  f"{len(hr)} matchs xG)")
        # nombre de matchs EFFECTIFS par equipe dans la fenetre d'entrainement
        ref = hist_fit["date"].max()
        ww = np.exp(-V.XI_WEEK * (ref - hist_fit["date"]).dt.days.values / 7.0)
        nm = {t: 0.0 for t in teams_fit}
        for t, wv in zip(hist_fit["home"], ww):
            nm[t] = nm.get(t, 0) + wv
        for t, wv in zip(hist_fit["away"], ww):
            nm[t] = nm.get(t, 0) + wv
        brut = {t: 0 for t in teams_fit}
        for t in hist_fit["home"]:
            brut[t] = brut.get(t, 0) + 1
        for t in hist_fit["away"]:
            brut[t] = brut.get(t, 0) + 1
        forces = {t: {"att": round(float(mo["att"][mo["idx"][t]]), 4),
                      "dfn": round(float(mo["dfn"][mo["idx"][t]]), 4),
                      "n_eff": round(float(nm.get(t, 0)), 1),
                      "n_brut": int(brut.get(t, 0))}
                  for t in teams_fit if t in mo["idx"]}
        # puissance globale = attaque / defense
        # LISSAGE VERS LA MOYENNE : une equipe avec trop peu de matchs dans la division
        # (promu, debut de saison) est ramenee vers le niveau moyen par interpolation
        # geometrique. Sans cela: Hull classe n.1 de Premier League apres 2 matchs.
        SEUIL_CONF = 15.0
        for t in forces:
            w = min(1.0, forces[t]["n_eff"] / SEUIL_CONF)
            forces[t]["att"] = round(forces[t]["att"] ** w, 4)
            forces[t]["dfn"] = round(forces[t]["dfn"] ** w, 4)
            forces[t]["lissage"] = round(w, 3)
            forces[t]["puissance"] = round(forces[t]["att"] / max(forces[t]["dfn"], 1e-6), 4)
        stats = {t: stats_equipe(sub, t) for t in teams_act}
        stats = {k: v for k, v in stats.items() if v}
        # marches secondaires : facteurs par equipe (au niveau de la division)
        # hist_fit et non sub : on utilise exactement la meme fenetre de 5 saisons
        # que le modele de buts. Sans cela, le resultat depend du nombre de
        # saisons presentes sur le disque et n'est pas reproductible.
        try:
            sec = MS.estimer(hist_fit, teams_act, arbitres=False)
        except Exception as e:
            print(f"    secondaires ECHEC {div}: {e}")
            sec = None
        pays = "".join(c for c in div if c.isalpha())
        out["ligues"][div] = {
            "nom": NOMS.get(div, div), "pays": PAYS.get(pays, pays),
            "saison": derniere, "equipes_actuelles": teams_act,
            "gamma": round(mo["gamma"], 4), "s_away": round(mo["s"], 4),
            "rho": round(mo["rho"], 4), "n_historique": int(len(hist_fit)),
            "moteur": moteur,
            "forces": forces, "stats": stats, "secondaires": sec,
            "dernier_match": str(sub["date"].max().date()),
        }
        # on compte la fenetre REELLEMENT utilisee pour l'entrainement (5 dernieres
        # saisons), pas tout ce qui est present sur le disque. Sinon le volume
        # annonce dans l'interface depend du nombre de fichiers telecharges et ne
        # correspond pas a ce que le modele a vraiment vu.
        total_matchs += len(hist_fit)
        print(f"  {NOMS.get(div,div):<24} {len(hist_fit):>5} matchs utilises "
              f"({len(sub):>5} charges) | {len(teams_act)} equipes | "
              f"gamma {mo['gamma']:.3f} | s {mo['s']:.3f}")

    # ---- arbitres : estimation GLOBALE (toutes divisions confondues)
    print("  Estimation des effets arbitres (toutes divisions)...")
    try:
        # meme fenetre de 5 saisons que le reste du modele : sans cela le facteur
        # d'un arbitre depend du nombre de saisons presentes sur le disque
        saisons_glob = sorted(df["season"].dropna().unique())[-5:]
        df_fit = df[df["season"].isin(saisons_glob)]
        ar = MS.estimer(df_fit, [], arbitres=True)["arbitres"]
        out["arbitres"] = ar
        if ar:
            sv = sorted(ar.items(), key=lambda kv: -kv[1]["jaunes"])
            sev = [k for k, v in sv if v["n"] >= 40]
            print(f"    {len(ar)} arbitres | {len(sev)} avec >=40 matchs")
            if sev:
                print(f"    le plus severe : {sev[0]} (jaunes x{ar[sev[0]]['jaunes']:.2f})")
                print(f"    le plus clément: {sev[-1]} (jaunes x{ar[sev[-1]]['jaunes']:.2f})")
    except Exception as e:
        print(f"    arbitres ECHEC: {e}")
        out["arbitres"] = {}

    # ---- matchs a venir (fixtures.csv)
    fix = []
    if os.path.exists("data/fixtures.csv"):
        f = pd.read_csv("data/fixtures.csv", encoding="utf-8-sig")
        f["Date"] = pd.to_datetime(f["Date"], format="mixed", dayfirst=True, errors="coerce")
        for c in ["Time", "HomeTeam", "AwayTeam", "Referee", "Div"]:
            if c not in f.columns:
                f[c] = ""
        for _, r in f.iterrows():
            fix.append({
                "div": str(r["Div"]), "date": str(r["Date"].date()) if pd.notna(r["Date"]) else "",
                "heure": str(r.get("Time", ""))[:5], "home": str(r["HomeTeam"]),
                "away": str(r["AwayTeam"]), "arbitre": str(r.get("Referee", "")) if pd.notna(r.get("Referee")) else "",
                "cote_1": _num(r.get("AvgH")), "cote_X": _num(r.get("AvgD")),
                "cote_2": _num(r.get("AvgA")),
                "cote_max_1": _num(r.get("MaxH")), "cote_max_X": _num(r.get("MaxD")),
                "cote_max_2": _num(r.get("MaxA")),
                "cote_over": _num(r.get("Avg>2.5")), "cote_under": _num(r.get("Avg<2.5")),
                "cote_over_max": _num(r.get("Max>2.5")), "cote_under_max": _num(r.get("Max<2.5")),
            })
    out["fixtures"] = fix
    # référence brute des cotes co.uk : le calendrier multi-sources
    # (maj_calendrier.py) fait la jonction à partir de cette liste.
    out["fixtures_cotes"] = fix
    out["meta"] = {"total_matchs": total_matchs, "n_ligues": len(out["ligues"]),
                   "n_fixtures": len(fix), "duree_s": round(time.time() - t0, 1)}
    json.dump(out, open("data/modeles.json", "w"))
    print(f"\nmodeles.json sauvegarde : {os.path.getsize('data/modeles.json')/1024:.0f} Ko | "
          f"{len(out['ligues'])} ligues | {len(fix)} matchs a venir | {time.time()-t0:.0f}s")


def _num(x):
    try:
        v = float(x)
        return round(v, 3) if v > 1.01 else None
    except Exception:
        return None


if __name__ == "__main__":
    main()
