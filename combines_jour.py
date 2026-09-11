"""COMBINÉS DU JOUR pour la vitrine (correctif 11/09, règle utilisateur :
« la vitrine doit toujours prendre les informations chez pronos-foot »).

Publie data/combines_jour.json (copié vers site/ par la CI) : les combinés du
robot (SAFE, SAFE week-end, COTE 2, COTE 5) pour AUJOURD'HUI et HIER, tels
qu'archivés/résolus par suivi.py — exactement ce que le site du robot affiche,
sans rien recréer ni réinventer côté vitrine.

Correctif au passage : `finaliser()` (serveur.py) ne renseigne pas la cote
totale des SAFE — elle restait « vide » partout. On la RECALCULE ici depuis
les cotes justes des jambes (produit des 1/p, arrondi 2 déc.), et db.py fait
désormais pareil avant l'écriture Supabase. Aucun chiffre inventé : c'est le
produit des cotes déjà calculées par le moteur.
"""
import datetime
import json
import os

RACINE = os.path.dirname(os.path.abspath(__file__))
SUIVI = os.path.join(RACINE, "data", "suivi.json")
PUBLIE = os.path.join(RACINE, "data", "combines_jour.json")
NOMS = ("safe", "safe_weekend", "cote2", "cote5")


def cote_depuis_jambes(c):
    """Cote totale = produit des cotes justes des jambes (1/p). Retourne la
    cote existante si elle est déjà renseignée."""
    if c.get("cote"):
        return c["cote"]
    prod = 1.0
    for l in c.get("legs") or []:
        p = l.get("p")
        if not p:
            return None
        prod *= 1.0 / p
    return round(prod, 2)


def construit():
    try:
        with open(SUIVI, encoding="utf-8") as f:
            suivi = json.load(f)
    except (OSError, ValueError):
        suivi = {}
    jours = suivi.get("jours") or {}
    auj = datetime.date.today().isoformat()
    hier = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    def vue(j):
        comb = (jours.get(j) or {}).get("combines") or {}
        out = {}
        for nom in NOMS:
            c = comb.get(nom)
            if not isinstance(c, dict):
                continue
            c = dict(c)
            c["cote"] = cote_depuis_jambes(c)
            out[nom] = c
        return out

    return {
        "genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
        "jour": auj,
        "du_jour": vue(auj),
        "hier": vue(hier),
        "note": ("Combinés du robot tels qu'archivés par suivi.py (SAFE ≥ seuils "
                 "mesurés, COTE 2 ≈ 1,90-2,35, COTE 5 ≈ 4,60-5,90 de cote juste). "
                 "Cotes = calcul du moteur (produit des cotes justes), jamais "
                 "celles d'un bookmaker. Le robot s'abstient plutôt que forcer : "
                 "une clé absente = pas de combiné ce jour-là."),
    }


if __name__ == "__main__":
    out = construit()
    with open(PUBLIE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    dj, h = out["du_jour"], out["hier"]
    print(f"combines_jour : aujourd'hui {sorted(dj) or '—'} | hier {sorted(h) or '—'}")
    for nom, c in list(dj.items()):
        print(f"  {nom} : cote {c.get('cote')} | p {c.get('p_combine')} | "
              f"{len(c.get('legs') or [])} jambe(s)")
