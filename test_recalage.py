"""
Test final: le recalibrage d'echelle.

Constat du backtest v3 (17 093 matchs, 11 ligues):
  - marche 1X2        : les BUTS seuls gagnent   (LL 0.9944 vs 1.0067)
  - marche Over/Under : le xG seul gagne         (LL 0.7335 vs 0.7575, Pinnacle 0.7527)
  MAIS le modele xG sous-estime le niveau absolu de -0.371 but/match.

Hypothese: il faut separer deux choses que le modele confond
  - la FORME  (repartition relative des forces) -> prise sur le xG, peu bruitee
  - le NIVEAU (echelle globale des buts)        -> prise sur les buts reels, non biaisee

Implementation: un facteur k calcule pour que la somme des lambda predits sur
l'historique egale la somme des buts reels observes. Aucun reentrainement.
"""
import warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import moteur_v3 as V

df = V.load()
sub = df[df["league"] == "E0"].sort_values("date").reset_index(drop=True)
sub = sub[sub["season"] >= "2223"]
print(f"Test sur Premier League, {len(sub)} matchs depuis 2022/23\n")


def recal(mo, hist, k_force=None):
    """Facteur k: aligne le niveau des lambda sur les buts reels observes."""
    h = hist.tail(400)
    lam_s = mu_s = 0.0
    buts = 0.0
    for _, m in h.iterrows():
        if m["home"] in mo["idx"] and m["away"] in mo["idx"]:
            lam_s += mo["att"][mo["idx"][m["home"]]] * mo["dfn"][mo["idx"][m["away"]]] * mo["gamma"]
            mu_s += mo["att"][mo["idx"][m["away"]]] * mo["dfn"][mo["idx"][m["home"]]] * mo["s"]
            buts += m["hg"] + m["ag"]
    if lam_s + mu_s <= 0:
        return mo, 1.0
    k = k_force if k_force else buts / (lam_s + mu_s)
    return {**mo, "gamma": mo["gamma"] * k, "s": mo["s"] * k}, k


def devig(*o):
    v = [float(x) for x in o if x is not None and np.isfinite(x) and x > 1.01]
    if len(v) != len(o) or len(v) < 2:
        return np.full(len(o), np.nan)
    i = np.array([1 / x for x in v]); return i / i.sum()


rows = []
weeks = sorted(sub["date"].dt.to_period("W").unique())
mg = mx = None
for k_i, wk in enumerate(weeks):
    cur = sub[sub["date"].dt.to_period("W") == wk]
    hist = sub[sub["date"] < wk.start_time]
    need = set(cur["home"]) | set(cur["away"])
    if mg is None or k_i % 6 == 0 or not need <= set(mg["idx"]):
        full = df[(df["league"] == "E0") & (df["date"] < wk.start_time)]
        if len(full) < 300:
            continue
        t = sorted(set(full["home"]) | set(full["away"]))
        mg = V.fit_goals(full, t); mx = V.fit_xg(full, t)
    if not cur["evaluable"].any():
        continue
    # FIX perf: le recalibrage est calcule UNE fois par semaine, pas par match
    past = sub[sub["date"] < wk.start_time]
    variants = {}
    for nm, w in (("buts_brut", 1.00), ("xG_brut", 0.00),
                  ("mix25_recale", 0.25)):
        variants[nm] = V.combine(mg, mx, w)
    rb, kb = recal(V.combine(mg, mx, 1.00), past); variants["buts_recale"] = rb
    rx, kx = recal(V.combine(mg, mx, 0.00), past); variants["xG_recale"] = rx
    r3, _ = recal(V.combine(mg, mx, 0.25), past); variants["mix25_recale"] = r3
    for _, m in cur.iterrows():
        if m["home"] not in mg["idx"] or m["away"] not in mg["idx"]:
            continue
        for name, mo in variants.items():
            Mt = V.score_matrix(mo, m["home"], m["away"])
            if Mt is None:
                continue
            d = V.derive(Mt)
            d.update({"v": name, "hg": m["hg"], "ag": m["ag"], "k": kx,
                      "oO": m.get("PC>2.5"), "oU": m.get("PC<2.5"),
                      "o1": m.get("PSCH"), "oX": m.get("PSCD"), "o2": m.get("PSCA"),
                      "aoO": m.get("Avg>2.5"), "aoU": m.get("Avg<2.5")})
            rows.append(d)

bt = pd.DataFrame(rows)
print(f"{'VARIANTE':<16}{'LL O/U2.5':>11}{'LL 1X2':>10}{'Buts pred':>11}{'Biais':>8}{'P(Over)':>9}{'Reel':>8}")
print("-" * 76)
res = {}
for v in ["buts_brut", "buts_recale", "mix25_recale", "xG_brut", "xG_recale"]:
    d = bt[bt["v"] == v]
    if not len(d):
        continue
    f = d.dropna(subset=["oO", "oU"])
    r2 = (f["hg"] + f["ag"] > 2.5).astype(int).values
    pm = np.array([devig(a, b) for a, b in zip(f["oO"], f["oU"])])
    po = np.concatenate([f[["pO25"]].values, f[["pU25"]].values], 1)
    ok = ~np.isnan(pm).any(1); pm, po, r2 = pm[ok], po[ok], r2[ok]
    ll2 = -np.mean(np.log(np.clip(po[np.arange(len(r2)), r2], 1e-9, 1)))
    ll2m = -np.mean(np.log(np.clip(pm[np.arange(len(r2)), r2], 1e-9, 1)))
    e = d.dropna(subset=["o1", "oX", "o2"])
    rr = np.where(e["hg"] > e["ag"], 0, np.where(e["hg"] == e["ag"], 1, 2))
    P = e[["p1", "pX", "p2"]].values; P = P / P.sum(1, keepdims=True)
    ll1 = -np.mean(np.log(np.clip(P[np.arange(len(rr)), rr], 1e-9, 1)))
    biais = d["exp"].mean() - (d["hg"] + d["ag"]).mean()
    res[v] = (ll2, ll1, biais, ll2m)
    print(f"{v:<16}{ll2:>11.4f}{ll1:>10.4f}{d['exp'].mean():>11.2f}{biais:>+8.3f}"
          f"{d['pO25'].mean():>9.1%}{(d['hg']+d['ag']>2.5).mean():>8.1%}")
print("-" * 76)
if res:
    ref = list(res.values())[0][3]
    print(f"\nReference PINNACLE cloture Over/Under : {ref:.4f}   (n={len(r2)} matchs)")
    print(f"\n{'VARIANTE':<16}{'ECART vs PINNACLE':>20}   verdict")
    for v, (ll2, ll1, b, _) in res.items():
        e = ll2 - ref
        print(f"{v:<16}{e:>+20.4f}   {'BAT le marche' if e < 0 else 'en retrait'}"
              f"{'  (biais corrige)' if abs(b) < 0.08 else f'  (biais {b:+.3f})'}")

print(f"\nFacteur de recalibrage k moyen : {bt[bt['v']=='xG_recale']['k'].mean():.4f}")
print("  (k > 1 signifie que le modele xG sous-estimait le niveau absolu des buts)")
