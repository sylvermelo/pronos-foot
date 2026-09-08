"""
db.py — PHASE 1 : la mémoire du robot dans Supabase (double écriture).
=======================================================================
Principe (docs/PLAN-PLATEFORME.md) :
  · le site et les JSON git restent la source PRINCIPALE — rien ne casse ;
  · à chaque exécution du robot, sélections / combinés / verdicts sont aussi
    écrits dans la base Postgres Supabase (upsert sur clés naturelles :
    rejouer une exécution ne duplique jamais rien) ;
  · chaque exécution laisse une ligne dans journal_pipeline (statut visible
    d'un coup d'œil dans le dashboard) ;
  · SANS les variables d'environnement SUPABASE_URL + SUPABASE_SERVICE_KEY,
    ce module ne fait RIEN et ne plante JAMAIS (retour « ignoré ») — c'est
    voulu : le pipeline continue de tourner avant la création du projet.

Sécurité :
  · la clé service_role (écriture) ne vit QUE dans GitHub Secrets /
    l'environnement — jamais dans un fichier du dépôt ;
  · RLS est activée sans politique publique : la clé anon ne voit rien.

Usage :
  python3 db.py --dry     # construit les lignes et les compte (sans écrire)
  python3 db.py --sync    # upsert sélections + combinés + ligne de journal
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile

RACINE = os.path.dirname(os.path.abspath(__file__))
CHEMIN_SUIVI = os.path.join(RACINE, "data", "suivi.json")
OK_HTTP = {"200", "201", "204"}


# ---------------------------------------------------------------- config
def config():
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY") or ""
    if not url.startswith("http") or not cle:
        return None
    return url, cle


def disponible():
    return config() is not None


def _requete(methode, chemin, donnees, params=""):
    """Appel PostgREST via curl (même tuyauterie que le reste du projet).
    Retourne (code_http, corps). (None, raison) si non configuré / échec."""
    cfg = config()
    if not cfg:
        return None, "Supabase non configuré (SUPABASE_URL / SUPABASE_SERVICE_KEY)"
    url, cle = cfg
    fd, tmp = tempfile.mkstemp(suffix=".json")
    reponse = tmp + ".resp"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False)
        cmd = ["curl", "-s", "--max-time", "30", "-X", methode,
               url + "/rest/v1/" + chemin + params,
               "-H", "apikey: " + cle,
               "-H", "Authorization: Bearer " + cle,
               "-H", "Content-Type: application/json",
               "-H", "Prefer: return=minimal,resolution=merge-duplicates",
               "-w", "%{http_code}", "-o", reponse, "-d", "@" + tmp]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        code = (p.stdout or "").strip() or "000"
        corps = ""
        try:
            with open(reponse, encoding="utf-8") as f:
                corps = f.read()[:400]
        except OSError:
            pass
        return code, corps
    except (subprocess.TimeoutExpired, OSError) as e:
        return None, str(e)
    finally:
        for x in (tmp, reponse):
            try:
                os.remove(x)
            except OSError:
                pass


# ---------------------------------------------------------------- lignes
def _lignes_selections(d):
    lignes = []
    for jour, entree in (d.get("jours") or {}).items():
        for s in entree.get("selections", []):
            r = s.get("resultat") or {}
            lignes.append({
                "jour": jour,
                "div": s.get("div") or "?",
                "ligue": s.get("ligue"),
                "heure": s.get("heure"),
                "home": s.get("home") or "?",
                "away": s.get("away") or "?",
                "option": s.get("option") or "?",
                "p": s.get("p"),
                "cote_juste": s.get("cote_juste"),
                "cote_marche": s.get("cote_marche"),
                "confiance": s.get("confiance"),
                "touche": r.get("touche"),
                "buts_home": r.get("buts_home"),
                "buts_away": r.get("buts_away"),
                "resolue_le": r.get("resolu_le"),
                "brut": s,
            })
    return lignes


def _lignes_combines(d):
    lignes = []
    for jour, entree in (d.get("jours") or {}).items():
        for nom, c in (entree.get("combines") or {}).items():
            if not isinstance(c, dict):
                continue
            r = c.get("resultat") or {}
            resolus = [l.get("resultat", {}).get("resolu_le")
                       for l in (c.get("legs") or [])
                       if isinstance(l.get("resultat"), dict)
                       and l["resultat"].get("resolu_le")]
            lignes.append({
                "jour": jour,
                "nom": nom,
                "p_combine": c.get("p_combine") or c.get("p"),
                "cote": c.get("cote_combine") or c.get("cote"),
                "touche": r.get("touche"),
                "resolu_le": max(resolus) if resolus else None,
                "jambes": c.get("legs") or [],
                "brut": c,
            })
    return lignes


# ---------------------------------------------------------------- écritures
def journal(statut, details=None, run_id=None):
    rid = run_id or os.environ.get("GITHUB_RUN_ID") or \
        "local-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return _requete("POST", "journal_pipeline",
                    [{"run_id": rid, "statut": statut,
                      "details": details or {}}])


def sync_suivi(d, run_id=None, combines_extra=None):
    """Upsert sélections + combinés depuis le contenu de data/suivi.json.
    Ne lève JAMAIS d'exception : retourne un dict de statut."""
    if not disponible():
        return {"statut": "ignore",
                "raison": "SUPABASE_URL / SUPABASE_SERVICE_KEY absentes"}
    try:
        sels = _lignes_selections(d)
        combs = _lignes_combines(d)
        resolues = sum(1 for s in sels if s["touche"] is not None)
        details = {"selections": len(sels), "dont_resolues": resolues,
                   "combines": len(combs), "jours": len(d.get("jours") or {}),
                   "source": "ci" if os.environ.get("GITHUB_RUN_ID") else "local"}
        code, corps = _requete(
            "POST", "selections", sels,
            "?on_conflict=jour,div,home,away,option")
        if code not in OK_HTTP:
            journal("echec", {**details, "etape": "selections",
                              "http": code, "corps": corps}, run_id)
            return {"statut": "echec", "etape": "selections",
                    "http": code, "corps": corps}
        code, corps = _requete(
            "POST", "combines", combs, "?on_conflict=jour,nom")
        if code not in OK_HTTP:
            journal("echec", {**details, "etape": "combines",
                              "http": code, "corps": corps}, run_id)
            return {"statut": "echec", "etape": "combines",
                    "http": code, "corps": corps}
        if combines_extra:
            details["coupon_corners"] = len(combines_extra)
            code, corps = _requete(
                "POST", "combines", combines_extra, "?on_conflict=jour,nom")
            if code not in OK_HTTP:
                journal("echec", {**details, "etape": "coupon",
                                  "http": code, "corps": corps}, run_id)
                return {"statut": "echec", "etape": "coupon",
                        "http": code, "corps": corps}
        journal("ok", details, run_id)
        return {"statut": "ok", **details}
    except Exception as e:                          # jamais bloquant
        try:
            journal("echec", {"exception": str(e)}, run_id)
        except Exception:
            pass
        return {"statut": "echec", "raison": str(e)}


# ---------------------------------------------------------------- CLI
def _charger_suivi():
    with open(CHEMIN_SUIVI, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    if "--dry" in sys.argv:
        d = _charger_suivi()
        sels, combs = _lignes_selections(d), _lignes_combines(d)
        print(f"dry-run : {len(sels)} sélection(s), {len(combs)} combiné(s), "
              f"{len(d.get('jours') or {})} jour(s)")
        if sels:
            print("exemple sélection :", json.dumps(sels[0], ensure_ascii=False)[:300])
        if combs:
            print("exemple combiné   :", json.dumps(combs[0], ensure_ascii=False)[:300])
        print("config Supabase   :", "présente" if disponible() else "ABSENTE (écriture ignorée)")
        sys.exit(0)
    if "--sync" in sys.argv:
        try:
            d = _charger_suivi()
        except (OSError, ValueError) as e:
            print(f"db.py : data/suivi.json illisible ({e}) — rien à synchroniser")
            sys.exit(0)
        r = sync_suivi(d)
        print("db.py :", json.dumps(r, ensure_ascii=False))
        sys.exit(0 if r.get("statut") in ("ok", "ignore") else 1)
    print(__doc__)
