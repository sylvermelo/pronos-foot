"""
CORNERS 1re MI-TEMPS — collecte ESPN + modèle « qui aura le plus de corners en MT1 ».
=====================================================================================
Aucune source gratuite ne publie les corners par mi-temps : co.uk donne le
total du match (HC/AC), le boxscore ESPN aussi. SEUL le fil de commentary
ESPN horodate chaque corner — vérifié sur échantillon : le total reconstruit
colle au boxscore officiel à 100 % sur les 8 divisions couvertes.

Méthode d'extraction (mesurée le 07/09/2026 sur matchs réels) :
  · le TEXTE de chaque entrée (« Corner, {équipe}. Conceded by {joueur}. »)
    est la source fiable — le champ structuré play.team mélange l'équipe qui
    obtient et celle qui concède le corner (St. Pauli-Leverkusen : champ
    team 4-4, texte 3-8, boxscore officiel 3-8) ;
  · certaines entrées n'ont NI type NI période (play absent) mais toujours
    le texte et time.value (secondes écoulées) : la mi-temps se déduit du
    marqueur « halftime » du fil (sinon 2 750 s) ;
  · la liste est chronologique : rien ne se perd.

Couverture ESPN (testée match par match contre boxscore) :
    COMPLÈTE : E0, E1, D1, I1, SP1, F1, N1, P1   (~2 900 matchs/saison)
    NULLE    : E2, E3, SC0-SC3, B1, T1, G1, D2, F2, I2, SP2
               (fil réduit à 15-20 événements clés, sans corners)
Les divisions non couvertes n'affichent simplement pas ce marché.

Stockage : data/corners_mt.json — cumulatif, une ligne par match terminé :
    "E0|2026-02-14|Aston Villa|Leeds" :
        {div, date, home, away, ch1, ca1, ch2, ca2, ch, ca, complet, evt}
    ch1/ca1 = corners 1re mi-temps domicile/extérieur, ch2/ca2 = 2e,
    ch/ca = totaux (recoupés boxscore), complet = texte == boxscore.

Modèle : mêmes formules que modeles_secondaires (décroissance exponentielle
XI_WEEK, lissage K pseudo-matchs, convolution de lois) — marché « cmt1 »
greffé dans modeles.json → ligues[div].secondaires à la fin de l'entraînement.
Pronostic : P(domicile plus de corners MT1) / P(égalité) / P(extérieur) +
over/under du TOTAL MT1. Probabilités BRUTES : la calibration walk-forward
viendra quand l'historique le permettra (comme corners.py l'a fait pour le
match complet) — d'ici là l'affichage le dit.

Usages :
    python corners_mt.py backfill [saisons]   # historique depuis les CSV
    python corners_mt.py recent               # 3 derniers jours (CI)
    python corners_mt.py verifier             # contrôle qualité vs boxscore/CSV
"""
import datetime
import difflib
import glob
import json
import os
import re
import sys
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor

RACINE = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.path.join(RACINE, "data", "corners_mt.json")
DATA = os.path.join(RACINE, "data")

# divisions où le fil ESPN contient les corners (vérifié contre boxscore)
DIVISIONS = {"E0": "eng.1", "E1": "eng.2", "D1": "ger.1", "I1": "ita.1",
             "SP1": "esp.1", "F1": "fra.1", "N1": "ned.1", "P1": "por.1"}
SAISONS_DEFAUT = ["2425", "2526", "2627"]
JOURS_RECENTS = 4          # fenêtre du ramassage incrémental (CI)
OUVRIERS = 3               # requêtes ESPN en parallèle (sans clé : raisonnable)
K_LISSAGE = 10.0           # pseudo-matchs de lissage par équipe (MT1 ≈ 2 corners/équipe : plus bruité que le match complet → lissage un peu plus fort que K_EQUIPE=12 ? non : 10 suffit avec 2 saisons)
XI_WEEK = 0.012            # même demi-vie (~58 semaines) que tous les modèles
KMAX = 14                  # convolution : 0..14 corners MT1 par équipe (large)
LIGNES_TOTAL = [3.5, 4.5]  # over/under du total MT1 (moyenne attendue ~4,2)
LIMITE_MT1_DEFAUT = 2750.0 # secondes (45' + arrêt de jeu moyen) si pas de marqueur

_VERROU = threading.Lock()


# --------------------------------------------------------------------------- 
# HTTP (ESPN refuse l'empreinte TLS d'urllib — curl, comme calendrier.py)
# ---------------------------------------------------------------------------
def _curl_json(url, timeout=25):
    import subprocess
    try:
        p = subprocess.run(["curl", "-s", "--max-time", str(timeout), url],
                           capture_output=True, text=True, timeout=timeout + 5)
        return json.loads(p.stdout) if p.stdout.strip() else None
    except Exception:
        return None


def _norme(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if c.isalnum()).lower()


SUFFIXES = [" Town", " City", " United", " Wanderers", " Rovers", " Athletic",
            " County", " North End", " Albion", " FC", " AFC", " CF", " SK",
            " Hamburg", " 04", " 05", " 09", " BK", " IF", " KB"]


def _variantes(nom):
    """Nom ESPN → variantes proches de l'orthographe co.uk."""
    out = [nom]
    n = nom
    for s in SUFFIXES:
        if n.endswith(s) and len(n) - len(s) >= 3:
            n = n[:-len(s)]
            out.append(n)
            break
    return out


# --------------------------------------------------------------------------- 
# État cumulatif
# ---------------------------------------------------------------------------
def charger():
    try:
        with open(CHEMIN, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("matchs"), dict):
            d.setdefault("dates_ok", [])
            return d
    except (OSError, ValueError):
        pass
    return {"matchs": {}, "dates_ok": [], "genere_le": None,
            "description": __doc__.splitlines()[1]}


def sauver(d, ajout=False):
    d["genere_le"] = datetime.datetime.now().isoformat(timespec="seconds")
    if ajout:
        # horodatage des AJOUTS réels : c'est lui que maj.py compare à
        # modeles.json pour décider du ré-entraînement (marché « cmt1 »).
        d["dernier_ajout"] = d["genere_le"]
    tmp = CHEMIN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, CHEMIN)


# --------------------------------------------------------------------------- 
# Noms : ESPN → co.uk (Mappeur de calendrier.py, alimenté par les CSV)
# ---------------------------------------------------------------------------
def equipes_par_division():
    eq = {}
    for chemin in glob.glob(os.path.join(DATA, "[0-9][0-9][0-9][0-9]_*.csv")):
        div = os.path.basename(chemin).split("_")[1].split(".")[0]
        if div not in DIVISIONS:
            continue
        try:
            import csv as _csv
            with open(chemin, encoding="latin-1") as f:
                for ligne in _csv.DictReader(f):
                    h = ligne.get("HomeTeam") or ligne.get("Home")
                    a = ligne.get("AwayTeam") or ligne.get("Away")
                    if h and a:
                        eq.setdefault(div, set()).update([h, a])
        except OSError:
            continue
    return {k: sorted(v) for k, v in eq.items()}


def _cote(nom, cotes):
    """Retrouve le côté (home/away) d'un nom d'équipe du fil commentary."""
    n = _norme(nom)
    for cote, nm in cotes.items():
        if n == _norme(nm):
            return cote
    for cote, nm in cotes.items():
        for v in _variantes(nm):
            if n == _norme(v):
                return cote
    for cote, nm in cotes.items():
        if difflib.get_close_matches(n, [_norme(nm)] + [_norme(v) for v in _variantes(nm)], n=1, cutoff=0.88):
            return cote
    return None


# --------------------------------------------------------------------------- 
# Extraction des corners par mi-temps depuis summary?event=
# ---------------------------------------------------------------------------
RE_CORNER = re.compile(r"^Corner,\s*(.+?)\.")   # 24/25 : « Corner,X. » sans espace ; 25/26+ : avec


def extraire(summary, cotes):
    """cotes = {"home": nom ESPN domicile, "away": nom ESPN extérieur}.
    Retourne {ch1, ca1, ch2, ca2, ch, ca, box_h, box_a, complet} ou None."""
    comm = (summary or {}).get("commentary")
    if comm is None:
        return None
    limite = LIMITE_MT1_DEFAUT
    for c in comm:                      # marqueur mi-temps (chronologique)
        p = c.get("play") or {}
        if (p.get("type") or {}).get("type") == "halftime":
            t = (c.get("time") or {}).get("value")
            if t:
                limite = float(t) + 1.0
            break
    n = {"home": [0, 0], "away": [0, 0]}
    vus = 0
    for c in comm:
        txt = c.get("text") or (c.get("play") or {}).get("text") or ""
        m = RE_CORNER.match(txt)
        if not m:
            continue
        cote = _cote(m.group(1), cotes)
        if cote is None:
            continue
        vus += 1
        p = c.get("play") or {}
        per = (p.get("period") or {}).get("number")
        if per in (1, 2):
            mt = per
        else:
            t = (c.get("time") or {}).get("value")
            mt = 1 if (t is not None and float(t) < limite) else 2
        n[cote][mt - 1] += 1
    # boxscore officiel : contrôle de complétude
    box = {}
    for t in ((summary or {}).get("boxscore") or {}).get("teams", []):
        nm = (t.get("team") or {}).get("displayName")
        for st in t.get("statistics", []):
            if st.get("name") == "wonCorners":
                try:
                    box[_cote(nm, cotes)] = int(st.get("displayValue"))
                except (TypeError, ValueError, KeyError):
                    pass
    ch = n["home"][0] + n["home"][1]
    ca = n["away"][0] + n["away"][1]
    complet = bool(box.get("home") is not None and box.get("away") is not None
                   and box["home"] == ch and box["away"] == ca)
    return {"ch1": n["home"][0], "ca1": n["away"][0],
            "ch2": n["home"][1], "ca2": n["away"][1],
            "ch": ch, "ca": ca,
            "box_h": box.get("home"), "box_a": box.get("away"),
            "complet": complet, "vus": vus}


# --------------------------------------------------------------------------- 
# Collecte d'une journée de division
# ---------------------------------------------------------------------------
def _scoreboard(slug, date_iso):
    return _curl_json("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                      f"{slug}/scoreboard?dates={date_iso.replace('-', '')}")


def _summary(slug, event_id):
    return _curl_json("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                      f"{slug}/summary?event={event_id}")


def jour(div, date_iso, etat, mappeur, date_cle=None):
    """Traite tous les matchs TERMINÉS d'une division à une date.
    Retourne le nombre de nouveaux matchs stockés."""
    slug = DIVISIONS[div]
    d = _scoreboard(slug, date_iso)
    if d is None:
        return None                     # réseau/ESPN : à retenter
    cle_date = f"{div}|{date_cle or date_iso}"
    ajoutes = 0
    tout_fait = True
    for e in d.get("events", []):
        if not e.get("status", {}).get("type", {}).get("completed"):
            continue
        comp = (e.get("competitions") or [{}])[0]
        src = {}
        for co in comp.get("competitors", []):
            nm = (co.get("team") or {}).get("displayName")
            if co.get("homeAway") == "home":
                src["home"] = nm
            elif co.get("homeAway") == "away":
                src["away"] = nm
        if not src.get("home") or not src.get("away"):
            continue
        h = mappeur.traduire(div, src["home"])
        a = mappeur.traduire(div, src["away"])
        if not h or not a:
            continue                    # nom non traduit : on ignore ce match
        cle = f"{div}|{date_cle or date_iso}|{h}|{a}"
        with _VERROU:
            deja = cle in etat["matchs"]
        if deja:
            continue
        s = _summary(slug, e.get("id"))
        if s is None:
            tout_fait = False
            continue
        x = extraire(s, src)
        if x is None:
            tout_fait = False
            continue
        if x["vus"] == 0 and not x["complet"]:
            # aucun corner dans le fil : division/match non couvert — on
            # enregistre quand même la ligne (0-0 tromperait le modèle) :
            # NON → on ne stocke PAS, et on marque la division comme vue.
            continue
        ligne = {"div": div, "date": date_cle or date_iso, "home": h, "away": a,
                 "ch1": x["ch1"], "ca1": x["ca1"], "ch2": x["ch2"], "ca2": x["ca2"],
                 "ch": x["ch"], "ca": x["ca"], "complet": x["complet"],
                 "evt": str(e.get("id"))}
        with _VERROU:
            etat["matchs"][cle] = ligne
        ajoutes += 1
    if tout_fait:
        with _VERROU:
            if cle_date not in etat["dates_ok"]:
                etat["dates_ok"].append(cle_date)
    return ajoutes


# --------------------------------------------------------------------------- 
# Backfill depuis les CSV co.uk (dates et noms locaux sûrs)
# ---------------------------------------------------------------------------
def dates_backfill(saisons):
    """[(div, date)] distincts où au moins un match existe dans les CSV."""
    import csv as _csv
    paires = set()
    for saison in saisons:
        for div in DIVISIONS:
            chemin = os.path.join(DATA, f"{saison}_{div}.csv")
            if not os.path.exists(chemin):
                continue
            try:
                with open(chemin, encoding="latin-1") as f:
                    for ligne in _csv.DictReader(f):
                        dte = (ligne.get("Date") or "").strip()
                        if not dte:
                            continue
                        try:
                            dt = datetime.datetime.strptime(dte, "%d/%m/%Y").date()
                        except ValueError:
                            try:
                                dt = datetime.datetime.strptime(dte, "%d/%m/%y").date()
                            except ValueError:
                                continue
                        paires.add((div, dt.isoformat()))
            except OSError:
                continue
    return sorted(paires, key=lambda x: (x[1], x[0]))


def backfill(saisons=None, ouvrier=OUVRIERS):
    import calendrier
    saisons = saisons or SAISONS_DEFAUT
    etat = charger()
    mappeur = calendrier.Mappeur(equipes_par_division())
    a_faire = [(dv, dt) for dv, dt in dates_backfill(saisons)
               if f"{dv}|{dt}" not in set(etat["dates_ok"])]
    total_dates = len(a_faire)
    print(f"backfill corners MT1 : {len(saisons)} saison(s), {total_dates} journées "
          f"à traiter ({len(etat['matchs'])} matchs déjà en base)")
    faits = [0]
    ajouts = [0]

    def traite(paire):
        div, dt = paire
        n = jour(div, dt, etat, mappeur)
        with _VERROU:
            faits[0] += 1
            if n:
                ajouts[0] += n
            if faits[0] % 25 == 0:
                sauver(etat, ajout=bool(ajouts[0]))
                print(f"  {faits[0]}/{total_dates} journées | +{ajouts[0]} matchs "
                      f"| total {len(etat['matchs'])}", flush=True)
        return n

    with ThreadPoolExecutor(max_workers=ouvrier) as ex:
        list(ex.map(traite, a_faire))
    sauver(etat, ajout=bool(ajouts[0]))
    couvert = {}
    for m in etat["matchs"].values():
        c = couvert.setdefault(m["div"], [0, 0])
        c[0] += 1
        c[1] += 1 if m["complet"] else 0
    print(f"backfill terminé : {len(etat['matchs'])} matchs")
    for div in sorted(couvert):
        n, ok = couvert[div]
        print(f"  {div:4s} : {n:5d} matchs | texte==boxscore : {100.0*ok/max(n,1):.1f} %")
    return etat


# --------------------------------------------------------------------------- 
# Ramassage incrémental (CI : derniers jours, mêmes divisions)
# ---------------------------------------------------------------------------
def collecter_recent(db=None):
    """Appelé par maj_calendrier.py après le calendrier. Fenêtre glissante
    JOURS_RECENTS. Retourne le nombre de nouveaux matchs stockés."""
    import calendrier
    etat = charger()
    ok = set(etat["dates_ok"])
    mappeur = calendrier.Mappeur(equipes_par_division())
    auj = datetime.date.today()
    taches = []
    for i in range(JOURS_RECENTS + 1):
        dt = (auj - datetime.timedelta(days=i)).isoformat()
        for div in DIVISIONS:
            if f"{div}|{dt}" not in ok:
                taches.append((div, dt))
    if not taches:
        return 0
    ajoutes = 0
    with ThreadPoolExecutor(max_workers=OUVRIERS) as ex:
        for n in ex.map(lambda p: jour(p[0], p[1], etat, mappeur), taches):
            if n:
                ajoutes += n
    if ajoutes or len(etat["dates_ok"]) != len(ok):
        sauver(etat, ajout=bool(ajoutes))
    return ajoutes


# --------------------------------------------------------------------------- 
# Modèle : greffe dans modeles.json (format identique à modeles_secondaires)
# ---------------------------------------------------------------------------
def _poids_semaines(ages_j):
    import numpy as np
    return np.exp(-XI_WEEK * np.asarray(ages_j, dtype=float) / 7.0)


def completer_modeles(out):
    """Greffe le marché « cmt1 » (corners 1re mi-temps) dans le dictionnaire
    de modèles avant sauvegarde. out = dictionnaire complet de entraine.py
    (clés « ligues » → div → « secondaires »). Sans données : ne fait rien."""
    import numpy as np
    etat = charger()
    if len(etat["matchs"]) < 100:
        return 0
    auj = datetime.date.today()
    par_div = {}
    for m in etat["matchs"].values():
        if not m.get("complet", False):
            continue                    # fil incomplet : hors entraînement
        try:
            dt = datetime.date.fromisoformat(m["date"])
        except ValueError:
            continue
        par_div.setdefault(m["div"], []).append(
            (dt, m["home"], m["away"], m["ch1"], m["ca1"]))
    greffes = 0
    for div, lignes in par_div.items():
        lig = (out.get("ligues") or {}).get(div)
        if not lig or "secondaires" not in lig or len(lignes) < 100:
            continue
        ref = max(l[0] for l in lignes)
        ages = [(ref - l[0]).days for l in lignes]
        w = _poids_semaines(ages)
        dom = np.array([l[3] for l in lignes], dtype=float)
        ext = np.array([l[4] for l in lignes], dtype=float)
        base = float(np.average(np.concatenate([dom, ext]),
                                weights=np.concatenate([w, w])))
        if not np.isfinite(base) or base <= 0:
            continue
        # dispersion mesurée (variance/moyenne) sur les comptes MT1
        tous = np.concatenate([dom, ext])
        disp = float(np.var(tous * 1.0) / max(np.mean(tous), 1e-9))
        disp = max(1.0, min(disp, 2.0)   # borne de sécurité
                  )
        sec = lig["secondaires"]
        sec.setdefault("base", {})
        sec["base"]["cmt1"] = round(base, 3)
        sec["base"]["cmt1_dispersion"] = round(disp, 3)
        sec["base"]["cmt1_n"] = len(lignes)
        equipes = sec.setdefault("equipes", {})
        em, rc = {}, {}
        for ww, (dt, h, a, dh, da) in zip(w, lignes):
            for t, marque, encaisse in ((h, dh, da), (a, da, dh)):
                e = em.setdefault(t, [0.0, 0.0])
                e[0] += marque * ww
                e[1] += ww
                r = rc.setdefault(t, [0.0, 0.0])
                r[0] += encaisse * ww
                r[1] += ww
        for t in set(list(em) + list(rc)):
            e = (em.get(t, [0, 0])[0] + K_LISSAGE * base) / (em.get(t, [0, 0])[1] + K_LISSAGE) / base
            r = (rc.get(t, [0, 0])[0] + K_LISSAGE * base) / (rc.get(t, [0, 0])[1] + K_LISSAGE) / base
            eq = equipes.setdefault(t, {})
            eq["cmt1_em"] = round(float(e), 4)
            eq["cmt1_rc"] = round(float(r), 4)
            eq["cmt1_n"] = round(float(em.get(t, [0, 0])[1]), 1)
        greffes += 1
    return greffes


def _pmf(lam, disp, kmax=KMAX):
    """Loi binomiale négative paramétrée (moyenne, dispersion) — EXACTEMENT
    la même fonction que le reste du robot (modeles_secondaires.pmf_marche)."""
    import modeles_secondaires as MS
    _k, p = MS.pmf_marche(lam, disp, kmax=kmax)
    return p


def pronostic(sec, home, away):
    """Pronostic corners MT1 d'un match. sec = ligues[div]['secondaires'].
    Retourne None si le marché n'est pas disponible (division non couverte,
    équipes sans facteur). Probabilités BRUTES (pas encore calibrées)."""
    import numpy as np
    if not sec or "cmt1" not in (sec.get("base") or {}):
        return None
    E = sec.get("equipes") or {}
    eh, rh = (E.get(home) or {}).get("cmt1_em"), (E.get(home) or {}).get("cmt1_rc")
    ea, ra = (E.get(away) or {}).get("cmt1_em"), (E.get(away) or {}).get("cmt1_rc")
    base = sec["base"]["cmt1"]
    disp = sec["base"].get("cmt1_dispersion", 1.15)
    for v in (eh, rh, ea, ra):
        if not isinstance(v, (int, float)) or not np.isfinite(v):
            return None
    lam_h = max(min(base * eh * ra, 12.0), 0.05)
    lam_a = max(min(base * ea * rh, 12.0), 0.05)
    ph = _pmf(lam_h, disp)
    pa = _pmf(lam_a, disp)
    M = np.outer(ph, pa)
    p_home = float(np.tril(M, -1).sum())   # domicile strictement plus
    p_nul = float(np.trace(M))
    p_away = float(np.triu(M, 1).sum())
    tot = np.convolve(ph, pa)              # loi du total MT1
    kk = np.arange(len(tot))
    over = {str(l): round(float(tot[kk > l].sum()), 4) for l in LIGNES_TOTAL}
    under = {str(l): round(float(tot[kk < l].sum()), 4) for l in LIGNES_TOTAL}
    return {"lambda_home": round(float(lam_h), 2),
            "lambda_away": round(float(lam_a), 2),
            "p_home": round(p_home, 4), "p_nul": round(p_nul, 4),
            "p_away": round(p_away, 4),
            "over": over, "under": under,
            "dispersion": disp,
            "n_h": (E.get(home) or {}).get("cmt1_n"),
            "n_a": (E.get(away) or {}).get("cmt1_n"),
            "n_base": sec["base"].get("cmt1_n")}


def resolu(div, date_iso, home, away):
    """Résultat MT1 RÉEL d'un match terminé (résolution automatique de
    l'affichage). Tolérance ±1 jour sur la date, comme le reste du robot."""
    etat = charger()
    for delta in ("", "-1", "+1"):
        if not delta:
            d = date_iso
        else:
            try:
                d = (datetime.date.fromisoformat(date_iso)
                     + datetime.timedelta(days=int(delta))).isoformat()
            except ValueError:
                continue
        m = etat["matchs"].get(f"{div}|{d}|{home}|{away}")
        if m:
            if not m.get("complet"):
                return None     # fil incomplet : pas de résolution automatique
            return {"ch1": m["ch1"], "ca1": m["ca1"],
                    "gagnant": "home" if m["ch1"] > m["ca1"] else
                               "away" if m["ca1"] > m["ch1"] else "nul",
                    "total": m["ch1"] + m["ca1"]}
    return None


# --------------------------------------------------------------------------- 
# Contrôle qualité
# ---------------------------------------------------------------------------
def verifier(n=12):
    """Compare les totaux reconstruits (ch+ca) au boxscore ET aux CSV co.uk
    (HC/AC) sur les matchs déjà collectés."""
    import csv as _csv
    etat = charger()
    # index CSV : (div, date, home, away) -> (HC, AC)
    idx = {}
    for chemin in glob.glob(os.path.join(DATA, "[0-9][0-9][0-9][0-9]_*.csv")):
        base = os.path.basename(chemin)
        div = base.split("_")[1].split(".")[0]
        if div not in DIVISIONS:
            continue
        try:
            with open(chemin, encoding="latin-1") as f:
                for ligne in _csv.DictReader(f):
                    dte = (ligne.get("Date") or "").strip()
                    h = ligne.get("HomeTeam") or ligne.get("Home")
                    a = ligne.get("AwayTeam") or ligne.get("Away")
                    hc, ac = ligne.get("HC"), ligne.get("AC")
                    if not (dte and h and a and hc and ac):
                        continue
                    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                        try:
                            dt = datetime.datetime.strptime(dte, fmt).date().isoformat()
                            break
                        except ValueError:
                            dt = None
                    if dt:
                        idx[(div, dt, h, a)] = (int(hc), int(ac))
        except (OSError, ValueError):
            continue
    n_ok = n_ko = n_part = 0
    echantillon = [m for m in etat["matchs"].values()
                   if (m["div"], m["date"], m["home"], m["away"]) in idx][:n]
    for m in echantillon:
        hc, ac = idx[(m["div"], m["date"], m["home"], m["away"])]
        meme = (m["ch"] == hc and m["ca"] == ac)
        ecart = abs(m["ch"] - hc) + abs(m["ca"] - ac)
        if meme:
            n_ok += 1
        elif ecart <= 1:
            n_part += 1
        else:
            n_ko += 1
            print(f"  ÉCART {m['div']} {m['date']} {m['home']}-{m['away']} : "
                  f"fil {m['ch']}-{m['ca']} vs CSV {hc}-{ac}")
    print(f"vérification vs CSV co.uk : {len(echantillon)} matchs | "
          f"identiques {n_ok} | écart ≤1 {n_part} | écarts >1 {n_ko}")
    comp = sum(1 for m in etat["matchs"].values() if m.get("complet"))
    print(f"contrôle interne texte==boxscore : {comp}/{len(etat['matchs'])} "
          f"({100.0*comp/max(len(etat['matchs']),1):.1f} %)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    if cmd == "backfill":
        backfill(sys.argv[2:] or None)
    elif cmd == "recent":
        n = collecter_recent()
        print(f"corners MT1 : {n} nouveau(x) match(s)")
    elif cmd == "verifier":
        verifier()
    else:
        print("usage : corners_mt.py [backfill [saisons]|recent|verifier]")
