"""
Serveur de l'application de pronostics.

Stdlib uniquement (http.server) : aucune dependance a installer, demarrage instantane.
Les modeles sont pre-entraines dans data/modeles.json -> reponse < 20 ms.
"""
import json, os, sys, gzip, io, urllib.parse, datetime
import threading, subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from scipy.stats import poisson
import modeles_secondaires as MS
import calendrier as CAL
import suivi

MAXG = 10
PORT = int(os.environ.get("PORT", 8000))
RACINE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(RACINE, "data/modeles.json")) as f:
    DB = json.load(f)

# pseudo-divisions de coupes (UCL, UEL, UECL, Carabao, Copa, Coppa, Pokal,
# Coupe de France) : forces domestiques transférées à la volée — voir coupes.py
import coupes
coupes.injecter(DB)


def integrer_calendrier():
    """Reconstruit le calendrier multi-sources (ESPN + TheSportsDB +
    OpenLigaDB) et remplace DB["fixtures"]. Les cotes restent celles de
    football-data.co.uk (jonction par équipes). Lancé en arrière-plan au
    démarrage pour ne pas bloquer l'ouverture du serveur."""
    try:
        log = CAL.appliquer(DB)
    except Exception as e:
        log = {"statut": f"erreur : {e}", "total": 0}
        DB["calendrier_log"] = log
    # La reconstruction du calendrier écrase les fixtures : ré-appliquer les
    # cotes Pinnacle en direct depuis le CACHE local (aucun appel réseau ici —
    # le téléchargement est fait par maj_calendrier.py avec le secret CI).
    try:
        import cotes_live
        n_pin = cotes_live.appliquer(DB)
        if n_pin:
            log = dict(log or {})
            log["cotes_pinnacle"] = n_pin
    except Exception:
        pass
    try:                                 # BOUCLE RAPIDE : résultats ESPN
        import resultats
        n_res = resultats.collecter(DB)
        if n_res:
            log = dict(log or {})
            log["boucle_rapide"] = n_res
    except Exception:
        pass
    try:                                        # suivi des pronostics
        conseils = api_conseils(suivi.SEUIL_ARCHIVE)
        d = suivi.archiver(conseils)
        d, n = suivi.resoudre(d, DB)
        rattrape = suivi.rattrapage_safe(d, conseils)
        suivi.sauver(d)
        log["suivi"] = {"jours": len(d["jours"]), "nouveaux_resultats": n}
        if rattrape:
            log["suivi"][rattrape] = "créé (jambe SAFE perdue)"
        try:                                 # Phase 1 : double écriture Supabase
            import db
            cp = coupon_corners()
            log["supabase"] = db.sync_suivi(
                d, combines_extra=[cp] if cp else []).get("statut")
        except Exception:
            log["supabase"] = "echec"        # jamais bloquant
    except Exception as e:
        log["suivi"] = {"erreur": str(e)}
    return log


# au démarrage du serveur uniquement — pas quand genere_app.py importe ce
# module (les fixtures viennent alors déjà fraîches de maj_calendrier.py).
if not os.environ.get("PRONOS_SANS_CALENDRIER"):
    threading.Thread(target=integrer_calendrier, daemon=True).start()

# backtest walk-forward des marches secondaires (genere par backtest_secondaires.py)
# chargement paresseux avec cache base sur la date de modification : apres avoir
# relance le backtest, inutile de redemarrer le serveur pour voir les nouveaux chiffres.
_BT_CHEMIN = os.path.join(RACINE, "data/backtest_secondaires.json")
_BT_CACHE = {"mtime": None, "data": {}}


def bt_secondaires():
    try:
        mt = os.path.getmtime(_BT_CHEMIN)
    except OSError:
        return {}
    if _BT_CACHE["mtime"] != mt:
        with open(_BT_CHEMIN) as f:
            _BT_CACHE["data"] = json.load(f)
        _BT_CACHE["mtime"] = mt
    return _BT_CACHE["data"]



# ------------------------------------------------------------------ moteur
_CACHE = {}


def matrice_scores(lig, home, away, fat=None):
    """Matrice 11x11 des probabilites de score exact (Dixon-Coles).

    fat = (multiplicateur λ_home, multiplicateur λ_away) : fatigue européenne
    MESURÉE (fatigue.py, étape ③) — une équipe qui a joué la C1/C2/C3 dans
    les jours précédents marque un peu moins et encaisse un peu plus.
    None = aucun effet (match sans date connue, coupe, ou repos suffisant)."""
    cle = (lig, home, away, fat)
    if cle in _CACHE:
        return _CACHE[cle]
    L = DB["ligues"].get(lig)
    if not L:
        return None
    if L.get("coupe"):
        # coupe : paramètres empruntés aux divisions domestiques des deux
        # équipes (même division = prédiction exacte du championnat ;
        # divisions différentes = approximation inter-ligues non calibrée).
        L, _, _ = coupes.parametres(DB, lig, home, away)
        if not L:
            return None
    F = L["forces"]
    if home not in F or away not in F:
        return None
    att_h, dfn_h = F[home]["att"], F[home]["dfn"]
    att_a, dfn_a = F[away]["att"], F[away]["dfn"]
    lam = min(max(att_h * dfn_a * L["gamma"], 1e-6), 30)
    mu = min(max(att_a * dfn_h * L["s_away"], 1e-6), 30)
    if fat:
        lam = min(max(lam * fat[0], 1e-6), 30)
        mu = min(max(mu * fat[1], 1e-6), 30)
    rho = L["rho"]
    k = np.arange(MAXG + 1)
    M = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
    M[0, 0] *= max(1 - lam * mu * rho, 1e-9)
    M[0, 1] *= max(1 + lam * rho, 1e-9)
    M[1, 0] *= max(1 + mu * rho, 1e-9)
    M[1, 1] *= max(1 - rho, 1e-9)
    M = np.clip(M, 0, None)
    M /= max(M.sum(), 1e-12)
    _CACHE[cle] = (M, lam, mu)
    return _CACHE[cle]


def devig(*cotes):
    v = [float(c) for c in cotes if c is not None and np.isfinite(c) and c > 1.01]
    if len(v) != len(cotes) or len(v) < 2:
        return None
    inv = np.array([1 / x for x in v])
    return (inv / inv.sum()).tolist()


def pronostic(lig, home, away):
    # FATIGUE EUROPÉENNE (étape ③) : la date du match vient des fixtures —
    # même source que le miroir JS (fixturesBrutes) pour la parité autonome.
    date_match = None
    for fx in DB.get("fixtures", []):
        if fx["div"] == lig and fx["home"] == home and fx["away"] == away:
            date_match = fx.get("date")
            break
    fat, info_fatigue = None, None
    try:
        import fatigue as FAT
        mh, ma, info_fatigue = FAT.coeffs_match(lig, home, away, date_match)
        if mh:
            fat = (mh, ma)
    except Exception:
        fat, info_fatigue = None, None
    r = matrice_scores(lig, home, away, fat=fat)
    if r is None:
        return None
    M, lam, mu = r
    g = np.add.outer(np.arange(MAXG + 1), np.arange(MAXG + 1))
    d = np.abs(np.subtract.outer(np.arange(MAXG + 1), np.arange(MAXG + 1)))
    tri = float(np.tril(M, -1).sum()); dg = float(np.trace(M))
    cases = [(int(i), int(j), float(M[i, j])) for i in range(MAXG + 1) for j in range(MAXG + 1)]
    top = sorted(cases, key=lambda z: -z[2])[:6]
    out = {
        "ligue": lig, "home": home, "away": away,
        "lambda_home": round(lam, 3), "lambda_away": round(mu, 3),
        "buts_attendus": round(lam + mu, 2),
        "victoire_1": round(tri, 4), "nul": round(dg, 4),
        "victoire_2": round(1 - tri - dg, 4),
        "double_chance_1X": round(tri + dg, 4),
        "double_chance_12": round(1 - dg, 4),
        "double_chance_X2": round(1 - tri, 4),
        "over": {str(x): round(float(M[g > x].sum()), 4) for x in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)},
        "under": {str(x): round(float(M[g < x].sum()), 4) for x in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)},
        "btts_oui": round(float(M[1:, 1:].sum()), 4),
        "btts_non": round(float(M[0, :].sum() + M[:, 0].sum() - M[0, 0]), 4),
        "score_fleuve_5plus": round(float(M[g >= 5].sum()), 4),
        "score_fleuve_6plus": round(float(M[g >= 6].sum()), 4),
        "eclat_3plus": round(float(M[d >= 3].sum()), 4),
        "eclat_4plus": round(float(M[d >= 4].sum()), 4),
        "clean_sheet_home": round(float(M[:, 0].sum()), 4),
        "clean_sheet_away": round(float(M[0, :].sum()), 4),
        "scores_top": [{"score": f"{i}-{j}", "p": round(p, 4)} for i, j, p in top],
        "matrice": [[round(float(M[i, j]), 4) for j in range(8)] for i in range(8)],
    }
    # indice de fiabilite : le nombre de matchs ponderes derriere chaque equipe
    L = DB["ligues"][lig]
    fh, fa = L["forces"].get(home, {}), L["forces"].get(away, {})
    ne_h, ne_a = fh.get("n_eff", 0), fa.get("n_eff", 0)
    nb_h, nb_a = fh.get("n_brut", 0), fa.get("n_brut", 0)
    mini = min(ne_h, ne_a)
    conf = "haute" if mini >= 40 else "moyenne" if mini >= 20 else "faible"
    out["fiabilite"] = {
        "niveau": conf, "home_n_eff": ne_h, "away_n_eff": ne_a,
        "home_n_brut": nb_h, "away_n_brut": nb_a,
        "message": None if conf == "haute" else (
            f"Attention : {' ou '.join(t for t, n in ((home, ne_h), (away, ne_a)) if n < 40)}"
            f" n'a que peu de matchs dans cette division (promu ou début de saison). "
            f"La régularisation a ramené ses paramètres vers la moyenne, mais la "
            f"prédiction reste moins fiable qu'en milieu de saison.")
    }
    if info_fatigue:
        out["fatigue"] = info_fatigue
    if DB["ligues"][lig].get("coupe"):
        idx_eq = DB.get("index_equipes") or {}
        dh, da = idx_eq.get(home), idx_eq.get(away)
        inter = bool(dh) and bool(da) and dh != da
        out["fiabilite"]["inter_ligues"] = inter
        if inter:
            out["fiabilite"]["niveau"] = "faible"
        out["fiabilite"]["message"] = (
            "Match de COUPE : chaque équipe apporte les forces de son "
            "championnat domestique. "
            + ("Les deux équipes viennent de divisions DIFFÉRENTES : aucun "
               "étalonnage inter-ligues n'est disponible gratuitement — cette "
               "prédiction est INDICATIVE (confiance forcée à « faible ») et "
               "le match n'entre dans aucune sélection conseillée ni combiné."
               if inter else
               "Les deux équipes viennent de la même division : la prédiction "
               "utilise exactement le modèle de ce championnat (contexte de "
               "coupe non modélisé : rotation d'effectif, enjeu différent).")
            + " Aucun gain garanti.")
    # comparaison au marche si des cotes existent
    for fx in DB.get("fixtures", []):
        if fx["div"] == lig and fx["home"] == home and fx["away"] == away:
            m = devig(fx["cote_1"], fx["cote_X"], fx["cote_2"])
            if m:
                out["marche"] = {"victoire_1": round(m[0], 4), "nul": round(m[1], 4),
                                 "victoire_2": round(m[2], 4),
                                 "cote_1": fx["cote_1"], "cote_X": fx["cote_X"],
                                 "cote_2": fx["cote_2"],
                                 "cote_max_1": fx["cote_max_1"],
                                 "cote_over": fx["cote_over"], "cote_under": fx["cote_under"],
                                 "ecart_1": round(out["victoire_1"] - m[0], 4),
                                 "ecart_X": round(out["nul"] - m[1], 4),
                                 "ecart_2": round(out["victoire_2"] - m[2], 4),
                                 "date": fx["date"], "heure": fx["heure"]}
                out["arbitre"] = fx.get("arbitre")
            break
    # marches secondaires : fautes, corners, cartons (avec effet arbitre si connu)
    sec = api_secondaires(lig, home, away)
    if sec:
        out["secondaires"] = sec
    return out


# ------------------------------------------------------------------ routes
def api_ligues():
    L = []
    for div, v in DB["ligues"].items():
        if v.get("coupe"):
            continue        # les coupes ne sont pas des championnats classables
        L.append({"div": div, "nom": v["nom"], "pays": v["pays"], "saison": v["saison"],
                  "n_equipes": len(v["equipes_actuelles"]), "n_historique": v["n_historique"],
                  "dernier_match": v["dernier_match"],
                  "gamma": v["gamma"], "s_away": v["s_away"],
                  "buts_moy": round(v["gamma"] + v["s_away"], 2)})
    return sorted(L, key=lambda x: (x["pays"], x["nom"]))


def api_classement(div):
    L = DB["ligues"].get(div)
    if not L:
        return None
    rows = []
    for t in L["equipes_actuelles"]:
        f = L["forces"].get(t)
        s = L["stats"].get(t) or {}
        if not f:
            continue
        ne = f.get("n_eff", 0)
        conf = "haute" if ne >= 40 else "moyenne" if ne >= 20 else "faible"
        rows.append({"equipe": t, "attaque": f["att"], "defense": f["dfn"],
                     "puissance": round(f["puissance"], 3),
                     "n_eff": ne, "n_brut": f.get("n_brut", 0), "confiance": conf,
                     "classement_att": 0, "classement_def": 0, **s})
    rows.sort(key=lambda r: -r["puissance"])
    for i, r in enumerate(rows):
        r["rang"] = i + 1
    aa = sorted(rows, key=lambda r: -r["attaque"])
    dd = sorted(rows, key=lambda r: r["defense"])
    for i, r in enumerate(aa):
        r["classement_att"] = i + 1
    for i, r in enumerate(dd):
        r["classement_def"] = i + 1
    return {"ligue": L["nom"], "pays": L["pays"], "saison": L["saison"],
            "moteur": L.get("moteur", "Dixon-Coles (buts réels)"),
            "gamma": L["gamma"], "s_away": L["s_away"], "rho": L["rho"],
            "n_historique": L["n_historique"], "dernier_match": L["dernier_match"],
            "equipes": rows}


def api_fleuves(div, top=12):
    L = DB["ligues"].get(div)
    if not L:
        return None
    eq = L["equipes_actuelles"]
    rows = []
    for h in eq:
        for a in eq:
            if h == a:
                continue
            r = matrice_scores(div, h, a)
            if r is None:
                continue
            M, lam, mu = r
            g = np.add.outer(np.arange(MAXG + 1), np.arange(MAXG + 1))
            d = np.abs(np.subtract.outer(np.arange(MAXG + 1), np.arange(MAXG + 1)))
            rows.append({"home": h, "away": a, "buts": round(lam + mu, 2),
                         "fleuve5": round(float(M[g >= 5].sum()), 4),
                         "fleuve6": round(float(M[g >= 6].sum()), 4),
                         "over25": round(float(M[g > 2.5].sum()), 4),
                         "over35": round(float(M[g > 3.5].sum()), 4),
                         "eclat3": round(float(M[d >= 3].sum()), 4)})
    rows.sort(key=lambda r: -r["fleuve5"])
    secs = sorted(rows, key=lambda r: r["buts"])[:top]
    return {"ligue": L["nom"], "plus_prolifiques": rows[:top], "plus_fermes": secs}


def api_matchs():
    aujourdhui = datetime.date.today()
    ref = aujourdhui.isoformat()
    out = []
    for fx in DB.get("fixtures", []):
        if (fx["date"] or "") < ref:
            continue                      # jamais de match deja joue
        p = pronostic(fx["div"], fx["home"], fx["away"])
        lig = DB["ligues"].get(fx["div"])
        item = {"div": fx["div"], "ligue": lig["nom"] if lig else fx["div"],
                "pays": lig["pays"] if lig else "?",
                "date": fx["date"], "heure": fx["heure"],
                "home": fx["home"], "away": fx["away"], "arbitre": fx["arbitre"],
                "cote_1": fx["cote_1"], "cote_X": fx["cote_X"], "cote_2": fx["cote_2"],
                "cote_over": fx["cote_over"], "cote_under": fx["cote_under"],
                "source": fx.get("source") or "co.uk", "ou_line": fx.get("ou_line"),
                "source_cotes": fx.get("source_cotes") or "co.uk",
                "coupe": bool(lig and lig.get("coupe")),
                "disponible": p is not None}
        # libelle de journee : aujourd'hui, demain, puis J+2, J+3...
        try:
            delta = (datetime.date.fromisoformat(fx["date"]) - aujourdhui).days
        except (ValueError, TypeError):
            delta = 0
        item["jour_delta"] = delta
        item["jour"] = ("Aujourd'hui" if delta == 0 else "Demain" if delta == 1
                        else f"Dans {delta} jours")
        if p:
            item.update({"p1": p["victoire_1"], "pX": p["nul"], "p2": p["victoire_2"],
                         "over25": p["over"]["2.5"], "btts": p["btts_oui"],
                         "buts": p["buts_attendus"], "fleuve": p["score_fleuve_5plus"],
                         "confiance": p["fiabilite"]["niveau"],
                         # toutes les lignes de buts, over ET under, de 0.5 a 5.5
                         "over": p["over"], "under": p["under"],
                         "double_chance": {"1X": p["double_chance_1X"],
                                           "12": p["double_chance_12"],
                                           "X2": p["double_chance_X2"]},
                         "clean_sheet": {"home": p["clean_sheet_home"],
                                         "away": p["clean_sheet_away"]},
                         "eclat_3plus": p["eclat_3plus"], "eclat_4plus": p["eclat_4plus"],
                         "scores_top": p["scores_top"],
                         "lambda_home": p["lambda_home"], "lambda_away": p["lambda_away"]})
            m = p.get("marche")
            if m:
                item["ecart_1"] = m["ecart_1"]; item["ecart_X"] = m["ecart_X"]
                item["ecart_2"] = m["ecart_2"]
                ec = [(m["ecart_1"], "1"), (m["ecart_X"], "X"), (m["ecart_2"], "2")]
                mv = max(ec, key=lambda z: z[0])
                item["meilleur_ecart"] = mv[0]; item["meilleur_pari"] = mv[1]
                item["cote_meilleur"] = {"1": fx["cote_max_1"], "X": fx["cote_max_X"],
                                         "2": fx["cote_max_2"]}[mv[1]]
        enrichir_secondaires(item)
        out.append(item)
    out.sort(key=lambda x: (x["date"] or "9999", x["heure"] or ""))
    return out


# ---------------------------------------------------------------------------
# BOUTON RAFRAÎCHIR : mise à jour à la demande (mode serveur uniquement).
# Lance maj.py en arrière-plan (téléchargement source + ré-entraînement si
# nouveauté), puis recharge la base en mémoire sans redémarrer le serveur.
# ---------------------------------------------------------------------------
_MAJ = {"etat": "arrete", "log": "", "fin": None}
_MAJ_VERROU = threading.Lock()


def _lancer_maj():
    global DB
    try:
        p = subprocess.run([sys.executable, os.path.join(RACINE, "maj.py")],
                           capture_output=True, text=True, timeout=1500, cwd=RACINE)
        _MAJ["log"] = (p.stdout or "")[-2000:] + (p.stderr or "")[-800:]
        with open(os.path.join(RACINE, "data/modeles.json")) as f:
            DB = json.load(f)
        _MAJ["etat"] = "termine"
    except Exception as e:                      # source injoignable, etc.
        _MAJ["log"] = str(e)
        _MAJ["etat"] = "erreur"
    _MAJ["fin"] = datetime.datetime.now().isoformat(timespec="seconds")


def api_refresh():
    with _MAJ_VERROU:
        if _MAJ["etat"] == "en_cours":
            return {"etat": "en_cours"}
        _MAJ["etat"] = "en_cours"
        threading.Thread(target=_lancer_maj, daemon=True).start()
        return {"etat": "demarre"}


def api_maj():
    return {"etat": _MAJ["etat"], "fin": _MAJ["fin"], "log": _MAJ["log"][-1200:],
            "calendrier": DB.get("calendrier_log") or {},
            "genere_le": datetime.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(RACINE, "data/modeles.json")))
                .isoformat(timespec="minutes")}


# Marges exigées POUR LES MARCHÉS FRAGILES, en plus du seuil de base.
# Justification mesurée (suivi réel + historiques co.uk 2023-2026) :
#  · unders touchés à 58 % contre 92 % aux overs dans le suivi en direct ;
#  · la fréquence RÉELLE d'un under 3.5 par division (58 à 75 %) est presque
#    toujours inférieure à ce que Dixon-Coles annonce — le modèle sous-estime
#    les matchs à 4-5 buts (queues de distribution trop fines).
# On durcit donc les unders au lieu de les supprimer : un under 3.5 doit être
# annoncé à seuil + 13 points pour entrer dans la sélection conseillée.
MARGES_MARCHE = {"under 3.5": 0.13, "under 2.5": 0.05, "under 1.5": 0.02}


def _jours_weekend(aujourdhui=None):
    """Dates ISO du vendredi, samedi et dimanche du week-end courant
    (ou du week-end à venir si on est entre lundi et jeudi)."""
    d = aujourdhui or datetime.date.today()
    wd = d.weekday()                       # lundi=0 … vendredi=4, samedi=5, dimanche=6
    if wd <= 3:                            # lun-jeu : le week-end qui vient
        ven = d + datetime.timedelta(days=4 - wd)
    elif wd == 4:                          # vendredi : c'est aujourd'hui
        ven = d
    else:                                  # sam/dim : celui en cours
        ven = d - datetime.timedelta(days=wd - 4)
    return [(ven + datetime.timedelta(days=i)).isoformat() for i in range(3)]


def _combinaisons(sels, seuil, pool_risque, aujourdhui=None):
    """Six combinés aux règles déterministes (même entrée → même sortie).

    SAFE DU JOUR   : 3 matchs MAXIMUM, tous du MÊME jour (aujourd'hui).
                     Moins de 3 éligibles → on prend ce qu'il y a (1 ou 2).
                     Zéro → None (l'interface affiche « 0 »). Jamais le robot
                     ne va chercher un match du jour suivant pour compléter.
    SAFE WEEK-END  : vendredi + samedi + dimanche (week-end à venir si on est
                     lun-jeu), 3 matchs maximum PAR JOUR → 9 au total si les 9
                     sont disponibles. Même règle par jour : ce qui existe,
                     rien de forcé. Les jours sans sélection comptent 0.
    RISQUE DU JOUR : les COTES les plus hautes parmi les options cotées
                     (aujourd'hui + demain), planchers de probabilité 55 %
                     (65 % pour un under 2.5, fragile d'après le suivi),
                     minimum 2 jambes, matchs des SAFE exclus.
    COTE 2 DU JOUR : combiné du jour dont le produit des cotes vise ≈ 2
                     (fourchette 1,90-2,35), 10 jambes max, les plus sûres
                     d'abord, matchs du SAFE DU JOUR exclus.
    COTE 5 DU JOUR : même principe, cible ≈ 5 (fourchette 4,60-5,90),
                     10 jambes max.
    FUN DU JOUR    : la grosse cote du jour, cible 20 à 50, 15 jambes max,
                     jambes les plus longues d'abord (mais toutes au-dessus
                     du seuil — un billet de loterie, assumé comme tel).
    Pour ces trois combinés : cote du marché si elle existe, sinon COTE
    JUSTE calculée (1/p) — le champ cote_type indique la source.
    Probabilité combinée = produit des probabilités (indépendance supposée,
    approximation — des matchs d'un même championnat peuvent être corrélés).
    """
    def construire(pool_, cle, mini_p, max_legs=3):
        """Les max_legs meilleures options du pool, en variant les ligues si
        possible. Retourne une liste (éventuellement vide), jamais forcée."""
        legs = []
        for diversifie in (True, False):
            legs, vus, ligues = [], set(), set()
            tri = sorted(pool_, key=lambda z: (-(z.get(cle) or 0), -z["p"],
                                               z["date"], z["home"], z["away"]))
            for s in tri:
                if len(legs) >= max_legs:
                    break
                if not (s.get(cle) or 0) > 0 or s["p"] < mini_p:
                    continue
                mid = (s["date"], s["home"], s["away"])
                if mid in vus or (diversifie and s["ligue"] in ligues):
                    continue
                legs.append(s); vus.add(mid); ligues.add(s["ligue"])
            if len(legs) >= 2:
                break
        return legs

    def finaliser(legs, par_jour=None):
        if not legs:
            return None
        p, cote, toutes_cotes = 1.0, 1.0, True
        for s in legs:
            p *= s["p"]
            if s.get("cote_marche"):
                cote *= s["cote_marche"]
            else:
                toutes_cotes = False
        out = {"legs": legs, "p_combine": round(p, 4),
               "cote_combine": round(cote, 2) if toutes_cotes else None,
               "cote_juste_combine": round(1 / p, 2) if p > 0 else None}
        if par_jour is not None:
            out["par_jour"] = par_jour
        return out

    def construire_cible(pool_, cible_min, cible_max, max_legs, p_asc=False):
        """Combiné « à cote cible » : remplit des jambes (1 option par match)
        jusqu'à ce que le produit des cotes entre dans [cible_min, cible_max].

        - cote d'une jambe = cote du MARCHÉ si elle existe, sinon COTE JUSTE
          calculée (1/p) — l'utilisateur voit toujours un nombre honnête,
          et le champ cote_type dit d'où il vient (marché / juste / mixte).
        - p_asc=False : jambes les plus sûres d'abord (cote 2, cote 5).
          p_asc=True  : jambes les plus longues d'abord (fun — atteint la
          cible 20-50 avec le moins de matchs possible, tous ≥ seuil).
        - jamais forcé : si la cible minimale n'est pas atteinte dans la
          limite de jambes → None (l'interface affiche « 0 »).
        """
        tri = sorted(pool_, key=(lambda s: (s["p"], s["date"], s["home"], s["away"]))
                     if p_asc else
                     (lambda s: (-s["p"], s["date"], s["home"], s["away"])))
        legs, vus, prod, n_m, n_j = [], set(), 1.0, 0, 0
        for s in tri:
            if len(legs) >= max_legs or prod >= cible_min:
                break
            cote_leg = s.get("cote_marche") or s.get("cote_juste")
            if not cote_leg or cote_leg <= 1.0:
                continue
            mid = (s["date"], s["home"], s["away"])
            if mid in vus or prod * cote_leg > cible_max:
                continue
            legs.append(s); vus.add(mid); prod *= cote_leg
            if s.get("cote_marche"):
                n_m += 1
            else:
                n_j += 1
        if not legs or prod < cible_min:
            return None
        p = 1.0
        for s in legs:
            p *= s["p"]
        return {"legs": legs, "p_combine": round(p, 4),
                "cote_combine": round(prod, 2),
                "cote_juste_combine": round(1 / p, 2) if p > 0 else None,
                "cote_type": "marché" if not n_j else "juste" if not n_m else "mixte",
                "cible": [cible_min, cible_max]}

    auj = aujourdhui or datetime.date.today()
    auj_iso = auj.isoformat()

    # --- SAFE DU JOUR : aujourd'hui UNIQUEMENT -------------------------------
    safe = finaliser(construire([s for s in sels if s.get("date") == auj_iso],
                                "p", seuil))

    # --- SAFE WEEK-END : 3 par jour (ven/sam/dim), jamais au-delà ------------
    legs_w, par_jour = [], {}
    for d in _jours_weekend(auj):
        legs_d = construire([s for s in sels if s.get("date") == d], "p", seuil)
        par_jour[d] = len(legs_d)
        legs_w.extend(legs_d)
    safe_weekend = finaliser(legs_w, par_jour=par_jour)

    # --- RISQUE : aujourd'hui + demain, options cotées, SAFE exclus ----------
    exclus = {(l["date"], l["home"], l["away"]) for l in legs_w}
    if safe:
        exclus |= {(l["date"], l["home"], l["away"]) for l in safe["legs"]}
    pool_risque = [s for s in pool_risque
                   if (s["date"], s["home"], s["away"]) not in exclus]
    legs_r = construire(pool_risque, "cote_marche", 0.55)
    risque = finaliser(legs_r) if len(legs_r) >= 2 else None

    # --- COTE 2 / COTE 5 / FUN DU JOUR : aujourd'hui uniquement, ------------
    # --- matchs du SAFE DU JOUR exclus, cote juste (1/p) si pas de marché ----
    pool_jour = [s for s in sels if s.get("date") == auj_iso]
    if safe:
        exclus_j = {(l["date"], l["home"], l["away"]) for l in safe["legs"]}
        pool_jour = [s for s in pool_jour
                     if (s["date"], s["home"], s["away"]) not in exclus_j]
    cote2 = construire_cible(pool_jour, 1.90, 2.35, 10)
    cote5 = construire_cible(pool_jour, 4.60, 5.90, 10)
    fun = construire_cible(pool_jour, 20.0, 50.0, 15, p_asc=True)

    return {"safe": safe, "safe_weekend": safe_weekend, "risque": risque,
            "cote2": cote2, "cote5": cote5, "fun": fun}


def api_conseils(seuil=0.75):
    """Sélection conseillée : pour chaque match à venir, l'option la plus
    probable parmi un panier de marchés « pariables » (1X2, over/under
    1.5-3.5, les deux équipes marquent, double chance). Si la probabilité
    de la meilleure option atteint le seuil, le match entre dans la liste.
    Rappel honnête : une probabilité élevée n'est pas un gain garanti."""
    seuil = float(seuil)
    jours = {}
    pool_risque = []
    # heure actuelle à Cotonou (UTC+1) : une sélection conseillée doit être
    # AVANT le coup d'envoi, jamais pendant — question d'honnêteté du suivi.
    now_cotonou = (datetime.datetime.now(datetime.timezone.utc)
                   + datetime.timedelta(hours=1)).replace(tzinfo=None)
    for m in api_matchs():
        if not m.get("disponible") or not m.get("over"):
            continue
        if m.get("coupe"):
            continue        # coupes : jamais dans les sélections/combinaisons
                            # suivies (approximation inter-ligues non calibrée)
        if m.get("heure") and m.get("date"):
            try:
                if f"{m['date']}T{m['heure']}" < now_cotonou.isoformat(timespec="minutes"):
                    continue                  # match déjà commencé
            except (ValueError, TypeError):
                pass
        o, u, dc = m["over"], m["under"], m.get("double_chance", {})
        base = {"div": m["div"], "ligue": m["ligue"], "pays": m["pays"],
                "date": m["date"], "heure": m["heure"], "jour": m["jour"],
                "jour_delta": m["jour_delta"],
                "home": m["home"], "away": m["away"],
                "confiance": m.get("confiance"), "buts": m.get("buts"),
                "cotes_source": m.get("source_cotes")}
        # pool du combiné « risque » : meilleure option COTÉE de chaque match
        # (aujourd'hui/demain), avec planchers de probabilité honnêtes.
        if m["jour_delta"] <= 1:
            opts_cotes = [("1", m["p1"], m.get("cote_1")),
                          ("X", m["pX"], m.get("cote_X")),
                          ("2", m["p2"], m.get("cote_2")),
                          ("over 2.5", o.get("2.5"), m.get("cote_over")),
                          ("under 2.5", u.get("2.5"), m.get("cote_under"))]
            elig = [(k, p_, c_) for k, p_, c_ in opts_cotes
                    if c_ and p_ is not None
                    and p_ >= (0.65 if k == "under 2.5" else 0.55)]
            if elig:
                k, p_, c_ = max(elig, key=lambda z: z[1])
                pool_risque.append({**base, "option": k, "p": round(p_, 4),
                                    "cote_juste": round(1 / p_, 2) if p_ > 0 else None,
                                    "cote_marche": c_})
        cands = [("1", m["p1"]), ("X", m["pX"]), ("2", m["p2"]),
                 ("over 1.5", o.get("1.5")), ("over 2.5", o.get("2.5")),
                 ("over 3.5", o.get("3.5")), ("under 1.5", u.get("1.5")),
                 ("under 2.5", u.get("2.5")), ("under 3.5", u.get("3.5")),
                 ("les deux marquent", m.get("btts")),
                 ("les deux ne marquent pas", round(1 - m["btts"], 4) if m.get("btts") is not None else None),
                 ("double chance 1X", dc.get("1X")), ("double chance 12", dc.get("12")),
                 ("double chance X2", dc.get("X2"))]
        cands = [(k, v) for k, v in cands if v is not None]
        opt, p = max(cands, key=lambda z: z[1])
        if p < seuil + MARGES_MARCHE.get(opt, 0.0) - 1e-9:
            continue        # seuil de base + marge pour les marchés fragiles
        item = {**base, "option": opt, "p": round(p, 4),
                "cote_juste": round(1 / p, 2) if p > 0 else None}
        # cote réelle du marché quand elle existe pour cette option
        if opt == "1":
            item["cote_marche"] = m.get("cote_1")
        elif opt == "X":
            item["cote_marche"] = m.get("cote_X")
        elif opt == "2":
            item["cote_marche"] = m.get("cote_2")
        elif opt == "over 2.5":
            item["cote_marche"] = m.get("cote_over")
        elif opt == "under 2.5":
            item["cote_marche"] = m.get("cote_under")
        jours.setdefault(m["jour_delta"], []).append(item)
    liste = []
    for delta in sorted(jours):
        sel = sorted(jours[delta], key=lambda x: -x["p"])
        liste.append({"jour": sel[0]["jour"], "jour_delta": delta,
                      "date": sel[0]["date"], "nb": len(sel), "selections": sel})
    a_plat = [s for j in liste for s in j["selections"]]
    return {"seuil": seuil, "jours": liste,
            "combines": _combinaisons(a_plat, seuil, pool_risque),
            "note": "Probabilités du moteur : pour les 5 grandes ligues (Angleterre, Espagne, Italie, Allemagne, France), les forces des équipes sont estimées sur les xG RÉELS d'Understat puis recalées sur les buts observés — gain validé par un test A/B en walk-forward sur 7 118 matchs (2022-2026). Ailleurs : Dixon-Coles sur les buts réels. Ensemble calibré sur 29 295 matchs. "
                    "Une option à 75 % se réalise environ 3 fois sur 4 en moyenne, "
                    "pas à chaque fois. Les unders sont DURCIS (marge exigée au-dessus "
                    "du seuil) : le suivi réel et les fréquences historiques montrent "
                    "que le modèle les surestime — il sous-estime les matchs à 4-5 buts. "
                    "Rentabilité face aux cotes non démontrée (voir l'onglet Fiabilité)."}


def api_bilan():
    return {
        "source": "football-data.co.uk (gratuit, sans cle API)",
        "volume": {**DB["meta"], "total_arbitres": len(DB.get("arbitres", {}))},
        "protocole": "Backtest walk-forward strict : reentrainement periodique, "
                     "aucune donnee posterieure au match predit.",
        "evalue_sur": "17 093 matchs, 11 ligues, saisons 2021/22 a 2025/26",
        "reference": "Cotes de cloture Pinnacle deviggees (le bookmaker le plus efficace)",
        "resultats": {
            "logloss_modele_1x2": 0.9944, "logloss_pinnacle_1x2": 0.9656,
            "rps_modele": 0.1349, "rps_pinnacle": 0.1295,
            "precision_favori_modele": 0.519, "precision_favori_pinnacle": 0.542,
            "roi_edge2": -0.0881, "roi_edge8": -0.1119, "clv": -0.0253,
        },
        "calibration": [
            {"plage": "0 - 15 %", "n": 4651, "reel": 0.114, "predite": 0.100, "ecart": 0.014},
            {"plage": "15 - 30 %", "n": 23475, "reel": 0.248, "predite": 0.241, "ecart": 0.007},
            {"plage": "30 - 45 %", "n": 11959, "reel": 0.355, "predite": 0.363, "ecart": -0.008},
            {"plage": "45 - 60 %", "n": 6797, "reel": 0.501, "predite": 0.516, "ecart": -0.015},
            {"plage": "60 - 100 %", "n": 4397, "reel": 0.703, "predite": 0.706, "ecart": -0.003},
        ],
        "baseline_triviale": {
            "note": "Test de controle indispensable : une constante naive calee sur la "
                    "frequence observee. Pinnacle la bat sur toutes les saisons.",
            "constante_naive": 0.6873, "hasard_50_50": 0.6931, "pinnacle": 0.6745,
            "echantillon": "Premier League, 2 099 matchs, cotes O/U propres",
        },
        "verdict": "Le modele est BIEN CALIBRE mais ne bat PAS le marche. "
                   "Il lui manque les compositions, les blessures et les vrais xG.",
        "avertissement": "Aucun modele ne garantit de gain. Le jeu peut creer une dependance.",
        "marches_secondaires": {
            "note": "Signal mesure sur 34 708 matchs, protocole A/B avec test de permutation.",
            "stabilite": [
                {"effet": "equipe -> fautes", "r": 0.729, "p": 0.0, "n": 283},
                {"effet": "equipe -> corners", "r": 0.668, "p": 0.0, "n": 283},
                {"effet": "equipe -> jaunes", "r": 0.619, "p": 0.0, "n": 283},
                {"effet": "arbitre -> fautes sifflees", "r": 0.502, "p": 0.0, "n": 94},
                {"effet": "arbitre -> taux d'avertissement", "r": 0.466, "p": 0.0, "n": 94},
            ],
            "surdispersion": {"fautes": 1.52, "corners": 1.18, "jaunes": 1.17, "rouges": 1.07},
            "limite_majeure": "AUCUNE COTE n'existe pour ces marches dans la source gratuite. "
                              "La previsibilite est demontree, la RENTABILITE ne l'est pas. "
                              "Un marche peut etre previsible et deja correctement cote.",
            "arbitres_couverts": len(DB.get("arbitres", {})),
            "backtest": bt_secondaires(),
            "verdict_backtest": (
                "Teste en walk-forward strict sur "
                + str(bt_secondaires().get("n_predictions", 0)) + " predictions. "
                "Le modele gagne " + str(bt_secondaires().get("gain_mae_pct", 0)) + " % de precision "
                "face a la moyenne de la division : c'est REEL mais FAIBLE. "
                "Les probabilites annoncees sont en revanche tres fiables "
                "(ecart annonce/realise <= 2 points sur "
                + str(bt_secondaires().get("n_seuils", 0)) + " seuils). "
                "L'apport isole de l'arbitre est negligeable ("
                + str(bt_secondaires().get("apport_arbitre_mae", 0)) + " sur la MAE). "
                "Conclusion : outil d'analyse credible, pas un generateur de mises."
                if bt_secondaires() else "Backtest non disponible : lancer backtest_secondaires.py."
            ),
        },
        "bugs_corriges": [
            "gamma non compense apres renormalisation des forces d'equipe",
            "inversion des issues 1 et 2 (precision tombee a 22,9 %, pire que le hasard)",
            "cotes O/U manquantes encodees en 0.00, non filtrees par dropna",
        ],
        "affirmation_retiree": "Le modele bat Pinnacle sur l'Over/Under 2,5 - FAUX, "
                               "invalide deux fois par des verifications plus rigoureuses.",
    }


def api_secondaires(div, home, away, arbitre=None):
    """Fautes / corners / cartons attendus, avec effet arbitre si connu."""
    if not arbitre:                      # on cherche l'arbitre dans les fixtures
        for fx in DB.get("fixtures", []):
            if fx["div"] == div and fx["home"] == home and fx["away"] == away:
                arbitre = fx.get("arbitre") or None
                break
    L = DB["ligues"].get(div)
    if not L or not L.get("secondaires"):
        return None
    modele = dict(L["secondaires"])
    modele["arbitres"] = DB.get("arbitres", {})
    res = MS.pronostiquer(modele, home, away, arbitre or None)
    if res is not None:
        # confrontation corners (dominante, partage, échelle d'handicaps brute)
        res["confrontation"] = MS.confrontation(modele, home, away)
        # CORNERS 1re MI-TEMPS (fil commentary ESPN — corners_mt.py) :
        # P(plus de corners MT1) / P(égalité) / P(moins) + over/under du
        # total MT1. Probabilités BRUTES (pas encore calibrées). None si la
        # division n'est pas couverte par le fil ESPN.
        try:
            import corners_mt as CMT
            res["cmt1"] = CMT.pronostic(modele, home, away)
        except Exception:
            res["cmt1"] = None
    return res


def coupon_corners(jour=None):
    """COUPON MONTANTE corners du jour (règle utilisateur), côté serveur.

    Tous les matchs du jour dont le meilleur handicap corners CALIBRÉ atteint
    corners.MIN_JAMBE entrent dans la sélection ; la cote totale est le produit
    des maillons (de 1,20 à l'infini selon la qualité du jour). Même jour
    uniquement, jamais de report. Retourne une ligne prête pour la table
    `combines` (nom « corners_montante ») — aucune table nouvelle.
    """
    import corners as CN
    jour = jour or datetime.date.today().isoformat()
    jambes = []
    for m in DB.get("fixtures", []):
        if m.get("date") != jour or m.get("coupe"):
            continue
        L = DB["ligues"].get(m["div"])
        if not L or not L.get("secondaires"):
            continue
        cf = MS.confrontation(L["secondaires"], m["home"], m["away"])
        if not cf:
            continue
        dom = m["home"] if cf["dom"] == "home" else m["away"]
        best = None
        for fam, _ in CN.FAMILLES:
            p = cf["echelle"].get(fam)
            pc = CN.calibrer(fam, p)
            if pc is None:
                continue
            if best is None or pc > best[0] or (pc == best[0] and (p or 0) > (best[1] or 0)):
                best = (pc, p, fam)
        if not best or best[0] < CN.MIN_JAMBE:
            continue
        pc, p, fam = best
        jambes.append({"date": jour, "heure": m.get("heure"),
                       "ligue": m.get("ligue"), "home": m["home"],
                       "away": m["away"], "dom": dom, "fam": fam,
                       "option": f"{dom} {fam} corners",
                       "p_cal": pc, "p_brut": p,
                       "cote": round(1.0 / pc, 2)})
    if not jambes:
        return None
    jambes.sort(key=lambda j: (j.get("heure") or "99:99", j["home"]))
    cote = ptot = mise = 1.0
    for j in jambes:
        j["mise"] = round(mise, 2)
        mise *= 1.0 / j["p_cal"]
        cote *= 1.0 / j["p_cal"]
        ptot *= j["p_cal"]
    return {"jour": jour, "nom": "corners_montante",
            "p_combine": round(ptot, 4), "cote": round(cote, 2),
            "touche": None, "resolu_le": None, "jambes": jambes,
            "brut": {"regle": "tous les bons matchs du jour (meilleur handicap "
                              f">= {CN.MIN_JAMBE} mesuré), même jour uniquement",
                     "mise_fin": round(mise, 2)}}


def api_corners():
    """Résumé de calibration corners (backtest walk-forward) pour l'interface."""
    import corners as CN
    histo = None
    try:
        with open(os.path.join(RACINE, "data", "analyse_corners.json"),
                  encoding="utf-8") as f:
            histo = json.load(f)
    except (OSError, ValueError):
        pass
    return {"resume": CN.resume(), "bandes": CN._bandes(),
            "familles": [f for f, _ in CN.FAMILLES],
            "min_jambe": CN.MIN_JAMBE, "cible": CN.CIBLE_COUPON,
            "histo": histo}


def enrichir_secondaires(item):
    r = api_secondaires(item["div"], item["home"], item["away"], item.get("arbitre"))
    if not r:
        item["sec"] = None
        return item
    mk = r["marches"]
    item["sec"] = {
        "arbitre_couvert": r["arbitre_couvert"],
        "arbitre_info": r["arbitre_info"],
        "fautes": mk.get("fautes", {}).get("total_attendu"),
        "corners": mk.get("corners", {}).get("total_attendu"),
        "jaunes": mk.get("jaunes", {}).get("total_attendu"),
        "over": {m: mk[m]["over"] for m in mk},
        "lambda": {m: {"dom": mk[m]["lambda_home"], "ext": mk[m]["lambda_away"]}
                   for m in mk},
    }
    cf = r.get("confrontation")
    if cf:
        import corners as CN
        cf = dict(cf)
        # échelle CALIBRÉE (fréquences réelles walk-forward — corners.py) :
        # c'est elle qui décide du coupon montante et des cotes justes.
        cf["echelle_cal"] = {k: CN.calibrer(k, v) for k, v in cf["echelle"].items()}
        cor = mk.get("corners", {})
        cf["over_cal"] = {k: CN.calibrer_total(v)
                          for k, v in (cor.get("over") or {}).items()}
        cf["under_cal"] = {k: CN.calibrer_total(v)
                           for k, v in (cor.get("under") or {}).items()}
        item["sec"]["confrontation"] = cf
    if r.get("cmt1") and item.get("sec"):
        item["sec"]["cmt1"] = r["cmt1"]     # corners 1re mi-temps
    return item


ROUTES = {"/api/ligues": lambda q: api_ligues(),
          "/api/secondaires": lambda q: api_secondaires(
              q.get("div", [""])[0], q.get("home", [""])[0], q.get("away", [""])[0],
              q.get("arbitre", [None])[0]),
          "/api/classement": lambda q: api_classement(q.get("div", [""])[0]),
          "/api/pronostic": lambda q: pronostic(q.get("div", [""])[0],
                                                q.get("home", [""])[0], q.get("away", [""])[0]),
          "/api/fleuves": lambda q: api_fleuves(q.get("div", [""])[0], int(q.get("top", ["12"])[0])),
          "/api/matchs": lambda q: api_matchs(),
          "/api/conseils": lambda q: api_conseils(float(q.get("seuil", ["0.75"])[0])),
          "/api/refresh": lambda q: api_refresh(),
          "/api/maj": lambda q: api_maj(),
          "/api/bilan": lambda q: api_bilan(),
          "/api/corners": lambda q: api_corners(),
          "/api/suivi": lambda q: suivi.vue()}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype, gz=False):
        raw = body.encode() if isinstance(body, str) else body
        hdrs = {"Content-Type": ctype, "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": "*", "Content-Length": str(len(raw))}
        if gz:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb") as g:
                g.write(raw)
            raw = buf.getvalue()
            hdrs["Content-Encoding"] = "gzip"
            hdrs["Content-Length"] = str(len(raw))
        try:
            self.send_response(code)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            # le client a ferme l'onglet / annule la requete : sans consequence
            pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        gz = "gzip" in self.headers.get("Accept-Encoding", "")
        if u.path == "/" or u.path == "/index.html":
            p = os.path.join(RACINE, "static", "index.html")
            if os.path.exists(p):
                return self._send(200, open(p, "rb").read(), "text/html; charset=utf-8", gz)
            return self._send(404, "index.html manquant", "text/plain")
        if u.path in ROUTES:
            try:
                r = ROUTES[u.path](q)
            except Exception as e:
                return self._send(500, json.dumps({"erreur": str(e)}), "application/json")
            if r is None:
                return self._send(404, json.dumps({"erreur": "introuvable"}), "application/json")
            return self._send(200, json.dumps(r, ensure_ascii=False), "application/json; charset=utf-8", gz)
        return self._send(404, "route inconnue", "text/plain")


if __name__ == "__main__":
    class Serveur(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

        def handle_error(self, request, client_address):
            exc = sys.exc_info()[1]
            if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                return                  # deconnexion benigne du navigateur
            super().handle_error(request, client_address)

    srv = Serveur(("0.0.0.0", PORT), H)
    print(f"Application de pronostics demarree sur 0.0.0.0:{PORT}")
    print(f"  {len(DB['ligues'])} ligues | {len(DB.get('fixtures', []))} matchs a venir")
    srv.serve_forever()
