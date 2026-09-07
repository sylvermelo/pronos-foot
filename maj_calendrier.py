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
    # pseudo-divisions de coupes (UCL, UEL, Carabao…) : à injecter AVANT le
    # calendrier pour que leurs matchs ESPN soient reconnus — voir coupes.py
    import coupes
    coupes.injecter(db)

    # BOUCLE RAPIDE : collecte des scores FINAUX ESPN des derniers jours
    # (complément d'entraînement en attendant la publication co.uk de
    # dimanche/mercredi). Échec non bloquant ; n'écrit le fichier que s'il y a
    # du nouveau — c'est ce fichier qui déclenchera le ré-entraînement dans
    # maj.py au prochain passage. Voir resultats.py.
    try:
        import resultats
        n_res = resultats.collecter(db)
        if n_res:
            print(f"boucle rapide : {n_res} nouveau(x) résultat(s) final(aux) — "
                  f"ré-entraînement au prochain passage")
    except Exception as e:
        print(f"boucle rapide : échec ignoré ({e})", file=sys.stderr)

    # CORNERS 1re MI-TEMPS : découpe MT1/MT2 des matchs terminés des derniers
    # jours (8 divisions couvertes par le fil ESPN — corners_mt.py).
    try:
        import corners_mt
        n_mt = corners_mt.collecter_recent(db)
        if n_mt:
            print(f"corners 1re MT : {n_mt} nouveau(x) match(s) découpés par mi-temps")
    except Exception as e:
        print(f"corners 1re MT : échec ignoré ({e})", file=sys.stderr)

    # FATIGUE EUROPÉENNE (étape ③) : calendriers C1/C2/C3 en fenêtre glissante
    # ±21 jours (matchs joués ET programmés — la fatigue d'un match de
    # championnat se connaît dès que le calendrier européen existe), puis
    # re-mesure du barème sur les CSV versionnés. ~6 requêtes ESPN par passage.
    try:
        import contextlib
        import io
        import fatigue
        n_fat = fatigue.rafraichir()
        with contextlib.redirect_stdout(io.StringIO()):
            fatigue.mesurer()
        if n_fat:
            print(f"fatigue européenne : +{n_fat} match(s) de coupes — barème re-mesuré")
    except Exception as e:
        print(f"fatigue européenne : échec ignoré ({e})", file=sys.stderr)

    # CORNERS — correction du biais mesuré (backtest_secondaires.py,
    # walk-forward 2023-2026 sur 42 733 prédictions). biais_division =
    # prédit − réel : si le modèle annonce trop bas (biais négatif), on
    # remonte la base. La base est PAR ÉQUIPE (le total du match ≈ 2×base),
    # donc on applique −biais/2. Idempotent grâce au marqueur.
    # Fautes et cartons : biais mesurés mais NON appliqués pour l'instant
    # (demande utilisateur = corners ; extensible sur simple feu vert).
    try:
        with open(os.path.join("data", "backtest_secondaires.json")) as f:
            _bt = json.load(f)
        n_corr = 0
        for div, L in db.get("ligues", {}).items():
            sec = L.get("secondaires")
            if not sec or not isinstance(sec.get("base"), dict):
                continue
            base = sec["base"]
            if "corners" not in base or base.get("corners_biais_applique") is not None:
                continue
            b = (_bt.get("biais_division", {}).get(div) or {}).get("corners")
            if b is None:
                continue
            base["corners"] = round(base["corners"] - b / 2.0, 3)
            base["corners_biais_applique"] = round(-b, 2)   # delta total appliqué
            n_corr += 1
        if n_corr:
            print(f"corners : biais walk-forward appliqué sur {n_corr} division(s)")
    except (OSError, ValueError) as e:
        print(f"corners : correction de biais ignorée ({e})", file=sys.stderr)
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
        conseils = S.api_conseils(suivi.SEUIL_ARCHIVE)
        d = suivi.archiver(conseils)
        d, n = suivi.resoudre(d, db)
        rattrape = suivi.rattrapage_safe(d, conseils)
        suivi.sauver(d)
        print(f"suivi : {len(d['jours'])} jour(s) archivé(s) | {n} résultat(s) résolu(s)")
        if rattrape:
            print("suivi : safe_2 créé (jambe du SAFE perdue, rattrapage avec "
                  "les matchs du jour pas encore commencés)")
        try:                                 # Phase 1 : double écriture Supabase
            import db
            cp = S.coupon_corners()
            r = db.sync_suivi(d, combines_extra=[cp] if cp else [])
            if r.get("statut") != "ignore":
                print(f"supabase : {r.get('statut')} "
                      f"({r.get('selections', 0)} sél, {r.get('combines', 0)} comb)")
        except Exception as e:
            print(f"supabase : échec IGNORÉ ({e}) — les JSON restent la source",
                  file=sys.stderr)
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
