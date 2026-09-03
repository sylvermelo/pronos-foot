"""
Test A/B cible: valider l'hypothese du parametre d'echelle manquant.

Hypothese: dans la formulation classique  lam = att_h * def_a * gamma  /  mu = att_a * def_h,
la normalisation mean(att)=mean(def)=1 FORCE la moyenne des buts a l'exterieur a ~1.0,
alors que la realite est ~1.19. Il manque donc un multiplicateur global libre 's'.

  v_A (actuel):  lam = att_h*def_a*gamma      mu = att_a*def_h
  v_B (corrige): lam = s*att_h*def_a*gamma    mu = s*att_a*def_h

Test sur la Premier League uniquement, 3 saisons, pour aller vite.
"""
import warnings, numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

warnings.filterwarnings("ignore")
MAXG = 10
import moteur as M

df = M.load_all()
sub = df[df["league"] == "E0"].sort_values("date").reset_index(drop=True)
print(f"Premier League: {len(sub)} matchs, {sub['date'].min().date()} -> {sub['date'].max().date()}")


def fit(hist, teams, use_scale, xi=0.012, ridge=0.03):
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    ref = hist["date"].max()
    w = np.exp(-xi * (ref - hist["date"]).dt.days.values / 7.0)
    hi, aw = hist["home"].map(idx).values, hist["away"].map(idx).values
    x, y = hist["hg"].values.astype(int), hist["ag"].values.astype(int)
    np_ = 2 * n + 3 if use_scale else 2 * n + 2

    def neg_ll(p):
        att, dfn = np.exp(p[:n]), np.exp(p[n:2 * n])
        gam = np.exp(p[2 * n]); rho = np.tanh(p[2 * n + 1])
        s = np.exp(p[2 * n + 2]) if use_scale else 1.0
        lam = np.clip(s * att[hi] * dfn[aw] * gam, 1e-6, 30)
        mu = np.clip(s * att[aw] * dfn[hi], 1e-6, 30)
        ll = poisson.logpmf(x, lam) + poisson.logpmf(y, mu)
        tau = np.ones_like(ll)
        a = (x == 0) & (y == 0); b = (x == 0) & (y == 1)
        c = (x == 1) & (y == 0); d = (x == 1) & (y == 1)
        tau[a] = 1 - lam[a] * mu[a] * rho; tau[b] = 1 + lam[b] * rho
        tau[c] = 1 + mu[c] * rho;          tau[d] = 1 - rho
        pen = (np.mean(p[:n]) ** 2) * 30.0 + ridge * np.sum(p[:2 * n] ** 2)
        return -np.sum(w * (ll + np.log(np.clip(tau, 1e-9, None)))) + pen

    p0 = np.zeros(np_); p0[2 * n] = np.log(1.30)
    if use_scale: p0[2 * n + 2] = np.log(1.15)
    r = minimize(neg_ll, p0, method="L-BFGS-B", options={"maxiter": 300, "maxfun": 8000})
    p = r.x
    att, dfn = np.exp(p[:n]), np.exp(p[n:2 * n])
    ma, md = att.mean(), dfn.mean()
    s = float(np.exp(p[2 * n + 2])) if use_scale else 1.0
    return {"att": att / ma, "dfn": dfn / md, "idx": idx, "rho": float(np.tanh(p[2 * n + 1])),
            "gamma": float(np.exp(p[2 * n]) * ma * md * s), "scale_away": s}


def mat(mo, h, a):
    att, dfn, i = mo["att"], mo["dfn"], mo["idx"]
    lam = np.clip(att[i[h]] * dfn[i[a]] * mo["gamma"], 1e-6, 30)
    mu = np.clip(att[i[a]] * dfn[i[h]] * mo["scale_away"], 1e-6, 30)
    k = np.arange(MAXG + 1); rho = mo["rho"]
    Mt = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
    Mt[0, 0] *= max(1 - lam * mu * rho, 1e-9); Mt[0, 1] *= max(1 + lam * rho, 1e-9)
    Mt[1, 0] *= max(1 + mu * rho, 1e-9);       Mt[1, 1] *= max(1 - rho, 1e-9)
    return np.clip(Mt, 0, None) / max(np.clip(Mt, 0, None).sum(), 1e-12)


def devig(*o):
    v = [float(x) for x in o if x is not None and np.isfinite(x) and x > 1.01]
    if len(v) != len(o): return np.full(len(o), np.nan)
    i = np.array([1 / x for x in v]); return i / i.sum()


rows = []
weeks = sorted(sub["date"].dt.to_period("W").unique())
mA = mB = None
for k, wk in enumerate(weeks):
    cur = sub[sub["date"].dt.to_period("W") == wk]
    if not cur["evaluable"].any() or cur["season"].min() < "2324":
        if k % 5 == 0 or mA is None:
            hist = sub[sub["date"] < wk.start_time]
            if len(hist) >= 200:
                t = sorted(set(hist["home"]) | set(hist["away"]))
                mA, mB = fit(hist, t, False), fit(hist, t, True)
        continue
    if mA is None or k % 5 == 0:
        hist = sub[sub["date"] < wk.start_time]
        if len(hist) < 200: continue
        t = sorted(set(hist["home"]) | set(hist["away"]))
        mA, mB = fit(hist, t, False), fit(hist, t, True)
    # garde: forcer le reentrainement si une equipe promue manque a l'index
    hist = sub[sub["date"] < wk.start_time]
    need = set(cur["home"]) | set(cur["away"])
    if not need <= set(mA["idx"]) and len(hist) >= 200:
        t = sorted(set(hist["home"]) | set(hist["away"]))
        mA, mB = fit(hist, t, False), fit(hist, t, True)
    for _, m in cur.iterrows():
        if m["home"] not in mA["idx"] or m["away"] not in mA["idx"]: continue
        for tag, mo in (("A", mA), ("B", mB)):
            Mt = mat(mo, m["home"], m["away"])
            tri, dg = np.tril(Mt, -1).sum(), np.trace(Mt)
            g = np.add.outer(np.arange(MAXG + 1), np.arange(MAXG + 1))
            rows.append({"v": tag, "hg": m["hg"], "ag": m["ag"], "res": int(m["hg"] > m["ag"]) - int(m["hg"] < m["ag"]),
                         "p1": tri, "pX": dg, "p2": Mt.sum() - tri - dg,
                         "pO": Mt[g > 2.5].sum(), "exp": (Mt * g).sum(),
                         "o1": m.get("PSCH"), "oX": m.get("PSCD"), "o2": m.get("PSCA"),
                         "oO": m.get("PC>2.5"), "oU": m.get("PC<2.5")})

bt = pd.DataFrame(rows)
print(f"\nMatchs evalues par variante : {len(bt)//2}\n")
print(f"{'METRIQUE':<40}{'v_A (actuel)':>15}{'v_B (avec s)':>15}")
print("-" * 70)

out = {}
for v in ("A", "B"):
    d = bt[bt["v"] == v].dropna(subset=["o1", "oX", "o2"])
    res = np.where(d["hg"] > d["ag"], 0, np.where(d["hg"] == d["ag"], 1, 2))
    P = d[["p1", "pX", "p2"]].values; P = P / P.sum(1, keepdims=True)
    mk = np.array([devig(a, b, c) for a, b, c in zip(d["o1"], d["oX"], d["o2"])])
    ok = ~np.isnan(mk).any(1); mk, P, res = mk[ok], P[ok], res[ok]
    ll1 = -np.mean(np.log(np.clip(P[np.arange(len(res)), res], 1e-9, 1)))
    llm = -np.mean(np.log(np.clip(mk[np.arange(len(res)), res], 1e-9, 1)))
    d2 = bt[bt["v"] == v].dropna(subset=["oO", "oU"])
    r2 = (d2["hg"] + d2["ag"] > 2.5).astype(int).values
    pm = np.array([devig(a, b) for a, b in zip(d2["oO"], d2["oU"])])
    po = d2[["pO"]].values; po = np.concatenate([po, 1 - po], 1)
    ok2 = ~np.isnan(pm).any(1); pm, po, r2 = pm[ok2], po[ok2], r2[ok2]
    ll2 = -np.mean(np.log(np.clip(po[np.arange(len(r2)), r2], 1e-9, 1)))
    ll2m = -np.mean(np.log(np.clip(pm[np.arange(len(r2)), r2], 1e-9, 1)))
    out[v] = (ll1, llm, np.mean(P.argmax(1) == res), ll2, ll2m, d["exp"].mean(),
              (d["hg"] + d["ag"]).mean(), np.mean(r2 == 1) * 0 + r2.mean(), po[:, 0].mean())

lbl = ["Log-loss 1X2 (mini=mieux)", "   ...reference PINNACLE cloture", "Precision favori 1X2",
       "Log-loss Over/Under 2.5 (mini=mieux)", "   ...reference PINNACLE cloture",
       "Buts predits / match", "Buts reels / match", "Taux Over 2.5 reel", "Taux Over 2.5 predit"]
for i, l in enumerate(lbl):
    a, b = out["A"][i], out["B"][i]
    fa = f"{a:.4f}" if i in (0, 1, 3, 4) else (f"{a:.2f}" if i in (5, 6) else f"{a:.1%}")
    fb = f"{b:.4f}" if i in (0, 1, 3, 4) else (f"{b:.2f}" if i in (5, 6) else f"{b:.1%}")
    mark = ""
    if i in (0, 3): mark = "  << AMELIORE" if b < a else "  << degrade"
    print(f"{l:<40}{fa:>15}{fb:>15}{mark}")

print(f"\nBiais de buts corrige : {out['A'][5]-out['A'][6]:+.3f}  ->  {out['B'][5]-out['B'][6]:+.3f}")
print(f"Parametre s estime (dernier fit) : {mB['scale_away']:.3f}   gamma : {mB['gamma']/mB['scale_away']:.3f}")
print(f"Buts exterieur moyens : reel {sub[sub['season']>='2324']['ag'].mean():.2f} | "
      f"v_A force a ~1.00 | v_B {mB['scale_away']:.2f}")
