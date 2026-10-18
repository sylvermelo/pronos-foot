"""Corners finaux ESPN : uniquement pour les matchs en attente du suivi."""
import datetime
import json
from pathlib import Path
import calendrier as CAL
import buts_affilee as BA

CHEMIN = Path(__file__).resolve().parent / "data" / "corners_finaux.json"
_journees = {}
_cache = None
_appels = 0
MAX_SUMMARIES = 40


def extraire(summary):
    comp = ((summary.get("header") or {}).get("competitions") or [{}])[0]
    statut = (comp.get("status") or {}).get("type") or {}
    if not statut.get("completed"):
        return None
    # Ne pas confondre temps réglementaire et prolongations/tirs au but.
    if (comp.get("status") or {}).get("period", 2) > 2:
        return None
    equipes = {str(c.get("id") or (c.get("team") or {}).get("id")): c.get("homeAway")
               for c in comp.get("competitors", [])}
    valeurs = {}
    for t in (summary.get("boxscore") or {}).get("teams", []):
        cote = equipes.get(str((t.get("team") or {}).get("id")))
        if cote not in ("home", "away"):
            continue
        for s in t.get("statistics", []):
            if s.get("name") == "wonCorners":
                try:
                    v = int(s["displayValue"])
                except (ValueError, TypeError, KeyError):
                    return None
                if v < 0:
                    return None
                valeurs[cote] = v
    return (valeurs["home"], valeurs["away"]) if set(valeurs) == {"home", "away"} else None


def chercher(div, jour, home, away):
    global _cache, _appels
    if _cache is None:
        try:
            _cache = json.loads(CHEMIN.read_text())
        except (OSError, ValueError):
            _cache = {}
    cle = f"{div}|{jour}|{home}|{away}"
    if cle in _cache:
        return tuple(_cache[cle])
    if div not in CAL.ESPN_SLUGS or _appels >= MAX_SUMMARIES:
        return None
    k = (div, jour)
    if k not in _journees:
        _journees[k] = BA.journees(div, jour, jour)
    from suivi_series import _trouve_event
    trouve = _trouve_event(_journees[k], {"home": home, "away": away})
    if not trouve:
        return None
    eid, _ = trouve
    _appels += 1
    s = CAL._curl_json(f"{BA.BASE}/{CAL.ESPN_SLUGS[div]}/summary?event={eid}")
    resultat = extraire(s) if s else None
    if resultat is not None:
        _cache[cle] = resultat
        tmp = CHEMIN.with_suffix(".part")
        tmp.write_text(json.dumps(_cache))
        tmp.replace(CHEMIN)
    return resultat
