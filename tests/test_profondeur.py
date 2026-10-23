import unittest,copy,datetime as dt
from unittest.mock import patch
import buteurs_profondeur as B
import hockey_joueurs as J
import hockey_collecte as C
import europe_profond as E
import europe_modele as M

class Profondeur(unittest.TestCase):
    def test_closed_season_never_used_early_and_homonyms_rejected(self):
        row={'key':B.nom('Éric Test'),'id':'1','div':'E0','available_from':'2026-07-01',**{k:1 for k in ('games','minutes','goals','xg','assists','xa','shots')}}
        data={'players':[row]}
        self.assertIsNone(B.reference('Eric Test','E0','2026-06-30',data))
        self.assertEqual(B.reference('Eric Test','E0','2026-07-01',data)['seasons'],1)
        data['players'].append({**row,'id':'2'})
        self.assertIsNone(B.reference('Eric Test','E0','2026-08-01',data))
    def test_nhl_calendar_day_and_benin_day_differ(self):
        raw={'id':1,'season':20262027,'gameType':2,'startTimeUTC':'2026-10-24T00:00:00Z','gameDate':'2026-10-23','gameState':'FUT','homeTeam':{'id':1,'abbrev':'A'},'awayTeam':{'id':2,'abbrev':'B'}}
        g=C.normalize(raw);self.assertEqual(g['date_nhl'],'2026-10-23');self.assertEqual(g['date'],'2026-10-24');self.assertEqual(g['heure'],'01:00')
    def test_nhl_minutes_and_shots_only_from_past(self):
        state=J.empty()
        for day in range(12):
            for pid in range(10):J.update(state,[str(pid),'g'+str(day),'2026-10-01','A','B','F','H',int(pid%3==0),int(pid%2==0),3,18.,0,0])
        p=J.predict(state,'1','but',600,.5);self.assertEqual(p['toi_estime'],18);self.assertTrue(0<p['p']<1)
        self.assertIsNone(J.predict(state,'missing','but'))
        # Player identity survives a team change.
        J.update(state,['1','new','2026-10-02','C','D','F','R',0,0,2,20.,0,0]);self.assertEqual(state['players']['1']['n'],13)
    def test_uefa_regular_score_never_aggregate(self):
        r={'competition':{'id':'1'},'id':1,'seasonYear':'2027','status':'FINISHED','kickOffTime':{'dateTime':'2026-10-22T19:00:00Z'},'homeTeam':{'id':1,'internationalName':'A','countryCode':'FRA'},'awayTeam':{'id':2,'internationalName':'B','countryCode':'ENG'},'score':{'regular':{'home':1,'away':1},'total':{'home':3,'away':1},'aggregate':{'home':5,'away':4}}}
        self.assertIsNone(E.normalize(r,'UECL'))
        g=E.normalize(r,'UCL');self.assertEqual((g['rh'],g['ra']),(1,1));del r['score']['regular'];g=E.normalize(r,'UCL');self.assertNotIn('rh',g)
    def test_uefa_abstains_for_unknown_or_small_history(self):
        self.assertIsNone(M.predict({'counts':{'1':5,'2':100}}, {'h':'1','a':'2'}))
