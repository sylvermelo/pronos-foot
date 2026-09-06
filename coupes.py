"""
Coupes d'Europe et coupes nationales — pseudo-divisions du calendrier.

Pourquoi des « pseudo-divisions » ?
    Nos modèles Dixon-Coles sont entraînés PAR DIVISION domestique (les 21
    couvertes par football-data.co.uk). Les coupes (Champions League, Europa
    League, Conference League, Carabao Cup, Copa del Rey, Coppa Italia,
    DFB-Pokal, Coupe de France) opposent des équipes de divisions — voire de
    pays — différents : aucune donnée historique de coupe n'est disponible
    gratuitement pour entraîner un modèle dédié.

Ce qu'on fait (honnêtement) :
    · Chaque équipe apporte ses forces (attaque/défense) de SA division
      domestique. Rien n'est dupliqué dans les fichiers : un index unique
      équipe → division est construit (`db["index_equipes"]`), et la
      prédiction est calculée à la volée.
    · Deux équipes de la MÊME division (ex. un Carabao E0 vs E0) : la
      prédiction est celle d'un match de championnat — qualité normale.
    · Deux équipes de divisions DIFFÉRENTES : les forces domestiques ne sont
      PAS comparables d'une ligue à l'autre (aucun étalonnage inter-ligues
      gratuit disponible — Club Elo était injoignable le 06/09/2026). La
      prédiction est alors INDICATIVE : confiance forcée à « faible », et ces
      matchs n'entrent JAMAIS dans les sélections conseillées, les combinés
      ni le suivi. Le robot ne parie pas sur ce qu'il ne sait pas calibrer.
    · Une équipe inconnue des 21 divisions (ex. un club kazakh ou chypriote)
      : le match n'est pas affiché — abstention complète, pas d'invention.
"""

# clé interne → (slug ESPN, nom affiché, pays affiché)
COUPES = {
    "UCL":  {"slug": "uefa.champions",
             "nom": "Champions League", "pays": "Europe"},
    "UEL":  {"slug": "uefa.europa",
             "nom": "Europa League", "pays": "Europe"},
    "UECL": {"slug": "uefa.europa.conf",
             "nom": "Conference League", "pays": "Europe"},
    "CAR":  {"slug": "eng.league_cup",
             "nom": "Carabao Cup", "pays": "Angleterre"},
    "CDR":  {"slug": "esp.copa_del_rey",
             "nom": "Copa del Rey", "pays": "Espagne"},
    "CDI":  {"slug": "ita.coppa_italia",
             "nom": "Coppa Italia", "pays": "Italie"},
    "DFP":  {"slug": "ger.dfb_pokal",
             "nom": "DFB-Pokal", "pays": "Allemagne"},
    "CDF":  {"slug": "fra.coupe_de_france",
             "nom": "Coupe de France", "pays": "France"},
}


def injecter(db):
    """Ajoute les pseudo-divisions de coupes à db["ligues"] (idempotent).

    Construit aussi db["index_equipes"] : {nom d'équipe co.uk → division
    domestique}. En cas d'homonymie entre divisions (très rare), la première
    division dans l'ordre alphabétique gagne — sans conséquence : les forces
    des deux homonymes seraient de toute façon signalées comme approximation.
    """
    ligues = db.setdefault("ligues", {})
    index = db.get("index_equipes") or {}
    for div in sorted(ligues):
        if div in COUPES:
            continue
        for t in ligues[div].get("forces", {}):
            index.setdefault(t, div)
    db["index_equipes"] = index

    for cle, meta in COUPES.items():
        if cle in ligues:
            # déjà injectée : rafraîchir uniquement le libellé (idempotent)
            ligues[cle]["nom"] = meta["nom"]
            ligues[cle]["pays"] = meta["pays"]
            continue
        ligues[cle] = {
            "nom": meta["nom"], "pays": meta["pays"], "saison": "coupes 2026/27",
            # pas de forces propres : elles sont empruntées à la volée aux
            # divisions domestiques via db["index_equipes"] (zéro duplication)
            "forces": {}, "stats": {}, "secondaires": None,
            "gamma": 0.0, "s_away": 0.0, "rho": 0.0,   # remplacés à la volée
            "equipes_actuelles": [], "n_historique": 0, "dernier_match": None,
            "moteur": ("Forces domestiques transférées (coupe — approximation "
                       "inter-ligues, non calibrée)"),
            "coupe": True, "slug_espn": meta["slug"],
        }
    return sorted(COUPES)


def parametres(db, cle, home, away):
    """Paramètres Dixon-Coles effectifs pour un match de coupe.

    Retourne (L_effectif, div_home, div_away) où L_effectif est un dictionnaire
    compatible avec matrice_scores :
      · même division domestique → les paramètres exacts de cette division ;
      · divisions différentes → forces de chacune + moyenne des gamma/s_away/rho
        (approximation assumée, signalée « confiance faible » en amont) ;
      · équipe inconnue → (None, …) : pas de prédiction.
    """
    index = db.get("index_equipes") or {}
    ligues = db.get("ligues") or {}
    dh, da = index.get(home), index.get(away)
    if not dh or not da:
        return None, dh, da
    Lh, La = ligues.get(dh), ligues.get(da)
    if not Lh or not La:
        return None, dh, da
    if dh == da:
        fh, fa = Lh["forces"].get(home), Lh["forces"].get(away)
        if not fh or not fa:
            return None, dh, da
        return Lh, dh, da
    fh, fa = Lh["forces"].get(home), La["forces"].get(away)
    if not fh or not fa:
        return None, dh, da
    synth = {
        "forces": {home: fh, away: fa},
        "gamma": (Lh["gamma"] + La["gamma"]) / 2.0,
        "s_away": (Lh["s_away"] + La["s_away"]) / 2.0,
        "rho": (Lh["rho"] + La["rho"]) / 2.0,
        "coupe": True, "interligues": True,
    }
    return synth, dh, da
