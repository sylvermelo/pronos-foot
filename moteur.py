"""
Moteur de pronostic football - Preuve de concept v2
Modele: Dixon-Coles (Poisson bivarie corrige) + decay temporel + regularisation ridge
Backtest walk-forward contre les cotes de cloture Pinnacle (benchmark le plus dur)

Corrections v2:
  - BUG CRITIQUE: gamma etait faux apres renormalisation des forces d'equipe
  - Warm-up: entrainement sur 8 saisons, backtest sur les 5 dernieres uniquement
  - devig() robuste aux cotes manquantes
"""
import os, warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

warnings.filterwarnings("ignore")
MAXG = 10

LIGUES = {"E0": "Premier League", "SP1": "La Liga", "I1": "Serie A",
          "D1": "Bundesliga", "F1": "Ligue 1"}
ALL_SEASONS = ["1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526"]
BACKTEST_FROM = "2122"          # on n'evalue que ces saisons (les autres = warm-up)


# ---------------------------------------------------------------- chargement
def load_all():
    frames = []
    for s in ALL_SEASONS:
        for d in LIGUES:
            f = f"data/{s}_{d}.csv"
            if os.path.exists(f):
                df = pd.read_csv(f, encoding="latin-1")
                df["league"] = d
                df["season"] = s
                frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["Date"], format="mixed", dayfirst=True, errors="coerce")
    df = df.dropna(subset=["date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    keep = ["date", "league", "season", "HomeTeam", "AwayTeam", "FTHG", "FTAG",
            "HF", "AF", "HC", "AC", "HY", "AY", "Referee",
            "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA",
            "P>2.5", "P<2.5", "PC>2.5", "PC<2.5", "Avg>2.5", "Avg<2.5"]
    df = df[[c for c in keep if c in df.columns]].copy()
    for c in df.columns:
        if c not in ("date", "league", "season", "HomeTeam", "AwayTeam", "Referee"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.rename(columns={"HomeTeam": "home", "AwayTeam": "away",
                            "FTHG": "hg", "FTAG": "ag"})
    df = df.dropna(subset=["hg", "ag"])
    df["hg"] = df["hg"].astype(int).clip(0, MAXG)
    df["ag"] = df["ag"].astype(int).clip(0, MAXG)
    df["evaluable"] = df["season"] >= BACKTEST_FROM
    return df.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------- Dixon-Coles
def dixon_coles_fit(hist, teams, xi_week=0.012, ridge=0.03):
    """xi_week=0.012  =>  demi-vie ~ 58 semaines (~13 mois), standard du domaine."""
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    ref = hist["date"].max()
    w = np.exp(-xi_week * (ref - hist["date"]).dt.days.values / 7.0)
    hi = hist["home"].map(idx).values
    aw = hist["away"].map(idx).values
    x = hist["hg"].values.astype(int)
    y = hist["ag"].values.astype(int)

    def neg_ll(p):
        att = np.exp(p[:n])
        dfn = np.exp(p[n:2 * n])
        gam = np.exp(p[2 * n])
        rho = np.tanh(p[2 * n + 1])
        lam = np.clip(att[hi] * dfn[aw] * gam, 1e-6, 30)
        mu = np.clip(att[aw] * dfn[hi], 1e-6, 30)
        ll = poisson.logpmf(x, lam) + poisson.logpmf(y, mu)
        tau = np.ones_like(ll)
        m00 = (x == 0) & (y == 0); m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0); m11 = (x == 1) & (y == 1)
        tau[m00] = 1 - lam[m00] * mu[m00] * rho
        tau[m01] = 1 + lam[m01] * rho
        tau[m10] = 1 + mu[m10] * rho
        tau[m11] = 1 - rho
        ll = ll + np.log(np.clip(tau, 1e-9, None))
        pen = (np.mean(p[:n]) ** 2) * 30.0 + ridge * np.sum(p[:2 * n] ** 2)
        return -np.sum(w * ll) + pen

    p0 = np.zeros(2 * n + 2)
    p0[2 * n] = np.log(1.30)
    res = minimize(neg_ll, p0, method="L-BFGS-B",
                   options={"maxiter": 300, "maxfun": 8000, "ftol": 1e-10})
    p = res.x
    att = np.exp(p[:n]); dfn = np.exp(p[n:2 * n])
    ma, md = att.mean(), dfn.mean()
    # FIX v2 : compenser gamma quand on renormalise att et dfn
    gamma = float(np.exp(p[2 * n]) * ma * md)
    return {"att": att / ma, "dfn": dfn / md, "gamma": gamma,
            "rho": float(np.tanh(p[2 * n + 1])), "idx": idx, "teams": teams}


def score_matrix(model, home, away):
    att, dfn, idx = model["att"], model["dfn"], model["idx"]
    lam = np.clip(att[idx[home]] * dfn[idx[away]] * model["gamma"], 1e-6, 30)
    mu = np.clip(att[idx[away]] * dfn[idx[home]], 1e-6, 30)
    rho = model["rho"]
    k = np.arange(MAXG + 1)
    M = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
    M[0, 0] *= max(1 - lam * mu * rho, 1e-9)
    M[0, 1] *= max(1 + lam * rho, 1e-9)
    M[1, 0] *= max(1 + mu * rho, 1e-9)
    M[1, 1] *= max(1 - rho, 1e-9)
    return np.clip(M, 0, None) / max(np.clip(M, 0, None).sum(), 1e-12)


def markets(M):
    tri = np.tril(M, -1).sum(); diag = np.trace(M)
    g = np.add.outer(np.arange(MAXG + 1), np.arange(MAXG + 1))
    # FIX v3: np.tril(M,-1) = cases i>j = buts DOMICILE > buts EXTERIEUR = victoire 1
    out = {"1": float(tri), "X": float(diag), "2": float(M.sum() - tri - diag),
           "exp_goals": float((M * g).sum())}
    for s in (1.5, 2.5, 3.5, 4.5, 5.5):
        out[f"O{s}"] = float(M[g > s].sum()); out[f"U{s}"] = float(M[g < s].sum())
    out["BTTS"] = float(M[1:, 1:].sum())
    out["NG"] = float(M[0, :].sum() + M[:, 0].sum() - M[0, 0])
    out["fleuve"] = float(M[g >= 5].sum())          # 5 buts ou plus
    out["eclat"] = float(M[np.abs(np.subtract.outer(np.arange(MAXG + 1),
                                                    np.arange(MAXG + 1))) >= 3].sum())
    out["top_scores"] = sorted(((f"{i}-{j}", float(M[i, j]))
                                for i in range(6) for j in range(6)),
                               key=lambda z: -z[1])[:3]
    return out


# ---------------------------------------------------------------- backtest
def devig(*odds):
    o = [float(x) for x in odds if x is not None and np.isfinite(x) and x > 1.01]
    if len(o) != len(odds) or len(o) < 2:
        return np.full(len(odds), np.nan)
    inv = np.array([1 / x for x in o])
    return inv / inv.sum()


def rps(probs, k):
    c = np.cumsum(probs)
    o = np.cumsum([1.0 if i == k else 0.0 for i in range(len(probs))])
    return float(np.mean((c - o) ** 2))


def run_backtest(refit_every=3, min_hist=200):
    df = load_all()
    print(f"Base : {len(df)} matchs | {df['league'].nunique()} ligues | "
          f"{df['season'].nunique()} saisons")
    print(f"Periode totale : {df['date'].min().date()} -> {df['date'].max().date()}")
    print(f"Backtest evalue a partir de la saison {BACKTEST_FROM}\n")

    rows, cur_model = [], {}
    for lg, lg_name in LIGUES.items():
        sub = df[df["league"] == lg].sort_values("date").reset_index(drop=True)
        if len(sub) < 400:
            print(f"  {lg_name:<16} ignore (trop peu de matchs)")
            continue
        weeks = sorted(sub["date"].dt.to_period("W").unique())
        model = None; nfit = 0
        for k, wk in enumerate(weeks):
            cur = sub[sub["date"].dt.to_period("W") == wk]
            if not cur["evaluable"].any():
                # semaine d'entrainement uniquement -> on garde le modele a jour
                if k % refit_every == 0 or model is None:
                    hist = sub[sub["date"] < wk.start_time]
                    if len(hist) >= min_hist:
                        teams = sorted(set(hist["home"]) | set(hist["away"]))
                        try:
                            model = dixon_coles_fit(hist, teams); nfit += 1
                        except Exception:
                            pass
                continue
            if model is None or k % refit_every == 0:
                hist = sub[sub["date"] < wk.start_time]
                if len(hist) < min_hist:
                    continue
                teams = sorted(set(hist["home"]) | set(hist["away"]))
                try:
                    model = dixon_coles_fit(hist, teams); nfit += 1
                except Exception:
                    continue
            for _, m in cur.iterrows():
                if m["home"] not in model["idx"] or m["away"] not in model["idx"]:
                    continue
                mk = markets(score_matrix(model, m["home"], m["away"]))
                rows.append({
                    "league": lg_name, "date": m["date"], "home": m["home"],
                    "away": m["away"], "hg": m["hg"], "ag": m["ag"],
                    "p1": mk["1"], "pX": mk["X"], "p2": mk["2"],
                    "pO25": mk["O2.5"], "pU25": mk["U2.5"], "pO35": mk["O3.5"],
                    "pBTTS": mk["BTTS"], "pFleuve": mk["fleuve"],
                    "exp_goals": mk["exp_goals"],
                    "o1": m.get("PSCH"), "oX": m.get("PSCD"), "o2": m.get("PSCA"),
                    "oO": m.get("PC>2.5"), "oU": m.get("PC<2.5"),
                    "oo1": m.get("PSH"), "ooX": m.get("PSD"), "oo2": m.get("PSA"),
                })
        cur_model[lg] = model
        print(f"  {lg_name:<16} {nfit:>4} reentrainements")
    return pd.DataFrame(rows), cur_model


def evaluate(bt):
    L = print
    L("\n" + "=" * 80)
    L("RAPPORT DE BACKTEST  -  aucune donnee future utilisee (walk-forward strict)")
    L("=" * 80)
    L(f"\nMatchs predits : {len(bt)}")
    tot = bt["hg"] + bt["ag"]
    L(f"Buts reels/match : {tot.mean():.2f}   |   Buts predits/match : "
      f"{bt['exp_goals'].mean():.2f}   -> ecart {bt['exp_goals'].mean()-tot.mean():+.3f}")

    d = bt.dropna(subset=["o1", "oX", "o2"]).copy()
    res = np.where(d["hg"] > d["ag"], 0, np.where(d["hg"] == d["ag"], 1, 2))
    P = d[["p1", "pX", "p2"]].values
    P = P / P.sum(1, keepdims=True)
    mkt = np.array([devig(a, b, c) for a, b, c in zip(d["o1"], d["oX"], d["o2"])])
    ok = ~np.isnan(mkt).any(1)
    m = mkt[ok]; po = P[ok]; r = res[ok]
    n = len(r)
    ll = lambda pr: -np.mean(np.log(np.clip(pr[np.arange(len(r)), r], 1e-9, 1)))
    L(f"\n--- MARCHE 1X2  ({n} matchs avec cote de cloture Pinnacle) ---")
    L(f"{'':<34}{'MODELE':>12}{'MARCHÉ':>12}")
    L(f"{'Log-loss  (plus bas = meilleur)':<34}{ll(po):>12.4f}{ll(m):>12.4f}")
    L(f"{'RPS       (plus bas = meilleur)':<34}"
      f"{np.mean([rps(po[i], r[i]) for i in range(n)]):>12.4f}"
      f"{np.mean([rps(m[i], r[i]) for i in range(n)]):>12.4f}")
    L(f"{'Precision du favori':<34}{np.mean(po.argmax(1)==r):>11.1%}"
      f"{np.mean(m.argmax(1)==r):>11.1%}")
    L(f"{'Taux de nuls reels':<34}{np.mean(r==1):>11.1%}"
      f"{po[:,1].mean():>11.1%}  (modele)")

    d2 = bt.dropna(subset=["oO", "oU"]).copy()
    if len(d2) > 100:
        r2 = (d2["hg"] + d2["ag"] > 2.5).astype(int).values
        pm = np.array([devig(a, b) for a, b in zip(d2["oO"], d2["oU"])])
        po2 = np.stack([d2["pO25"].values, d2["pU25"].values], 1)
        po2 = po2 / po2.sum(1, keepdims=True)
        ok2 = ~np.isnan(pm).any(1)
        pm, po2, r2 = pm[ok2], po2[ok2], r2[ok2]
        ll2 = lambda pr: -np.mean(np.log(np.clip(pr[np.arange(len(r2)), r2], 1e-9, 1)))
        L(f"\n--- MARCHE OVER/UNDER 2.5 BUTS  ({len(r2)} matchs) ---")
        L(f"{'':<34}{'MODELE':>12}{'MARCHÉ':>12}")
        L(f"{'Log-loss  (plus bas = meilleur)':<34}{ll2(po2):>12.4f}{ll2(pm):>12.4f}")
        L(f"{'Taux Over 2.5 reel':<34}{r2.mean():>11.1%}{po2[:,0].mean():>11.1%}")

    L(f"\n--- CALIBRATION DU MODELE (1X2) ---")
    L(f"{'Proba predite':<20}{'N':>8}{'Taux reel':>12}{'Ecart':>10}")
    lo_ = pd.DataFrame({"p": np.concatenate([d["p1"], d["pX"], d["p2"]]),
                        "y": np.concatenate([(d["hg"] > d["ag"]).astype(int),
                                             (d["hg"] == d["ag"]).astype(int),
                                             (d["hg"] < d["ag"]).astype(int)])})
    for a, b in [(0, .25), (.25, .40), (.40, .55), (.55, .70), (.70, 1.01)]:
        s = lo_[(lo_["p"] >= a) & (lo_["p"] < b)]
        if len(s) > 30:
            L(f"{a:>6.0%} - {min(b,1):<6.0%}{'':<6}{len(s):>8}{s['y'].mean():>11.1%}"
              f"{s['y'].mean()-s['p'].mean():>+10.1%}")

    L(f"\n--- TEST DE RENTABILITE (mise a plat, vs cote de CLOTURE Pinnacle) ---")
    for edge in (0.02, 0.04, 0.06, 0.10):
        st = pnl = 0; nb = w = 0
        for i in range(len(d)):
            for j, o in enumerate([d["o1"].iloc[i], d["oX"].iloc[i], d["o2"].iloc[i]]):
                if not (o and np.isfinite(o) and o > 1.01):
                    continue
                p = P[i, j]
                if p > (1 / o) * (1 + edge):
                    nb += 1; st += 1
                    if res[i] == j:
                        pnl += o - 1; w += 1
                    else:
                        pnl -= 1
        if nb:
            L(f"  edge requis {edge:>4.0%} : {nb:>5} paris | reussite {w/nb:>5.1%} | "
              f"ROI {pnl/st:>+7.2%} | P/L {pnl:>+8.1f} unites")
        else:
            L(f"  edge requis {edge:>4.0%} : aucun pari declenche")

    L(f"\n--- CLOSING LINE VALUE : le seul vrai juge de paix ---")
    d3 = d.dropna(subset=["oo1", "ooX", "oo2"]).copy()
    if len(d3) > 100:
        r3 = np.where(d3["hg"] > d3["ag"], 0, np.where(d3["hg"] == d3["ag"], 1, 2))
        P3 = d3[["p1", "pX", "p2"]].values; P3 = P3 / P3.sum(1, keepdims=True)
        op = np.array([devig(a, b, c) for a, b, c in zip(d3["oo1"], d3["ooX"], d3["oo2"])])
        ok3 = ~np.isnan(op).any(1)
        op, P3, r3 = op[ok3], P3[ok3], r3[ok3]
        f = lambda pr: -np.mean(np.log(np.clip(pr[np.arange(len(r3)), r3], 1e-9, 1)))
        L(f"  Log-loss MODELE            : {f(P3):.4f}")
        L(f"  Log-loss COTE D'OUVERTURE  : {f(op):.4f}")
        L(f"  Log-loss COTE DE CLOTURE   : {ll(m):.4f}")
        gap = f(op) - f(P3)
        if gap > 0.010:
            v = "MODELE NETTEMENT MEILLEUR que l'ouverture -> edge reel detecte"
        elif gap > 0.002:
            v = "modele legerement meilleur que l'ouverture -> base solide"
        elif gap > -0.010:
            v = "modele au niveau de l'ouverture -> correct, a affiner (xG, absences)"
        else:
            v = "modele en retrait -> features supplementaires necessaires"
        L(f"  VERDICT : {v}")
    return {"ll_model": ll(po), "ll_market": ll(m),
            "rps_model": np.mean([rps(po[i], r[i]) for i in range(n)]),
            "acc_model": float(np.mean(po.argmax(1) == r))}


if __name__ == "__main__":
    bt, models = run_backtest()
    bt.to_csv("backtest_results.csv", index=False)
    stats = evaluate(bt)
    # exemple concret de sortie du moteur
    L = print
    L("\n" + "=" * 80)
    L("EXEMPLE DE SORTIE DU MOTEUR (dernier modele entraine)")
    L("=" * 80)
    if models.get("E0"):
        mo = models["E0"]
        teams = mo["teams"]
        rank = sorted(teams, key=lambda t: -(mo["att"][mo["idx"][t]] /
                                             max(mo["dfn"][mo["idx"][t]], 1e-6)))
        L(f"\nAttaque la plus forte : {max(teams, key=lambda t: mo['att'][mo['idx'][t]])}"
          f"  ({mo['att'][mo['idx'][max(teams, key=lambda t: mo['att'][mo['idx'][t]])]]:.2f})")
        L(f"Defense la plus faible: {max(teams, key=lambda t: mo['dfn'][mo['idx'][t]])}"
          f"  ({mo['dfn'][mo['idx'][max(teams, key=lambda t: mo['dfn'][mo['idx'][t]])]]:.2f})")
        L(f"Avantage domicile     : x{mo['gamma']:.3f}")
        L(f"Correction Dixon-Coles: rho = {mo['rho']:+.3f}")
        big = max([(markets(score_matrix(mo, h, a))["fleuve"], h, a)
                   for h in rank[:6] for a in rank[-6:] if h != a])
        mk = markets(score_matrix(mo, big[1], big[2]))
        L(f"\nLe match le plus susceptible de produire un SCORE FLEUVE :")
        L(f"  {big[1]} vs {big[2]}")
        L(f"  P(5 buts ou plus) = {mk['fleuve']:.1%}")
        L(f"  P(ecart >= 3 buts) = {mk['eclat']:.1%}")
        L(f"  P(Over 2.5) = {mk['O2.5']:.1%}   P(Over 3.5) = {mk['O3.5']:.1%}")
        L(f"  Buts attendus = {mk['exp_goals']:.2f}")
        L(f"  Scores les plus probables : " +
          ", ".join(f"{s} ({p:.1%})" for s, p in mk["top_scores"]))
