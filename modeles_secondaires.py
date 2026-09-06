"""
Modeles des marches secondaires : fautes, corners, cartons jaunes.

Justification mesuree (test_marches_secondaires.py, 34 708 matchs) :
  equipe -> fautes    r(A->B) = +0.729  p<0.0001
  equipe -> corners   r(A->B) = +0.668  p<0.0001
  equipe -> jaunes    r(A->B) = +0.619  p<0.0001
  arbitre -> fautes   r(A->B) = +0.502  p<0.0001
  arbitre -> jaunes   r(A->B) = +0.466  p<0.0001

Sur-dispersion mesuree (variance observee / variance de Poisson) :
  fautes 1.52 | corners 1.18 | jaunes 1.17 | rouges 1.07
-> loi binomiale negative pour les fautes, Poisson pour le reste.

Chaque marche est modelise par deux facteurs par equipe (emission / reception),
normalises a 1, pondérés par decay temporel, et lisses par Bayes empirique.
"""
import numpy as np
import pandas as pd

XI_WEEK = 0.012          # meme demi-vie que le modele de buts
K_EQUIPE = 12.0          # force du lissage par equipe (pseudo-matchs)
K_ARBITRE = 25.0         # lissage plus fort pour les arbitres (moins de matchs)
MARCHES = {
    "fautes":  {"col_dom": "HF", "col_ext": "AF", "arbitre": True,  "dispersion": 1.52},
    "corners": {"col_dom": "HC", "col_ext": "AC", "arbitre": False, "dispersion": 1.18},
    "jaunes":  {"col_dom": "HY", "col_ext": "AY", "arbitre": True,  "dispersion": 1.17},
}


def _poids(dates, ref):
    return np.exp(-XI_WEEK * (ref - dates).dt.days.values / 7.0)


def estimer(sub, teams, arbitres=True):
    """Estime les facteurs de chaque marche pour chaque equipe + les arbitres."""
    ref = sub["date"].max()
    w = _poids(sub["date"], ref)
    out = {"base": {}, "equipes": {t: {} for t in teams}, "arbitres": {}}
    has_ref = arbitres and "Referee" in sub.columns

    for mk, cfg in MARCHES.items():
        cd, ce = cfg["col_dom"], cfg["col_ext"]
        if cd not in sub.columns or ce not in sub.columns:
            continue
        dom = sub[cd].values.astype(float)
        ext = sub[ce].values.astype(float)
        # FIX 1 : filtrer les NaN (certaines divisions n'ont pas ces stats).
        # np.average propage le NaN et contaminait toute la base de reference.
        ok = np.isfinite(dom) & np.isfinite(ext) & np.isfinite(w)
        if ok.sum() < 30:
            continue
        dom, ext, w_m = dom[ok], ext[ok], w[ok]
        sub_m = sub[ok]
        base = float(np.average(np.concatenate([dom, ext]),
                                weights=np.concatenate([w_m, w_m])))
        if not np.isfinite(base) or base <= 0:
            continue
        out["base"][mk] = round(base, 3)
        out["base"][mk + "_dispersion"] = cfg["dispersion"]

        # facteurs par equipe : emission = ce qu'elle produit, reception = ce qu'elle laisse produire
        em = {t: [0.0, 0.0] for t in teams}      # [somme ponderee, poids]
        rc = {t: [0.0, 0.0] for t in teams}
        for h, a, dh, da, ww in zip(sub_m["home"], sub_m["away"], dom, ext, w_m):
            if h in em:
                em[h][0] += dh * ww; em[h][1] += ww
                rc[h][0] += da * ww; rc[h][1] += ww
            if a in em:
                em[a][0] += da * ww; em[a][1] += ww
                rc[a][0] += dh * ww; rc[a][1] += ww
        for t in teams:
            e = (em[t][0] + K_EQUIPE * base) / (em[t][1] + K_EQUIPE) / max(base, 1e-6)
            r = (rc[t][0] + K_EQUIPE * base) / (rc[t][1] + K_EQUIPE) / max(base, 1e-6)
            out["equipes"][t][mk + "_em"] = round(float(e), 4)
            out["equipes"][t][mk + "_rc"] = round(float(r), 4)
            out["equipes"][t]["n_eff"] = round(float(em[t][1]), 1)

    # ---- arbitres : multiplicateur de fautes et taux d'avertissement
    if has_ref:
        cols_ar = [c for c in ("HF", "AF", "HY", "AY") if c in sub.columns]
        ar = sub.dropna(subset=["Referee"] + cols_ar) if cols_ar else sub.dropna(subset=["Referee"])
        ar = ar[ar["Referee"].astype(str).str.len() > 1]
        if len(ar):
            wa = _poids(ar["date"], ref)
            fa = _poids(ar["date"], ref)
            base_f = float(np.average(ar["HF"] + ar["AF"], weights=fa)) if "HF" in ar else 0.0
            base_j = float(np.average(ar["HY"] + ar["AY"], weights=fa)) if "HY" in ar else 0.0
            if not np.isfinite(base_f): base_f = 0.0
            if not np.isfinite(base_j): base_j = 0.0
            base_t = (base_j / base_f) if base_f else 0
            acc = {}
            for nm, ft, jy, ww in zip(ar["Referee"], (ar["HF"] + ar["AF"]).values,
                                      (ar["HY"] + ar["AY"]).values, wa):
                d = acc.setdefault(nm, [0.0, 0.0, 0.0, 0.0, 0])
                d[0] += ft * ww; d[1] += jy * ww; d[2] += ww; d[3] += ww; d[4] += 1
            for nm, (sf, sj, wf, wj, n) in acc.items():
                f = (sf + K_ARBITRE * base_f) / (wf + K_ARBITRE) / max(base_f, 1e-6)
                j = (sj + K_ARBITRE * base_j) / (wj + K_ARBITRE) / max(base_j, 1e-6)
                out["arbitres"][nm] = {"fautes": round(float(f), 4),
                                       "jaunes": round(float(j), 4),
                                       "taux_avert": round(float(sj / max(sf, 1e-9)), 4),
                                       "n": int(n)}
    return out


def nbinom_pmf(k, lam, disp):
    """Binomiale negative parametree par la moyenne et la sur-dispersion."""
    if disp <= 1.0001:
        return _pois(k, lam)
    r = lam / (disp - 1.0)
    p = r / (r + lam)
    from scipy.stats import nbinom
    return nbinom.pmf(k, r, p)


def _pois(k, lam):
    from scipy.stats import poisson
    return poisson.pmf(k, lam)


def pmf_marche(lam, disp, kmax=60):
    k = np.arange(kmax + 1)
    p = nbinom_pmf(k, lam, disp)
    return k, p / max(p.sum(), 1e-12)


def pronostiquer(modele, home, away, arbitre=None):
    """Probabilites Over/Under pour fautes, corners, jaunes d'un match donne."""
    if not modele:
        return None
    E = modele.get("equipes", {})
    if home not in E or away not in E:
        return None
    A = modele.get("arbitres", {}).get(arbitre) if arbitre else None
    res = {"arbitre": arbitre, "arbitre_couvert": A is not None,
           "arbitre_info": A, "marches": {}}
    for mk, cfg in MARCHES.items():
        if mk not in modele.get("base", {}):
            continue
        base = modele["base"][mk]; disp = modele["base"][mk + "_dispersion"]
        demi = base            # FIX 2 : base est deja une moyenne PAR EQUIPE
        mult = 1.0
        if cfg["arbitre"] and A:
            mult = A["fautes"] if mk == "fautes" else A["jaunes"]
        lam_h = demi * E[home][mk + "_em"] * E[away][mk + "_rc"] * mult
        lam_a = demi * E[away][mk + "_em"] * E[home][mk + "_rc"] * mult
        lam_h = max(min(lam_h, 60), 0.05); lam_a = max(min(lam_a, 60), 0.05)
        k, ph = pmf_marche(lam_h, disp)
        _, pa = pmf_marche(lam_a, disp)
        # convolution -> distribution du total
        tot = np.convolve(ph, pa)[:61]
        tot = tot / max(tot.sum(), 1e-12)
        kk = np.arange(len(tot))
        seuils = {"fautes": [19.5, 21.5, 23.5, 25.5, 27.5],
                  "corners": [7.5, 8.5, 9.5, 10.5, 11.5],
                  "jaunes": [1.5, 2.5, 3.5, 4.5, 5.5]}[mk]
        res["marches"][mk] = {
            "lambda_home": round(float(lam_h), 2),
            "lambda_away": round(float(lam_a), 2),
            "total_attendu": round(float(lam_h + lam_a), 2),
            "dispersion": disp,
            "over": {str(s): round(float(tot[kk > s].sum()), 4) for s in seuils},
            "under": {str(s): round(float(tot[kk < s].sum()), 4) for s in seuils},
            "plus_probable": int(kk[np.argmax(tot)]),
        }
    return res


def confrontation(modele, home, away):
    """CONFRONTATION CORNERS : qui prend le pas sur qui ?

    D = corners(home) − corners(away), obtenu par convolution des deux lois
    binomiales négatives de pronostiquer (dispersion mesurée 1.18,
    indépendance supposée — même approximation que la production).

    Retourne les probabilités BRUTES du modèle pour l'échelle d'handicaps
    relative à la DOMINANTE attendue (plus gros λ corners) :
        « +2 »      : D_dom ≥ −1  (la dominante peut perdre de 1 corner)
        « +1 »      : D_dom ≥ 0   (victoire ou nul aux corners)
        « victoire »: D_dom ≥ 1
        « −1 »      : D_dom ≥ 2   … jusqu'à « −4 » : D_dom ≥ 5
    La calibration de production (fréquences réelles walk-forward) est
    appliquée ailleurs (corners.py) — jamais ici.
    """
    if not modele:
        return None
    E = modele.get("equipes", {})
    if home not in E or away not in E:
        return None
    if "corners" not in modele.get("base", {}):
        return None
    eh, rh = E[home].get("corners_em"), E[home].get("corners_rc")
    ea, ra = E[away].get("corners_em"), E[away].get("corners_rc")
    if not all(isinstance(v, (int, float)) and np.isfinite(v)
               for v in (eh, rh, ea, ra)):
        return None
    base = modele["base"]["corners"]
    disp = modele["base"].get("corners_dispersion", 1.18)
    lam_h = max(min(base * eh * ra, 60), 0.05)
    lam_a = max(min(base * ea * rh, 60), 0.05)

    KMAX = 40
    ph = np.asarray(pmf_marche(lam_h, disp, kmax=KMAX)[1], dtype=float)
    pa = np.asarray(pmf_marche(lam_a, disp, kmax=KMAX)[1], dtype=float)
    M = np.outer(ph, pa)
    idx = (np.arange(KMAX + 1)[:, None] - np.arange(KMAX + 1)[None, :]).ravel() + KMAX
    dist = np.bincount(idx, weights=M.ravel(), minlength=2 * KMAX + 1)

    dom_home = lam_h >= lam_a
    lam_d, lam_f = (lam_h, lam_a) if dom_home else (lam_a, lam_h)

    def queue(t):
        """P(D_dom ≥ t)."""
        if dom_home:
            return float(dist[KMAX + t:].sum())
        return float(dist[:KMAX - t + 1].sum())

    p_nul = float(dist[KMAX])
    p_vict_dom = queue(1)
    echelle = {"+2": queue(-1), "+1": queue(0), "victoire": p_vict_dom,
               "-1": queue(2), "-2": queue(3), "-3": queue(4), "-4": queue(5)}
    return {
        "lambda_home": round(float(lam_h), 2),
        "lambda_away": round(float(lam_a), 2),
        "dom": "home" if dom_home else "away",
        "partage_dom": round(float(lam_d / max(lam_d + lam_f, 1e-9)), 4),
        "p_vict_dom": round(p_vict_dom, 4),
        "p_nul": round(p_nul, 4),
        "p_vict_autre": round(max(0.0, 1.0 - p_vict_dom - p_nul), 4),
        "echelle": {k: round(min(max(v, 0.0), 1.0), 4) for k, v in echelle.items()},
    }
