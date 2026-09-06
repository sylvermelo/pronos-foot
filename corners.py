"""
CORNERS — calibration de production des marchés de confrontation.
=================================================================
Le backtest walk-forward (backtest_corners.py, 16 408 matchs, 21 divisions,
saisons 2324-2526) a mesuré que le modèle brut est TROP CONFIANT sur les
handicaps corners :

    barreau « +2 »      : annoncé 0,933 → réalisé 0,888   (−4,5 pts)
    barreau « +1 / 1X » : annoncé 0,927 → réalisé 0,872   (−5,4 pts)
    barreau « victoire »: annoncé 0,922 → réalisé 0,788   (−13,4 pts !)
    barreaux −1 et au-delà : encore moins fiables

Rien n'est inventé ici : la probabilité CALIBRÉE d'un barreau est la
fréquence RÉELLE observée dans le backtest pour la famille et la bande
d'annonce correspondantes (cellules de ≥ 40 matchs ; les cellules plus
minces sont fusionnées avec la bande inférieure, plus prudente). La
probabilité calibrée ne dépasse jamais l'annonce du modèle.

C'est cette probabilité calibrée qui :
    · est affichée dans l'espace Corners (à côté de l'annonce brute) ;
    · décide de l'entrée d'un match dans le COUPON MONTANTE du jour
      (bon match = meilleur handicap ≥ MIN_JAMBE, cote TOTALE = produit) ;
    · produit la cote juste (1/p) de chaque jambe et du coupon.

Les totaux over/under de corners sont mieux calibrés (backtest secondaires
global : annoncé 0,847 → réalisé 0,848 ; 0,932 → 0,923) : simple marge
conservatrice de 1 pt au-dessus de 0,90.

Rappel honnête : aucune source gratuite ne fournit les corners en direct —
ces sélections ne peuvent PAS être résolues automatiquement par le suivi
(résolution hebdomadaire possible via les CSV co.uk, à demander).
"""
import json
import os

RACINE = os.path.dirname(os.path.abspath(__file__))
CHEMIN_BT = os.path.join(RACINE, "data", "backtest_corners.json")

# échelle de handicaps (D = corners dominante − corners adversaire)
FAMILLES = [("+2", -1), ("+1", 0), ("victoire", 1),
            ("-1", 2), ("-2", 3), ("-3", 4), ("-4", 5)]
BORNES = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.93, 0.96, 0.98, 1.01]

# --- RÈGLE DU COUPON MONTANTE (validée avec l'utilisateur) ---------------
# Ce n'est PAS un match qui fait la cote : TOUS les bons matchs du jour
# entrent dans la sélection, et c'est l'ENSEMBLE qui donne une cote totale
# allant de 1,20 à l'infini selon la qualité du jour. Jamais de report sur
# la journée suivante. Seuls les HANDICAPS entrent dans le coupon.
MIN_JAMBE = 0.85            # « bon match » : le meilleur handicap du match
                            # doit atteindre 85 % de fréquence RÉELLE mesurée
                            # (≈ 17 fois sur 20). À 80 %, les coupons du week-
                            # end montaient à 13 maillons / 11 % de réussite —
                            # plus une montante, un billet de loterie.
CIBLE_COUPON = 1.20         # cote TOTALE plancher de la sélection entière
                            # (produit des maillons — jamais d'exigence de
                            # cote par match).
MARGE_TOTAUX = 0.01         # totaux over/under ≥ 0,90 : −1 pt (mesuré)
N_MIN_CELLULE = 40          # en dessous : fusion avec la bande inférieure

_CACHE = {}


def _bandes():
    """Cellules de calibration {famille: [(borne_inf, n, realise), …]} triées,
    avec fusion des cellules minces vers le bas (prudence)."""
    if "bandes" in _CACHE:
        return _CACHE["bandes"]
    try:
        with open(CHEMIN_BT, encoding="utf-8") as f:
            bt = json.load(f)
    except (OSError, ValueError):
        bt = {}
    out = {}
    for fam, _ in FAMILLES:
        cells = []
        for i in range(len(BORNES) - 1):
            b = f"{BORNES[i]:.2f}-{BORNES[i+1]:.2f}" if BORNES[i + 1] <= 1.0 else "0.98-1.00"
            c = (bt.get("calibration") or {}).get(f"{fam}|{b}")
            if c and c.get("n"):
                cells.append([BORNES[i], int(c["n"]), float(c["realise"])])
        # fusion des cellules minces avec la précédente (remonte du bas vers le haut)
        fusion = []
        for c in cells:
            if fusion and (c[1] < N_MIN_CELLULE or fusion[-1][1] < N_MIN_CELLULE):
                p = fusion[-1]
                n = p[1] + c[1]
                p[2] = (p[2] * p[1] + c[2] * c[1]) / n
                p[1] = n
            else:
                fusion.append(list(c))
        out[fam] = fusion
    _CACHE["bandes"] = out
    return out


def calibrer(famille, p):
    """Probabilité calibrée d'un barreau d'handicap corners (jamais > p)."""
    if p is None or p < 0.5:
        return p
    cells = _bandes().get(famille) or []
    chosen = None
    for borne, n, realise in cells:
        if p >= borne:
            chosen = realise            # dernière bande dont la borne ≤ p
    if chosen is None:
        return round(p, 4)              # sous la 1re bande mesurée : annonce brute
    return round(min(p, chosen), 4)


def calibrer_total(p):
    """Over/under de corners : marge conservatrice mesurée (1 pt au-dessus de 0,90)."""
    if p is None:
        return None
    return round(min(p, p - MARGE_TOTAUX if p >= 0.90 else p), 4)


def resume():
    """Résumé lisible (pour l'interface) : réalisé moyen par famille en zone ≥ 0,90."""
    try:
        with open(CHEMIN_BT, encoding="utf-8") as f:
            bt = json.load(f)
    except (OSError, ValueError):
        return None
    return {"zone_securite": bt.get("zone_securite", {}),
            "n_matchs": bt.get("n_matchs", 0),
            "saisons": bt.get("saisons_testees", []),
            "min_jambe": MIN_JAMBE, "cible": CIBLE_COUPON}
