#!/usr/bin/env python3
"""BUTS D'AFFILÉE — collecte des buts minutés + mesures + modèle exact.

Voir docs/SPEC-BUTS-AFFILEE.md (définitions, critères, limites).

Commandes :
  python3 buts_affilee.py collecter E0 2025-08-01 2026-05-31 [--limite N]
      Collecte incrémentale (cache data/buts_minutes.json) : énumère les
      matchs FINIS via le scoreboard ESPN (fenêtres ≤ 42 jours, REGLES §4),
      puis lit les buts minutés dans summary.keyEvents. Un match dont la
      séquence est incohérente est marqué « rejete » (jamais d'imputation).
  python3 buts_affilee.py rapport
      Mesures : P(série 2+/3+), par ligue et par total de buts, test de
      momentum, effet d'état du score, écarts en minutes + modèle théorique
      exact (Poisson fusionné) pour comparaison. Écrit
      data/buts_affilee_stats.json.

RÈGLES respectées : ESPN via curl (jamais urllib), aucun coefficient inventé,
données rejetées plutôt qu'approximées, lecture seule (rien ne modifie le
calendrier ni les sélections).
"""
import datetime
import json
import math
import os
import re
import sys
import time
import unicodedata

import calendrier  # réutilise _curl_json (ESPN via curl) et ESPN_SLUGS

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
CACHE = os.path.join("data", "buts_minutes.json")
STATS = os.path.join("data", "buts_affilee_stats.json")

RE_MIN = re.compile(r"(\d+)(?:'\s*\+\s*(\d+))?")
# Paire de scores en fin de phrase : « Fulham 1, Manchester United 1 ».
# Noms sans chiffre ni virgule ; le préfixe « Goal! » est retiré avant.
RE_SCORE = re.compile(r"([^\d,]+?)\s+(\d{1,2})\s*,\s*([^\d,]+?)\s+(\d{1,2})\s*\.?$")
# Types d'évènements qui sont des buts (mesuré le 10/09 sur E0) :
#  · « Goal », « Goal - Header », « Goal - Volley », « Goal - Free-kick »…
#  · « Penalty - Scored » (texte commençant quand même par « Goal! A x, B y. »)
#  · « Own Goal » (texte « Own Goal by X, Équipe. A x, B y. » — le but compte
#    pour l'équipe qui en bénéficie, d'où l'attribution par score progressif)
TYPES_BUT = ("penalty - scored", "own goal")


def _est_but(typ):
    tl = str(typ or "").lower()
    return tl.startswith("goal") or tl in TYPES_BUT


def _norme(s):
    """Normalisation tolérante des noms d'équipes.

    « Brighton & Hove Albion » (scoreboard) et « Brighton and Hove Albion »
    (texte des buts) doivent donner la même clé : « & » et « and » sautent.
    Les accents aussi : « Alavés » (scoreboard) vs « Alaves » (texte) — mesuré
    le 10/09 sur SP1 (72 matchs rejetés à tort avant ce correctif).
    ATTENTION : pas de retrait des suffixes (City/United/…) — mesuré le 10/09 :
    « Manchester City » et « Manchester United » collisionneraient en
    « manchester » et le match serait rejeté à tort.
    """
    x = unicodedata.normalize("NFKD", str(s or "").lower())
    x = "".join(c for c in x if not unicodedata.combining(c))
    x = re.sub(r"[^a-z0-9 ]", " ", x)
    x = re.sub(r"\band\b", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


# ------------------------------------------------------------------ cache
def _charge_cache():
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def _sauve_cache(c):
    tmp = CACHE + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)
    os.replace(tmp, CACHE)


# ------------------------------------------------------------- collecte
def journees(div, debut, fin):
    """Matchs FINIS d'une division entre deux dates, via scoreboard ESPN.

    Fenêtres de 42 jours maximum (REGLES §4). Rend {event_id: infos}.
    """
    slug = calendrier.ESPN_SLUGS.get(div)
    if not slug:
        raise SystemExit(f"division inconnue : {div} (voir calendrier.ESPN_SLUGS)")
    d0 = datetime.date.fromisoformat(debut)
    d1 = min(datetime.date.fromisoformat(fin), datetime.date.today())
    evs = {}
    cur = d0
    while cur <= d1:
        w_end = min(cur + datetime.timedelta(days=41), d1)
        d = calendrier._curl_json(
            f"{BASE}/{slug}/scoreboard?dates={cur:%Y%m%d}-{w_end:%Y%m%d}")
        for e in (d or {}).get("events", []):
            st = ((e.get("status") or {}).get("type") or {})
            if not st.get("completed"):
                continue
            comp = (e.get("competitions") or [{}])[0]
            h = a = None
            sh = sa = None
            for co in comp.get("competitors", []):
                nom = (co.get("team") or {}).get("displayName")
                try:
                    buts = int(co.get("score"))
                except (TypeError, ValueError):
                    buts = None
                if co.get("homeAway") == "home":
                    h, sh = nom, buts
                elif co.get("homeAway") == "away":
                    a, sa = nom, buts
            if h and a and e.get("id"):
                evs[str(e["id"])] = {
                    "div": div, "date": (e.get("date") or "")[:10],
                    "home": h, "away": a, "sh": sh, "sa": sa}
        cur = w_end + datetime.timedelta(days=1)
        time.sleep(0.2)
    return evs


def _minute(ev):
    txt = ((ev.get("clock") or {}).get("displayValue")) or \
          ((ev.get("time") or {}).get("displayValue")) or ""
    m = RE_MIN.search(txt)
    if not m:
        return None
    return int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0)


def _evenements_buts(summary):
    """Évènements-buts depuis le COMMENTARY (complet — vérifié le 10/09 sur
    Fulham-Man U, Man U-Burnley, Fulham-Leeds où keyEvents était tronqué),
    avec repli sur keyEvents.

    Rend [(minute_texte, type, nom_équipe_structuré, texte)]. Le nom vient du
    champ structuré play.team / team : c'est le nom ESPN officiel (identique
    au scoreboard), PAS le nom traduit du texte (« FC Bayern München » dans le
    texte vs « Bayern Munich » en structuré — mesuré le 10/09 sur D1).
    Pour un « Own Goal », play.team = l'équipe qui BÉNÉFICIE du but (vérifié
    le 10/09 sur Fulham-Leeds : but de Gudmundsson (Leeds) → team=Fulham).
    """
    com = summary.get("commentary") or []
    evs = []
    for c in com:
        play = c.get("play") or {}
        typ = ((play.get("type")) or {}).get("text")
        if not _est_but(typ):
            continue
        tm = (c.get("time") or {}).get("displayValue") or \
             ((play.get("clock")) or {}).get("displayValue") or ""
        equipe = (play.get("team") or {}).get("displayName")
        evs.append((tm, str(typ), equipe, c.get("text") or ""))
    if evs:
        return evs
    for ev in summary.get("keyEvents") or []:       # repli
        typ = ((ev.get("type") or {}).get("text")) or ""
        if not _est_but(typ):
            continue
        tm = ((ev.get("clock") or {}).get("displayValue")) or \
             ((ev.get("time") or {}).get("displayValue")) or ""
        equipe = (ev.get("team") or {}).get("displayName")
        evs.append((tm, str(typ), equipe, ev.get("text") or ""))
    return evs


def _score_apres(txt):
    """Paires de scores CANDIDATES lues dans le texte — vérification croisée.

    Les noms d'équipes allemands contiennent des chiffres et des points
    (« 1. FC Heidenheim 1846 », « 1. FSV Mainz 05 » — mesuré le 10/09 sur
    D1) : un parseur positionnel s'y trompe. À la place, on liste tous les
    chiffres suivis d'une virgule (candidats score domicile) et tous ceux
    suivis d'un point (candidats score extérieur) ; le match n'est rejeté que
    si AUCUNE combinaison ne correspond au score officiel progressif.
    [] = texte sans candidats (cross-check impossible, les autres
    vérifications suffisent).
    """
    s1 = [int(m.group(1)) for m in re.finditer(r"(?<!\d)(\d{1,2})\s*,", txt)]
    s2 = [int(m.group(1)) for m in re.finditer(r"(?<!\d)(\d{1,2})\s*\.", txt)]
    return [(a, b) for a in s1 for b in s2]


def extraire_buts(summary, home, away, sh_fin, sa_fin):
    """Buts minutés d'un summary ESPN — None si le moindre doute.

    Attribution par le champ structuré play.team (nom ESPN officiel). Pour les
    buts contre son camp, ESPN donne déjà l'équipe bénéficiaire. Triple
    vérification : minute lisible, progression du score (cross-check texte si
    parseable), score final reconstitué == score officiel ET nombre
    d'évènements == nombre de buts. Sinon rejet — jamais d'imputation.
    """
    evs = _evenements_buts(summary)
    if not evs and (sh_fin or sa_fin):
        return None                          # des buts mais aucun évènement
    hn, an = _norme(home), _norme(away)

    def equipe(nom):
        n = _norme(nom)
        if not n:
            return None
        if n == hn or n in hn or hn in n:
            return "home"
        if n == an or n in an or an in n:
            return "away"
        return None

    buts, sh, sa = [], 0, 0
    for tm, typ, nom, txt in evs:
        mn_match = RE_MIN.search(tm or "")
        if not mn_match:
            return None                      # minute illisible → rejeté
        mn = int(mn_match.group(1)) + (int(mn_match.group(2)) if mn_match.group(2) else 0)
        cote = equipe(nom)
        if not cote:
            return None                      # équipe inconnue → rejeté
        if cote == "home":
            sh += 1
        else:
            sa += 1
        cands = _score_apres(txt)
        if cands and (sh, sa) not in cands:
            return None                      # contradiction avec le texte → rejeté
        buts.append({"min": mn, "equipe": cote})
    if sh_fin is not None and sa_fin is not None and (sh != sh_fin or sa != sa_fin):
        return None                          # score final différent → rejeté
    if len(evs) != sh + sa:
        return None
    buts.sort(key=lambda b: b["min"])        # stable : ordre du flux conservé
    return buts


def collecter(div, debut, fin, limite=None):
    cache = _charge_cache()
    # les matchs rejetés sont réessayés à chaque lancement (le parseur peut
    # avoir été amélioré depuis) ; les matchs valides ne sont jamais refaits
    n_retry = sum(1 for v in cache.values() if v.get("rejete"))
    cache = {k: v for k, v in cache.items() if not v.get("rejete")}
    if n_retry:
        print(f"{n_retry} matchs précédemment rejetés → nouvelle tentative")
    evs = journees(div, debut, fin)
    slug = calendrier.ESPN_SLUGS[div]
    todo = [(i, v) for i, v in evs.items() if f"{div}:{i}" not in cache]
    print(f"{div} : {len(evs)} matchs finis trouvés, {len(todo)} à collecter")
    n_new = n_ok = n_rej = n_ech = 0
    for eid, info in todo:
        s = calendrier._curl_json(f"{BASE}/{slug}/summary?event={eid}")
        cle = f"{div}:{eid}"
        entree = {"div": div, "id": eid, "date": info["date"],
                  "home": info["home"], "away": info["away"],
                  "sh": info["sh"], "sa": info["sa"]}
        if not s:
            n_ech += 1                       # non stocké : sera retenté
        else:
            buts = extraire_buts(s, info["home"], info["away"],
                                 info["sh"], info["sa"])
            entree["buts"] = buts
            entree["rejete"] = buts is None
            cache[cle] = entree
            n_new += 1
            if buts is None:
                n_rej += 1
            else:
                n_ok += 1
        if n_new and n_new % 25 == 0:
            _sauve_cache(cache)
            print(f"  … {n_new} collectés ({n_ok} valides, {n_rej} rejetés, "
                  f"{n_ech} échecs réseau)", flush=True)
        time.sleep(0.1)
        if limite and n_new + n_ech >= limite:
            break
    _sauve_cache(cache)
    print(f"TERMINÉ {div} : {n_new} nouveaux dont {n_ok} valides, "
          f"{n_rej} rejetés, {n_ech} échecs réseau (non stockés, "
          f"relancer pour réessayer)")


# ------------------------------------------------------- modèle exact
# Source unique : series_buts.py (même module utilisé par serveur.py et
# mirroré en JS dans genere_app.py — parité REGLES §5).
from series_buts import p_no_run, p_serie, p_serie_team  # noqa: E402


# ------------------------------------------------------------- mesures
def _seq(entree):
    return "".join("H" if b["equipe"] == "home" else "A"
                   for b in entree["buts"])


def _max_run(seq):
    best = cur = 0
    for i, c in enumerate(seq):
        cur = cur + 1 if i and c == seq[i - 1] else 1
        best = max(best, cur)
    return best


def rapport():
    cache = _charge_cache()
    valides = [v for v in cache.values() if not v.get("rejete") and v.get("buts") is not None]
    rejetes = [v for v in cache.values() if v.get("rejete")]
    if not valides:
        print("Aucun match valide collecté — lancer d'abord : "
              "python3 buts_affilee.py collecter E0 2025-08-01 2026-05-31")
        return
    print(f"ÉCHANTILLON : {len(valides)} matchs valides, {len(rejetes)} rejetés "
          f"({100.0 * len(rejetes) / max(1, len(cache)):.1f} %)")

    out = {"genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
           "n_valides": len(valides), "n_rejetes": len(rejetes)}

    def bloc(matchs):
        n = len(matchs)
        if not n:
            return None
        seqs = [_seq(m) for m in matchs]
        s2h = sum(1 for s in seqs if "HH" in s)
        s2a = sum(1 for s in seqs if "AA" in s)
        s2 = sum(1 for s in seqs if "HH" in s or "AA" in s)
        s3 = sum(1 for s in seqs if "HHH" in s or "AAA" in s)
        return {"n": n,
                "p_serie2_any": round(s2 / n, 4),
                "p_serie2_home": round(s2h / n, 4),
                "p_serie2_away": round(s2a / n, 4),
                "p_serie3_any": round(s3 / n, 4)}

    out["global"] = bloc(valides)
    print("\n=== GLOBAL ===")
    for k, v in out["global"].items():
        print(f"  {k}: {v}")

    out["par_div"] = {}
    print("\n=== PAR LIGUE ===")
    for div in sorted({m["div"] for m in valides}):
        ms = [m for m in valides if m["div"] == div]
        out["par_div"][div] = bloc(ms)
        b = out["par_div"][div]
        print(f"  {div:4s} n={b['n']:4d}  série2+ {b['p_serie2_any'] * 100:5.1f} %  "
              f"(dom {b['p_serie2_home'] * 100:4.1f} / ext {b['p_serie2_away'] * 100:4.1f})  "
              f"série3+ {b['p_serie3_any'] * 100:4.1f} %")

    print("\n=== PAR TOTAL DE BUTS ===")
    out["par_total"] = {}
    for lib, lo, hi in (("0-1", 0, 1), ("2-3", 2, 3), ("4-5", 4, 5), ("6+", 6, 99)):
        ms = [m for m in valides if lo <= (m["sh"] or 0) + (m["sa"] or 0) <= hi]
        b = bloc(ms)
        out["par_total"][lib] = b
        if b:
            print(f"  {lib:4s} n={b['n']:4d}  série2+ {b['p_serie2_any'] * 100:5.1f} %  "
                  f"série3+ {b['p_serie3_any'] * 100:4.1f} %")

    # --- momentum : P(but suivant même équipe | équipe vient de marquer)
    trans = {"same": 0, "tot": 0, "H_apres_H": 0, "tot_apres_H": 0,
             "A_apres_A": 0, "tot_apres_A": 0,
             "H_mene": 0, "H_egal": 0, "H_mene_A": 0,   # état du score
             "n_H_mene": 0, "n_egal": 0, "n_mene_A": 0}
    ecarts_series, ecarts_tous = [], []
    for m in valides:
        buts = m["buts"]
        sh = sa = 0
        for i, b in enumerate(buts):
            if b["equipe"] == "home":
                sh += 1
            else:
                sa += 1
            if i + 1 < len(buts):
                nx = buts[i + 1]
                trans["tot"] += 1
                meme = nx["equipe"] == b["equipe"]
                trans["same"] += 1 if meme else 0
                if b["equipe"] == "home":
                    trans["tot_apres_H"] += 1
                    trans["H_apres_H"] += 1 if nx["equipe"] == "home" else 0
                else:
                    trans["tot_apres_A"] += 1
                    trans["A_apres_A"] += 1 if nx["equipe"] == "away" else 0
                # état du score après le but i, avant le but i+1
                if sh > sa:
                    trans["n_H_mene"] += 1
                    trans["H_mene"] += 1 if nx["equipe"] == "home" else 0
                elif sh == sa:
                    trans["n_egal"] += 1
                    trans["H_egal"] += 1 if nx["equipe"] == "home" else 0
                else:
                    trans["n_mene_A"] += 1
                    trans["H_mene_A"] += 1 if nx["equipe"] == "home" else 0
                gap = nx["min"] - b["min"]
                ecarts_tous.append(gap)
                if meme:
                    ecarts_series.append(gap)
    tot_buts = sum(len(m["buts"]) for m in valides)
    nh = sum(1 for m in valides for b in m["buts"] if b["equipe"] == "home")
    p_home_brut = nh / max(1, tot_buts)
    p_same = trans["same"] / max(1, trans["tot"])
    # Attente « sans mémoire » EXACTE conditionnée au score final : pour un
    # ordre aléatoire uniforme de hg buts H et ag buts A, chaque paire
    # consécutive a [hg(hg−1)+ag(ag−1)] / [n(n−1)] d'être de la même équipe,
    # donc le nombre ATTENDU de transitions « même équipe » dans le match vaut
    # [hg(hg−1)+ag(ag−1)] / n. (L'approximation p̂²+(1−p̂)² est fausse aux
    # petits n — corrigé le 10/09 après le premier run.)
    att = num = 0.0
    for m in valides:
        buts = m["buts"]
        n = len(buts)
        if n < 2:
            continue
        hg = sum(1 for b in buts if b["equipe"] == "home")
        ag = n - hg
        att += (hg * (hg - 1) + ag * (ag - 1)) / n
        num += n - 1
    attente = att / num if num else 0.0
    # bruit statistique sur la mesure (écart-type binomial)
    se = math.sqrt(max(0.0, p_same * (1 - p_same) / max(1, trans["tot"])))
    out["momentum"] = {
        "transitions": trans["tot"], "but_H_brut": round(p_home_brut, 4),
        "p_meme_equipe_apres_but": round(p_same, 4),
        "attente_sans_memoire": round(attente, 4),
        "bruit_1_sigma": round(se, 4),
        "ecart_mesure_attente": round(p_same - attente, 4),
        "verdict": ("aucun effet détecté (écart < 2 sigma)"
                    if abs(p_same - attente) <= 2 * se else
                    "ÉCART SIGNIFICATIF — à investiguer en phase 2"),
        "P_H_apres_H": round(trans["H_apres_H"] / max(1, trans["tot_apres_H"]), 4),
        "P_A_apres_A": round(trans["A_apres_A"] / max(1, trans["tot_apres_A"]), 4),
        "etat_score": {
            "P_H_quand_H_mene": round(trans["H_mene"] / max(1, trans["n_H_mene"]), 4),
            "n_H_mene": trans["n_H_mene"],
            "P_H_a_egalite": round(trans["H_egal"] / max(1, trans["n_egal"]), 4),
            "n_egal": trans["n_egal"],
            "P_H_quand_A_mene": round(trans["H_mene_A"] / max(1, trans["n_mene_A"]), 4),
            "n_mene_A": trans["n_mene_A"],
        },
    }
    print("\n=== MOMENTUM (le modèle sans mémoire prédit : aucun effet) ===")
    mo = out["momentum"]
    print(f"  transitions analysées : {mo['transitions']} "
          f"(minimum REGLES : 60/palier — {'OK' if mo['transitions'] >= 60 else 'INSUFFISANT'})")
    print(f"  P(but suivant = même équipe)            : {mo['p_meme_equipe_apres_but'] * 100:.1f} %")
    print(f"  attente sans mémoire (exacte, selon score) : {mo['attente_sans_memoire'] * 100:.1f} %")
    print(f"  écart mesuré − attendu                  : {mo['ecart_mesure_attente'] * 100:+.1f} pts "
          f"(bruit 1σ = ±{mo['bruit_1_sigma'] * 100:.1f} pts)")
    print(f"  verdict                                 : {mo['verdict']}")
    es = mo["etat_score"]
    print(f"  état du score → P(but suivant domicile) : "
          f"domicile mène {es['P_H_quand_H_mene'] * 100:.1f} % (n={es['n_H_mene']}) · "
          f"égal {es['P_H_a_egalite'] * 100:.1f} % (n={es['n_egal']}) · "
          f"extérieur mène {es['P_H_quand_A_mene'] * 100:.1f} % (n={es['n_mene_A']})")

    if ecarts_series:
        ecarts_series.sort()
        med = ecarts_series[len(ecarts_series) // 2]
        moy = sum(ecarts_series) / len(ecarts_series)
        out["ecarts_minutes_series"] = {
            "n": len(ecarts_series), "median": med, "moyenne": round(moy, 1)}
        print(f"\n=== ÉCART ENTRE 2 BUTS D'UNE SÉRIE ===\n"
              f"  n={len(ecarts_series)}  médiane={med} min  moyenne={moy:.1f} min")
    if ecarts_tous:
        ecarts_tous.sort()
        out["ecarts_minutes_tous"] = {
            "n": len(ecarts_tous),
            "median": ecarts_tous[len(ecarts_tous) // 2],
            "moyenne": round(sum(ecarts_tous) / len(ecarts_tous), 1)}

    # --- modèle exact : table de référence + comparaison globale
    lam_moy = sum((m["sh"] or 0) for m in valides) / len(valides)
    mu_moy = sum((m["sa"] or 0) for m in valides) / len(valides)
    th2 = p_serie(lam_moy, mu_moy, 2)
    th3 = p_serie(lam_moy, mu_moy, 3)
    out["modele"] = {"lambda_home_moy": round(lam_moy, 3),
                     "mu_away_moy": round(mu_moy, 3),
                     "p_serie2_theorique_moyennes": round(th2, 4),
                     "p_serie3_theorique_moyennes": round(th3, 4)}
    print("\n=== MODÈLE EXACT (Poisson fusionné, sans mémoire) ===")
    print(f"  λ domicile moyen {lam_moy:.2f} · λ extérieur moyen {mu_moy:.2f}")
    print(f"  P(série 2+) théorique : {th2 * 100:.1f} %  (mesuré : "
          f"{out['global']['p_serie2_any'] * 100:.1f} %)")
    print(f"  P(série 3+) théorique : {th3 * 100:.1f} %  (mesuré : "
          f"{out['global']['p_serie3_any'] * 100:.1f} %)")
    print("  (comparaison grossière : le mélange de λ entre matchs joue — "
          "la calibration fine par match = phase 2, walk-forward)")
    print("\n  Table de référence P(série 2+) selon λ dom / λ ext :")
    print("        " + "".join(f"{mu:>7.2f}" for mu in (0.8, 1.2, 1.6, 2.0, 2.5)))
    for lam in (0.8, 1.2, 1.6, 2.0, 2.5):
        print(f"  λ={lam:.2f} " + "".join(f"{p_serie(lam, mu, 2) * 100:6.1f}%" for mu in (0.8, 1.2, 1.6, 2.0, 2.5)))
    out["table_reference"] = {
        str(lam): {str(mu): round(p_serie(lam, mu, 2), 4)
                   for mu in (0.8, 1.2, 1.6, 2.0, 2.5)}
        for lam in (0.8, 1.2, 1.6, 2.0, 2.5)}

    with open(STATS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nStatistiques écrites dans {STATS}")


# ------------------------------------------------------------- calibration
def _interp(p, points):
    """Interpolation linéaire par morceaux sur des points x croissants."""
    if p <= points[0][0]:
        return points[0][1]
    for i in range(1, len(points)):
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        if p <= x2:
            return y1 + (y2 - y1) * ((p - x1) / (x2 - x1))
    return points[-1][1]


def calibrer():
    """Vérification match par match du modèle exact contre le réel.

    Joint les λ walk-forward du backtest (backtest_results.csv, colonnes
    exp_h/exp_a ajoutées le 10/09 — aucune donnée future utilisée) avec les
    buts minutés collectés (data/buts_minutes.json). Les noms d'équipes
    diffèrent entre football-data.co.uk et ESPN → rapprochement flou par
    ligue (difflib), vérifié par le score final : si le score du backtest ne
    colle pas au score ESPN, le match est écarté.
    """
    import csv
    import difflib
    LIGUE_PAR_DIV = {"E0": "Premier League", "SP1": "La Liga", "I1": "Serie A",
                     "D1": "Bundesliga", "F1": "Ligue 1"}
    cache = _charge_cache()
    valides = [v for v in cache.values()
               if not v.get("rejete") and v.get("buts") is not None]
    with open("backtest_results.csv", newline="", encoding="utf-8") as f:
        lect = csv.DictReader(f)
        if "exp_h" not in (lect.fieldnames or []):
            raise SystemExit("backtest_results.csv sans exp_h/exp_a — "
                             "relancer d'abord : python3 moteur.py")
        bt = list(lect)
    print(f"backtest : {len(bt)} lignes | buts minutés : {len(valides)} matchs")

    # index backtest par (ligue, date)
    par_ld = {}
    for row in bt:
        cle = (row["league"], (row["date"] or "")[:10])
        par_ld.setdefault(cle, []).append(row)

    # correspondance de noms ESPN → co.uk, construite par ligue
    def carte_noms(ligue, div):
        noms_bt = sorted({r["home"] for r in bt if r["league"] == ligue} |
                         {r["away"] for r in bt if r["league"] == ligue})
        noms_espn = sorted({m["home"] for m in valides if m["div"] == div} |
                           {m["away"] for m in valides if m["div"] == div})
        carte = {}
        for n in noms_espn:
            cands = difflib.get_close_matches(_norme(n), [_norme(x) for x in noms_bt], n=1, cutoff=0.6)
            if cands:
                for x in noms_bt:
                    if _norme(x) == cands[0]:
                        carte[n] = x
                        break
        return carte

    joints, ecartes = [], 0
    for div, ligue in LIGUE_PAR_DIV.items():
        carte = carte_noms(ligue, div)
        for m in valides:
            if m["div"] != div:
                continue
            h, a = carte.get(m["home"]), carte.get(m["away"])
            if not h or not a:
                ecartes += 1
                continue
            d = datetime.date.fromisoformat(m["date"])
            trouve = None
            for delta in (0, -1, 1):
                for row in par_ld.get((ligue, (d + datetime.timedelta(days=delta)).isoformat()), []):
                    if row["home"] == h and row["away"] == a:
                        trouve = row
                        break
                if trouve:
                    break
            if not trouve:
                ecartes += 1
                continue
            if int(float(trouve["hg"])) != m["sh"] or int(float(trouve["ag"])) != m["sa"]:
                ecartes += 1          # scores divergents → prudence, écarté
                continue
            joints.append((float(trouve["exp_h"]), float(trouve["exp_a"]), m))

    n = len(joints)
    print(f"matchs joints : {n} | écartés (nom/score introuvable) : {ecartes}")
    if n < 60:
        raise SystemExit("échantillon trop petit pour conclure (REGLES : ≥ 60)")

    # mesure globale
    pred, reel, brier = [], [], []
    for lam, mu, m in joints:
        p2 = p_serie(lam, mu, 2)
        seq = _seq(m)
        y = 1.0 if ("HH" in seq or "AA" in seq) else 0.0
        pred.append(p2); reel.append(y); brier.append((p2 - y) ** 2)
    mp, mr = sum(pred) / n, sum(reel) / n
    print(f"\nP(série 2+) : modèle {mp * 100:.1f} %  |  réel {mr * 100:.1f} %  "
          f"|  écart {(mr - mp) * 100:+.1f} pts  |  Brier {sum(brier) / n:.4f}")

    # fiabilité par décile de probabilité prédite
    ordre = sorted(range(n), key=lambda i: pred[i])
    print("\n  décile   n   prédit    réel    écart")
    deciles = []
    pas = max(1, n // 10)
    for b in range(10):
        idx = ordre[b * pas:(b + 1) * pas] if b < 9 else ordre[9 * pas:]
        if not idx:
            continue
        pm = sum(pred[i] for i in idx) / len(idx)
        rm = sum(reel[i] for i in idx) / len(idx)
        deciles.append({"n": len(idx), "predit": round(pm, 4), "reel": round(rm, 4),
                        "ecart": round(rm - pm, 4)})
        print(f"  {b + 1:>6}  {len(idx):>4}  {pm * 100:5.1f} %  {rm * 100:5.1f} %  {(rm - pm) * 100:+5.1f}")
    pire = max(deciles, key=lambda d: abs(d["ecart"])) if deciles else None

    # séries 3+ en contrôle croisé (aucun paramètre ajusté nulle part)
    pred3, reel3 = [], []
    for lam, mu, m in joints:
        pred3.append(p_serie(lam, mu, 3))
        seq = _seq(m)
        reel3.append(1.0 if ("HHH" in seq or "AAA" in seq) else 0.0)
    n3 = len(joints)
    print(f"\nP(série 3+) : modèle {sum(pred3) / n3 * 100:.1f} %  |  réel "
          f"{sum(reel3) / n3 * 100:.1f} %  (contrôle, zéro réglage)")

    out = {"genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
           "n_joints": n, "n_ecartes": ecartes,
           "serie2": {"modele": round(mp, 4), "reel": round(mr, 4),
                      "brier": round(sum(brier) / n, 4)},
           "serie3": {"modele": round(sum(pred3) / n3, 4), "reel": round(sum(reel3) / n3, 4)},
           "deciles": deciles}

    # ---- split par saison + correction éventuelle (--corriger)
    def saison(m):
        return "2024-25" if m["date"] < "2025-07-01" else "2025-26"

    def points_correction(idx):
        """Points (prédit, réel) par décile sur le sous-échantillon idx,
        bornés par (0,0) et (1,1), monotonisés (isotone léger)."""
        if len(idx) < 60:
            return None
        ordre2 = sorted(idx, key=lambda i: pred[i])
        pas2 = max(1, len(ordre2) // 10)
        pts = [(0.0, 0.0)]
        for b in range(10):
            chunk = ordre2[b * pas2:(b + 1) * pas2] if b < 9 else ordre2[9 * pas2:]
            if not chunk:
                continue
            pm = sum(pred[i] for i in chunk) / len(chunk)
            rm = sum(reel[i] for i in chunk) / len(chunk)
            pts.append((pm, rm))
        pts.append((1.0, 1.0))
        # x strictement croissants, y non décroissants
        nettoyes = [pts[0]]
        for x, y in pts[1:]:
            if x <= nettoyes[-1][0]:
                continue
            nettoyes.append((x, max(y, nettoyes[-1][1])))
        return [(round(x, 4), round(y, 4)) for x, y in nettoyes]

    idx24 = [i for i in range(n) if saison(joints[i][2]) == "2024-25"]
    idx25 = [i for i in range(n) if saison(joints[i][2]) == "2025-26"]
    for lib, idx in (("2024-25", idx24), ("2025-26", idx25)):
        if idx:
            pm = sum(pred[i] for i in idx) / len(idx)
            rm = sum(reel[i] for i in idx) / len(idx)
            out["saison_" + lib] = {"n": len(idx), "modele": round(pm, 4), "reel": round(rm, 4)}
            print(f"\nsaison {lib} : n={len(idx)}  modèle {pm * 100:.1f} %  réel {rm * 100:.1f} %  ({(rm - pm) * 100:+.1f} pts)")

    if "--corriger" in sys.argv:
        def evalue(pts, idx):
            if not pts or not idx:
                return None
            rs, ps = [], []
            for i in idx:
                pc = _interp(pred[i], pts)
                ps.append(pc); rs.append(reel[i])
            return sum(rs) / len(rs) - sum(ps) / len(ps)

        pts_a = points_correction(idx24)
        pts_pool = points_correction(list(range(n)))
        if pts_a:
            res_holdout = evalue(pts_a, idx25)
            print(f"\nCORRECTION ajustée sur 2024-25, validée sur 2025-26 (holdout) :")
            print(f"  résidu holdout : {res_holdout * 100:+.1f} pts")
            out["holdout"] = {"points": pts_a, "residu_2025_26": round(res_holdout, 4)}
        if pts_pool:
            r24 = evalue(pts_pool, idx24); r25 = evalue(pts_pool, idx25)
            print(f"\nCORRECTION ajustée sur les DEUX saisons (pool) :")
            print(f"  résidu 2024-25 {r24 * 100:+.1f} pts | résidu 2025-26 {r25 * 100:+.1f} pts")
            out["correction_pool"] = {"points": pts_pool,
                                      "residu_2024_25": round(r24, 4),
                                      "residu_2025_26": round(r25, 4)}
            print("\n  points à figer dans series_buts.py (et miroir JS) :")
            print("  CORRECTION_SERIE2 = " + repr(pts_pool))

    # ---- SÉRIES PAR ÉQUIPE (10/09, demande utilisateur : domicile et
    # extérieur séparément, en plus du match entier ci-dessus) ----
    def points_gen(pred_l, reel_l, idx):
        """Points (prédit, réel) par décile — version généralisée."""
        if len(idx) < 60:
            return None
        ordre2 = sorted(idx, key=lambda i: pred_l[i])
        pas2 = max(1, len(ordre2) // 10)
        pts = [(0.0, 0.0)]
        for b in range(10):
            chunk = ordre2[b * pas2:(b + 1) * pas2] if b < 9 else ordre2[9 * pas2:]
            if not chunk:
                continue
            pm = sum(pred_l[i] for i in chunk) / len(chunk)
            rm = sum(reel_l[i] for i in chunk) / len(chunk)
            pts.append((pm, rm))
        pts.append((1.0, 1.0))
        nettoyes = [pts[0]]
        for x, y in pts[1:]:
            if x <= nettoyes[-1][0]:
                continue
            nettoyes.append((x, max(y, nettoyes[-1][1])))
        return [(round(x, 4), round(y, 4)) for x, y in nettoyes]

    def evalue_gen(pred_l, reel_l, pts, idx):
        if not pts or not idx:
            return None
        rs = sum(reel_l[i] for i in idx) / len(idx)
        ps = sum(_interp(pred_l[i], pts) for i in idx) / len(idx)
        return rs - ps

    def rapport_equipe(lib, pred_l, reel_l):
        mp = sum(pred_l) / n
        mr = sum(reel_l) / n
        print(f"\n{lib} : modèle {mp * 100:.1f} %  |  réel {mr * 100:.1f} %  "
              f"|  écart {(mr - mp) * 100:+.1f} pts")
        res = {"modele": round(mp, 4), "reel": round(mr, 4)}
        tout = list(range(n))
        for slib, idx in (("2024-25", idx24), ("2025-26", idx25)):
            pm = sum(pred_l[i] for i in idx) / len(idx)
            rm = sum(reel_l[i] for i in idx) / len(idx)
            res["saison_" + slib] = {"modele": round(pm, 4), "reel": round(rm, 4)}
            print(f"    {slib} : {pm * 100:5.1f} % vs {rm * 100:5.1f} %  ({(rm - pm) * 100:+.1f} pts)")
        if "--corriger" in sys.argv:
            pts24 = points_gen(pred_l, reel_l, idx24)
            if pts24:
                rh = evalue_gen(pred_l, reel_l, pts24, idx25)
                res["holdout_residu"] = round(rh, 4)
                print(f"    holdout (réglé 2024-25 → testé 2025-26) : {rh * 100:+.1f} pts")
            pts_pool = points_gen(pred_l, reel_l, tout)
            if pts_pool:
                r24 = evalue_gen(pred_l, reel_l, pts_pool, idx24)
                r25 = evalue_gen(pred_l, reel_l, pts_pool, idx25)
                res["points_pool"] = pts_pool
                res["residus_pool"] = [round(r24, 4), round(r25, 4)]
                print(f"    pool : résidus {r24 * 100:+.1f} / {r25 * 100:+.1f} pts")
                print(f"    POINTS_À_FIGER[{lib}] = {repr(pts_pool)}")
        return res

    seqs = [_seq(m) for _, _, m in joints]
    cas = {
        "serie2_dom": (2, True, "HH"),
        "serie2_ext": (2, False, "AA"),
        "serie3_dom": (3, True, "HHH"),
        "serie3_ext": (3, False, "AAA"),
    }
    out["par_equipe"] = {}
    print("\n" + "=" * 60)
    print("PAR ÉQUIPE (domicile / extérieur)")
    print("=" * 60)
    for lib, (k, home, motif) in cas.items():
        pred_l = [p_serie_team(lam, mu, k, home) for lam, mu, _ in joints]
        reel_l = [1.0 if motif in sq else 0.0 for sq in seqs]
        out["par_equipe"][lib] = rapport_equipe(lib, pred_l, reel_l)

    with open(os.path.join("data", "buts_affilee_calibration.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nÉcrit dans data/buts_affilee_calibration.json")
    if pire:
        print(f"pire décile : écart {pire['ecart'] * 100:+.1f} pts (n={pire['n']})")


# ------------------------------------------------------------------ CLI
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    cmd = sys.argv[1]
    if cmd == "collecter":
        if len(sys.argv) < 5:
            print("usage : buts_affilee.py collecter DIV DEBUT FIN [--limite N]")
            raise SystemExit(1)
        lim = None
        if "--limite" in sys.argv:
            lim = int(sys.argv[sys.argv.index("--limite") + 1])
        collecter(sys.argv[2], sys.argv[3], sys.argv[4], lim)
    elif cmd == "rapport":
        rapport()
    elif cmd == "calibrer":
        calibrer()
    else:
        print("commande inconnue :", cmd)
        raise SystemExit(1)
