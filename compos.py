"""
compos.py — ÉTAPE ④ : compositions et absences de dernière minute (ESPN).
==========================================================================
Faits ESPN vérifiés le 07/09 :
  · le summary d'un match TERMINÉ conserve les compositions complètes
    (titulaires + banc) → on peut reconstruire l'historique et MESURER
    l'effet réel des absents — jamais de coefficient inventé (même
    principe que fatigue.py) ;
  · pour un match À VENIR, les compositions sont vides jusqu'à ~1 h avant
    le coup d'envoi (« pas de J−2 ») : limite connue et documentée.

Stockage : data/compos.json — 60 derniers jours, toutes divisions ESPN,
clé « div|date|home_src|away_src », compositions compactes :
[id, nom, poste, titulaire(0/1)].

Usage :
    python3 compos.py bootstrap 21   # amorçage : 21 derniers jours (terminés)
    python3 compos.py collecter      # CI horaire : finis récents + matchs à H−1
    python3 compos.py mesurer        # barème d'impact → data/absences_mesuree.json
"""
import datetime
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)
from calendrier import _curl_json, ESPN_SLUGS      # noqa: E402

CHEMIN = os.path.join(RACINE, "data", "compos.json")
CHEMIN_MESURE = os.path.join(RACINE, "data", "absences_mesuree.json")
OUVRIERS = 4               # requêtes ESPN en parallèle (sans clé : raisonnable)
FENETRE_H = 3              # un match à venir est interrogé si coup d'envoi < 3 h
HISTO_JOURS = 45           # fenêtre pour les « titulaires attendus »
MIN_MATCHS = 3             # matchs stockés minimum pour attendre un onze
TAUX_TITU = 0.60           # titulaire « régulier » : ≥ 60 % des matchs
BORNE_MIN_N = 60           # en dessous : pas de coefficient (honnêteté)
CLAMP = (0.70, 1.40)
RETENTION_JOURS = 60


# ------------------------------------------------------------------ stockage
def charger():
    try:
        with open(CHEMIN, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"matchs": {}, "genere_le": None}


def sauver(etat):
    etat["genere_le"] = datetime.datetime.now().isoformat(timespec="seconds")
    # rétention : on garde 60 jours + 3 jours à venir
    auj = datetime.date.today()
    borne = (auj - datetime.timedelta(days=RETENTION_JOURS)).isoformat()
    futur = (auj + datetime.timedelta(days=3)).isoformat()
    etat["matchs"] = {k: m for k, m in etat["matchs"].items()
                      if borne <= m.get("date", "") <= futur}
    tmp = CHEMIN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, CHEMIN)


# ------------------------------------------------------------------ ESPN
def _scoreboard(slug, dates):
    return _curl_json("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                      f"{slug}/scoreboard?dates={dates}") or {}


def _extraire(summary, evt_id, div, slug, date_iso, home_src, away_src, fini):
    """Compositions compactes à partir d'un summary ESPN. None si absentes."""
    if not summary:
        return None
    ros = summary.get("rosters") or []
    if not ros:
        return None
    # correspondance équipe → côté (home/away) via le header
    cote = {}
    try:
        comps = (summary.get("header") or {}).get("competitions") or [{}]
        for c in comps[0].get("competitors") or []:
            tid = str((c.get("team") or {}).get("id"))
            cote[tid] = c.get("homeAway")
    except Exception:
        pass
    compos = {}
    for r in ros:
        tid = str((r.get("team") or {}).get("id"))
        c = r.get("homeAway") or cote.get(tid)
        if c not in ("home", "away"):
            continue
        joueurs = []
        for j in (r.get("roster") or []):
            ath = j.get("athlete") or {}
            if not ath.get("id"):
                continue
            joueurs.append([str(ath["id"]),
                            ath.get("displayName") or ath.get("lastName") or "?",
                            (j.get("position") or {}).get("displayName") or "?",
                            1 if j.get("starter") else 0])
        if joueurs:
            compos[c] = joueurs
    if not compos.get("home") and not compos.get("away"):
        return None
    return {"div": div, "slug": slug, "evt": str(evt_id), "date": date_iso,
            "home_src": home_src, "away_src": away_src, "fini": 1 if fini else 0,
            "compos": compos,
            "collecte_le": datetime.datetime.now().isoformat(timespec="seconds")}


def _evenements(slug, dates):
    """Événements d'un scoreboard aplatis (id, date, fini, home, away)."""
    out = []
    for e in (_scoreboard(slug, dates).get("events") or []):
        try:
            comp = e["competitions"][0]
            st = (comp.get("status") or {}).get("type") or {}
            homes = [c for c in comp.get("competitors") or []
                     if c.get("homeAway") == "home"]
            aways = [c for c in comp.get("competitors") or []
                     if c.get("homeAway") == "away"]
            if not homes or not aways:
                continue
            out.append({"id": e["id"], "date": (e.get("date") or "")[:10],
                        "ko": e.get("date") or "",
                        "fini": bool(st.get("completed")),
                        "home": (homes[0].get("team") or {}).get("displayName"),
                        "away": (aways[0].get("team") or {}).get("displayName")})
        except Exception:
            continue
    return out


def _summary(slug, evt_id):
    return _curl_json("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                      f"{slug}/summary?event={evt_id}")


def bootstrap(jours=21):
    """Amorçage : compositions des matchs TERMINÉS des `jours` derniers jours."""
    etat = charger()
    auj = datetime.date.today()
    debut = (auj - datetime.timedelta(days=jours)).isoformat().replace("-", "")
    fin = (auj + datetime.timedelta(days=1)).isoformat().replace("-", "")
    taches = []
    for div, slug in ESPN_SLUGS.items():
        if div in _COUPES():
            continue
        for ev in _evenements(slug, f"{debut}-{fin}"):
            if not ev["fini"] or not ev["home"] or not ev["away"]:
                continue
            cle = f"{div}|{ev['date']}|{ev['home']}|{ev['away']}"
            if cle in etat["matchs"] and etat["matchs"][cle].get("compos"):
                continue
            taches.append((div, slug, ev))
    print(f"bootstrap : {len(taches)} matchs à interroger")
    n_ok = 0

    def une(t):
        div, slug, ev = t
        try:
            s = _summary(slug, ev["id"])
            return _extraire(s, ev["id"], div, slug, ev["date"],
                             ev["home"], ev["away"], True)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=OUVRIERS) as ex:
        for i, m in enumerate(ex.map(une, taches)):
            if m:
                etat["matchs"][f"{m['div']}|{m['date']}|{m['home_src']}|{m['away_src']}"] = m
                n_ok += 1
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(taches)} — {n_ok} compositions")
    sauver(etat)
    print(f"bootstrap terminé : {n_ok} compositions stockées "
          f"(total {len(etat['matchs'])} matchs)")
    return n_ok


def _COUPES():
    try:
        import coupes
        return set(coupes.COUPES)
    except Exception:
        return set()


def collecter(fenetre_h=FENETRE_H):
    """Passage CI : matchs terminés depuis la dernière collecte + matchs à
    venir dont le coup d'envoi est dans < fenetre_h heures (compositions H−1)."""
    etat = charger()
    auj = datetime.date.today()
    hier = (auj - datetime.timedelta(days=1)).isoformat().replace("-", "")
    aujd = auj.isoformat().replace("-", "")
    now = datetime.datetime.utcnow()
    n = 0
    for div, slug in ESPN_SLUGS.items():
        if div in _COUPES():
            continue
        try:
            evs = _evenements(slug, f"{hier}-{aujd}")
        except Exception:
            continue
        for ev in evs:
            if not ev["home"] or not ev["away"]:
                continue
            cle = f"{div}|{ev['date']}|{ev['home']}|{ev['away']}"
            deja = etat["matchs"].get(cle)
            if ev["fini"]:
                if deja and deja.get("compos"):
                    continue          # déjà stocké avec compositions
            else:
                # à venir : on n'interroge qu'à l'approche du coup d'envoi
                try:
                    ko = datetime.datetime.strptime(ev["ko"][:16],
                                                    "%Y-%m-%dT%H:%M")
                except ValueError:
                    continue
                if (ko - now).total_seconds() > fenetre_h * 3600:
                    continue
                if deja and deja.get("compos"):
                    continue          # compositions déjà capturées
            try:
                m = _extraire(_summary(slug, ev["id"]), ev["id"], div, slug,
                              ev["date"], ev["home"], ev["away"], ev["fini"])
            except Exception:
                m = None
            if m:
                etat["matchs"][cle] = m
                n += 1
            elif deja is None:
                # garder une trace même sans composition (fini seulement)
                if ev["fini"]:
                    etat["matchs"][cle] = {
                        "div": div, "slug": slug, "evt": str(ev["id"]),
                        "date": ev["date"], "home_src": ev["home"],
                        "away_src": ev["away"], "fini": 1, "compos": {},
                        "collecte_le": datetime.datetime.now().isoformat(
                            timespec="seconds")}
    sauver(etat)
    return n


# ------------------------------------------------- titulaires attendus / absents
def _titulaires_attendus(etat, div, equipe_src, avant_date):
    """Onze attendu d'après les compositions stockées AVANT avant_date
    (fenêtre 45 jours). Retourne (attendus, n_matchs) — attendus = liste de
    [id, nom, poste, taux]."""
    borne = (datetime.date.fromisoformat(avant_date)
             - datetime.timedelta(days=HISTO_JOURS)).isoformat()
    vus = {}          # id -> [n_matchs, n_titulaire, nom, poste]
    n_matchs = 0
    for m in etat["matchs"].values():
        if m["div"] != div or not (borne <= m["date"] < avant_date):
            continue
        cote = None
        if m["home_src"] == equipe_src:
            cote = "home"
        elif m["away_src"] == equipe_src:
            cote = "away"
        if not cote or not (m.get("compos") or {}).get(cote):
            continue
        n_matchs += 1
        for pid, nom, pos, st in m["compos"][cote]:
            v = vus.setdefault(pid, [0, 0, nom, pos])
            v[0] += 1
            v[1] += st
    if n_matchs < MIN_MATCHS:
        return [], n_matchs
    attendus = []
    for pid, (nm, nt, nom, pos) in vus.items():
        if nt / nm >= TAUX_TITU and nt >= MIN_MATCHS:
            attendus.append([pid, nom, pos, round(nt / nm, 2)])
    attendus.sort(key=lambda z: -z[3])
    return attendus[:11], n_matchs


def absences(div, home_src, away_src, date_iso, etat=None):
    """État des compositions d'un match : publiées ? absents de chaque côté ?"""
    etat = etat or charger()
    m = etat["matchs"].get(f"{div}|{date_iso}|{home_src}|{away_src}")
    if not m or not (m.get("compos") or {}).get("home") \
            or not (m.get("compos") or {}).get("away"):
        return None
    out = {"publie": True, "date": date_iso}
    for cote, equipe in (("home", home_src), ("away", away_src)):
        attendus, n_matchs = _titulaires_attendus(etat, div, equipe, date_iso)
        ids_squad = {j[0] for j in m["compos"].get(cote, [])}
        ids_titu = {j[0] for j in m["compos"].get(cote, []) if j[3] == 1}
        absents, banc = [], []
        for pid, nom, pos, taux in attendus:
            if pid not in ids_squad:
                absents.append({"nom": nom, "poste": pos, "taux": taux})
            elif pid not in ids_titu:
                banc.append({"nom": nom, "poste": pos, "taux": taux})
        out[cote] = {"equipe": equipe, "absents": absents, "banc": banc,
                     "n_attendus": len(attendus), "base": n_matchs}
    return out


# ------------------------------------------------------------------ mesures
def _saison_csv(date_iso):
    y, mo = int(date_iso[:4]), int(date_iso[5:7])
    a = y + (1 if mo >= 7 else 0)
    return str(a)[2:] + str(a + 1)[2:]


def _resultat_csv(div, date_iso, home_co, away_co):
    import csv as _csv
    chemin = os.path.join(RACINE, "data", f"{_saison_csv(date_iso)}_{div}.csv")
    if not os.path.exists(chemin):
        return None
    d = datetime.date.fromisoformat(date_iso)
    with open(chemin, encoding="latin-1") as f:
        for ligne in _csv.DictReader(f):
            for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                try:
                    if datetime.datetime.strptime(ligne["Date"], fmt).date() == d:
                        break
                except (ValueError, KeyError):
                    continue
            else:
                continue
            if ligne.get("HomeTeam") == home_co and ligne.get("AwayTeam") == away_co:
                try:
                    return int(ligne["FTHG"]), int(ligne["FTAG"])
                except (ValueError, KeyError):
                    return None
    return None


def mesurer():
    """Impact MESURÉ des absents sur les buts (principe conservative : effet
    appliqué uniquement dans le sens de la perte). Écrit absences_mesuree.json."""
    etat = charger()
    try:
        import fatigue
        traduire = fatigue._traduire
    except Exception:
        print("mesurer : traduction indisponible (fatigue.py) — abandon")
        return None
    seaux = {}          # "0"/"1"/"2"/"3+" → [n, buts_pour, buts_contre]
    for m in sorted(etat["matchs"].values(), key=lambda z: z["date"]):
        if not m.get("fini") or not (m.get("compos") or {}).get("home"):
            continue
        th = traduire(m["home_src"])
        ta = traduire(m["away_src"])
        if not th or not ta:
            continue
        res = _resultat_csv(m["div"], m["date"], th[0], ta[0])
        if not res:
            continue
        ab = absences(m["div"], m["home_src"], m["away_src"], m["date"], etat)
        if not ab:
            continue
        bh, ba = res
        for cote, buts_p, buts_c in (("home", bh, ba), ("away", ba, bh)):
            info = ab.get(cote) or {}
            if not info.get("n_attendus"):
                continue
            k = min(len(info.get("absents") or []), 3)
            s = seaux.setdefault(str(k), [0, 0, 0])
            s[0] += 1
            s[1] += buts_p
            s[2] += buts_c
    ref = seaux.get("0")
    bareme = {}
    if ref and ref[0] >= BORNE_MIN_N:
        att_ref = ref[1] / ref[0]
        dfn_ref = ref[2] / ref[0]
        for k, s in seaux.items():
            if k == "0" or s[0] < BORNE_MIN_N:
                continue
            brut_att = (s[1] / s[0]) / att_ref if att_ref else 1.0
            brut_def = (s[2] / s[0]) / dfn_ref if dfn_ref else 1.0
            bareme[k] = {"n": s[0],
                         "f_att": round(min(1.0, brut_att), 4),
                         "f_def": round(max(1.0, brut_def), 4),
                         "brut_att": round(brut_att, 4),
                         "brut_def": round(brut_def, 4)}
    out = {"genere_le": datetime.datetime.now().isoformat(timespec="seconds"),
           "seaux": {k: {"n": v[0], "buts_pour": round(v[1] / v[0], 3),
                         "buts_contre": round(v[2] / v[0], 3)}
                     for k, v in seaux.items() if v[0]},
           "borne_min_n": BORNE_MIN_N, "bareme": bareme}
    with open(CHEMIN_MESURE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def coeffs_match(lig, home, away, date_match):
    """(mult_home, mult_away, info) pour le pronostic — None tant que le
    barème n'est pas mesuré (n < 60 par seau) : information seulement."""
    if not date_match:
        return None, None, None
    try:
        import coupes
        if lig in coupes.COUPES:
            return None, None, None
    except Exception:
        pass
    etat = charger()
    # retrouver le match stocké (noms ESPN) via la traduction
    import fatigue
    m_trouve = None
    for m in etat["matchs"].values():
        if m["div"] != lig or m["date"] != date_match:
            continue
        th, ta = fatigue._traduire(m["home_src"]), fatigue._traduire(m["away_src"])
        if th and ta and th[0] == home and ta[0] == away:
            m_trouve = m
            break
    if not m_trouve:
        return None, None, None
    ab = absences(lig, m_trouve["home_src"], m_trouve["away_src"],
                  date_match, etat)
    if not ab:
        return None, None, None
    info = {"publie": True}
    for cote in ("home", "away"):
        info[cote] = ab.get(cote)
    bareme = {}
    try:
        with open(CHEMIN_MESURE, encoding="utf-8") as f:
            bareme = (json.load(f).get("bareme")) or {}
    except (OSError, ValueError):
        pass
    if not bareme:
        return None, None, info        # pas encore mesuré → info seulement
    mh, ma = 1.0, 1.0
    for cote in ("home", "away"):
        n_abs = min(len((ab.get(cote) or {}).get("absents") or []), 3)
        cel = bareme.get(str(n_abs))
        if not cel:
            continue
        if cote == "home":
            mh *= cel["f_att"]; ma *= cel["f_def"]
        else:
            ma *= cel["f_att"]; mh *= cel["f_def"]
    mh = round(min(max(mh, CLAMP[0]), CLAMP[1]), 4)
    ma = round(min(max(ma, CLAMP[0]), CLAMP[1]), 4)
    if mh == 1.0 and ma == 1.0:
        return None, None, info
    return mh, ma, info


# ------------------------------------------------------------------ export app
def export_app():
    """Données embarquées dans l'app autonome : matchs à venir avec
    compositions publiées + barème (le cas échéant)."""
    etat = charger()
    auj = datetime.date.today().isoformat()
    try:
        import fatigue
        trad = fatigue._traduire
    except Exception:
        trad = lambda x: None          # noqa: E731
    matchs = {}
    for m in etat["matchs"].values():
        if m["date"] < auj or not (m.get("compos") or {}).get("home"):
            continue
        th, ta = trad(m["home_src"]), trad(m["away_src"])
        if not th or not ta:
            continue
        ab = absences(m["div"], m["home_src"], m["away_src"], m["date"], etat)
        if not ab:
            continue
        cle = f"{m['div']}|{m['date']}|{th[0]}|{ta[0]}"
        entree = {"home": ab.get("home"), "away": ab.get("away")}
        mh, ma, _ = coeffs_match(m["div"], th[0], ta[0], m["date"])
        if mh:
            entree["mh"], entree["ma"] = mh, ma
        matchs[cle] = entree
    bareme = {}
    try:
        with open(CHEMIN_MESURE, encoding="utf-8") as f:
            bareme = (json.load(f).get("bareme")) or {}
    except (OSError, ValueError):
        pass
    return {"matchs": matchs, "bareme": bareme,
            "taux_titu": TAUX_TITU, "min_matchs": MIN_MATCHS,
            "histo_jours": HISTO_JOURS}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collecter"
    if cmd == "bootstrap":
        j = int(sys.argv[2]) if len(sys.argv) > 2 else 21
        bootstrap(j)
    elif cmd == "mesurer":
        r = mesurer()
        print(json.dumps(r, ensure_ascii=False, indent=1) if r else "rien")
    else:
        n = collecter()
        print(f"collecter : {n} composition(s) ajoutée(s)")
