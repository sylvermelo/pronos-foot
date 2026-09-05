"""
Reconstruit le calendrier multi-sources (ESPN + TheSportsDB + OpenLigaDB)
et le fusionne dans data/modeles.json. Les cotes restent celles de
football-data.co.uk (jonction par équipes). Sauvegarde aussi
data/calendrier.json pour l'application autonome.

Léger et sans ré-entraînement : exécutable à chaque mise à jour, même quand
la source co.uk n'a pas bougé (les calendriers ESPN, eux, changent souvent).
"""
import csv, json, os, sys, datetime

RACINE = os.path.dirname(os.path.abspath(__file__))
os.chdir(RACINE)
sys.path.insert(0, RACINE)

import calendrier

CHEMIN_DB = os.path.join("data", "modeles.json")


def _num(x):
    try:
        v = float(str(x).strip())
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def lire_cotes_co_uk(chemin=os.path.join("data", "fixtures.csv")):
    """Relit le fixtures.csv fraîchement téléchargé : même quand co.uk a publié
    de nouvelles cotes sans nouveauté historique, maj.py ne ré-entraîne pas et
    modeles.json garderait les ANCIENNES cotes. On repart donc toujours du
    fichier brut. Aucun échec n'est bloquant : None → repli sur la base."""
    if not os.path.exists(chemin):
        return None
    out = []
    try:
        with open(chemin, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                d = (r.get("Date") or "").strip()
                date_iso = ""
                try:                      # format co.uk : JJ/MM/AAAA
                    jj, mm, aa = d.split("/")
                    date_iso = f"{aa}-{mm}-{jj}"
                except ValueError:
                    pass
                out.append({
                    "div": (r.get("Div") or "").strip(), "date": date_iso,
                    "heure": (r.get("Time") or "").strip()[:5],
                    "home": (r.get("HomeTeam") or "").strip(),
                    "away": (r.get("AwayTeam") or "").strip(),
                    "arbitre": (r.get("Referee") or "").strip() or None,
                    "cote_1": _num(r.get("AvgH")), "cote_X": _num(r.get("AvgD")),
                    "cote_2": _num(r.get("AvgA")),
                    "cote_max_1": _num(r.get("MaxH")), "cote_max_X": _num(r.get("MaxD")),
                    "cote_max_2": _num(r.get("MaxA")),
                    "cote_over": _num(r.get("Avg>2.5")), "cote_under": _num(r.get("Avg<2.5")),
                    "cote_over_max": _num(r.get("Max>2.5")), "cote_under_max": _num(r.get("Max<2.5")),
                    "source": "co.uk",
                })
    except OSError:
        return None
    return out or None


def main():
    with open(CHEMIN_DB) as f:
        db = json.load(f)
    t0 = datetime.datetime.now()
    log = calendrier.appliquer(db, cotes=lire_cotes_co_uk())
    # Cotes EN DIRECT (The Odds API → Pinnacle) : écrase les cotes moyennes
    # co.uk des matchs reconnus (48 prochaines heures). La clé vient du secret
    # GitHub ODDS_API_KEY — jamais du dépôt. Une seule vraie mise à jour par
    # jour (cache 20 h, 500 crédits/mois). Échec non bloquant.
    try:
        import cotes_live
        n_sp = cotes_live.rafraichir(db)
        n_fx = cotes_live.appliquer(db)
        print(f"cotes live : {'cache mis à jour' if n_sp else 'cache encore frais'}"
              f" ({n_sp} sport(s)) | {n_fx} fixture(s) en cotes Pinnacle")
    except Exception as e:
        print(f"cotes live : ÉCHEC non bloquant ({e}) — cotes co.uk conservées",
              file=sys.stderr)
    with open(CHEMIN_DB, "w") as f:
        json.dump(db, f)
    with open(os.path.join("data", "calendrier.json"), "w") as f:
        json.dump({"matchs": db.get("fixtures", []), "journal": log,
                   "genere_le": datetime.datetime.now().isoformat(timespec="minutes")}, f)
    # suivi des pronostics : archive la sélection conseillée du jour et
    # compare les matchs archivés déjà joués aux scores FINAUX (ESPN).
    try:
        os.environ["PRONOS_SANS_CALENDRIER"] = "1"
        import serveur as S
        import suivi
        d = suivi.archiver(S.api_conseils(suivi.SEUIL_ARCHIVE))
        d, n = suivi.resoudre(d, db)
        suivi.sauver(d)
        print(f"suivi : {len(d['jours'])} jour(s) archivé(s) | {n} résultat(s) résolu(s)")
    except Exception as e:
        print(f"suivi : ÉCHEC ({e}) — sans effet sur le calendrier", file=sys.stderr)

    duree = (datetime.datetime.now() - t0).total_seconds()
    src = log.get("sources", {})
    print(f"calendrier : {log.get('total', 0)} matchs "
          f"(ESPN {src.get('ESPN', 0)}, TheSportsDB {src.get('TheSportsDB', 0)}, "
          f"OpenLigaDB {src.get('OpenLigaDB', 0)}) | cotes co.uk : {log.get('avec_cotes', 0)} "
          f"| non traduits : {len(log.get('noms_non_traduits', {}))} | {duree:.0f} s | {log.get('statut')}")
    return 0 if log.get("statut") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
