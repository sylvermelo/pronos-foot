"""
Serveur de l'application de pronostics.

Stdlib uniquement (http.server) : aucune dependance a installer, demarrage instantane.
Les modeles sont pre-entraines dans data/modeles.json -> reponse < 20 ms.
"""
import json, os, sys, gzip, io, urllib.parse, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from scipy.stats import poisson
import modeles_secondaires as MS

MAXG = 10
PORT = int(os.environ.get("PORT", 8000))
RACINE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(RACINE, "data/modeles.json")) as f:
    DB = json.load(f)

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


def matrice_scores(lig, home, away):
    """Matrice 11x11 des probabilites de score exact (Dixon-Coles)."""
    cle = (lig, home, away)
    if cle in _CACHE:
        return _CACHE[cle]
    L = DB["ligues"].get(lig)
    if not L:
        return None
    F = L["forces"]
    if home not in F or away not in F:
        return None
    att_h, dfn_h = F[home]["att"], F[home]["dfn"]
    att_a, dfn_a = F[away]["att"], F[away]["dfn"]
    lam = min(max(att_h * dfn_a * L["gamma"], 1e-6), 30)
    mu = min(max(att_a * dfn_h * L["s_away"], 1e-6), 30)
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
    r = matrice_scores(lig, home, away)
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


def api_conseils(seuil=0.75):
    """Sélection conseillée : pour chaque match à venir, l'option la plus
    probable parmi un panier de marchés « pariables » (1X2, over/under
    1.5-3.5, les deux équipes marquent, double chance). Si la probabilité
    de la meilleure option atteint le seuil, le match entre dans la liste.
    Rappel honnête : une probabilité élevée n'est pas un gain garanti."""
    seuil = float(seuil)
    jours = {}
    for m in api_matchs():
        if not m.get("disponible") or not m.get("over"):
            continue
        o, u, dc = m["over"], m["under"], m.get("double_chance", {})
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
        if p < seuil:
            continue
        item = {"div": m["div"], "ligue": m["ligue"], "pays": m["pays"],
                "date": m["date"], "heure": m["heure"], "jour": m["jour"],
                "jour_delta": m["jour_delta"],
                "home": m["home"], "away": m["away"],
                "option": opt, "p": round(p, 4),
                "cote_juste": round(1 / p, 2) if p > 0 else None,
                "confiance": m.get("confiance"), "buts": m.get("buts")}
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
    return {"seuil": seuil, "jours": liste,
            "note": "Probabilités du modèle Dixon-Coles calibré sur 29 295 matchs. "
                    "Une option à 75 % se réalise environ 3 fois sur 4 en moyenne, "
                    "pas à chaque fois. Rentabilité face aux cotes non démontrée "
                    "(voir l'onglet Fiabilité)."}


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
    return MS.pronostiquer(modele, home, away, arbitre or None)


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
          "/api/bilan": lambda q: api_bilan()}


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
