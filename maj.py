"""
MISE À JOUR AUTOMATIQUE — à lancer tous les jours, ou à la main.
================================================================================
Ce script remplace fetch.py, qui avait deux défauts bloquants pour la continuité :
  1. il ne re-téléchargeait JAMAIS un fichier déjà présent ;
  2. il ne couvrait que 11 divisions sur 21, et oubliait la saison en cours.

Celui-ci :
  · détermine tout seul la saison en cours et les 4 précédentes
  · couvre les 21 divisions reconnues
  · n'interroge le réseau que pour savoir SI quelque chose a changé
    (requête d'en-tête, quelques dizaines d'octets) et ne télécharge que
    les fichiers réellement modifiés
  · ne ré-entraîne les modèles que si c'est utile
  · régénère le fichier HTML autonome et peut le déposer dans un dossier
    synchronisé (Google Drive, iCloud, OneDrive, Dropbox) pour que ton
    téléphone et tes autres ordinateurs en profitent
  · n'écrase jamais rien en cas de coupure internet

Fonctionne à l'identique sur Windows, Mac et Linux.

Usage :
    python3 maj.py             mise à jour normale (source co.uk si changée,
                               calendrier multi-sources toujours reconstruit)
    python3 maj.py --check     regarde seulement s'il y a du nouveau, ne touche à rien
    python3 maj.py --config    choisit le dossier de synchronisation
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path

# nombre de requêtes simultanées : assez pour aller vite, assez bas pour
# rester poli avec un serveur gratuit
PARALLELE = 8

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
LOG = DATA / "maj.log"
CONFIG = DATA / "config.json"
BASE = "https://www.football-data.co.uk"
ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; pronos-foot/1.0)"}

DIVS = ["E0", "E1", "E2", "E3", "SP1", "SP2", "I1", "I2", "D1", "D2", "F1", "F2",
        "N1", "B1", "P1", "T1", "G1", "SC0", "SC1", "SC2", "SC3"]
APP = RACINE / "pronos-foot-autonome.html"


# --------------------------------------------------------------------- journal
def log(msg, niveau="INFO"):
    ligne = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} [{niveau}] {msg}"
    print(ligne)
    try:
        DATA.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
        # on garde le journal raisonnable : 500 dernières lignes
        if LOG.stat().st_size > 400_000:
            lignes = LOG.read_text(encoding="utf-8").splitlines()[-500:]
            LOG.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------- config
def dossiers_sync_possibles():
    """Détecte les dossiers partagés par cloud installés sur la machine."""
    m = Path.home()
    cands = [
        m / "Google Drive",
        m / "GoogleDrive",
        m / "OneDrive",
        m / "Dropbox",
        m / "Library/Mobile Documents/com~apple~CloudDocs",   # iCloud (Mac)
        m / "iCloudDrive",
    ]
    # OneDrive peut porter un nom d'entreprise
    for p in m.glob("OneDrive*"):
        if p.is_dir() and p not in cands:
            cands.append(p)
    return [p for p in cands if p.is_dir()]


def charger_config():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log("config.json illisible, valeurs par défaut rétablies", "WARN")
    cfg = {"dossier_sync": None, "entrainer_si_changement": True}
    DATA.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def choisir_config():
    print("\nOù déposer le fichier HTML mis à jour, pour que tes autres\n"
          "appareils (téléphone, autre ordinateur) en profitent ?\n")
    cands = dossiers_sync_possibles()
    if not cands:
        print("  Aucun dossier cloud détecté sur cette machine.")
        print("  Le fichier restera simplement dans le dossier de l'application.\n")
        cfg = charger_config()
        cfg["dossier_sync"] = None
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        return cfg
    print("  0. Aucun — garder le fichier seulement ici")
    for i, p in enumerate(cands, 1):
        print(f"  {i}. {p}")
    rep = input("\nTon choix (numéro) : ").strip()
    cfg = charger_config()
    if rep.isdigit() and 1 <= int(rep) <= len(cands):
        cfg["dossier_sync"] = str(cands[int(rep) - 1])
        log(f"dossier de synchronisation : {cfg['dossier_sync']}")
    else:
        cfg["dossier_sync"] = None
        log("aucun dossier de synchronisation choisi")
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


# ---------------------------------------------------------------------- saisons
def saisons_pertinentes(aujourdhui=None):
    """Saison en cours + les 4 précédentes. Se déduit de la date, jamais codé en dur."""
    d = aujourdhui or dt.date.today()
    a = d.year
    # une saison de football va d'août à mai ; en juillet la nouvelle démarre
    courante = f"{a % 100:02d}{(a + 1) % 100:02d}" if d.month >= 7 \
        else f"{(a - 1) % 100:02d}{a % 100:02d}"
    base = 2000 + int(courante[:2])
    out = []
    for k in range(5):
        y = base - k
        out.append(f"{y % 100:02d}{(y + 1) % 100:02d}")
    return out


# ----------------------------------------------------------------------- réseau
def entete(url, timeout=25):
    """Renvoie les en-têtes HTTP sans télécharger le fichier, ou None si absent."""
    try:
        req = urllib.request.Request(url, headers=ENTETES, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return dict(r.headers)
    except Exception:
        return None


def date_publiee(entetes):
    if not entetes:
        return None
    v = entetes.get("Last-Modified") or entetes.get("last-modified")
    if not v:
        return None
    try:
        return parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None


def telecharger(url, dest):
    """Télécharge dans un fichier temporaire puis déplace : jamais de fichier tronqué."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers=ENTETES)
        with urllib.request.urlopen(req, timeout=40) as r:
            contenu = r.read()
        if len(contenu) < 500:
            log(f"{dest.name} : réponse trop courte ({len(contenu)} o), ignorée", "WARN")
            return False
        tmp.write_bytes(contenu)
        shutil.move(str(tmp), str(dest))
        return True
    except Exception as e:
        log(f"{dest.name} : échec du téléchargement ({e})", "WARN")
        if tmp.exists():
            tmp.unlink()
        return False


# ------------------------------------------------------------------ mise à jour
def verifier_source():
    """Un seul coup d'œil à la source suffit : la page d'accueil liste tout."""
    return entete(f"{BASE}/fixtures.csv") is not None


def a_change(dest, entetes):
    """True si le fichier distant est plus récent que la copie locale."""
    if entetes is None:
        return None                      # absent de la source
    pub = date_publiee(entetes)
    if dest.exists() and pub is not None:
        local = dt.datetime.fromtimestamp(dest.stat().st_mtime, tz=dt.timezone.utc)
        return pub > local
    return not dest.exists() or pub is None


def sonder(cibles):
    """Interroge la source en parallèle. cibles = [(chemin_local, url), ...]"""
    with ThreadPoolExecutor(max_workers=PARALLELE) as ex:
        entetes = list(ex.map(lambda cu: entete(cu[1]), cibles))
    return dict(zip((str(c[0]) for c in cibles), entetes))


def inspecter():
    """Compte ce qui a changé sur la source SANS rien télécharger.

    Renvoie (historiques_nouveaux, fixtures_modifiees, absents).
    """
    cibles = [(DATA / f"{s_}_{d_}.csv", f"{BASE}/mmz4281/{s_}/{d_}.csv")
              for s_ in saisons_pertinentes() for d_ in DIVS]
    fx = DATA / "fixtures.csv"
    cibles.append((fx, f"{BASE}/fixtures.csv"))

    t0 = time.time()
    h = sonder(cibles)
    log(f"  source interrogée en {time.time() - t0:.0f} s ({len(cibles)} fichiers)")

    nouveaux = absents = 0
    for dest, _ in cibles[:-1]:
        r = a_change(dest, h[str(dest)])
        if r is None:
            absents += 1
        elif r:
            nouveaux += 1
    fx_mod = bool(a_change(fx, h[str(fx)]))
    return nouveaux, fx_mod, absents


def maj_donnees():
    """Télécharge uniquement ce qui a changé. Renvoie (n_historiques, fixtures_a_change)."""
    DATA.mkdir(exist_ok=True)
    changés_hist = échecs = 0

    saisons = saisons_pertinentes()
    log(f"saisons ciblées : {', '.join(saisons)} | {len(DIVS)} divisions")

    cibles = [(DATA / f"{s_}_{d_}.csv", f"{BASE}/mmz4281/{s_}/{d_}.csv")
              for s_ in saisons for d_ in DIVS]
    fx = DATA / "fixtures.csv"
    cibles.append((fx, f"{BASE}/fixtures.csv"))

    # une seule passe parallèle pour savoir ce qui a changé
    t0 = time.time()
    h = sonder(cibles)
    log(f"  source interrogée en {time.time() - t0:.0f} s ({len(cibles)} fichiers)")

    ignorés = 0
    fx_changé = False
    for dest, url in cibles:
        r = a_change(dest, h[str(dest)])
        if r is None:
            ignorés += 1                   # absent de la source : normal
            continue
        if not r:
            ignorés += 1                   # déjà à jour
            continue
        if telecharger(url, dest):
            if dest is fx or dest.name == "fixtures.csv":
                fx_changé = True
                log(f"  ↓ fixtures.csv ({dest.stat().st_size} o)")
            else:
                changés_hist += 1
                pub = date_publiee(h[str(dest)])
                log(f"  ↓ {dest.name}"
                    + (f" (publié le {pub:%d/%m/%Y %H:%M} UTC)" if pub else ""))
        else:
            échecs += 1
        time.sleep(0.12)                   # rester poli avec le serveur gratuit

    log(f"historiques : {changés_hist} téléchargés, {ignorés} déjà à jour, {échecs} échecs")
    return changés_hist, fx_changé, échecs


def lancer(script, duree_attendue):
    log(f"→ {script} ({duree_attendue})")
    t0 = time.time()
    r = subprocess.run([sys.executable, str(RACINE / script)],
                       cwd=str(RACINE), capture_output=True, text=True)
    if r.returncode != 0:
        log(f"{script} a ÉCHOUÉ : {r.stderr.strip()[-600:]}", "ERROR")
        return False
    log(f"  {script} terminé en {time.time() - t0:.0f} s")
    return True


def copier_vers_sync(cfg):
    if not cfg.get("dossier_sync") or not APP.exists():
        return
    dest = Path(cfg["dossier_sync"])
    if not dest.is_dir():
        log(f"dossier de synchronisation introuvable : {dest}", "WARN")
        return
    cible = dest / APP.name
    try:
        shutil.copy2(str(APP), str(cible))
        log(f"→ fichier copié vers {cible}")
    except OSError as e:
        log(f"copie vers le dossier synchronisé impossible : {e}", "WARN")


# ------------------------------------------------------------------------ main
def complement_espn_plus_frais():
    """BOUCLE RAPIDE : le complément ESPN (resultats.py) contient-il des
    résultats écrits APRÈS le dernier entraînement ? On compare les
    horodatages INTERNES des fichiers (champ « genere_le », format ISO donc
    triable) : les dates de modification (mtime) ne survivent pas de façon
    fiable au cache GitHub Actions — constaté sur le run du 07/09 20h25."""
    def horodatage(chemin, cle="genere_le"):
        try:
            with open(chemin, encoding="utf-8") as f:
                return json.load(f).get(cle) or ""
        except (OSError, ValueError, AttributeError):
            return ""
    mod = horodatage(DATA / "modeles.json")
    res = horodatage(DATA / "resultats_espn.json")
    if res and mod and res > mod:
        return True
    # corners 1re mi-temps : de nouveaux matchs découpés rafraîchissent le
    # marché « cmt1 » (corners_mt.py) → même déclencheur.
    cmt = horodatage(DATA / "corners_mt.json", "dernier_ajout")
    if cmt and mod and cmt > mod:
        return True
    if res and mod:
        return False
    try:                      # secours : dates de modification des fichiers
        return (os.path.getmtime(DATA / "resultats_espn.json")
                > os.path.getmtime(DATA / "modeles.json"))
    except OSError:
        return False


def main():
    args = set(sys.argv[1:])
    if "--config" in args:
        choisir_config()
        return 0

    log("=" * 62)
    log("MISE À JOUR — pronos-foot")
    cfg = charger_config()

    if not verifier_source():
        log("source football-data.co.uk inaccessible (pas d'internet ?). "
            "Rien n'est modifié, les données existantes restent utilisables.", "WARN")
        # BOUCLE RAPIDE : co.uk en panne ne doit pas bloquer l'entraînement —
        # entraine.py travaille uniquement sur les fichiers locaux (CSV en
        # cache + complément ESPN). On ré-entraîne si besoin, puis on sort
        # quand même en code 2 (le workflow continue : calendrier, app, pub).
        if complement_espn_plus_frais() and cfg.get("entrainer_si_changement", True):
            log("boucle rapide : complément ESPN plus récent que les modèles — "
                "ré-entraînement sans attendre co.uk")
            lancer("entraine.py", "≈35 s")
        return 2

    if "--check" in args:
        log("mode --check : simple inspection, aucun fichier ne sera modifié")
        nouveaux, fx_mod, absents = inspecter()
        log(f"  {nouveaux} fichier(s) historique(s) plus récent(s) sur la source")
        log(f"  liste des matchs à venir modifiée : {'oui' if fx_mod else 'non'}")
        log(f"  {absents} combinaison(s) saison/division absente(s) (normal)")
        if nouveaux or fx_mod:
            log("→ une mise à jour est utile : relance sans --check")
        else:
            log("→ rien de neuf, aucune mise à jour nécessaire")
        return 0

    changés, fx_changé, échecs = maj_donnees()

    # xG RÉELS (Understat, sans compte ni clé) : rafraîchit le cache s'il a plus
    # de 7 jours, AVANT un éventuel ré-entraînement. Échec non bloquant : le
    # modèle retombe sur le fichier xG existant (ou sur les buts seuls).
    try:
        import xg
        n_xg = sum(len(v) for v in xg.frais().values())
        log(f"xG Understat : {n_xg} matchs en cache")
    except Exception as e:
        log(f"xG Understat : échec non bloquant ({e}) — cache existant conservé", "WARN")

    if changés == 0 and not fx_changé:
        log("aucune nouveauté sur la source co.uk — le calendrier multi-sources "
            "(ESPN + TheSportsDB + OpenLigaDB) est quand même reconstruit, "
            "car il évolue tous les jours.")

    # BOUCLE RAPIDE : ré-entraîner aussi quand le complément ESPN est plus
    # récent que les modèles (voir complement_espn_plus_frais / resultats.py).
    if (changés > 0 or complement_espn_plus_frais()) and cfg.get("entrainer_si_changement", True):
        if not lancer("entraine.py", "≈35 s"):
            log("entraînement échoué : le fichier autonome n'est PAS régénéré, "
                "l'ancienne version reste en place.", "ERROR")
            return 1
    elif fx_changé:
        log("seule la liste des matchs à venir a changé : pas besoin de ré-entraîner")

    if not lancer("maj_calendrier.py", "≈40 s"):
        log("calendrier multi-sources ÉCHOUÉ (sources injoignables ?) : "
            "le calendrier existant est conservé.", "WARN")

    if not lancer("genere_app.py", "≈2 s"):
        log("génération du fichier autonome échouée", "ERROR")
        return 1

    copier_vers_sync(cfg)

    if échecs:
        log(f"terminé avec {échecs} échec(s) de téléchargement — "
            "ils seront retentés à la prochaine exécution", "WARN")
    else:
        log("mise à jour terminée avec succès")
    return 0


if __name__ == "__main__":
    sys.exit(main())
