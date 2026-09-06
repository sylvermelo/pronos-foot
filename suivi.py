"""
SUIVI DES PRONOSTICS — « prédictions d'hier vs résultats réels ».

Principe (honnête, sans triche) :
  1. À chaque mise à jour (toutes les heures), on ARCHIVE la sélection conseillée
     du moment (seuil 75 %) dans data/suivi.json, sous la date du jour.
     Le dernier passage de la journée écrase les précédents : c'est l'état le
     plus frais des conseils avant les matchs.
  2. Quand un match archivé est terminé, on récupère le score FINAL sur ESPN
     (sans clé) et on marque l'option conseillée comme touchée / manquée.
  3. L'onglet « Pronos vs Résultats » affiche le bilan, jour par jour.

Limites documentées :
  · seuls les marchés de BUTS sont vérifiables gratuitement (1X2, over/under,
    les deux marquent, double chance) — fautes/corners/cartons ne le sont pas ;
  · les prédictions ne commencent que le jour où ce fichier existe : rien
    d'antérieur n'est inventé (le comblement rétroactif, s'il y en a un, est
    explicitement marqué "retro" et n'existe que si le modèle n'avait pas
    encore vu ces matchs à l'entraînement) ;
  · le gain simulé suppose 1 unité misée sur chaque sélection cotée, sans
    gestion de bankroll : c'est un indicateur, pas un conseil financier.
"""
import datetime
import json
import os

import calendrier as CAL

CHEMIN = os.path.join("data", "suivi.json")
GARDE_JOURS = 30          # durée de conservation de l'archive
SEUIL_ARCHIVE = 0.75      # seuil de la sélection conseillée archivée


# ---------------------------------------------------------------- stockage
def charger():
    try:
        with open(CHEMIN, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("jours", {})
        return d
    except (OSError, ValueError):
        return {"jours": {}}


def sauver(d):
    d["maj"] = datetime.datetime.now().isoformat(timespec="minutes")
    tmp = CHEMIN + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, CHEMIN)


# ---------------------------------------------------------------- verdicts
def touche(option, bh, ba):
    """L'option conseillée s'est-elle réalisée ? (True/False, None si inconnu)"""
    t = bh + ba
    try:
        if option == "1":
            return bh > ba
        if option == "X":
            return bh == ba
        if option == "2":
            return bh < ba
        if option.startswith("over "):
            return t > float(option.split()[1])
        if option.startswith("under "):
            return t < float(option.split()[1])
        if option == "les deux marquent":
            return bh > 0 and ba > 0
        if option == "les deux ne marquent pas":
            return not (bh > 0 and ba > 0)
        if option == "double chance 1X":
            return bh >= ba
        if option == "double chance 12":
            return bh != ba
        if option == "double chance X2":
            return bh <= ba
    except (ValueError, IndexError):
        return None
    return None


# ---------------------------------------------------------------- archivage
def archiver(conseils, d=None, jour=None, retro=False):
    """Archive les sélections conseillées d'un jour — FUSION, jamais d'écrasement.

    conseils : réponse de api_conseils() (serveur.py)

    Règles (bug du 05-06/09/2026 corrigé ici) :
    - api_conseils() exclut les matchs déjà commencés. Si on ÉCRASAIT l'entrée
      du jour à chaque exécution, les matchs commencés disparaissaient de
      l'archive AVANT d'avoir pu être résolus → « toujours en attente ».
      Désormais : une sélection déjà archivée n'est JAMAIS supprimée.
    - Les sélections encore à venir sont rafraîchies (p, cotes…) à chaque
      passage ; leur résultat éventuel est conservé.
    - Combinés : la version archivée la première dans la journée est gardée
      (c'est la recommandation du matin, avant les premiers coups d'envoi) ;
      un type de combiné pas encore archivé est ajouté.
    """
    d = d if d is not None else charger()
    jour = jour or datetime.date.today().isoformat()
    sels = []
    for j in conseils.get("jours", []):
        for s in j.get("selections", []):
            sels.append({k: s.get(k) for k in
                         ("div", "ligue", "pays", "date", "heure", "home", "away",
                          "option", "p", "cote_juste", "cote_marche", "confiance",
                          "buts")})
    entree = d["jours"].get(jour) or {}

    def _cle(s):
        return (s.get("date"), s.get("home"), s.get("away"), s.get("option"))

    anciennes = {_cle(s): s for s in entree.get("selections", [])}
    vus = set()
    for s in sels:
        old = anciennes.get(_cle(s))
        if old is not None:
            s["resultat"] = old.get("resultat")    # résultat déjà résolu conservé
            vus.add(_cle(s))
        else:
            s["resultat"] = None                   # nouvelle sélection
    # les sélections archivées qui ont DISPARU des nouveaux conseils (matchs
    # déjà commencés) sont gardées telles quelles : elles seront résolues.
    gardees = [s for k, s in anciennes.items() if k not in vus]
    sels = sels + gardees
    sels.sort(key=lambda s: (s.get("date") or "", s.get("heure") or "",
                             s.get("div") or "", s.get("home") or ""))

    # combinés : reporter les jambes déjà résolues (évite de re-interroger ESPN)
    anciens_comb = {}
    for c in (entree.get("combines") or {}).values():
        if isinstance(c, dict):
            for l in c.get("legs") or []:
                if l.get("resultat"):
                    anciens_comb[(l.get("date"), l.get("home"), l.get("away"),
                                  l.get("option"))] = l["resultat"]
    comb = dict(entree.get("combines") or {})      # on GARDE ceux déjà archivés
    for k, c in (conseils.get("combines") or {}).items():
        if k in comb:
            continue                               # version du matin conservée
        if isinstance(c, dict):
            for l in c.get("legs") or []:
                r = anciens_comb.get((l.get("date"), l.get("home"), l.get("away"),
                                      l.get("option")))
                if r:
                    l["resultat"] = r
        comb[k] = c
    d["jours"][jour] = {
        "genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
        "seuil": SEUIL_ARCHIVE, "retro": bool(retro), "selections": sels,
        "combines": comb}
    return d


# ---------------------------------------------------------------- résolution
def resoudre(d, db):
    """Récupère les scores finaux (ESPN) des matchs archivés non résolus.

    Résout les sélections ET chaque jambe des combinés (une jambe peut être
    une option cotée qui n'est pas dans la sélection conseillée du match).
    Retourne (d, n_nouveaux). Un match sans score disponible reste en attente
    et sera retenté au passage suivant.
    """
    auj = datetime.date.today()
    eq = {div: sorted(L["forces"].keys()) for div, L in db.get("ligues", {}).items()}
    map_ = CAL.Mappeur(eq)
    cache = {}                                 # (div, date) → {(h, a): (bh, ba)}

    def score_de(div, date_m, home, away):
        if not div or not date_m or not home or not away:
            return None
        try:
            dm = datetime.date.fromisoformat(date_m)
        except ValueError:
            return None
        if dm > auj:
            return None                        # pas encore joué
        cle = (div, date_m)
        if cle not in cache:
            idx = {}
            slug = CAL.ESPN_SLUGS.get(div)
            if slug:
                for r in CAL.espn_resultats(slug, date_m):
                    h = map_.traduire(div, r["home_src"])
                    a = map_.traduire(div, r["away_src"])
                    if h and a:
                        idx[(h, a)] = (r["buts_home"], r["buts_away"])
            cache[cle] = idx
        return cache[cle].get((home, away))

    def marquer(s):
        sc = score_de(s.get("div"), s.get("date"), s.get("home"), s.get("away"))
        if not sc:
            return False
        bh, ba = sc
        s["resultat"] = {"buts_home": bh, "buts_away": ba,
                         "touche": touche(s.get("option"), bh, ba),
                         "resolu_le": auj.isoformat()}
        return True

    n = 0
    for jour, entree in d["jours"].items():
        for s in entree.get("selections", []):
            if not s.get("resultat") and marquer(s):
                n += 1
        # combinés : chaque jambe est résolue indépendamment, puis le verdict
        for c in (entree.get("combines") or {}).values():
            if not isinstance(c, dict):
                continue
            legs = c.get("legs") or []
            for l in legs:
                if not l.get("resultat") and marquer(l):
                    n += 1
            if legs and all(l.get("resultat") for l in legs):
                c["resultat"] = {
                    "touche": all(bool(l["resultat"].get("touche")) for l in legs),
                    "legs": [{"home": l.get("home"), "away": l.get("away"),
                              "option": l.get("option"),
                              "score": "{}:{}".format(l["resultat"]["buts_home"],
                                                      l["resultat"]["buts_away"]),
                              "touche": bool(l["resultat"].get("touche"))}
                             for l in legs]}
            else:
                c.pop("resultat", None)
    # purge des jours trop anciens
    coupe = (auj - datetime.timedelta(days=GARDE_JOURS)).isoformat()
    d["jours"] = {k: v for k, v in d["jours"].items() if k >= coupe}
    return d, n


def _pnl(s):
    """Gain simulé : 1 unité misée si une cote marché existe, sinon None."""
    r = s.get("resultat")
    c = s.get("cote_marche")
    if not r or not c:
        return None
    return round(c - 1.0, 2) if r.get("touche") else -1.0


def _combines_vue(combines):
    """Combinés du jour + gain simulé (1 unité) quand la cote est connue."""
    out = {}
    for nom in ("safe", "safe_weekend", "risque"):
        c = combines.get(nom)
        if not isinstance(c, dict):
            continue
        r = c.get("resultat")
        pnl = None
        if r and c.get("cote_combine"):
            pnl = round(c["cote_combine"] - 1.0, 2) if r.get("touche") else -1.0
        out[nom] = {**c, "pnl": pnl}
    return out


def vue():
    """Construit la réponse de /api/suivi (serveur) ou de DATA.suivi (autonome)."""
    d = charger()
    auj = datetime.date.today()
    jours = []
    for jour in sorted(d["jours"], reverse=True):
        e = d["jours"][jour]
        sels = e.get("selections", [])
        res = [s for s in sels if s.get("resultat")]
        touch = [s for s in res if s["resultat"].get("touche")]
        pnl = [p for p in (_pnl(s) for s in res) if p is not None]
        try:
            delta = (auj - datetime.date.fromisoformat(jour)).days
        except ValueError:
            delta = 0
        jours.append({
            "jour_prono": jour,
            "libelle": ("Aujourd'hui" if delta == 0 else "Hier (la veille)"
                        if delta == 1 else f"Il y a {delta} jours"),
            "delta_jours": delta,
            "genere_le": e.get("genere_le"), "seuil": e.get("seuil", SEUIL_ARCHIVE),
            "retro": bool(e.get("retro")),
            "nb": len(sels), "nb_resolus": len(res), "nb_touches": len(touch),
            "taux": round(len(touch) / len(res), 4) if res else None,
            "pnl": round(sum(pnl), 2) if pnl else None,
            "selections": [{**s, "pnl": _pnl(s)} for s in sels],
            "combines": _combines_vue(e.get("combines") or {}),
        })
    fam = {}
    for j in jours:
        for s in j["selections"]:
            r = s.get("resultat")
            if not r:
                continue
            o = s.get("option") or ""
            cle = ("under" if o.startswith("under") else
                   "over" if o.startswith("over") else o)
            t = fam.setdefault(cle, [0, 0])
            t[0] += 1
            t[1] += 1 if r.get("touche") else 0
    par_marche = {k: {"resolus": v[0], "touches": v[1],
                      "taux": round(v[1] / v[0], 4)}
                  for k, v in sorted(fam.items(), key=lambda z: -z[1][0])}
    t_res = sum(j["nb_resolus"] for j in jours)
    t_tou = sum(j["nb_touches"] for j in jours)
    t_pnl = [j["pnl"] for j in jours if j["pnl"] is not None]
    return {
        "jours": jours,
        "total": {"selections": sum(j["nb"] for j in jours), "resolus": t_res,
                  "touches": t_tou,
                  "taux": round(t_tou / t_res, 4) if t_res else None,
                  "pnl": round(sum(t_pnl), 2) if t_pnl else None},
        "par_marche": par_marche,
        "depuis": min((j["jour_prono"] for j in jours), default=None),
        "note": ("Suivi réel : chaque sélection conseillée (seuil 75 %) est archivée "
                 "puis comparée au score final officiel (ESPN). Une option à 75 % "
                 "se réalise environ 3 fois sur 4 EN MOYENNE — les séries de misses "
                 "font partie du jeu. Le gain simulé (1 unité par sélection cotée) "
                 "n'est pas un conseil financier. Marchés de buts uniquement : "
                 "fautes, corners et cartons ne sont pas vérifiables gratuitement."),
        "maj": d.get("maj"),
    }
