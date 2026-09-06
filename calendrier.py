"""
Calendrier MULTI-SOURCES des matchs à venir.
============================================================================
Pourquoi : le fichier fixtures.csv de football-data.co.uk n'est rafraîchi
qu'une fois par semaine (Last-Modified vérifié : lundi). Entre deux mises à
jour, l'application était aveugle. On croise donc trois sources gratuites :

  1. ESPN  (API publique du site, sans clé)  : calendrier à ~7 jours par
     ligue, statut des matchs, ligne over/under du marché.
  2. TheSportsDB (clé publique « 3 »)        : prochain match de chaque ligue,
     utilisé seulement là où ESPN ne donne rien.
  3. OpenLigaDB (données ouvertes)           : renfort et recoupement Allemagne.

Les COTES restent celles de football-data.co.uk (15 bookmakers) : jonction par
(div, domicile, extérieur). Un match sans cote s'affiche sans comparaison au
marché — jamais avec un edge inventé.

Chaque match rendu porte sa source (« ESPN », « TheSportsDB », « co.uk ») :
l'interface l'affiche en badge, et le journal de mise à jour compte les
matchs fournis par chacune.

Rien ici n'est payant. Si une source tombe, les autres prennent le relais et
le journal le dit.
"""
import json
import subprocess
import datetime
import difflib
import unicodedata

# --------------------------------------------------------------------------- 1
# Correspondance division du moteur -> identifiant ESPN
ESPN_SLUGS = {
    "E0": "eng.1", "E1": "eng.2", "E2": "eng.3", "E3": "eng.4",
    "SC0": "sco.1", "SC1": "sco.2", "SC2": "sco.3", "SC3": "sco.4",
    "B1": "bel.1", "N1": "ned.1",
    "D1": "ger.1", "D2": "ger.2",
    "F1": "fra.1", "F2": "fra.2",
    "I1": "ita.1", "I2": "ita.2",
    "SP1": "esp.1", "SP2": "esp.2",
    "P1": "por.1", "T1": "tur.1", "G1": "gre.1",
}
# Coupes d'Europe et coupes nationales (pseudo-divisions — voir coupes.py) :
# UCL, Europa League, Conference League, Carabao Cup, Copa del Rey,
# Coppa Italia, DFB-Pokal, Coupe de France.
import coupes as _coupes
for _cle, _meta in _coupes.COUPES.items():
    ESPN_SLUGS[_cle] = _meta["slug"]
# TheSportsDB (secours) : identifiants de ligues connus
TSD_IDS = {"E0": "4328", "D1": "4331", "I1": "4332", "SP1": "4335",
           "F1": "4334", "P1": "4330", "N1": "4344", "T1": "4338",
           "G1": "4346", "SC0": "4340", "B1": "4336"}

# Corrections manuelles de noms (nom source -> nom football-data.co.uk).
# Complétée par mesure réelle sur les 21 ligues ; le flou statistique
# (difflib) fait le reste.
# Suffixes de raison sociale que co.uk ne écrit pas : on les retire avant
# de comparer (« Ipswich Town » -> « Ipswich », « Leeds United » -> « Leeds »).
SUFFIXES = [" Town", " City", " United", " Wanderers", " Rovers", " Athletic",
            " County", " North End", " Albion", " FC", " AFC", " CF", " SK",
            " BK", " SC", " SV", " VfL", " VfB", " AC", " AS", " SS", " RC",
            " SL", " KV", " KSC", " BSC", " FK", " IK", " IF", " Amsterdam",
            " Foot", " FCO", " 04", " 05", " 07", " 08", " 93", " 98", " 99",
            " 1846", " 1899", " 1900", " II", " Aveyron", " Lorraine",
            " Athens", " JK", " Amadora", " Praia"]
PREFIXES = ["1. FC ", "FC ", "SC ", "SV ", "VfL ", "VfB ", "TSV ", "Bayer ",
            "Eintracht ", "Dynamo ", "Arminia ", "Energie ", "KVC ", "KRC ",
            "KV ", "RSC ", "KAA ", "PEC ", "NEC ", "ADO ", "NAC ", "Racing ",
            "Fortuna ", "Heracles ", "Sparta ", "SpVgg ", "Stade ",
            "Real ", "Hellas ", "Rayo ", "AS ", "AC ", "SSC ", "UD ",
            "CD ", "SD ", "Caykur ", "Çaykur ", "MKE ", "Corendon ",
            "Fatih ", "PAS ", "CS ", "Vitória de ", "Vitoria de "]


def _variantes(nom):
    """Toutes les formes plausibles d'un nom : brut, manuel, sans préfixe(s)
    (jusqu'à 2 en chaîne, ex. « TSV Eintracht Braunschweig »), sans suffixe."""
    cands = [nom]
    if nom in MANUEL:
        cands.append(MANUEL[nom])
    front = list(cands)
    for _ in range(2):
        add = []
        for b in front:
            for p in PREFIXES:
                if b.startswith(p):
                    t = b[len(p):].strip()
                    if t and t not in front and t not in add:
                        add.append(t)
        front += add
    out = list(front)
    for b in front:
        for s in SUFFIXES:
            if b.endswith(s):
                t = b[:-len(s)].strip()
                if t and t not in out:
                    out.append(t)
    return list(dict.fromkeys(cands + out))

MANUEL = {
    "Manchester City": "Man City", "Manchester United": "Man United",
    "Brighton & Hove Albion": "Brighton", "Nottingham Forest": "Nott'm Forest",
    "Preston North End": "Preston", "Queens Park Rangers": "QPR",
    "West Bromwich Albion": "West Brom", "Peterborough United": "Peterboro",
    "Sheffield Wednesday": "Sheffield Weds", "Plymouth Argyle": "Plymouth",
    "Accrington Stanley": "Accrington", "Crewe Alexandra": "Crewe",
    "Heart of Midlothian": "Hearts", "Inverness Caledonian Thistle": "Inverness C",
    "Raith Rovers": "Raith Rvs", "Partick Thistle": "Partick",
    "Greenock Morton": "Morton", "Royal Charleroi SC": "Charleroi",
    "Union St.-Gilloise": "St. Gilloise", "KVC Westerlo": "Westerlo",
    "Sint-Truidense": "St Truiden", "Standard Liege": "Standard",
    "Zulte-Waregem": "Waregem", "Racing Genk": "Genk",
    "Waasland-Beveren": "Beveren", "OH Leuven": "Oud-Heverlee Leuven",
    "PEC Zwolle": "Zwolle", "NEC Nijmegen": "Nijmegen",
    "Ajax Amsterdam": "Ajax", "FC Twente": "Twente",
    "ADO Den Haag": "Den Haag", "Fortuna Sittard": "For Sittard",
    "FC Cologne": "FC Koln", "Bayer Leverkusen": "Leverkusen",
    "SC Paderborn 07": "Paderborn", "Eintracht Frankfurt": "Ein Frankfurt",
    "Arminia Bielefeld": "Bielefeld", "1. FC Nürnberg": "Nurnberg",
    "SV Darmstadt 98": "Darmstadt", "Energie Cottbus": "Cottbus",
    "Dynamo Dresden": "Dresden", "VfL Bochum": "Bochum",
    "Hertha Berlin": "Hertha", "Stade Rennais": "Rennes",
    "Stade Laval": "Laval", "Pau": "Pau FC",
    "1. FC Heidenheim 1846": "Heidenheim", "1. FC Magdeburg": "Magdeburg",
    "SpVgg Greuther Fürth": "Greuther Furth",
    "Eintracht Frankfurt": "Ein Frankfurt", "Stade de Reims": "Reims",
    "Celta Vigo": "Celta",
    "Saint-Étienne": "St Etienne", "AS Saint-Étienne": "St Etienne",
    "AS Nancy Lorraine": "Nancy", "Internazionale": "Inter",
    "Atlético Madrid": "Ath Madrid", "Atletico Madrid": "Ath Madrid",
    "Deportivo": "La Coruna", "Deportivo La Coruña": "La Coruna",
    "Sporting Gijón": "Sp Gijon", "Sporting Gijon": "Sp Gijon",
    "Athletic Club": "Ath Bilbao", "Athletic Bilbao": "Ath Bilbao",
    "Red Star FC 93": "Red Star", "Rodez Aveyron": "Rodez",
    "Braga": "Sp Braga", "SC Braga": "Sp Braga",
    "Sporting CP": "Sp Lisbon", "Sporting Lisbon": "Sp Lisbon",
    "Vitória de Guimaraes": "Guimaraes", "Vitoria de Guimaraes": "Guimaraes",
    "Vitória Guimarães": "Guimaraes",
    "Istanbul Basaksehir": "Buyuksehyr", "İstanbul Başakşehir": "Buyuksehyr",
    "Basaksehir FK": "Buyuksehyr",
    "Erzurum BB": "Erzurumspor", "Amed SFK": "Amedspor",
    "Adana Demirspor": "Ad. Demirspor",
    "Goztepe": "Goztep", "Göztepe": "Goztep",
    "Olympiacos": "Olympiakos", "Olympiakos Piraeus": "Olympiakos",
    "Volos NPS": "Volos NFC",
    "RC Celta Fortuna": "Celta B",
    "AVS Futebol SAD": "AVS", "Estoril Praia": "Estoril",
    "Paços de Ferreira": "Pacos Ferreira",
    "Tottenham Hotspur": "Tottenham", "Wolverhampton Wanderers": "Wolves",
    "West Ham United": "West Ham", "Newcastle United": "Newcastle",
    "Paris Saint-Germain": "Paris SG", "Olympique Lyonnais": "Lyon",
    "Olympique de Marseille": "Marseille", "AS Monaco": "Monaco",
    "Bayern München": "Bayern Munich", "Bayer 04 Leverkusen": "Leverkusen",
    "Borussia Mönchengladbach": "M'gladbach", "Borussia Dortmund": "Dortmund",
    "Eintracht Frankfurt": "Ein Frankfurt", "VfB Stuttgart": "Stuttgart",
    "RB Leipzig": "RB Leipzig", "1. FC Köln": "Köln", "FC Köln": "Köln",
    "Sport-Club Freiburg": "Freiburg", "SC Freiburg": "Freiburg",
    "TSG 1899 Hoffenheim": "Hoffenheim", "1. FSV Mainz 05": "Mainz",
    "FC St. Pauli": "St Pauli", "SV Werder Bremen": "Werder Bremen",
    "VfL Wolfsburg": "Wolfsburg", "FC Augsburg": "Augsburg",
    "Inter Milan": "Inter", "AC Milan": "Milan", "SSC Napoli": "Napoli",
    "AS Roma": "Roma", "Juventus Turin": "Juventus", "Genoa CFC": "Genoa",
    "Real Madrid CF": "Real Madrid", "FC Barcelona": "Barcelona",
    "Atlético de Madrid": "Ath Madrid", "Athletic Club": "Ath Bilbao",
    "Real Betis Balompié": "Betis", "Sevilla FC": "Sevilla",
    "Valencia CF": "Valencia", "Real Sociedad de Fútbol": "Sociedad",
    "RC Celta de Vigo": "Celta", "Getafe CF": "Getafe",
    "AFC Ajax": "Ajax", "PSV Eindhoven": "PSV", "Feyenoord Rotterdam": "Feyenoord",
    "FC Porto": "Porto", "SL Benfica": "Benfica", "Sporting CP": "Sp Lisbon",
    "Galatasaray SK": "Galatasaray", "Fenerbahçe SK": "Fenerbahce",
    "Beşiktaş JK": "Besiktas", "Trabzonspor SK": "Trabzonspor",
    "Olympiacos FC": "Olympiakos", "Panathinaikos FC": "Panathinaikos",
    "AEK Athens FC": "AEK", "PAOK FC": "PAOK",
    "Celtic FC": "Celtic", "Rangers FC": "Rangers",
    "Club Brugge KV": "Club Bruges", "RSC Anderlecht": "Anderlecht",
    "KRC Genk": "Genk", "Standard Liège": "Standard",
    "KAA Gent": "Gent", "Oud-Heverlee Leuven": "Oud-Heverlee Leuven",
}

UA = {"User-Agent": "curl/8.0"}


def _curl_json(url, timeout=25):
    """ESPN refuse l'empreinte TLS d'urllib mais accepte curl : on passe par curl."""
    try:
        p = subprocess.run(["curl", "-s", "--max-time", str(timeout), url],
                           capture_output=True, text=True, timeout=timeout + 5)
        return json.loads(p.stdout) if p.stdout.strip() else None
    except Exception:
        return None


def _norme(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if c.isalnum()).lower()


class Mappeur:
    """Traduit les noms d'équipes des sources vers ceux de co.uk, par ligue."""

    def __init__(self, equipes_par_div):
        self.eq = equipes_par_div or {}
        self.cache = {}
        self.rates = {}

    def traduire(self, div, nom):
        if not nom:
            return None
        cle = (div, nom)
        if cle in self.cache:
            return self.cache[cle]
        eqs = self.eq.get(div, [])
        normes = {_norme(e): e for e in eqs}
        res = None
        if nom in eqs:
            res = nom
        elif nom in MANUEL and MANUEL[nom] in eqs:
            res = MANUEL[nom]
        else:
            variantes = _variantes(nom)
            for v in variantes:                # exact, normalisé ou variant
                n = _norme(v)
                if n in normes:
                    res = normes[n]
                    break
            if res is None:                    # puis flou contrôlé
                for v in variantes:
                    m = difflib.get_close_matches(_norme(v), list(normes), n=1, cutoff=0.86)
                    if m:
                        res = normes[m[0]]
                        break
        if res is None:
            self.rates[nom] = self.rates.get(nom, 0) + 1
        self.cache[cle] = res
        return res


# --------------------------------------------------------------------------- 2
def _espn_jour(slug, date_iso):
    d = _curl_json(f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
                   f"{slug}/scoreboard?dates={date_iso.replace('-', '')}")
    out = []
    if not d:
        return out
    for e in d.get("events", []):
        if e.get("status", {}).get("type", {}).get("completed", False):
            continue
        comp = (e.get("competitions") or [{}])[0]
        h = a = None
        for co in comp.get("competitors", []):
            if co.get("homeAway") == "home":
                h = co.get("team", {}).get("displayName")
            elif co.get("homeAway") == "away":
                a = co.get("team", {}).get("displayName")
        dt = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        # affichage en heure de Cotonou (UTC+1), fuseau de l'utilisateur
        loc = dt + datetime.timedelta(hours=1)
        odds = [o for o in (comp.get("odds") or []) if o]
        out.append({"home_src": h, "away_src": a,
                    "date": loc.date().isoformat(),
                    "heure": loc.strftime("%H:%M"),
                    "ou_line": odds[0].get("overUnder") if odds else None,
                    "fournisseur_cote": odds[0].get("provider", {}).get("name") if odds else None})
    return out


def espn_resultats(slug, date_iso):
    """Scores FINAUX des matchs terminés d'une date (ESPN, sans clé).

    Retourne [{home_src, away_src, date, heure, buts_home, buts_away}].
    Les dates/heures sont converties en heure de Cotonou (UTC+1), comme le
    calendrier : c'est ce qui permet de retrouver les matchs du suivi.
    """
    d = _curl_json(f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
                   f"{slug}/scoreboard?dates={date_iso.replace('-', '')}")
    out = []
    if not d:
        return out
    for e in d.get("events", []):
        if not e.get("status", {}).get("type", {}).get("completed", False):
            continue
        comp = (e.get("competitions") or [{}])[0]
        h = a = None
        bh = ba = None
        for co in comp.get("competitors", []):
            nom = co.get("team", {}).get("displayName")
            try:
                buts = int(co.get("score"))
            except (TypeError, ValueError):
                buts = None
            if co.get("homeAway") == "home":
                h, bh = nom, buts
            elif co.get("homeAway") == "away":
                a, ba = nom, buts
        if not (h and a) or bh is None or ba is None:
            continue
        try:
            dt = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        loc = dt + datetime.timedelta(hours=1)
        out.append({"home_src": h, "away_src": a, "date": loc.date().isoformat(),
                    "heure": loc.strftime("%H:%M"), "buts_home": bh, "buts_away": ba})
    return out


def _tsd_prochain(div):
    lid = TSD_IDS.get(div)
    if not lid:
        return []
    d = _curl_json(f"https://www.thesportsdb.com/api/v1/json/3/"
                   f"eventsnextleague.php?id={lid}")
    out = []
    for e in (d or {}).get("events") or []:
        out.append({"home_src": e.get("strHomeTeam"), "away_src": e.get("strAwayTeam"),
                    "date": e.get("dateEvent"),
                    "heure": (e.get("strTime") or "")[:5],
                    "ou_line": None, "fournisseur_cote": None})
    return out


def _openligadb():
    d = _curl_json("https://api.openligadb.de/getmatchdata/bl1")
    out = []
    for m in d or []:
        if m.get("matchIsFinished"):
            continue
        dt = datetime.datetime.fromisoformat(
            (m.get("matchDateTimeUTC") or "").replace("Z", "+00:00") or None) \
            if m.get("matchDateTimeUTC") else None
        if not dt:
            continue
        loc = dt + datetime.timedelta(hours=1)
        out.append({"home_src": (m.get("team1") or {}).get("teamName"),
                    "away_src": (m.get("team2") or {}).get("teamName"),
                    "date": loc.date().isoformat(), "heure": loc.strftime("%H:%M"),
                    "ou_line": None, "fournisseur_cote": None})
    return out


# --------------------------------------------------------------------------- 3
def construire(equipes_par_div, cotes_co_uk, jours=8, log=None):
    """Rend la liste des matchs à venir, toutes sources confondues.

    equipes_par_div : {div: [noms co.uk]}   pour la traduction des noms
    cotes_co_uk     : liste des fixtures co.uk (pour la jonction des cotes)
    Retourne (matchs, journal).
    """
    log = log if log is not None else {}
    map_ = Mappeur(equipes_par_div)
    auj = datetime.date.today()
    dates = [(auj + datetime.timedelta(days=i)).isoformat() for i in range(jours)]
    vus = set()
    out = []
    par_source = {"ESPN": 0, "TheSportsDB": 0, "OpenLigaDB": 0}

    def ajouter(div, m, source):
        h = map_.traduire(div, m["home_src"])
        a = map_.traduire(div, m["away_src"])
        if not h or not a or h == a:
            return False
        cle = (div, h, a, m["date"])
        if cle in vus or m["date"] < auj.isoformat():
            return False
        vus.add(cle)
        out.append({"div": div, "home": h, "away": a, "date": m["date"],
                    "heure": m["heure"], "arbitre": None,
                    "source": source, "ou_line": m.get("ou_line"),
                    "cote_1": None, "cote_X": None, "cote_2": None,
                    "cote_over": None, "cote_under": None,
                    "cote_max_1": None, "cote_max_X": None, "cote_max_2": None})
        par_source[source] += 1
        return True

    # 1) ESPN, ligue par ligue, jour par jour
    for div, slug in ESPN_SLUGS.items():
        for d in dates:
            for m in _espn_jour(slug, d):
                ajouter(div, m, "ESPN")
    # 2) TheSportsDB seulement là où ESPN n'a rien donné sur la fenêtre
    présents = {o["div"] for o in out}
    for div in TSD_IDS:
        if div in présents:
            continue
        for m in _tsd_prochain(div):
            ajouter(div, m, "TheSportsDB")
    # 3) OpenLigaDB : recoupement Allemagne (n'ajoute que ce qui manque)
    for m in _openligadb():
        ajouter("D1", m, "OpenLigaDB")

    # jonction des cotes football-data.co.uk (semaine) par équipes
    idx = {(f["div"], f["home"], f["away"]): f for f in cotes_co_uk}
    avec_cotes = 0
    for o in out:
        f = idx.get((o["div"], o["home"], o["away"]))
        if f:
            for k in ("cote_1", "cote_X", "cote_2", "cote_over", "cote_under",
                      "cote_max_1", "cote_max_X", "cote_max_2", "arbitre"):
                o[k] = f.get(k)
            avec_cotes += 1
    out.sort(key=lambda x: (x["date"], x["heure"] or ""))
    log.update({"sources": par_source, "total": len(out),
                "avec_cotes": avec_cotes,
                "noms_non_traduits": dict(sorted(map_.rates.items(),
                                                 key=lambda z: -z[1])[:12]),
                "genere_le": datetime.datetime.now().isoformat(timespec="minutes")})
    return out, log


if __name__ == "__main__":
    import sys
    with open("data/modeles.json") as f:
        DB = json.load(f)
    eq = {d: sorted(L["forces"].keys()) for d, L in DB["ligues"].items()}
    m, log = construire(eq, DB.get("fixtures", []))
    print(f"{len(m)} matchs à venir :")
    for x in m[:25]:
        print(f"  {x['date']} {x['heure']} [{x['source']:<11}] "
              f"{x['home']:<22} vs {x['away']:<22} cotes:{'oui' if x['cote_1'] else '—'}")
    print("journal :", json.dumps(log, ensure_ascii=False, indent=1)[:2500])


def appliquer(db, cotes=None):
    """Construit le calendrier multi-sources et remplace db["fixtures"].

    db     : base modeles.json chargée (dict, modifiée sur place)
    cotes  : fixtures co.uk bruts (avec cotes) à jour ; à défaut, ceux déjà
             présents dans la base (db["fixtures_cotes"]).
    Les bruts sont conservés dans db["fixtures_cotes"] pour la jonction.
    Retourne le journal de construction.
    """
    eq = {d: sorted(L["forces"].keys()) for d, L in db.get("ligues", {}).items()}
    # pseudo-divisions de coupes : pas de forces propres, le traducteur de noms
    # travaille sur TOUTES les équipes des 21 divisions domestiques (index).
    _idx = db.get("index_equipes") or {}
    for d, L in db.get("ligues", {}).items():
        if L.get("coupe"):
            eq[d] = sorted(_idx)
    bruts = cotes or db.get("fixtures_cotes") or db.get("fixtures", [])
    matchs, log = construire(eq, bruts)
    if matchs:
        db["fixtures"] = matchs
        db["fixtures_cotes"] = bruts
        log["statut"] = "ok"
    else:
        log["statut"] = ("echec — calendrier existant conservé"
                         if db.get("fixtures") else "echec — aucun match")
    db["calendrier_log"] = log
    return log
