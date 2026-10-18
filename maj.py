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
        try:
            meta = json.loads((DATA / "sources_http.json").read_text())
            return meta.get(dest.name) != pub.isoformat()
        except (OSError, ValueError):
            return True
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
    a_telecharger = []
    for dest, url in cibles:
        if a_change(dest, h[str(dest)]):
            a_telecharger.append((dest, url))
        else:
            ignorés += 1
    def transfert(cible):
        dest, url = cible
        succes = telecharger(url, dest)
        time.sleep(0.12)
        return dest, succes
    with ThreadPoolExecutor(max_workers=4) as ex:
        transferts = list(ex.map(transfert, a_telecharger))
    for dest, succes in transferts:
        if succes:
            meta_file = DATA / "sources_http.json"
            try:
                meta = json.loads(meta_file.read_text())
            except (OSError, ValueError):
                meta = {}
            publiee = date_publiee(h[str(dest)])
            meta[dest.name] = publiee.isoformat() if publiee else None
            meta_file.write_text(json.dumps(meta))
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
def main():
    args = set(sys.argv[1:])
    if "--config" in args:
        choisir_config()
        return 0

    log("=" * 62)
    log("MISE À JOUR — pronos-foot")
    cfg = charger_config()

    # Collecter les scores AVANT de décider d'entraîner : même passage.
    if "--check" in args:
        if not verifier_source():
            return 2
        log(str(inspecter()))
        return 0
    import apprentissage
    apprentissage.restaurer_resultats()
    try:
        import resultats
        with open(DATA / "modeles.json") as f:
            base = json.load(f)
        n = resultats.collecter(base)
        log(f"résultats finaux : {n} ajout(s)/correction(s)")
        log(str(apprentissage.sauvegarder_resultats()))
    except Exception as e:
        log(f"collecte résultats indisponible : {e}", "WARN")

    # Historique lourd : deux passes quotidiennes maximum (horodatage interne).
    etat_path = DATA / "collectes.json"
    try:
        etat = json.loads(etat_path.read_text())
    except (OSError, ValueError):
        etat = {}
    maintenant = dt.datetime.now(dt.timezone.utc)
    dernier = etat.get("historique_le")
    du = not dernier or (maintenant - dt.datetime.fromisoformat(dernier)).total_seconds() >= 43200
    if du and verifier_source():
        maj_donnees()
        etat["historique_le"] = maintenant.isoformat()
        etat_path.write_text(json.dumps(etat))
    elif du:
        log("CSV indisponibles : résultats ESPN et données existantes conservés", "WARN")
    try:
        import xg
        xg.frais(jours=1)
    except Exception as e:
        log(f"xG indisponibles : cache conservé ({e})", "WARN")

    # Le cache réseau ne conserve que 2 jours ; il ne contient pas l'historique métier.
    for p in (DATA / "http_cache").glob("*.json"):
        try:
            if time.time() - json.loads(p.read_text())["fetched_at"] > 172800:
                p.unlink()
        except (OSError, ValueError, KeyError):
            pass
    empreinte = apprentissage.empreinte()
    try:
        modele = json.loads((DATA / "modeles.json").read_text())
    except (OSError, ValueError):
        modele = {}
    if modele.get("apprentissage", {}).get("empreinte") != empreinte:
        if not lancer("entraine.py", "données nouvelles ou moteur corrigé"):
            return 1
        modele = json.loads((DATA / "modeles.json").read_text())
        modele["apprentissage"] = apprentissage.etat(empreinte)
        tmp = DATA / "modeles.json.part"
        tmp.write_text(json.dumps(modele))
        os.replace(tmp, DATA / "modeles.json")
    else:
        log("données d'apprentissage inchangées : pas de réentraînement")
    # La CI orchestre une seule génération, sans doublon.
    if "--donnees-seules" in args:
        return 0
    if not lancer("maj_calendrier.py", "calendrier et suivi"):
        log("calendrier partiellement indisponible", "WARN")
    if not lancer("genere_app.py", "application"):
        return 1
    copier_vers_sync(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
