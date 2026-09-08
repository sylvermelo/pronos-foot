"""
analyse_divisions.py — les divisions secondaires sont-elles aussi fiables ?
==========================================================================
Question utilisateur (07/09) : « les championnats ajoutés sont instables —
une fois dans le safe / les coupons / les conseils, nos résultats chutent. »

Protocole — walk-forward STRICT, identique à la production :
  · chaque saison évaluée S (2223 → 2526) est prédite par un modèle
    ré-entraîné UNIQUEMENT sur les saisons précédentes (fenêtre de 5,
    Dixon-Coles + shrink adaptatif 20 ; Big 5 : xG réels Understat recalés
    sur les buts ; lissage des forces d'équipes — SEUIL_CONF 15) ;
  · pour chaque match : le panier EXACT des « conseils du jour » (14 options,
    marges durcies sur les unders : +0,13 / +0,05 / +0,02) au seuil 0,75 ;
  · verdict via suivi.touche (le même code que le suivi live).

Aucune donnée postérieure au match prédit n'est jamais utilisée.

Usage :  python3 analyse_divisions.py          (~3-5 min, 21 divisions × 4 saisons)
Sortie : data/analyse_divisions.json + tableau console
"""
import datetime
import json
import os
import sys
import time

import numpy as np
from scipy.stats import poisson

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)
import moteur_v3 as V          # noqa: E402
import suivi                   # noqa: E402

MAXG = 10
SEUIL = 0.75
SEUIL_HAUT = 0.80
MARGES = {"under 3.5": 0.13, "under 2.5": 0.05, "under 1.5": 0.02}
SEUIL_CONF = 15.0
BIG5 = {"E0", "SP1", "I1", "D1", "F1"}
EVAL = ["2223", "2324", "2425", "2526"]


def entrainer(hist_fit, div):
    """Réplique exacte d'entraine.main pour une division/fenêtre donnée."""
    teams_fit = sorted(set(hist_fit["home"]) | set(hist_fit["away"]))
    mo = V.fit_goals(hist_fit, teams_fit, shrink=20.0)
    moteur = "Dixon-Coles"
    if div in BIG5 and "xgRH" in hist_fit.columns:
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
                    moteur = "xG réels recalés"
    # matchs effectifs (decay) + lissage géométrique — comme en production
    ref = hist_fit["date"].max()
    ww = np.exp(-V.XI_WEEK * (ref - hist_fit["date"]).dt.days.values / 7.0)
    nm = {t: 0.0 for t in teams_fit}
    for t, wv in zip(hist_fit["home"], ww):
        nm[t] = nm.get(t, 0.0) + wv
    for t, wv in zip(hist_fit["away"], ww):
        nm[t] = nm.get(t, 0.0) + wv
    forces = {}
    for t in teams_fit:
        if t not in mo["idx"]:
            continue
        i = mo["idx"][t]
        w = min(1.0, nm.get(t, 0.0) / SEUIL_CONF)
        forces[t] = (float(mo["att"][i]) ** w, float(mo["dfn"][i]) ** w)
    return mo, forces, moteur


def matrice(mo, forces, h, a):
    if h not in forces or a not in forces:
        return None
    att_h, dfn_h = forces[h]
    att_a, dfn_a = forces[a]
    lam = min(max(att_h * dfn_a * mo["gamma"], 1e-6), 30)
    mu = min(max(att_a * dfn_h * mo["s"], 1e-6), 30)
    rho = mo["rho"]
    k = np.arange(MAXG + 1)
    M = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
    M[0, 0] *= 1 - lam * mu * rho
    M[0, 1] *= 1 + lam * rho
    M[1, 0] *= 1 + mu * rho
    M[1, 1] *= 1 - rho
    M = np.clip(M, 0, None)
    s = M.sum()
    return M / s if s > 0 else None


def options_de(M):
    """Le panier exact d'api_conseils (14 options)."""
    g = np.add.outer(np.arange(MAXG + 1), np.arange(MAXG + 1))
    p1 = float(np.tril(M, -1).sum())
    pX = float(np.trace(M))
    p2 = float(np.triu(M, 1).sum())
    btts = float(M[1:, 1:].sum())
    o = {l: float(M[g > l].sum()) for l in (1.5, 2.5, 3.5)}
    u = {l: float(M[g < l].sum()) for l in (1.5, 2.5, 3.5)}
    return {
        "1": p1, "X": pX, "2": p2,
        "over 1.5": o[1.5], "over 2.5": o[2.5], "over 3.5": o[3.5],
        "under 1.5": u[1.5], "under 2.5": u[2.5], "under 3.5": u[3.5],
        "les deux marquent": btts, "les deux ne marquent pas": 1 - btts,
        "double chance 1X": p1 + pX, "double chance 12": p1 + p2,
        "double chance X2": pX + p2,
    }, (p1, pX, p2)


def main():
    import entraine
    t0 = time.time()
    df = entraine.charger()
    out = {"genere_le": datetime.datetime.now().isoformat(timespec="seconds"),
           "protocole": ("walk-forward strict : chaque saison S prédite par un modèle "
                         "ré-entraîné sur les 5 saisons < S (protocole production : "
                         "shrink 20, Big 5 xG recalés, lissage 15) ; panier exact des "
                         "conseils (14 options, marges unders) au seuil 0,75 ; verdict "
                         "suivi.touche"),
           "seuil": SEUIL, "marges": MARGES, "saisons_evaluees": EVAL,
           "divisions": {}}
    for div in sorted(df["league"].unique()):
        sub = (df[df["league"] == div]
               .sort_values(["date", "home", "away"], kind="mergesort"))
        saisons = sorted(sub["season"].unique())
        A = {"n": 0, "fav_ok": 0, "ll": 0.0,
             "n_sel": 0, "sel_ok": 0, "sel_p": 0.0,
             "n_sel80": 0, "sel80_ok": 0,
             "options": {}, "par_saison": {}}
        for S in EVAL:
            if S not in saisons:
                continue
            prec = [x for x in saisons if x < S][-5:]
            if len(prec) < 2:
                continue
            hist = sub[sub["season"].isin(prec)]
            if len(hist) < 300:
                continue
            try:
                mo, forces, moteur = entrainer(hist, div)
            except Exception as e:
                print(f"  {div} {S} : ÉCHEC entraînement ({e})")
                continue
            rec = sub[sub["season"] == S]
            SA = {"n": 0, "n_sel": 0, "sel_ok": 0}
            for _, m in rec.iterrows():
                M = matrice(mo, forces, m["home"], m["away"])
                if M is None:
                    continue
                opts, (p1, pX, p2) = options_de(M)
                bh, ba = int(m["hg"]), int(m["ag"])
                A["n"] += 1
                SA["n"] += 1
                # favori 1X2 + log-loss
                probs = (p1, pX, p2)
                A["fav_ok"] += int(max(range(3), key=lambda i: probs[i])
                                   == (0 if bh > ba else 1 if bh == ba else 2))
                p_real = probs[0 if bh > ba else 1 if bh == ba else 2]
                A["ll"] += -float(np.log(max(p_real, 1e-9)))
                # sélection « conseils du jour »
                opt, p = max(opts.items(), key=lambda z: z[1])
                if p >= SEUIL + MARGES.get(opt, 0.0) - 1e-9:
                    t = suivi.touche(opt, bh, ba)
                    if t is not None:
                        A["n_sel"] += 1
                        SA["n_sel"] += 1
                        A["sel_ok"] += int(t)
                        SA["sel_ok"] += int(t)
                        A["sel_p"] += p
                        O = A["options"].setdefault(
                            opt, {"n": 0, "ok": 0, "p": 0.0})
                        O["n"] += 1
                        O["ok"] += int(t)
                        O["p"] += p
                        if p >= SEUIL_HAUT + MARGES.get(opt, 0.0) - 1e-9:
                            A["n_sel80"] += 1
                            A["sel80_ok"] += int(t)
            if SA["n"]:
                A["par_saison"][S] = SA
        if A["n"] == 0:
            continue
        out["divisions"][div] = A
        hit = A["sel_ok"] / A["n_sel"] if A["n_sel"] else None
        print(f"  {div}: {A['n']} matchs — sélections {A['n_sel']} — "
              f"réussite {('%.1f %%' % (hit*100)) if hit is not None else 'n/a'} — "
              f"log-loss {A['ll']/A['n']:.4f}")

    # ---------- agrégats grands 5 vs secondaires ----------
    def agrege(divs):
        g = {"n": 0, "fav_ok": 0, "ll": 0.0, "n_sel": 0, "sel_ok": 0,
             "sel_p": 0.0, "n_sel80": 0, "sel80_ok": 0}
        for d in divs:
            A = out["divisions"].get(d)
            if not A:
                continue
            for k in g:
                g[k] += A[k]
        return g

    big = [d for d in BIG5 if d in out["divisions"]]
    sec = [d for d in out["divisions"] if d not in BIG5]
    groupes = {"big5": {"divisions": big, "agg": agrege(big)},
               "secondaires": {"divisions": sec, "agg": agrege(sec)}}
    out["groupes"] = groupes

    print("\n================ CONCLUSION ================")
    for nom, G in groupes.items():
        a = G["agg"]
        if not a["n_sel"]:
            continue
        hit = a["sel_ok"] / a["n_sel"]
        pmoy = a["sel_p"] / a["n_sel"]
        hit80 = (a["sel80_ok"] / a["n_sel80"]) if a["n_sel80"] else None
        print(f"{nom:>12} : {len(G['divisions'])} divisions · {a['n']} matchs · "
              f"{a['n_sel']} sélections ≥75 % · réussite {hit*100:.1f} % "
              f"(annoncé {pmoy*100:.1f} %, écart {(pmoy-hit)*100:+.1f} pts) · "
              f"≥80 % : {a['n_sel80']} sél., "
              f"{('%.1f %%' % (hit80*100)) if hit80 is not None else 'n/a'} · "
              f"fav 1X2 {a['fav_ok']/a['n']*100:.1f} % · "
              f"log-loss {a['ll']/a['n']:.4f}")

    # détail par division, trié par réussite
    rows = []
    for d, A in out["divisions"].items():
        if A["n_sel"] < 20:
            continue
        rows.append((d, A["n_sel"], A["sel_ok"] / A["n_sel"],
                     A["sel_p"] / A["n_sel"], A["ll"] / A["n"]))
    rows.sort(key=lambda r: -r[2])
    print("\n division | sél. | réussite | annoncé | log-loss")
    for d, n, hit, pm, ll in rows:
        marqueur = " (Big 5)" if d in BIG5 else ""
        print(f"   {d:<5} | {n:>4} | {hit*100:>6.1f} % | {pm*100:>5.1f} % | {ll:.4f}{marqueur}")

    chemin = os.path.join(RACINE, "data", "analyse_divisions.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"\nécrit : {chemin} ({time.time()-t0:.0f} s)")


if __name__ == "__main__":
    main()
