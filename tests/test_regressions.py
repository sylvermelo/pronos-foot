import contextlib
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ["PRONOS_SANS_CALENDRIER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scipy.stats import nbinom
import moteur_v3 as V
import calendrier as CAL
import buts_affilee as BA
import suivi_series as SS
import resultats
import resultats_corners as RC
import cotation
import cotes_live
import compos
import fatigue
import serveur as S
import suivi
import backtest_secondaires as BS


class Regressions(unittest.TestCase):
    def test_normalisation_conserve_les_deux_intensites(self):
        p = np.log([1.2, .8, 1.5, 1.5, 1.3, 1, 1])
        hist = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]),
                             "home": ["H"], "away": ["A"], "hg": [1], "ag": [0]})
        with patch.object(V, "minimize", return_value=type("R", (), {"x": p})()):
            m = V.fit_goals(hist, ["H", "A"])
        self.assertAlmostEqual(m["att"][0]*m["dfn"][1]*m["gamma"], 2.34)
        self.assertAlmostEqual(m["att"][1]*m["dfn"][0]*m["s"], 1.2)

    def test_melange_conserve_moyenne_geometrique_des_taux(self):
        a = {"att": np.array([1.2,.8]), "dfn":np.array([.7,1.3]), "gamma":1.9,"s":1.4,"rho":0,"idx":{"H":0,"A":1}}
        b = {"att":np.array([.6,1.4]), "dfn":np.array([1.1,.9]), "gh":1.6,"ga":1.1}
        c = V.combine(a,b,.5)
        self.assertAlmostEqual(c["att"][0]*c["dfn"][1]*c["gamma"], math.sqrt(1.2*1.3*1.9*.6*.9*1.6))
        self.assertAlmostEqual(c["att"][1]*c["dfn"][0]*c["s"], math.sqrt(.8*.7*1.4*1.4*1.1*1.1))

    def test_evaluation_over_realise(self):
        row = dict(w=1.,o1=1.5,oX=4.,o2=6.,hg=3,ag=0,p1=.7,pX=.2,p2=.1,
                   oO=1.25,oU=5.,pO25=.8,pU25=.2,exp=3.,oo1=np.nan,ooX=np.nan,oo2=np.nan)
        with contextlib.redirect_stdout(io.StringIO()):
            mesure = V.evaluate(pd.DataFrame([row]*250))
        self.assertAlmostEqual(mesure[4], -math.log(.8))

    def test_distribution_secondaire_identique(self):
        self.assertAlmostEqual(BS.ll(10,1.18,10),nbinom.logpmf(10,10/.18,1/1.18))

    def test_saison(self):
        self.assertEqual(compos._saison_csv("2026-06-30"),"2526")
        self.assertEqual(compos._saison_csv("2026-07-01"),"2627")

    def test_buts_additionnels_avant_seconde_periode(self):
        summary={"commentary":[{"time":{"displayValue":m},"play":{"type":{"text":"Goal"},"team":{"displayName":t}},"text":""}
                    for m,t in [("48'","Home"),("47'","Away"),("45'+4","Home")]]}
        buts=BA.extraire_buts(summary,"Home","Away",2,1)
        self.assertEqual([b["equipe"] for b in buts],["home","away","home"])
        self.assertEqual(SS.series_de_buts(buts)["max_match"],1)

    def test_zero_zero_valide_et_reprise(self):
        jour=dt.date.today().isoformat()
        m={"div":"E0","home":"H","away":"A","non":{"code":"match2"},"resultat":{"verifiable":False}}
        archive={"jours":{jour:{"matchs":[m]}}}
        info={"home":"H","away":"A","sh":0,"sa":0,"date":jour}
        with patch.object(BA,"_charge_cache",return_value={}), patch.object(BA,"_sauve_cache"), patch.object(BA,"journees",return_value=[]), patch.object(SS,"_trouve_event",return_value=("123",info)), patch.object(CAL,"_curl_json",return_value={"commentary":[]}):
            SS.resoudre(archive)
        self.assertTrue(m["resultat"]["verifiable"])
        self.assertTrue(m["resultat"]["touche"])

    def test_corners_zero_est_valide_absent_ne_l_est_pas(self):
        s={"header":{"competitions":[{"status":{"type":{"completed":True},"period":2},"competitors":[{"id":"1","homeAway":"home"},{"id":"2","homeAway":"away"}]}]},
           "boxscore":{"teams":[{"team":{"id":i},"statistics":[{"name":"wonCorners","displayValue":n}]} for i,n in [("2","7"),("1","0")]]}}
        self.assertEqual(RC.extraire(s),(0,7))
        s["boxscore"]["teams"][1]["statistics"]=[]
        self.assertIsNone(RC.extraire(s))

    def test_coupe_inconnue_reste_visible(self):
        jour=dt.date.today().isoformat()
        fx={"home_src":"Club inconnu","away_src":"Arsenal","date":jour,"heure":"21:00"}
        with patch.object(CAL,"ESPN_SLUGS",{"UCL":"uefa.champions"}), patch.object(CAL,"TSD_IDS",{}), patch.object(CAL,"_openligadb",return_value=[]), patch.object(CAL,"_espn_jour",return_value=[fx]):
            rows,_=CAL.construire({"UCL":["Arsenal"]},[],jours=1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["home"],"Club inconnu")

    def test_resultats_conserves_et_corriges(self):
        with tempfile.TemporaryDirectory() as d, patch.object(resultats,"CHEMIN",str(Path(d)/"r.json")), patch.object(CAL,"ESPN_SLUGS",{"E0":"eng.1"}):
            ancien={"div":"E0","date":"2020-01-01","home":"H","away":"A","hg":1,"ag":0,"season":"1920"}
            resultats.sauver({"matchs":{"old":ancien}})
            r={"date":dt.date.today().isoformat(),"home_src":"H","away_src":"A","buts_home":2,"buts_away":1}
            with patch.object(CAL,"espn_resultats",return_value=[r]):
                self.assertEqual(resultats.collecter({"ligues":{"E0":{"forces":{"H":{},"A":{}}}}}),1)
            self.assertIn("old",resultats.charger()["matchs"])
            r["buts_home"]=3
            with patch.object(CAL,"espn_resultats",return_value=[r]):
                self.assertEqual(resultats.collecter({"ligues":{"E0":{"forces":{"H":{},"A":{}}}}}),1)

    def test_quota_inconnu_aucune_requete_payante(self):
        with tempfile.TemporaryDirectory() as d, patch.object(cotes_live,"BUDGET",str(Path(d)/"q.json")), patch.object(cotes_live,"cle",return_value="test"), patch.object(cotes_live,"_curl_json",return_value=([],{})) as api:
            self.assertEqual(cotes_live.rafraichir({}),0)
            self.assertEqual(api.call_count,1)
            self.assertIn("/sports/?",api.call_args.args[0])

    def test_cote_perimee_ou_sans_source_refusee(self):
        now=dt.datetime.now(dt.timezone.utc)
        q={"price":1.5,"bookmaker":"book","event_id":"e","last_update":now.isoformat(),"commence_time":(now+dt.timedelta(hours=2)).isoformat()}
        self.assertTrue(cotation.valide(q,now))
        q["last_update"]=(now-dt.timedelta(hours=25)).isoformat()
        self.assertFalse(cotation.valide(q,now))
        self.assertIsNone(cotation.produit([{"p":.8}]))
        self.assertIsNone(cotation.produit([{"cote_marche":1.5,"cotation":{"bookmaker":"A"}},{"cote_marche":1.6,"cotation":{"bookmaker":"B"}}]))

    def test_filtrer_options_avant_choisir(self):
        m={"div":"E0","ligue":"L","pays":"P","date":(dt.date.today()+dt.timedelta(days=1)).isoformat(),"heure":"23:00","jour":"Demain","jour_delta":1,"home":"H","away":"A","disponible":True,
           "p1":.5,"pX":.2,"p2":.3,"over":{"1.5":.8,"2.5":.4,"3.5":.15},"under":{"1.5":.2,"2.5":.6,"3.5":.85},"double_chance":{},"btts":.5}
        with patch.object(S,"api_matchs",return_value=[m]):
            c=S.api_conseils()
        self.assertEqual(c["jours"][0]["selections"][0]["option"],"over 1.5")
        self.assertIsNone(c["jours"][0]["selections"][0]["cote_juste"])
        self.assertTrue(all(v is None for v in c["combines"].values()))

    def test_fatigue_match_futur_devient_final(self):
        e={"id":"e","date":"2026-10-18T12:00:00Z","status":{"type":{"completed":False}},"competitions":[{"competitors":[{"homeAway":"home","team":{"displayName":"H"},"score":"1"},{"homeAway":"away","team":{"displayName":"A"},"score":"0"}]}]}
        etat={"matchs":{},"plages_ok":[]}
        comp=next(iter(fatigue.COMPETITIONS))
        with patch.object(CAL,"_curl_json",return_value={"events":[e]}):
            fatigue.collecter_plage(comp,"2026-10-18","2026-10-18",etat)
            e["status"]["type"]["completed"]=True
            fatigue.collecter_plage(comp,"2026-10-18","2026-10-18",etat)
        self.assertTrue(next(iter(etat["matchs"].values()))["fini"])


if __name__ == "__main__":
    unittest.main()
