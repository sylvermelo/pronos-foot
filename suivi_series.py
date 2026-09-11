"""SUIVI BUTS D'AFFILÉE — conseils « NON » du jour pour la vitrine.

Règle utilisateur (11/09) : dans « Choix exotiques → But d'affilée », UN SEUL
conseil clair par match, uniquement des NON (jamais de but d'affilée
affirmatif) : « 2 d'affilée — NON », « 3 d'affilée — NON », « équipe X
N d'affilée — NON », avec sa probabilité mesurée (60 à 100 %).

Fonctionnement (même philosophie honnête que suivi.py) :
  1. À chaque mise à jour, on ARCHIVE les conseils NON du jour dans
     data/suivi_series.json. Fusion : un match archivé n'est JAMAIS retiré
     (il disparaît du calendrier au coup d'envoi — seul l'archive le garde
     toute la journée) ; la probabilité est rafraîchie tant que le match
     n'a pas commencé.
  2. Quand le match est fini, on résout via ESPN avec le parseur de
     buts_affilee.py (buts minutés, triple vérification, jamais d'imputation ;
     cache data/buts_minutes.json partagé).
  3. Vue publiée pour la vitrine (10 derniers jours) : data/affilee_suivi.json,
     copié vers site/ par la CI → lu en same-origin par la vitrine.

Un conseil par match, point. Pas de coupon, pas de combiné.
"""
import datetime
import json
import os

import serveur
from serveur import pronostic, DB
import buts_affilee as BA
import calendrier as CAL

RACINE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(RACINE, "data", "suivi_series.json")
PUBLIE = os.path.join(RACINE, "data", "affilee_suivi.json")
GARDE_JOURS = 10       # fenêtre publiée (la vitrine affiche 7 jours)
RESOUT_JOURS = 8       # on tente de résoudre jusqu'à 8 jours en arrière
SEUIL_MIN = 0.60       # en dessous : pas de conseil (le robot s'abstient)
SEUIL_MAX = 0.97       # au-dessus : conseil « trop gratuit », on préfère en dessous


def _source():
    """Matchs à venir : calendrier.json (frais, multi-sources) sinon fixtures."""
    fx = DB.get("fixtures", [])
    cal = os.path.join(RACINE, "data", "calendrier.json")
    if os.path.exists(cal):
        try:
            with open(cal, encoding="utf-8") as f:
                fx = json.load(f).get("matchs", []) or fx
        except (ValueError, OSError):
            pass
    return fx


def non_pick(home, away, p):
    """UN seul conseil NON par match : la probabilité la plus haute parmi
    celles ≤ 97 % (au-dessus, le conseil est « trop gratuit »), plancher 60 %."""
    cands = [
        (1 - p["serie3_dom"], "dom3", f"{home} marque 3 buts d'affilée — NON"),
        (1 - p["serie3_ext"], "ext3", f"{away} marque 3 buts d'affilée — NON"),
        (1 - p["serie3"], "match3", "Une équipe marque 3 buts d'affilée — NON"),
        (1 - p["serie2_dom"], "dom2", f"{home} marque 2 buts d'affilée — NON"),
        (1 - p["serie2_ext"], "ext2", f"{away} marque 2 buts d'affilée — NON"),
        (1 - p["serie2"], "match2", "Une équipe marque 2 buts d'affilée — NON"),
    ]
    elig = [(pp, c, l) for pp, c, l in cands
            if pp is not None and pp >= SEUIL_MIN]
    if not elig:
        return None
    elig.sort(key=lambda e: (e[0] <= SEUIL_MAX, e[0]), reverse=True)
    pp, c, l = elig[0]
    return {"code": c, "option": l, "p": round(pp, 4),
            "cote_juste": round(1.0 / pp, 2)}


# ------------------------------------------------------------------ archive
def _charger():
    if os.path.exists(ARCHIVE):
        try:
            with open(ARCHIVE, encoding="utf-8") as f:
                a = json.load(f)
                a.setdefault("jours", {})
                return a
        except (ValueError, OSError):
            pass
    return {"jours": {}}


def archiver(a):
    auj = datetime.date.today().isoformat()
    e = a["jours"].setdefault(auj, {"matchs": []})
    par_cle = {(m["home"], m["away"]): m for m in e["matchs"]}
    n_ajout = n_maj = 0
    for fx in _source():
        if fx.get("date") != auj:
            continue
        p = pronostic(fx["div"], fx["home"], fx["away"])
        if not p or p.get("serie2") is None:
            continue
        non = non_pick(fx["home"], fx["away"], p)
        if non is None:
            continue
        cle = (fx["home"], fx["away"])
        if cle in par_cle:
            m = par_cle[cle]
            if m.get("resultat") is None:
                m["non"] = non            # état le plus frais avant coup d'envoi
                n_maj += 1
        else:
            lig = DB["ligues"].get(fx["div"])
            e["matchs"].append({
                "div": fx["div"], "ligue": lig["nom"] if lig else fx["div"],
                "heure": fx.get("heure") or "", "home": fx["home"],
                "away": fx["away"], "non": non, "resultat": None})
            par_cle[cle] = e["matchs"][-1]
            n_ajout += 1
    e["matchs"].sort(key=lambda m: (m.get("heure") or "99:99", m["home"]))
    return n_ajout, n_maj


# --------------------------------------------------------------- résolution
def series_de_buts(buts):
    """Longueurs maximales de séries d'affilée depuis les buts minutés."""
    max_match = max_home = max_away = cur = 0
    cote = None
    for b in sorted(buts, key=lambda x: x.get("min") or 0):
        if b.get("equipe") == cote:
            cur += 1
        else:
            cote, cur = b.get("equipe"), 1
        max_match = max(max_match, cur)
        if cote == "home":
            max_home = max(max_home, cur)
        elif cote == "away":
            max_away = max(max_away, cur)
    return {"max_match": max_match, "max_home": max_home, "max_away": max_away}


def juge(code, r):
    return {"match2": r["max_match"] < 2, "match3": r["max_match"] < 3,
            "dom2": r["max_home"] < 2, "dom3": r["max_home"] < 3,
            "ext2": r["max_away"] < 2, "ext3": r["max_away"] < 3}.get(code)


def _trouve_event(evs, m):
    """Match terminé ↔ conseil archivé : inclusion de noms normalisés dans les
    DEUX sens (« Sp Braga » ⊂ « Braga » non, mais « Braga » ⊂ « spbraga »… on
    teste donc a⊂b OU b⊂a). Jamais de retrait de suffixe (City/United)."""
    def ok(a, b):
        na, nb = BA._norme(a), BA._norme(b)
        return bool(na) and bool(nb) and (na == nb or na in nb or nb in na)
    for eid, info in evs.items():
        if ok(info.get("home"), m["home"]) and ok(info.get("away"), m["away"]):
            return eid, info
    return None


def resoudre(a):
    auj = datetime.date.today().isoformat()
    cache = BA._charge_cache()
    cache_modif = False
    n_res = 0
    for jour in sorted(a["jours"]):
        d = datetime.date.fromisoformat(jour)
        if (datetime.date.today() - d).days > RESOUT_JOURS or jour > auj:
            continue
        en_attente = [m for m in a["jours"][jour]["matchs"]
                      if m.get("resultat") is None]
        if not en_attente:
            continue
        par_div = {}
        for m in en_attente:
            par_div.setdefault(m["div"], []).append(m)
        for div, ms in par_div.items():
            if div not in CAL.ESPN_SLUGS:
                continue                    # non vérifiable ESPN — reste en attente
            try:
                evs = BA.journees(div, jour, jour)
            except SystemExit:
                continue
            slug = CAL.ESPN_SLUGS[div]
            for m in ms:
                trouve = _trouve_event(evs, m)
                if not trouve:
                    continue                # pas encore fini (ou introuvable)
                eid, info = trouve
                cle = f"{div}:{eid}"
                ent = cache.get(cle)
                if ent is None or ent.get("rejete"):
                    s = CAL._curl_json(f"{BA.BASE}/{slug}/summary?event={eid}")
                    buts = BA.extraire_buts(s, info["home"], info["away"],
                                            info["sh"], info["sa"]) if s else None
                    ent = {"div": div, "id": eid, "date": info["date"],
                           "home": info["home"], "away": info["away"],
                           "sh": info["sh"], "sa": info["sa"],
                           "buts": buts, "rejete": buts is None}
                    cache[cle] = ent
                    cache_modif = True
                resolu_le = datetime.datetime.now().isoformat(timespec="minutes")
                if ent.get("rejete") or not ent.get("buts"):
                    # score connu mais buts minutés non vérifiables → on ne
                    # tranche PAS le conseil (honnêteté), score affiché quand même
                    m["resultat"] = {"verifiable": False, "touche": None,
                                     "sh": info["sh"], "sa": info["sa"],
                                     "resolu_le": resolu_le}
                else:
                    r = series_de_buts(ent["buts"])
                    m["resultat"] = {"verifiable": True,
                                     "touche": juge(m["non"]["code"], r),
                                     "sh": info["sh"], "sa": info["sa"],
                                     "series": r, "resolu_le": resolu_le}
                n_res += 1
    if cache_modif:
        BA._sauve_cache(cache)
    return n_res


# ------------------------------------------------------------------ publication
def publier(a):
    jours = sorted(a["jours"])[-GARDE_JOURS:]
    vue = {
        "genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
        "jour": datetime.date.today().isoformat(),
        "jours": {j: a["jours"][j] for j in jours},
        "note": ("Un seul conseil NON par match (jamais de but d'affilée "
                 "affirmatif), probabilités mesurées sur 2 923 matchs réels "
                 "puis corrigées. Résultats résolus sur les buts minutés ESPN "
                 "(triple vérification, jamais d'imputation). Information "
                 "chiffrée, jamais un conseil d'argent : aucun bookmaker de "
                 "nos sources ne propose ces marchés."),
    }
    with open(PUBLIE, "w", encoding="utf-8") as f:
        json.dump(vue, f, ensure_ascii=False)
    return vue


def _nettoie(a):
    """Ne garde que 30 jours d'archive glissante."""
    cut = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    a["jours"] = {j: e for j, e in a["jours"].items() if j >= cut}


if __name__ == "__main__":
    a = _charger()
    n_ajout, n_maj = archiver(a)
    n_res = resoudre(a)
    _nettoie(a)
    a["maj"] = datetime.datetime.now().isoformat(timespec="minutes")
    with open(ARCHIVE, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False)
    vue = publier(a)
    auj = vue["jour"]
    m_auj = vue["jours"].get(auj, {}).get("matchs", [])
    en_attente = sum(1 for m in m_auj if m.get("resultat") is None)
    print(f"suivi_series : {len(m_auj)} conseils NON aujourd'hui "
          f"(+{n_ajout} ajoutés, {n_maj} rafraîchis), {n_res} résolus ce run, "
          f"{en_attente} en attente")
