import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import hockey_collecte as C
import hockey_modele as M
import hockey as H
import calendrier as CAL

UTC=dt.timezone.utc
class HockeyTests(unittest.TestCase):
    def raw(self,period='REG',hg=2,ag=1):
        return {'id':2026020001,'season':20262027,'gameType':2,'gameScheduleState':'OK','startTimeUTC':'2026-10-22T23:00:00Z','gameState':'OFF','neutralSite':False,
          'homeTeam':{'id':9,'abbrev':'OTT','placeName':{'default':'Ottawa'},'commonName':{'default':'Senators'},'score':hg},
          'awayTeam':{'id':8,'abbrev':'MTL','placeName':{'default':'Montréal'},'commonName':{'default':'Canadiens'},'score':ag},'gameOutcome':{'lastPeriodType':period}}
    def test_periods_and_midnight_benin(self):
        g=C.normalize(self.raw('SO',3,2));self.assertEqual((g['rh'],g['ra']),(2,2));self.assertEqual(g['date'],'2026-10-23');self.assertEqual(g['heure'],'00:00')
        g=C.normalize(self.raw('OT',2,3));self.assertEqual((g['rh'],g['ra']),(2,2));self.assertEqual((g['hg'],g['ag']),(2,3))
        self.assertEqual(C.normalize(self.raw('REG',0,1))['rh'],0)
    def test_missing_scores_and_bad_states(self):
        self.assertIsNone(C.normalize(self.raw('OT',5,2)))
        self.assertIsNone(C.normalize(self.raw('REG',None,1)))
        for field,value in [('gameType',1),('gameType',3),('gameScheduleState','PPD')]:
            r=self.raw();r[field]=value;self.assertIsNone(C.normalize(r))
    def model(self):
        return {'teams':['9','8'],'v':[np.log(2.5),.1,0,0,0,0,0,0],'ot':[0,0],
          'counts':{'9':100,'8':100},'empirical':{'reg':[.4,.2,.4],'ml':.5,'over':{str(k):.5 for k in M.LINES}},
          'blend':{'reg':1,'ml':1,'total':1},'asof':'2026-10-01T00:00:00+00:00','fingerprint':'test'}
    def test_distribution_and_total_complements(self):
        g=C.normalize(self.raw());p=M.predict(self.model(),g,[g]);self.assertAlmostEqual(sum(p['reg']),1,places=10)
        self.assertGreaterEqual(p['ml'],p['reg'][0]);self.assertLessEqual(p['ml'],p['reg'][0]+p['reg'][1])
        self.assertGreater(p['over']['4.5'],p['over']['5.5']);self.assertGreater(p['over']['5.5'],p['over']['6.5'])
        g['h']='inconnu';self.assertIsNone(M.predict(self.model(),g,[g]))
    def test_freezing_no_post_game_forecast_or_rewrite(self):
        g=C.normalize(self.raw());g.pop('rh');g.pop('ra');g['state']='FUT';g.pop('hg');g.pop('ag');g.pop('period')
        before=C.instant(g['start'])-dt.timedelta(hours=1)
        a=H.freeze([g],self.model(),{},before);self.assertEqual(len(a),1);saved=copy.deepcopy(a[g['id']]['p'])
        with patch.object(M,'predict',side_effect=AssertionError('prévision recalculée')):
            finished=C.normalize(self.raw('SO',3,2));H.freeze([finished],self.model(),a,before+dt.timedelta(hours=8))
        self.assertEqual(a[g['id']]['p'],saved);self.assertEqual(a[g['id']]['resultat']['rh'],2)
        self.assertEqual(H.freeze([g],self.model(),{},before+dt.timedelta(hours=2)),{})
    def test_rescheduled_to_before_forecast_invalid(self):
        g=C.normalize(self.raw());a={g['id']:{'frozen_at':'2026-10-23T01:00:00+00:00','p':{'ml':.7}}}
        H.freeze([g],None,a,C.instant('2026-10-24T00:00:00Z'));self.assertTrue(a[g['id']]['invalid_schedule'])
    def test_walk_never_fits_future_outcomes(self):
        rows=[]
        for i in range(70):
            g=C.normalize(self.raw());g['id']=str(i);g['start']=(dt.datetime(2026,1,1,tzinfo=UTC)+dt.timedelta(days=i)).isoformat();rows.append(g)
        trained=[]
        def fit(gs,**params):trained.append(max(g['start'] for g in gs));return {'cutoff':trained[-1],'empirical':{}}
        def predict(model,g,*args,**kwargs):self.assertLess(model['cutoff'][:10],g['start'][:10]);return {'ok':1}
        with patch.object(M,'fit',side_effect=fit),patch.object(M,'predict',side_effect=predict):
            out=M.walk(rows,rows[40:],{})
        self.assertEqual(len(out),30);self.assertEqual(len(trained),2)
    def test_future_final_not_training_and_no_zero_missing(self):
        g=C.normalize(self.raw());self.assertEqual(M.finals([g],C.instant(g['start'])+dt.timedelta(hours=1)),[])
        self.assertEqual(len(M.finals([g],C.instant(g['start'])+dt.timedelta(hours=9))),1)
    def test_rest_only_dates_not_future_scores(self):
        g=C.normalize(self.raw());other=copy.deepcopy(g);other['id']='2';other['start']='2026-10-24T23:00:00+00:00'
        a=M.rest_features([g,other]);g['rh']=99;g['ra']=0
        self.assertEqual(a,M.rest_features([g,other]))
    def test_espn_fallback_and_no_double_fetch_for_empty(self):
        with patch.object(CAL,'_curl_json',side_effect=[None,{'events':[]}]) as fetch:
            out=CAL.scoreboard_jours('uefa.champions','2026-11-04')
            self.assertEqual(out['events'],[]);self.assertEqual(fetch.call_count,2)
            self.assertIn('site.web.api.espn.com',fetch.call_args_list[0].args[0])
        with patch.object(CAL,'_curl_json',return_value={'events':[]}) as fetch:
            CAL.scoreboard_jours('uefa.champions','2026-11-04');self.assertEqual(fetch.call_count,1)

    def test_archive_cups_j21_unknown_and_finished(self):
        etat={'matchs':{'1':{'comp':'UCL','date':'2026-11-04','heure':'21:00','home_src':'Club non modélisé','away_src':'Arsenal','fini':False,'evt':'123'},'2':{'comp':'UEL','date':'2026-10-22','home_src':'A','away_src':'B','fini':True}}}
        out=CAL.coupes_archive({'index_equipes':{'Arsenal':'E0'}},etat,dt.date(2026,10,23));self.assertEqual(len(out),1);self.assertEqual(out[0]['home'],'Club non modélisé');self.assertEqual(out[0]['event_id'],'123')
    def test_model_learns_finite_probabilities(self):
        rng=np.random.default_rng(18);games=[]
        for i in range(500):
            g=C.normalize(self.raw());g['id']=str(i);g['start']=(dt.datetime(2023,1,1,tzinfo=UTC)+dt.timedelta(days=i)).isoformat()
            gh,ga=int(rng.poisson(3)),int(rng.poisson(2.7));g.update(rh=gh,ra=ga,hg=gh+(gh==ga),ag=ga);games.append(g)
        m=M.fit(games,120,5);p=M.predict(m,games[-1],games,rest_override=[0,0]);self.assertTrue(0<p['ml']<1);self.assertTrue(np.isfinite(m['v']).all())

if __name__=='__main__':unittest.main()
