"""SÉRIES DE BUTS D'AFFILÉE — probabilités exactes (source unique).

Une « série de k buts d'affilée » = k buts consécutifs de la même équipe dans
le match, sans but adverse entre-temps. Spéc et mesures : docs/SPEC-BUTS-AFFILEE.md.

Modèle : fusion de deux processus de Poisson indépendants (λ domicile,
μ extérieur). Le nombre total de buts suit Poisson(λ+μ) et chaque but est
marqué par l'équipe à domicile avec probabilité p = λ/(λ+μ), indépendamment
des autres. P(série ≥ k) en découle EXACTEMENT — aucune simulation, aucun
coefficient ajusté. Validé le 10/09/2026 sur 1 751 matchs réels des 5 grands
championnats (saison 2025-26, buts minutés ESPN) : 57,0 % mesuré vs 56,4 %
théorique en agrégé, aucun effet « momentum » détecté (écart +0,5 pt, bruit
±0,9 pt) → l'hypothèse sans mémoire est cohérente avec le réel.

IMPLÉMENTATION DÉTERMINISTE : le miroir JavaScript (genere_app.py) exécute
exactement les mêmes opérations dans le même ordre — parité obligatoire
(REGLES §5). Ne pas « optimiser » ce module sans mettre à jour le miroir.
"""
import math


def p_no_run(N, p, k):
    """P(aucune série ≥ k en N buts) — chaque but « home » avec proba p.

    Programmation dynamique sur (dernière équipe 0/1, longueur du run 1..k−1).
    """
    if N == 0:
        return 1.0
    q = 1.0 - p
    dp = [[0.0] * k for _ in range(2)]
    dp[1][1] = p
    dp[0][1] = q
    for _ in range(1, N):
        nd = [[0.0] * k for _ in range(2)]
        for c in (0, 1):
            for r in range(1, k):
                w = dp[c][r]
                if w == 0.0:
                    continue
                if c == 1:
                    if r + 1 < k:
                        nd[1][r + 1] += w * p
                    nd[0][1] += w * q
                else:
                    nd[1][1] += w * p
                    if r + 1 < k:
                        nd[0][r + 1] += w * q
        dp = nd
    tot = 0.0
    for c in (0, 1):
        for r in range(1, k):
            tot += dp[c][r]
    return tot


def p_serie(lam, mu, k=2, nmax=40):
    """P(au moins une série de k buts d'affilée dans le match).

    pmf de Poisson itérative, 41 termes fixes (queue < 1e-15 pour λ+μ ≤ 12,
    très au-delà des λ réels du moteur). Mêmes opérations, même ordre que le
    miroir JS.
    """
    tot = lam + mu
    if tot <= 0.0:
        return 0.0
    p = lam / tot
    s = 0.0
    pn = math.exp(-tot)
    for N in range(0, nmax + 1):
        s += pn * (1.0 - p_no_run(N, p, k))
        pn = pn * tot / (N + 1)
    return s


# ------------------------------------------------------- séries PAR ÉQUIPE
# P(une équipe PRÉCISE marque k buts d'affilée). Même modèle de Poisson
# fusionné : chaque but appartient à cette équipe avec probabilité pe,
# indépendamment. DP sur la longueur du run courant de cette équipe
# (un but adverse remet le compteur à 0 ; atteindre k = succès absorbant).
def p_no_run_team(N, p, k, home=True):
    """P(aucune série ≥ k de l'équipe `home` en N buts). pe = p si home
    sinon 1−p. Mêmes opérations, même ordre que le miroir JS."""
    if N == 0:
        return 1.0
    pe = p if home else 1.0 - p
    autre = 1.0 - pe
    dp = [0.0] * k
    dp[0] = 1.0
    for _ in range(N):
        nd = [0.0] * k
        for r in range(k):
            w = dp[r]
            if w == 0.0:
                continue
            nd[0] += w * autre
            if r + 1 < k:
                nd[r + 1] += w * pe
        dp = nd
    tot = 0.0
    for r in range(k):
        tot += dp[r]
    return tot


def p_serie_team(lam, mu, k=2, home=True, nmax=40):
    """P(l'équipe à domicile (home=True) ou à l'extérieur marque au moins
    une série de k buts d'affilée dans le match)."""
    tot = lam + mu
    if tot <= 0.0:
        return 0.0
    p = lam / tot
    s = 0.0
    pn = math.exp(-tot)
    for N in range(0, nmax + 1):
        s += pn * (1.0 - p_no_run_team(N, p, k, home))
        pn = pn * tot / (N + 1)
    return s


# ---------------------------------------------------------------- correction
# BIAIS MESURÉ EN WALK-FORWARD, PUIS CORRIGÉ (precedent : biais corners).
# Le moteur de backtest (Dixon-Coles pur) sous-estime les totaux de buts
# (~2,47 prédits vs ~2,72 réels/match sur 2 923 matchs joints), donc
# P(série 2+) brute est basse de ~4,8 pts — biais stable sur deux saisons
# (+4,6 pts en 2024-25, +4,9 pts en 2025-26). Correction = interpolation
# linéaire par morceaux sur les déciles mesurés (292 matchs/décile, bien au
# dessus du minimum REGLES de 60). Validation holdout : correction ajustée
# sur 2024-25 seule → résidu −1,1 pt sur 2025-26 (non vue). Pool des deux
# saisons figé ici le 10/09/2026 — recalibrer à chaque nouvelle saison
# collectée (buts_affilee.py calibrer --corriger).
# P(série 3+) NON corrigée : biais brut mesuré +0,7 pt, dans le bruit.
CORRECTION_SERIE2 = [
    (0.0, 0.0), (0.3518, 0.4897), (0.4185, 0.4897), (0.4531, 0.4932),
    (0.4825, 0.5171), (0.5085, 0.5788), (0.5332, 0.5788), (0.559, 0.6096),
    (0.5919, 0.6199), (0.6326, 0.6267), (0.7215, 0.7492), (1.0, 1.0),
]


def interp(p, points):
    """Interpolation linéaire par morceaux (x croissants) — mêmes opérations
    et même ordre que le miroir JS (genere_app.py)."""
    if p <= points[0][0]:
        return points[0][1]
    for i in range(1, len(points)):
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        if p <= x2:
            return y1 + (y2 - y1) * ((p - x1) / (x2 - x1))
    return points[-1][1]


def p_serie2(lam, mu):
    """P(série 2+ buts d'affilée) CORRIGÉE du biais walk-forward mesuré.
    C'est cette valeur qui est affichée (serveur.py + app autonome).

    Note (10/09) : p_serie n'est PAS strictement monotone en λ aux λ
    minuscules (< 0,14) — à λ≈0 tous les buts sont visiteurs donc toute
    paire est une série ; un soupçon de λ domicile casse des séries avant
    que le volume de buts n'en recrée. Mathématiquement exact, sans effet
    pratique : le moteur ne produit jamais λ < 0,3. Ne pas « corriger »."""
    return interp(p_serie(lam, mu, 2), CORRECTION_SERIE2)


# ------------------------------------------- corrections PAR ÉQUIPE (10/09)
# Mesures walk-forward sur 2 923 matchs joints (2 saisons, Big 5) — détails
# docs/SPEC-BUTS-AFFILEE.md §8.5. Décisions série par série (règle : on ne
# corrige que si le biais est STABLE et que la correction passe le holdout) :
# - série 2+ DOMICILE : biais −1,0 pt, signe INVERSÉ entre saisons (−2,4 puis
#   +0,3) et correction holdout pire que le brut (+2,4 vs +0,3) → BRUTE.
# - série 2+ EXTÉRIEUR : biais +8,3 pts stable (+9,2 / +7,4) → CORRIGÉE
#   (holdout : résidu 7,4 → 2,4 pts).
# - série 3+ DOMICILE : biais −2,1 pts, signe stable → CORRIGÉE (pool ±0,8).
# - série 3+ EXTÉRIEUR : biais +3,1 pts, signe stable → CORRIGÉE (pool +0,5/−1,3).
# L'asymétrie réelle dom 36-37 % / ext 27-28 % est confirmée par deux
# échantillons indépendants (phase 1 : 1 751 matchs 2025-26 ; calibration :
# 2 923 joints 2 saisons). Recalibrer à chaque nouvelle saison.
CORRECTION_SERIE2_EXT = [
    (0.0, 0.0), (0.0613, 0.1678), (0.0957, 0.1986), (0.1204, 0.1986),
    (0.1424, 0.2021), (0.1645, 0.25), (0.1878, 0.25), (0.2171, 0.3151),
    (0.2608, 0.3733), (0.3134, 0.4247), (0.4216, 0.4949), (1.0, 1.0),
]
CORRECTION_SERIE3_DOM = [
    (0.0, 0.0), (0.0278, 0.0342), (0.0505, 0.0479), (0.0697, 0.0719),
    (0.0893, 0.0719), (0.1095, 0.0788), (0.1317, 0.0993), (0.1628, 0.1267),
    (0.2037, 0.1815), (0.2632, 0.2226), (0.3905, 0.3627), (1.0, 1.0),
]
CORRECTION_SERIE3_EXT = [
    (0.0, 0.0), (0.0074, 0.0205), (0.0145, 0.0514), (0.021, 0.0514),
    (0.0274, 0.0548), (0.0346, 0.0548), (0.0428, 0.0548), (0.0544, 0.1096),
    (0.0737, 0.1199), (0.1005, 0.161), (0.1688, 0.2203), (1.0, 1.0),
]


def p_serie2_dom(lam, mu):
    """P(domicile marque 2+ buts d'affilée) — BRUTE (pas de biais stable)."""
    return p_serie_team(lam, mu, 2, True)


def p_serie2_ext(lam, mu):
    """P(extérieur marque 2+ buts d'affilée) — corrigée (+8,3 pts mesurés)."""
    return interp(p_serie_team(lam, mu, 2, False), CORRECTION_SERIE2_EXT)


def p_serie3_dom(lam, mu):
    """P(domicile marque 3+ buts d'affilée) — corrigée (−2,1 pts mesurés)."""
    return interp(p_serie_team(lam, mu, 3, True), CORRECTION_SERIE3_DOM)


def p_serie3_ext(lam, mu):
    """P(extérieur marque 3+ buts d'affilée) — corrigée (+3,1 pts mesurés)."""
    return interp(p_serie_team(lam, mu, 3, False), CORRECTION_SERIE3_EXT)
