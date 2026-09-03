"""
MOTEUR v3 - version corrigee et amelioree

Ameliorations par rapport a la v2:
  1. FIX  parametre d'echelle global 's' (valide en A/B: -35% d'ecart avec Pinnacle)
  2. FIX  cotes nulles/invalides filtrees (elles polluaient le log-loss Over/Under)
  3. NEW  second signal: force d'equipe estimee sur le proxy xG (tirs cadres)
          combinee par moyenne geometrique avec la force estimee sur les buts
  4. NEW  multiplicateur de niveau de buts par ligue x saison
  5. NEW  backtest multi-poids: 5 variantes evaluees pour UN seul entrainement

Les modeles "buts" et "xG" sont independants du poids w, donc on entraine une
fois et on derive les 5 variantes gratuitement.
"""
import os, json, warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

warnings.filterwarnings("ignore")
MAXG = 10
POIDS = [1.00, 0.75, 0.50, 0.25, 0.00]     # 1.00 = buts seuls, 0.00 = xG seul
XI_WEEK = 0.012                              # demi-vie ~58 semaines
RIDGE = 0.03
BACKTEST_FROM = "2122"

LIGUES = {"E0": "Premier League", "SP1": "La Liga", "I1": "Serie A",
          "D1": "Bundesliga", "F1": "Ligue 1", "N1": "Eredivisie",
          "B1": "Jupiler Pro", "P1": "Liga Portugal", "T1": "Super Lig",
          "G1": "Super League Grece", "E1": "Championship"}
ALL_SEASONS = ["1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526"]

COLS_ODDS = ["PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA",
             "P>2.5", "P<2.5", "PC>2.5", "PC<2.5", "Avg>2.5", "Avg<2.5"]


def load():
    coef = json.load(open("data/coef_xg.json"))
    frames = []
    for s in ALL_SEASONS:
        for d in LIGUES:
            f = f"data/{s}_{d}.csv"
            if os.path.exists(f):
                x = pd.read_csv(f, encoding="latin-1")
                x["league"] = d; x["season"] = s
                frames.append(x)
    raw = pd.concat(frames, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["Date"], format="mixed", dayfirst=True, errors="coerce")
    raw = raw.dropna(subset=["date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    raw = raw.rename(columns={"HomeTeam": "home", "AwayTeam": "away",
                              "FTHG": "hg", "FTAG": "ag"})
    num = ["hg", "ag", "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC",
           "HY", "AY"] + COLS_ODDS
    for c in num:
        if c in raw.columns:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
    # FIX n.2 : toute cote <= 1.01 est invalide (0, vide, absurdite) -> NaN
    for c in COLS_ODDS:
        if c in raw.columns:
            raw.loc[raw[c] <= 1.01, c] = np.nan
    raw = raw.dropna(subset=["hg", "ag"])
    raw["hg"] = raw["hg"].astype(int).clip(0, MAXG)
    raw["ag"] = raw["ag"].astype(int).clip(0, MAXG)
    # proxy xG (coefficients ajustes sur nos propres donnees)
    ch, nh, ih = coef["domicile"]; ca, na, ia = coef["exterieur"]
    if {"HST", "AST", "HS", "AS"} <= set(raw.columns):
        ok = raw[["HS", "AS", "HST", "AST"]].notna().all(1)
        raw["xgH"] = np.nan; raw["xgA"] = np.nan
        raw.loc[ok, "xgH"] = (ch * raw.loc[ok, "HST"] + nh * (raw.loc[ok, "HS"] - raw.loc[ok, "HST"]) + ih).clip(0.05, 6)
        raw.loc[ok, "xgA"] = (ca * raw.loc[ok, "AST"] + na * (raw.loc[ok, "AS"] - raw.loc[ok, "AST"]) + ia).clip(0.05, 6)
    else:
        raw["xgH"] = np.nan; raw["xgA"] = np.nan
    raw["evaluable"] = raw["season"] >= BACKTEST_FROM
    return raw.sort_values("date").reset_index(drop=True)


# --------------------------------------------------------- modele 1 : les buts
def fit_goals(hist, teams, shrink=0.0):
    """
    Dixon-Coles complet sur les buts reels, avec parametre d'echelle s.

    shrink > 0 active la regularisation ADAPTATIVE : la penalite d'une equipe est
    multipliee par (1 + shrink / n_matchs). Sans cela, une equipe promue avec 2 matchs
    obtient des parametres extremes (observe: Hull classe n.1 de Premier League avec
    une defense a 0.080 apres 2 matchs). shrink=0 preserve le comportement du backtest.
    """
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    ref = hist["date"].max()
    w = np.exp(-XI_WEEK * (ref - hist["date"]).dt.days.values / 7.0)
    hi, aw = hist["home"].map(idx).values, hist["away"].map(idx).values
    x, y = hist["hg"].values.astype(int), hist["ag"].values.astype(int)

    # nombre de matchs EFFECTIFS (ponderes par le decay) par equipe
    neff = np.zeros(n)
    np.add.at(neff, hi, w); np.add.at(neff, aw, w)
    neff = np.maximum(neff, 0.5)
    rg = RIDGE * (1.0 + shrink / neff) if shrink > 0 else np.full(n, RIDGE)

    def neg_ll(p):
        att, dfn = np.exp(p[:n]), np.exp(p[n:2 * n])
        gam = np.exp(p[2 * n]); rho = np.tanh(p[2 * n + 1]); s = np.exp(p[2 * n + 2])
        lam = np.clip(s * att[hi] * dfn[aw] * gam, 1e-6, 30)
        mu = np.clip(s * att[aw] * dfn[hi], 1e-6, 30)
        ll = poisson.logpmf(x, lam) + poisson.logpmf(y, mu)
        tau = np.ones_like(ll)
        a = (x == 0) & (y == 0); b = (x == 0) & (y == 1)
        c = (x == 1) & (y == 0); d = (x == 1) & (y == 1)
        tau[a] = 1 - lam[a] * mu[a] * rho; tau[b] = 1 + lam[b] * rho
        tau[c] = 1 + mu[c] * rho;          tau[d] = 1 - rho
        pen = (np.mean(p[:n]) ** 2) * 30.0 + float(np.sum(rg * p[:n] ** 2) +
                                                   np.sum(rg * p[n:2 * n] ** 2))
        return -np.sum(w * (ll + np.log(np.clip(tau, 1e-9, None)))) + pen

    p0 = np.zeros(2 * n + 3); p0[2 * n] = np.log(1.30); p0[2 * n + 2] = np.log(1.15)
    r = minimize(neg_ll, p0, method="L-BFGS-B", options={"maxiter": 250, "maxfun": 6000})
    p = r.x
    att, dfn = np.exp(p[:n]), np.exp(p[n:2 * n])
    ma, md = att.mean(), dfn.mean()
    s = float(np.exp(p[2 * n + 2]))
    return {"att": att / ma, "dfn": dfn / md, "idx": idx,
            "gamma": float(np.exp(p[2 * n]) * ma * md * s), "s": s,
            "rho": float(np.tanh(p[2 * n + 1]))}


# ------------------------------------------------------- modele 2 : le proxy xG
def fit_xg(hist, teams):
    """
    Force d'equipe estimee sur les xG proxy, par moindres carres ponderes en log.
      log(xgH) = log(att_h) + log(def_a) + log(gamma_h)
      log(xgA) = log(att_a) + log(def_h) + log(gamma_a)
    Lineaire -> rapide et stable, aucune optimisation non lineaire.
    """
    h = hist.dropna(subset=["xgH", "xgA"])
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    if len(h) < 60:
        return None
    ref = hist["date"].max()
    w = np.exp(-XI_WEEK * (ref - h["date"]).dt.days.values / 7.0)
    hi, aw = h["home"].map(idx).values, h["away"].map(idx).values
    if np.isnan(hi).any() or np.isnan(aw).any():
        return None
    # inconnues: a[0..n-1], d[0..n-1], gh, ga   (2n+2)
    m = len(h)
    A = np.zeros((2 * m, 2 * n + 2)); b = np.zeros(2 * m); ww = np.zeros(2 * m)
    A[np.arange(m), hi] = 1; A[np.arange(m), n + aw] = 1; A[np.arange(m), 2 * n] = 1
    b[:m] = np.log(h["xgH"].values)
    A[m + np.arange(m), aw] = 1; A[m + np.arange(m), n + hi] = 1; A[m + np.arange(m), 2 * n + 1] = 1
    b[m:] = np.log(h["xgA"].values)
    ww[:m] = w; ww[m:] = w
    sw = np.sqrt(ww)
    Aa = A * sw[:, None]; bb = b * sw
    # regularisation: forces tirees vers 0 (log) + identifiabilite moyenne(att)=1
    reg = np.zeros((n + 1, 2 * n + 2))
    for i in range(n):
        reg[i, i] = np.sqrt(RIDGE * 40)
        reg[i, n + i] = np.sqrt(RIDGE * 40)
    reg[n, :n] = np.sqrt(400.0) / n
    Aa = np.vstack([Aa, reg]); bb = np.concatenate([bb, np.zeros(n + 1)])
    sol, *_ = np.linalg.lstsq(Aa, bb, rcond=None)
    att = np.exp(sol[:n]); dfn = np.exp(sol[n:2 * n])
    ma, md = att.mean(), dfn.mean()
    gh, ga = float(np.exp(sol[2 * n]) * ma * md), float(np.exp(sol[2 * n + 1]) * ma * md)
    return {"att": att / ma, "dfn": dfn / md, "idx": idx, "gh": gh, "ga": ga}


# ------------------------------------------------------------- combinaison
def combine(mg, mx, w, n_teams_hint=None):
    """
    Moyenne geometrique des forces -> preserve l'echelle multiplicative.
      att = att_buts^w * att_xg^(1-w)
    Les niveaux globaux (gamma) sont combines de la meme maniere.
    """
    if mx is None or w >= 0.999:
        return {"att": mg["att"], "dfn": mg["dfn"], "gamma": mg["gamma"],
                "s": mg["s"], "rho": mg["rho"], "idx": mg["idx"]}
    if w <= 0.001:
        # xG seul: on garde rho du modele buts (non estimable en moindres carres)
        return {"att": mx["att"], "dfn": mx["dfn"], "gamma": mx["gh"],
                "s": mx["ga"], "rho": mg["rho"], "idx": mg["idx"], "xg_only": True}
    att = np.exp(w * np.log(np.clip(mg["att"], 1e-3, None)) + (1 - w) * np.log(np.clip(mx["att"], 1e-3, None)))
    dfn = np.exp(w * np.log(np.clip(mg["dfn"], 1e-3, None)) + (1 - w) * np.log(np.clip(mx["dfn"], 1e-3, None)))
    att /= att.mean(); dfn /= dfn.mean()
    gam = mg["gamma"] ** w * mx["gh"] ** (1 - w)
    s = mg["s"] ** w * mx["ga"] ** (1 - w)
    return {"att": att, "dfn": dfn, "gamma": gam * s, "s": s, "rho": mg["rho"],
            "idx": mg["idx"]}


def score_matrix(mo, home, away):
    att, dfn, i = mo["att"], mo["dfn"], mo["idx"]
    if home not in i or away not in i:
        return None
    lam = np.clip(att[i[home]] * dfn[i[away]] * mo["gamma"], 1e-6, 30)
    mu = np.clip(att[i[away]] * dfn[i[home]] * mo["s"], 1e-6, 30)
    rho = mo["rho"]; k = np.arange(MAXG + 1)
    Mt = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
    Mt[0, 0] *= max(1 - lam * mu * rho, 1e-9); Mt[0, 1] *= max(1 + lam * rho, 1e-9)
    Mt[1, 0] *= max(1 + mu * rho, 1e-9);       Mt[1, 1] *= max(1 - rho, 1e-9)
    return np.clip(Mt, 0, None) / max(np.clip(Mt, 0, None).sum(), 1e-12)


def derive(M):
    tri = np.tril(M, -1).sum(); dg = np.trace(M)
    g = np.add.outer(np.arange(MAXG + 1), np.arange(MAXG + 1))
    d = np.abs(np.subtract.outer(np.arange(MAXG + 1), np.arange(MAXG + 1)))
    return {"p1": float(tri), "pX": float(dg), "p2": float(M.sum() - tri - dg),
            "pO25": float(M[g > 2.5].sum()), "pU25": float(M[g < 2.5].sum()),
            "pO35": float(M[g > 3.5].sum()), "pO15": float(M[g > 1.5].sum()),
            "pBTTS": float(M[1:, 1:].sum()), "pFleuve": float(M[g >= 5].sum()),
            "pEclat": float(M[d >= 3].sum()), "exp": float((M * g).sum())}


def devig(*o):
    v = [float(x) for x in o if x is not None and np.isfinite(x) and x > 1.01]
    if len(v) != len(o) or len(v) < 2:
        return np.full(len(o), np.nan)
    i = np.array([1 / x for x in v]); return i / i.sum()


def run(refit=4, min_hist=200):
    df = load()
    print(f"Base : {len(df)} matchs | {df['league'].nunique()} ligues | "
          f"{df['season'].nunique()} saisons | {df['xgH'].notna().sum()} avec xG proxy")
    print(f"Periode : {df['date'].min().date()} -> {df['date'].max().date()}\n")
    rows = []
    for lg, nom in LIGUES.items():
        sub = df[df["league"] == lg].sort_values("date").reset_index(drop=True)
        if len(sub) < 400:
            continue
        weeks = sorted(sub["date"].dt.to_period("W").unique())
        mg = mx = None; nfit = 0
        for k, wk in enumerate(weeks):
            cur = sub[sub["date"].dt.to_period("W") == wk]
            hist = sub[sub["date"] < wk.start_time]
            if mg is None or k % refit == 0 or not (set(cur["home"]) | set(cur["away"])) <= set(mg["idx"]):
                if len(hist) < min_hist:
                    continue
                t = sorted(set(hist["home"]) | set(hist["away"]))
                try:
                    mg = fit_goals(hist, t); mx = fit_xg(hist, t); nfit += 1
                except Exception:
                    continue
            if not cur["evaluable"].any() or mg is None:
                continue
            for _, m in cur.iterrows():
                base = {"league": nom, "date": m["date"], "home": m["home"], "away": m["away"],
                        "hg": m["hg"], "ag": m["ag"],
                        "o1": m.get("PSCH"), "oX": m.get("PSCD"), "o2": m.get("PSCA"),
                        "oO": m.get("PC>2.5"), "oU": m.get("PC<2.5"),
                        "oo1": m.get("PSH"), "ooX": m.get("PSD"), "oo2": m.get("PSA"),
                        "aoO": m.get("Avg>2.5"), "aoU": m.get("Avg<2.5")}
                for w in POIDS:
                    mo = combine(mg, mx, w)
                    Mt = score_matrix(mo, m["home"], m["away"])
                    if Mt is None:
                        continue
                    r = dict(base); r["w"] = w; r.update(derive(Mt)); rows.append(r)
        print(f"  {nom:<22} {nfit:>4} entrainements doubles")
    return pd.DataFrame(rows)


def evaluate(bt):
    print("\n" + "=" * 92)
    print("COMPARAISON DES POIDS  buts / xG   (walk-forward strict, aucune donnee future)")
    print("=" * 92)
    hdr = (f"{'POIDS buts':<12}{'LogLoss 1X2':>13}{'RPS':>9}{'Prec.fav':>10}"
           f"{'LL O/U2.5':>11}{'Buts pred':>11}{'Biais':>8}")
    print(hdr); print("-" * 92)
    best = None
    for w in POIDS:
        d = bt[bt["w"] == w]
        # --- 1X2
        e = d.dropna(subset=["o1", "oX", "o2"])
        res = np.where(e["hg"] > e["ag"], 0, np.where(e["hg"] == e["ag"], 1, 2))
        P = e[["p1", "pX", "p2"]].values; P = P / P.sum(1, keepdims=True)
        mk = np.array([devig(a, b, c) for a, b, c in zip(e["o1"], e["oX"], e["o2"])])
        ok = ~np.isnan(mk).any(1); mk, P, res = mk[ok], P[ok], res[ok]
        if len(res) < 200:
            continue
        n = len(res)
        ll1 = -np.mean(np.log(np.clip(P[np.arange(n), res], 1e-9, 1)))
        llm = -np.mean(np.log(np.clip(mk[np.arange(n), res], 1e-9, 1)))
        rpsv = np.mean([np.mean((np.cumsum(P[i]) - np.cumsum(np.eye(3)[res[i]])) ** 2)
                        for i in range(n)])
        acc = np.mean(P.argmax(1) == res)
        # --- Over/Under 2.5
        f = d.dropna(subset=["oO", "oU"])
        r2 = (f["hg"] + f["ag"] > 2.5).astype(int).values
        pm = np.array([devig(a, b) for a, b in zip(f["oO"], f["oU"])])
        po = np.concatenate([f[["pO25"]].values, f[["pU25"]].values], 1)
        ok2 = ~np.isnan(pm).any(1); pm, po, r2 = pm[ok2], po[ok2], r2[ok2]
        ll2 = -np.mean(np.log(np.clip(po[np.arange(len(r2)), r2], 1e-9, 1))) if len(r2) else np.nan
        ll2m = -np.mean(np.log(np.clip(pm[np.arange(len(r2)), r2], 1e-9, 1))) if len(r2) else np.nan
        biais = d["exp"].mean() - (d["hg"] + d["ag"]).mean()
        tag = f"{w:.2f}" + (" (buts seuls)" if w == 1 else " (xG seul)" if w == 0 else "")
        print(f"{tag:<12}{ll1:>13.4f}{rpsv:>9.4f}{acc:>9.1%}{ll2:>11.4f}"
              f"{d['exp'].mean():>11.2f}{biais:>+8.3f}")
        if best is None or ll1 < best[1]:
            best = (w, ll1, rpsv, acc, ll2, llm, ll2m, n, len(r2), biais)
    print("-" * 92)
    w, ll1, rpsv, acc, ll2, llm, ll2m, n, n2, biais = best
    print(f"\nMEILLEURE CONFIGURATION : poids buts = {w:.2f}")
    print(f"  1X2          log-loss modele {ll1:.4f}  vs  PINNACLE {llm:.4f}   ecart {ll1-llm:+.4f}")
    print(f"  Over/Under   log-loss modele {ll2:.4f}  vs  PINNACLE {ll2m:.4f}   ecart {ll2-ll2m:+.4f}")
    print(f"  Precision favori {acc:.1%}   |   RPS {rpsv:.4f}   |   biais de buts {biais:+.3f}")
    print(f"  Echantillon : {n} matchs 1X2, {n2} matchs Over/Under")

    # --- calibration de la meilleure config
    d = bt[bt["w"] == w]
    e = d.dropna(subset=["o1", "oX", "o2"])
    L = pd.DataFrame({"p": np.concatenate([e["p1"], e["pX"], e["p2"]]),
                      "y": np.concatenate([(e["hg"] > e["ag"]).astype(int),
                                           (e["hg"] == e["ag"]).astype(int),
                                           (e["hg"] < e["ag"]).astype(int)])})
    print(f"\nCALIBRATION (poids {w:.2f})")
    print(f"{'Predite':<18}{'N':>8}{'Reel':>10}{'Ecart':>10}")
    for a, b in [(0, .15), (.15, .30), (.30, .45), (.45, .60), (.60, 1.01)]:
        s = L[(L["p"] >= a) & (L["p"] < b)]
        if len(s) > 30:
            print(f"{a:>5.0%} - {min(b,1):<5.0%}{'':<5}{len(s):>8}{s['y'].mean():>9.1%}"
                  f"{s['y'].mean()-s['p'].mean():>+10.1%}")

    # --- CLV + ROI de la meilleure config
    g = e.dropna(subset=["oo1", "ooX", "oo2"])
    r3 = np.where(g["hg"] > g["ag"], 0, np.where(g["hg"] == g["ag"], 1, 2))
    P3 = g[["p1", "pX", "p2"]].values; P3 = P3 / P3.sum(1, keepdims=True)
    op = np.array([devig(a, b, c) for a, b, c in zip(g["oo1"], g["ooX"], g["oo2"])])
    ok3 = ~np.isnan(op).any(1); op, P3, r3 = op[ok3], P3[ok3], r3[ok3]
    if len(r3) > 200:
        f2 = lambda pr: -np.mean(np.log(np.clip(pr[np.arange(len(r3)), r3], 1e-9, 1)))
        print(f"\nCLOSING LINE VALUE (poids {w:.2f})")
        print(f"  Log-loss modele          : {f2(P3):.4f}")
        print(f"  Log-loss cote OUVERTURE  : {f2(op):.4f}")
        print(f"  Ecart vs ouverture       : {f2(op)-f2(P3):+.4f}  "
              f"({'positif = le modele ajoute de l info' if f2(op)>f2(P3) else 'negatif'})")
    print(f"\nROI vs cote de CLOTURE Pinnacle (mise a plat)")
    for edge in (0.02, 0.05, 0.08):
        st = pnl = nb = wn = 0
        res = np.where(e["hg"] > e["ag"], 0, np.where(e["hg"] == e["ag"], 1, 2))
        P = e[["p1", "pX", "p2"]].values; P = P / P.sum(1, keepdims=True)
        for i in range(len(e)):
            for j, o in enumerate([e["o1"].iloc[i], e["oX"].iloc[i], e["o2"].iloc[i]]):
                if not (o and np.isfinite(o) and o > 1.01):
                    continue
                if P[i, j] > (1 / o) * (1 + edge):
                    nb += 1; st += 1
                    if res[i] == j:
                        pnl += o - 1; wn += 1
                    else:
                        pnl -= 1
        if nb:
            print(f"  edge {edge:>4.0%} : {nb:>5} paris | reussite {wn/nb:>5.1%} | "
                  f"ROI {pnl/st:>+7.2%} | P/L {pnl:>+8.1f} u")
    return best


if __name__ == "__main__":
    bt = run()
    bt.to_csv("backtest_v3.csv", index=False)
    evaluate(bt)
