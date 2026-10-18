"""Traçabilité et mémoire durable des scores ; aucune donnée future inventée."""
import datetime
import hashlib
import json
import os
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
VERSION = "2026-10-18-normalisation-v1"


def empreinte():
    h = hashlib.sha256(VERSION.encode())
    for p in sorted(DATA.glob("2*_*.csv")) + [DATA / "xg_understat.json", DATA / "corners_mt.json"]:
        if p.exists():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    import resultats
    h.update(json.dumps(resultats.charger()["matchs"], sort_keys=True).encode())
    return h.hexdigest()


def etat(signature):
    import resultats
    matchs = resultats.charger()["matchs"]
    return {"version": VERSION, "empreinte": signature,
            "resultats_complementaires": len(matchs),
            "dernier_resultat": max((m["date"] for m in matchs.values()), default=None),
            "entraine_le": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "note": "Scores finaux intégrés avant entraînement ; coupes conservées séparément, pas assimilées à des matchs de championnat."}


def restaurer_resultats():
    """Relit les scores privés lors de perte du cache, sans effacer le local."""
    import db
    import resultats
    if not db.disponible():
        return 0
    d = resultats.charger()
    # Une restauration par jour suffit ; aucune lecture d'identités clients.
    auj = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    if d.get("restaure_le") == auj:
        return 0
    n = 0
    for offset in range(0, 100000, 1000):
        code, corps = db._requete("GET", "matchs", None,
            "?select=division,saison,date_match,heure,home,away,buts_home,buts_away"
            f"&statut=eq.fini&order=id&limit=1000&offset={offset}")
        if code != "200":
            return n
        lignes = json.loads(corps)
        for m in lignes:
            cle = f"{m['division']}|{m['date_match']}|{m['home']}|{m['away']}"
            if cle not in d["matchs"]:
                d["matchs"][cle] = {"div": m["division"], "season": m["saison"],
                    "date": m["date_match"], "heure": m["heure"], "home": m["home"],
                    "away": m["away"], "hg": m["buts_home"], "ag": m["buts_away"]}
                n += 1
        if len(lignes) < 1000:
            d["restaure_le"] = auj
            # La signature ne dépend pas de cet horodatage de restauration.
            resultats.sauver(d)
            return n
    raise RuntimeError("Restauration incomplète : limite de pagination atteinte")


def sauvegarder_resultats():
    """Upserts privés des seuls scores nouveaux/corrigés. Pas de purge."""
    import db
    import resultats
    if not db.disponible():
        return {"statut": "ignore"}
    chemin = DATA / "resultats_synchronises.json"
    try:
        connus = json.loads(chemin.read_text())
    except (OSError, ValueError):
        connus = {}
    attente = []
    signatures = {}
    for cle, m in resultats.charger()["matchs"].items():
        row = {"division": m["div"], "saison": m.get("season") or resultats.saison_pour(m["date"]),
               "date_match": m["date"], "heure": m.get("heure"), "home": m["home"],
               "away": m["away"], "statut": "fini", "buts_home": m["hg"], "buts_away": m["ag"]}
        sig = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
        signatures[cle] = sig
        if connus.get(cle) != sig:
            attente.append((cle, row))
    for i in range(0, len(attente), 250):
        lot = attente[i:i + 250]
        code, corps = db._requete("POST", "matchs", [r for _, r in lot],
                                  "?on_conflict=division,saison,date_match,home,away")
        if code not in db.OK_HTTP:
            raise RuntimeError(f"Sauvegarde scores non confirmée : HTTP {code}")
        for cle, _ in lot:
            connus[cle] = signatures[cle]
        tmp = chemin.with_suffix(".part")
        tmp.write_text(json.dumps(connus))
        os.replace(tmp, chemin)
    return {"statut": "ok", "resultats_sauvegardes": len(attente)}
