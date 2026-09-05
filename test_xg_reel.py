# -*- coding: utf-8 -*-
"""
Test A/B honnête : les xG RÉELS d'Understat améliorent-ils le moteur ?

Protocole (identique au backtest v3, walk-forward strict, aucune donnée future) :
  - 5 ligues couvertes par Understat : E0, SP1, I1, D1, F1
  - période évaluée : 2223 -> aujourd'hui (l'xG réel commence en 2122,
    donc le modèle xG a toujours au moins une saison d'historique)
  - variantes :
      BUTS    = fit_goals seul (w=1.0, le moteur de production actuel)
      PROXY   = combine(buts, xG-proxy-tirs, w)
      REEL    = combine(buts, xG Understat, w)
  - référence : cotes de clôture Pinnacle (devig)

Usage : python3 test_xg_reel.py
"""
import json, os, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import moteur_v3 as V

LIGUES_TEST = {"E0": "Premier League", "SP1": "La Liga", "I1": "Serie A",
               "D1": "Bundesliga", "F1": "Ligue 1"}
POIDS_TEST = [1.00, 0.75, 0.50, 0.25, 0.00]
EVAL_FROM = pd.Timestamp("2022-08-01")
REFIT = 4          # ré-entraînement toutes les 4 semaines (comme le backtest v3)
MIN_HIST = 200


def charger_avec_xg_reel():
    """Base moteur_v3 + colonnes xgRH/xgRA (xG réels Understat, jointure ±1 jour)."""
    if "2627" not in V.ALL_SEASONS:
        V.ALL_SEASONS = V.ALL_SEASONS + ["2627"]
    df = V.load()
    df = df[df["league"].isin(LIGUES_TEST)].reset_index(drop=True)

    with open("data/xg_understat.json") as f:
        xg = json.load(f)
    lut = {}
    for div, matchs in xg.items():
        for m in matchs:
            d = pd.Timestamp(m["date"]).normalize()
            lut[(div, m["home"], m["away"], d)] = (m["xg_h"], m["xg_a"])

    rh = np.full(len(df), np.nan); ra = np.full(len(df), np.nan)
    for i, row in enumerate(df.itertuples()):
        for delta in (0, -1, 1):
            k = (row.league, row.home, row.away, row.date.normalize() + pd.Timedelta(days=delta))
            if k in lut:
                rh[i], ra[i] = lut[k]
                break
    df["xgRH"] = np.where(np.isnan(rh), np.nan, np.clip(rh, 0.05, 6.0))
    df["xgRA"] = np.where(np.isnan(ra), np.nan, np.clip(ra, 0.05, 6.0))
    return df


def walk_forward(df):
    rows = []
    for lg, nom in LIGUES_TEST.items():
        sub = df[df["league"] == lg].sort_values("date").reset_index(drop=True)
        weeks = sorted(sub["date"].dt.to_period("W").unique())
        mg = mxp = mxr = None; k_cal = None
        nfit = 0
        t0 = time.time()
        for k, wk in enumerate(weeks):
            cur = sub[(sub["date"].dt.to_period("W") == wk) & (sub["date"] >= EVAL_FROM)]
            if mg is None or k % REFIT == 0:
                hist = sub[sub["date"] < wk.start_time]
                if len(hist) < MIN_HIST:
                    continue
                t = sorted(set(hist["home"]) | set(hist["away"]))
                try:
                    mg = V.fit_goals(hist, t)
                except Exception:
                    mg = None
                    continue
                mxp = V.fit_xg(hist, t)
                hr = hist[hist["xgRH"].notna()]
                if len(hr) >= 60:
                    hr2 = hr.copy(); hr2["xgH"] = hr2["xgRH"]; hr2["xgA"] = hr2["xgRA"]
                    try:
                        mxr = V.fit_xg(hr2, t)
                    except Exception:
                        mxr = None
                else:
                    mxr = None
                k_cal = None
                if mxr is not None:
                    hc = hist[hist["home"].isin(mxr["idx"]) & hist["away"].isin(mxr["idx"])]
                    if len(hc) >= 100:
                        hi_ = hc["home"].map(mxr["idx"]).values
                        aw_ = hc["away"].map(mxr["idx"]).values
                        pred = (mxr["gh"] * mxr["att"][hi_] * mxr["dfn"][aw_] +
                                mxr["ga"] * mxr["att"][aw_] * mxr["dfn"][hi_])
                        if pred.mean() > 0:
                            k_cal = float((hc["hg"] + hc["ag"]).mean() / pred.mean())
                nfit += 1
            if mg is None or len(cur) == 0:
                continue
            for m in cur.itertuples():
                if m.home not in mg["idx"] or m.away not in mg["idx"]:
                    continue
                base = {"league": nom, "date": m.date, "home": m.home, "away": m.away,
                        "hg": m.hg, "ag": m.ag,
                        "o1": getattr(m, "PSCH", np.nan), "oX": getattr(m, "PSCD", np.nan),
                        "o2": getattr(m, "PSCA", np.nan),
                        "oO": getattr(m, "_26", np.nan), "oU": getattr(m, "_27", np.nan)}
                # cotes O/U : noms de colonnes à caractères spéciaux
                try:
                    d0 = sub.loc[m.Index]
                    base["oO"] = d0.get("PC>2.5", np.nan); base["oU"] = d0.get("PC<2.5", np.nan)
                except Exception:
                    pass
                for w in POIDS_TEST:
                    for var, mx in (("PROXY", mxp), ("REEL", mxr)):
                        mo = V.combine(mg, mx, w)
                        if var == "REEL" and w == 0.0 and mxr is not None and k_cal:
                            # variante REELCAL : xG seul, niveau de buts recalé sur
                            # les buts RÉELS de la fenêtre (corrige le biais log-linéaire)
                            mo2 = dict(mo); mo2["gamma"] = mo["gamma"] * k_cal
                            mo2["s"] = mo["s"] * k_cal
                            Mt = V.score_matrix(mo2, m.home, m.away)
                            if Mt is not None:
                                r = dict(base); r["w"] = 0.0; r["var"] = "REELCAL"
                                r.update(V.derive(Mt)); rows.append(r)
                        Mt = V.score_matrix(mo, m.home, m.away)
                        if Mt is None:
                            continue
                        r = dict(base); r["w"] = w; r["var"] = var
                        r.update(V.derive(Mt)); rows.append(r)
        print(f"  {nom:<16} {nfit:>3} entraînements | {time.time()-t0:.0f} s", flush=True)
    return pd.DataFrame(rows)


def metriques(d, colonne_p, n_classes):
    pass


def rapporter(bt):
    print("\n" + "=" * 100)
    print("RÉSULTATS — walk-forward strict, 5 ligues, août 2022 → aujourd'hui")
    print("référence : cotes de clôture Pinnacle (devig) sur le même sous-ensemble")
    print("=" * 100)

    # référence marché (1X2)
    e = bt[bt["w"] == 1.0].dropna(subset=["o1", "oX", "o2"]).drop_duplicates(
        subset=["league", "date", "home", "away"])
    res = np.where(e["hg"] > e["ag"], 0, np.where(e["hg"] == e["ag"], 1, 2))
    mk = np.array([V.devig(a, b, c) for a, b, c in zip(e["o1"], e["oX"], e["o2"])])
    ok = ~np.isnan(mk).any(1)
    ll_mkt = -np.mean(np.log(np.clip(mk[ok][np.arange(ok.sum()), res[ok]], 1e-9, 1)))
    print(f"\nMarché (Pinnacle clôture, n={ok.sum()}) : LogLoss 1X2 = {ll_mkt:.4f}")

    hdr = (f"{'VARIANTE':<10}{'w buts':>8}{'n':>7}{'LogLoss 1X2':>13}{'RPS':>9}"
           f"{'Préc.fav':>10}{'LL O/U2.5':>11}{'Biais buts':>12}")
    print("\n" + hdr); print("-" * 100)

    lignes = [("BUTS", 1.0)] + [("PROXY", w) for w in POIDS_TEST if w < 1] + \
             [("REEL", w) for w in POIDS_TEST if w < 1] + [("REELCAL", 0.0)]
    resats = {}
    for var, w in lignes:
        d = bt[(bt["var"] == var) & (bt["w"] == w)] if var != "BUTS" else \
            bt[(bt["var"] == "PROXY") & (bt["w"] == 1.0)]
        if len(d) == 0:
            continue
        n = len(d)
        r = np.where(d["hg"] > d["ag"], 0, np.where(d["hg"] == d["ag"], 1, 2))
        P = d[["p1", "pX", "p2"]].values; P = P / P.sum(1, keepdims=True)
        ll = -np.mean(np.log(np.clip(P[np.arange(n), r], 1e-9, 1)))
        rps = np.mean([np.mean((np.cumsum(P[i]) - np.cumsum(np.eye(3)[r[i]])) ** 2)
                       for i in range(n)])
        acc = np.mean(P.argmax(1) == r)
        f = d.dropna(subset=["oO", "oU"])
        if len(f) > 100:
            r2 = (f["hg"] + f["ag"] > 2.5).astype(int).values
            po = np.concatenate([f[["pO25"]].values, f[["pU25"]].values], 1)
            ll2 = -np.mean(np.log(np.clip(po[np.arange(len(r2)), r2], 1e-9, 1)))
        else:
            ll2 = np.nan
        biais = d["exp"].mean() - (d["hg"] + d["ag"]).mean()
        resats[(var, w)] = ll
        print(f"{var:<10}{w:>8.2f}{n:>7}{ll:>13.4f}{rps:>9.4f}{acc:>10.1%}"
              f"{ll2:>11.4f}{biais:>+12.3f}")

    print("-" * 100)
    base = resats.get(("BUTS", 1.0) if ("BUTS", 1.0) in resats else ("PROXY", 1.0))
    print(f"\nÉcarts vs moteur actuel (buts seuls, LL {base:.4f}) :")
    for (var, w), ll in sorted(resats.items(), key=lambda kv: kv[1]):
        if (var, w) == ("PROXY", 1.0):
            continue
        print(f"  {var} w={w:.2f} : {ll - base:+.4f}  ({'MIEUX' if ll < base else 'pire'})")
    return resats


if __name__ == "__main__":
    t0 = time.time()
    df = charger_avec_xg_reel()
    cov = df[df["date"] >= EVAL_FROM].groupby("league")["xgRH"].apply(
        lambda s: f"{s.notna().mean():.0%}")
    print("Base :", len(df), "matchs | couverture xG réel (période évaluée) :")
    print(" ", dict(cov))
    bt = walk_forward(df)
    rapporter(bt)
    bt.to_csv("data/ab_xg_reel.csv", index=False)
    print(f"\nDurée totale : {time.time()-t0:.0f} s | détails : data/ab_xg_reel.csv")
