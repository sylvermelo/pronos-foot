"""Prix reçus exclusivement ; aucune conversion de probabilité en cote."""
import datetime
import math


def option_outcome(market, o, e):
    nom = o.get("name")
    if market in ("totals", "alternate_totals") and nom in ("Over", "Under"):
        if o.get("point") in (1.5, 2.5, 3.5):
            return f"{nom.lower()} {o['point']}"
    if market == "h2h":
        return {e.get("home_team"): "1", "Draw": "X", e.get("away_team"): "2"}.get(nom)
    if market == "double_chance":
        # Noms normalisés documentés et noms d'équipes explicites.
        return {"Home or Draw": "double chance 1X", "Draw or Away": "double chance X2", "Away or Draw": "double chance X2", "Home or Away": "double chance 12", "Home/Draw": "double chance 1X", "Draw/Away": "double chance X2",
                "Home/Away": "double chance 12",
                f"{e.get('home_team')}/Draw": "double chance 1X",
                f"Draw/{e.get('away_team')}": "double chance X2",
                f"{e.get('home_team')}/{e.get('away_team')}": "double chance 12"}.get(nom)
    return None


def valide(q, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        date = datetime.datetime.fromisoformat(q["last_update"].replace("Z", "+00:00"))
        debut = datetime.datetime.fromisoformat(q["commence_time"].replace("Z", "+00:00"))
        return (bool(q.get("bookmaker") and q.get("event_id")) and math.isfinite(q["price"])
                and q["price"] > 1 and 0 <= (now - date).total_seconds() <= 86400
                and debut > now)
    except (KeyError, TypeError, ValueError):
        return False


def produit(legs):
    """Prix archivés à la décision, pas revalidés après le match historique."""
    if not legs or any(not l.get("cotation") or not l.get("cote_marche") for l in legs):
        return None
    if len({l["cotation"].get("bookmaker") for l in legs}) != 1:
        return None
    return round(math.prod(l["cote_marche"] for l in legs), 2)
