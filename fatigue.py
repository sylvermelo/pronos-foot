"""
FATIGUE EUROPÉENNE — C1/C2/C3 jouée peu de jours avant le championnat.
=======================================================================
Principe (validé par l'utilisateur, étape ③ du plan) : une équipe qui joue
la Ligue des champions, l'Europa League ou la Conference League moins de
~5 jours avant son match de championnat est affaiblie. La littérature le
mesure (Ekstrand/UEFA sur 11 saisons ; Verheijen : asymétrie du repos court,
−40 % de victoires ; Harper : sprints réduits sous 4 jours de repos).

Rien n'est inventé ici : l'effet est MESURÉ sur nos propres données —
    · calendriers européens : ESPN (sans clé, par plages de dates — 1 requête
      couvre 6 semaines) → data/fatigue_coupes.json ;
    · matchs de championnat : les CSV co.uk déjà dans le dépôt (buts réels) ;
    · pour chaque apparition d'une équipe européenne en championnat : repos =
      jours depuis son dernier match de C1/C2/C3. On compare les buts
      marqués/encaissés par seau de repos à la moyenne de l'équipe cette
      saison-là (ratio). Seau de référence : repos ≥ 8 jours.

Application : multiplicateurs sur les λ de Dixon-Coles AU MOMENT du pronostic
(jamais dans l'entraînement — la fatigue est un état ponctuel, pas une force) :
    λ_domicile ×= f_att(domicile) × f_def(extérieur)
    λ_extérieur ×= f_att(extérieur) × f_def(domicile)
avec f_att ≤ 1 (marque moins) et f_def ≥ 1 (encaisse plus) mesurés par seau.
Un match de coupe dans les 7 jours AVANT le championnat compte ; au-delà,
aucun effet (le barème mesuré le dit).

Honnêteté : le match de coupe LUI-MÊME n'est pas prédit ici (voir coupes.py) ;
seul son effet résiduel sur le championnat suivant l'est. Les sélections
conseillées et combinés héritent automatiquement de l'ajustement puisque les
λ changent.

Usage :
    python fatigue.py backfill      # 3 saisons de coupes d'Europe (~70 requêtes)
    python fatigue.py mesurer       # mesure les multiplicateurs → data/fatigue_mesuree.json
    python fatigue.py rafraichir    # fenêtre glissante ±21 j (appelé par la CI)
"""
import datetime
import json
import os
import sys
import threading

RACINE = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.path.join(RACINE, "data", "fatigue_coupes.json")
CHEMIN_MESURE = os.path.join(RACINE, "data", "fatigue_mesuree.json")

COMPETITIONS = {"UCL": "uefa.champions", "UEL": "uefa.europa",
                "UECL": "uefa.europa.conf"}
NOMS_COMPS = {"UCL": "Ligue des champions", "UEL": "Europa League",
              "UECL": "Conference League"}
SAISONS = [("2024-07-01", "2025-07-15"), ("2025-07-01", "2026-07-15"),
           ("2026-07-01", None)]              # None = aujourd'hui + 21 j
PLAGE_JOURS = 42           # ESPN accepte les plages ; 6 semaines = sûr (testé)
FENETRE_REPOS = 7          # jours de repos examinés (au-delà : aucun effet)
REPOS_REFERENCE = 8        # repos ≥ 8 j = référence (ratio 1)
BORNE_MIN_N = 60           # échantillon minimal d'un seau (sinon fusionné)
CLAMP = (0.70, 1.40)       # garde-fou des multiplicateurs
_VERROU = threading.Lock()


# ---------------------------------------------------------------------------
# Stockage
# ---------------------------------------------------------------------------
def charger():
    try:
        with open(CHEMIN, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("matchs"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"matchs": {}, "plages_ok": [], "genere_le": None,
            "description": __doc__.splitlines()[1]}


def sauver(d, ajout=False):
    d["genere_le"] = datetime.datetime.now().isoformat(timespec="seconds")
    if ajout:
        d["dernier_ajout"] = d["genere_le"]
    tmp = CHEMIN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, CHEMIN)


# ---------------------------------------------------------------------------
# Collecte ESPN (par plages — 1 requête = 6 semaines d'une compétition)
# ---------------------------------------------------------------------------
def _plages(debut, fin):
    """Découpe [debut, fin] en fenêtres de PLAGE_JOURS (dates ISO)."""
    d0 = datetime.date.fromisoformat(debut)
    d1 = datetime.date.fromisoformat(fin)
    out = []
    while d0 <= d1:
        d2 = min(d0 + datetime.timedelta(days=PLAGE_JOURS - 1), d1)
        out.append((d0.isoformat(), d2.isoformat()))
        d0 = d2 + datetime.timedelta(days=1)
    return out


def collecter_plage(comp, debut, fin, etat):
    """Tous les matchs (joués OU programmés) d'une compétition sur une plage."""
    import calendrier
    slug = COMPETITIONS[comp]
    url = ("https://site.api.espn.com/apis/site/v2/sports/soccer/"
           f"{slug}/scoreboard?dates={debut.replace('-', '')}-{fin.replace('-', '')}")
    d = calendrier._curl_json(url, timeout=30)
    if d is None:
        return None
    cle_plage = f"{comp}|{debut}|{fin}"
    ajoutes = 0
    for e in d.get("events", []):
        try:
            dt = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        loc = dt + datetime.timedelta(hours=1)   # heure de Cotonou, comme le calendrier
        comp_e = (e.get("competitions") or [{}])[0]
        h = a = None
        bh = ba = None
        for co in comp_e.get("competitors", []):
            nom = (co.get("team") or {}).get("displayName")
            if co.get("homeAway") == "home":
                h = nom
                try:
                    bh = int(co.get("score"))
                except (TypeError, ValueError):
                    bh = None
            elif co.get("homeAway") == "away":
                a = nom
                try:
                    ba = int(co.get("score"))
                except (TypeError, ValueError):
                    ba = None
        if not h or not a:
            continue
        fini = e.get("status", {}).get("type", {}).get("completed", False)
        cle = f"{comp}|{loc.date().isoformat()}|{h}|{a}"
        with _VERROU:
            deja = cle in etat["matchs"]
        if deja:
            continue
        with _VERROU:
            etat["matchs"][cle] = {
                "comp": comp, "date": loc.date().isoformat(),
                "heure": loc.strftime("%H:%M"),
                "home_src": h, "away_src": a,
                "hg": bh if fini else None, "ag": ba if fini else None,
                "fini": fini, "evt": str(e.get("id")),
            }
        ajoutes += 1
    with _VERROU:
        if cle_plage not in etat["plages_ok"]:
            etat["plages_ok"].append(cle_plage)
    return ajoutes


def _fenetres():
    auj = datetime.date.today()
    out = []
    for debut, fin in SAISONS:
        f = fin or (auj + datetime.timedelta(days=21)).isoformat()
        out.extend(_plages(debut, f))
    return out


def backfill():
    etat = charger()
    ok = set(etat["plages_ok"])
    total = 0
    for debut, fin in _fenetres():
        for comp in COMPETITIONS:
            if f"{comp}|{debut}|{fin}" in ok:
                continue
            n = collecter_plage(comp, debut, fin, etat)
            if n:
                total += n
        sauver(etat, ajout=bool(total))
    print(f"fatigue européenne : {len(etat['matchs'])} matchs de coupes "
          f"d'Europe en base (+{total})")
    par_comp = {}
    for m in etat["matchs"].values():
        par_comp[m["comp"]] = par_comp.get(m["comp"], 0) + 1
    print("  par compétition :", par_comp)
    return etat


def rafraichir():
    """Fenêtre glissante pour la CI : 21 jours en arrière, 21 en avant.
    Les matchs PROGRAMMÉS sont collectés aussi : la fatigue d'un match de
    championnat dimanche se connaît dès que le calendrier européen existe."""
    etat = charger()
    auj = datetime.date.today()
    debut = (auj - datetime.timedelta(days=21)).isoformat()
    fin = (auj + datetime.timedelta(days=21)).isoformat()
    cle = f"rafraichir|{debut}|{fin}"
    if cle in set(etat["plages_ok"]):
        return 0
    total = 0
    for comp in COMPETITIONS:
        n = collecter_plage(comp, debut, fin, etat)
        if n:
            total += n
    # purge des anciennes fenêtres glissantes (évite l'accumulation de clés)
    etat["plages_ok"] = [p for p in etat["plages_ok"]
                         if not p.startswith("rafraichir|")] + [cle]
    sauver(etat, ajout=bool(total))
    return total


# ---------------------------------------------------------------------------
# Traduction des noms européens → noms co.uk (+ division domestique)
# ---------------------------------------------------------------------------
def equipes_par_division():
    import csv as _csv
    import glob
    eq = {}
    for chemin in glob.glob(os.path.join(RACINE, "data", "[0-9][0-9][0-9][0-9]_*.csv")):
        div = os.path.basename(chemin).split("_")[1].split(".")[0]
        try:
            with open(chemin, encoding="latin-1") as f:
                for ligne in _csv.DictReader(f):
                    h = ligne.get("HomeTeam") or ligne.get("Home")
                    a = ligne.get("AwayTeam") or ligne.get("Away")
                    if h and a:
                        eq.setdefault(div, set()).update([h, a])
        except OSError:
            continue
    return {k: sorted(v) for k, v in eq.items()}


_MAPPEUR = None
_EQ = None
_TRADUCTIONS = {}


def _traduire(nom_src):
    """nom ESPN → (nom co.uk, division) ou None. Une équipe européenne porte
    le nom de SA division domestique ; on teste les divisions une à une
    (le cache rend l'opération unique par nom)."""
    global _MAPPEUR, _EQ
    if nom_src in _TRADUCTIONS:
        return _TRADUCTIONS[nom_src]
    if _MAPPEUR is None:
        import calendrier
        _EQ = equipes_par_division()
        _MAPPEUR = calendrier.Mappeur(_EQ)
    res = None
    for div in sorted(_EQ):
        nom = _MAPPEUR.traduire(div, nom_src)
        if nom:
            res = (nom, div)
            break
    _TRADUCTIONS[nom_src] = res
    return res


def dates_coupes_par_equipe(etat=None):
    """{nom co.uk → [(date ISO, comp)]} trié, pour les matchs FINIS seulement
    (la fatigue ne se mesure que sur du joué)."""
    etat = etat or charger()
    out = {}
    for m in etat["matchs"].values():
        if not m.get("fini"):
            continue
        for cote in ("home_src", "away_src"):
            t = _traduire(m[cote])
            if not t:
                continue
            nom = t[0]
            out.setdefault(nom, []).append((m["date"], m["comp"]))
    for nom in out:
        out[nom].sort()
    return out


def dates_futures_par_equipe(etat=None):
    """{nom co.uk → [(date, comp)]} des matchs PROGRAMMÉS (à venir)."""
    etat = etat or charger()
    auj = datetime.date.today().isoformat()
    out = {}
    for m in etat["matchs"].values():
        if m["date"] < auj:
            continue                    # joué ou dépassé : traité ailleurs
        for cote in ("home_src", "away_src"):
            t = _traduire(m[cote])
            if not t:
                continue
            out.setdefault(t[0], []).append((m["date"], m["comp"]))
    for nom in out:
        out[nom].sort()
    return out


# ---------------------------------------------------------------------------
# Mesure de l'effet (sur nos CSV + les calendriers européens)
# ---------------------------------------------------------------------------
def mesurer(saisons_csv=("2425", "2526", "2627")):
    """Ratio buts marqués/encaissés par seau de repos, base = moyenne de
    l'équipe cette saison-là. Écrit data/fatigue_mesuree.json."""
    import csv as _csv
    etat = charger()
    dates = dates_coupes_par_equipe(etat)
    # apparitions européennes : (équipe, date) → repos impossible à précalculer
    # ici car il dépend du match de championnat suivant ; on calcule à la volée.
    apparitions = {}   # (saison, div, équipe) -> [(date, HM, AM, marque, encaisse, repos ou None)]
    for saison in saisons_csv:
        for div in sorted({os.path.basename(p).split("_")[1].split(".")[0]
                           for p in __import__("glob").glob(
                               os.path.join(RACINE, "data", f"{saison}_*.csv"))}):
            chemin = os.path.join(RACINE, "data", f"{saison}_{div}.csv")
            if not os.path.exists(chemin):
                continue
            with open(chemin, encoding="latin-1") as f:
                for ligne in _csv.DictReader(f):
                    d = None
                    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                        try:
                            d = datetime.datetime.strptime(ligne["Date"], fmt).date()
                            break
                        except (KeyError, ValueError):
                            continue
                    try:
                        hg = int(ligne.get("FTHG") or ligne.get("HG"))
                        ag = int(ligne.get("FTAG") or ligne.get("AG"))
                    except (TypeError, ValueError):
                        continue
                    if d is None:
                        continue
                    for eq, marque, encaisse in ((ligne.get("HomeTeam"), hg, ag),
                                                 (ligne.get("AwayTeam"), ag, hg)):
                        if not eq:
                            continue
                        cle = (saison, div, eq)
                        apparitions.setdefault(cle, []).append([d, marque, encaisse])
    # repos depuis la dernière coupe d'Europe pour chaque apparition
    seaux = {}       # repos (2..7, 1 pour ≤1, 99 pour référence ≥8) -> [n, marque, base_marque, encaisse, base_encaisse]
    for (saison, div, eq), apps in apparitions.items():
        if eq not in dates:
            continue
        n_tot = len(apps)
        if n_tot < 10:
            continue
        moy_m = sum(a[1] for a in apps) / n_tot
        moy_e = sum(a[2] for a in apps) / n_tot
        if moy_m <= 0 or moy_e <= 0:
            continue
        coupes = [datetime.date.fromisoformat(x[0]) for x in dates[eq]]
        for d, marque, encaisse in apps:
            precedents = [c for c in coupes if c < d]
            if not precedents:
                continue
            repos = (d - max(precedents)).days
            if repos > 30:
                continue
            seau = repos if repos <= REPOS_REFERENCE - 1 else 99
            if seau < 2:
                seau = 1                  # lendemain de coupe (rarissime)
            s = seaux.setdefault(seau, [0, 0.0, 0.0, 0.0, 0.0])
            s[0] += 1
            s[1] += marque
            s[2] += moy_m
            s[3] += encaisse
            s[4] += moy_e
    # fusion des seaux minces vers le voisin le plus proche (prudence)
    bareme = {}
    for seau in sorted(seaux):
        n, m, bm, e, be = seaux[seau]
        if seau == 99:
            continue
        if n < BORNE_MIN_N:
            continue                      # trop mince : pas de coefficient (→ 1.0)
        brut_att = m / bm
        brut_def = e / be
        # PRINCIPE CONSERVATEUR (honnêteté) : on n'applique l'effet mesuré
        # que dans le sens de la fatigue — une équipe fatiguée n'est JAMAIS
        # renforcée par le modèle. Les « bonus » mesurés (ex. repos 3 j :
        # défenses ×0,95) viennent vraisemblablement de biais de sélection
        # (calendrier, adversaires) et ne sont pas appliqués ; la mesure
        # brute reste affichée dans le fichier pour transparence.
        bareme[str(seau)] = {
            "n": n,
            "f_att": round(min(max(min(brut_att, 1.0), CLAMP[0]), CLAMP[1]), 4),
            "f_def": round(min(max(max(brut_def, 1.0), CLAMP[0]), CLAMP[1]), 4),
            "mesure_brute_att": round(brut_att, 4),
            "mesure_brute_def": round(brut_def, 4),
            "buts_marques_reels": round(m / n, 3),
            "buts_marques_attendus": round(bm / n, 3),
            "buts_encaisses_reels": round(e / n, 3),
            "buts_encaisses_attendus": round(be / n, 3),
        }
    ref = seaux.get(99)
    resultat = {
        "genere_le": datetime.datetime.now().isoformat(timespec="seconds"),
        "methode": "ratio buts réels / moyenne saison de l'équipe, par seau de "
                   "repos depuis le dernier match C1/C2/C3 ; référence repos ≥ 8 j",
        "reference": {"n": ref[0],
                      "ratio_att": round(ref[1] / ref[2], 4),
                      "ratio_def": round(ref[3] / ref[4], 4)} if ref else None,
        "bareme": bareme,
        "fenetre": FENETRE_REPOS,
    }
    with open(CHEMIN_MESURE, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=1)
    print(f"fatigue mesurée sur {sum(v[0] for v in seaux.values())} apparitions :")
    if ref:
        print(f"  référence (repos ≥ {REPOS_REFERENCE} j) : n={ref[0]} | "
              f"attaques {ref[1]/ref[2]:.3f} × attendu | défenses {ref[3]/ref[4]:.3f} × attendu")
    for seau in sorted(bareme):
        b = bareme[seau]
        print(f"  repos {seau} j : n={b['n']:4d} | marque ×{b['f_att']:.3f} "
              f"({b['buts_marques_reels']} vs {b['buts_marques_attendus']}) | "
              f"encaisse ×{b['f_def']:.3f} ({b['buts_encaisses_reels']} vs {b['buts_encaisses_attendus']})")
    return resultat


# ---------------------------------------------------------------------------
# Application au pronostic
# ---------------------------------------------------------------------------
_BAREME = None


def bareme():
    global _BAREME
    if _BAREME is None:
        try:
            with open(CHEMIN_MESURE, encoding="utf-8") as f:
                _BAREME = json.load(f)
        except (OSError, ValueError):
            _BAREME = {}
    return _BAREME


def dernier_match_coupe(equipe, date_match, dates=None):
    """(date ISO, comp) du dernier match européen JOUÉ avant date_match,
    dans la fenêtre FENETRE_REPOS, sinon None."""
    if dates is None:
        dates = dates_coupes_par_equipe()
    try:
        d = datetime.date.fromisoformat(date_match)
    except (TypeError, ValueError):
        return None
    meilleur = None
    for dc, comp in dates.get(equipe, ()):
        dc_d = datetime.date.fromisoformat(dc)
        delta = (d - dc_d).days
        if 0 <= delta <= FENETRE_REPOS:
            if meilleur is None or dc > meilleur[0]:
                meilleur = (dc, comp, delta)
    return meilleur


def coeffs_match(lig, home, away, date_match, dates=None):
    """Multiplicateurs de λ pour un match. Retourne
    (mult_lambda_home, mult_lambda_away, info) — (None, None, None) sans effet.
    info = dictionnaire sérialisable IDENTIQUE côté Python et JS (parité)."""
    if not date_match:
        return None, None, None
    try:                      # mesuré sur les matchs de CHAMPIONNAT uniquement
        import coupes
        if lig in coupes.COUPES:
            return None, None, None
    except Exception:
        pass
    b = bareme().get("bareme") or {}
    if not b:
        return None, None, None
    if dates is None:
        dates = dates_coupes_par_equipe()
    info = {}
    mult_h = mult_a = 1.0
    for eq, role in ((home, "home"), (away, "away")):
        der = dernier_match_coupe(eq, date_match, dates)
        if not der:
            continue
        dc, comp, repos = der
        seau = str(max(repos, 1))
        cel = b.get(seau)
        if not cel:
            continue
        f_att, f_def = cel["f_att"], cel["f_def"]
        if role == "home":
            mult_h *= f_att            # le fatigué marque moins
            mult_a *= f_def            # … et laisse l'adversaire marquer plus
        else:
            mult_a *= f_att
            mult_h *= f_def
        info[role] = {"equipe": eq, "comp": comp, "comp_nom": NOMS_COMPS.get(comp, comp),
                      "date_coupe": dc, "repos_j": repos,
                      "f_att": f_att, "f_def": f_def, "n": cel["n"]}
    if not info:
        return None, None, None
    mult_h = round(min(max(mult_h, CLAMP[0]), CLAMP[1]), 4)
    mult_a = round(min(max(mult_a, CLAMP[0]), CLAMP[1]), 4)
    if mult_h == 1.0 and mult_a == 1.0:
        return None, None, None
    return mult_h, mult_a, {"home": info.get("home"), "away": info.get("away")}


def export_app(jours_avant=None):
    """Données embarquées dans l'app autonome : barème mesuré + dates de
    coupe par équipe (fenêtre utile aux pronostics à venir).
    jours_avant : élargit la fenêtre arrière (tests de parité historique)."""
    auj = datetime.date.today()
    debut = (auj - datetime.timedelta(
        days=jours_avant if jours_avant else FENETRE_REPOS + 3)).isoformat()
    fin = (auj + datetime.timedelta(days=30)).isoformat()
    etat = charger()
    equipes = {}
    for m in etat["matchs"].values():
        if not (debut <= m["date"] <= fin):
            continue
        for cote in ("home_src", "away_src"):
            t = _traduire(m[cote])
            if not t:
                continue
            equipes.setdefault(t[0], []).append(
                [m["date"], m["comp"], 1 if m.get("fini") else 0])
    for nom in equipes:
        equipes[nom].sort()
    return {"bareme": bareme().get("bareme") or {},
            "reference": bareme().get("reference"),
            "fenetre": FENETRE_REPOS,
            "noms": NOMS_COMPS,
            "equipes": equipes}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "rafraichir"
    if cmd == "backfill":
        backfill()
    elif cmd == "mesurer":
        mesurer()
    elif cmd == "rafraichir":
        n = rafraichir()
        print(f"fatigue européenne : +{n} match(s) de coupes collecté(s)")
    else:
        print("usage : fatigue.py [backfill|mesurer|rafraichir]")
