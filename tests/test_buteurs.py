import copy
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['PRONOS_SANS_CALENDRIER']='1'
import buteurs_collecte as C
import buteurs_modele as M
import buteurs
import buteurs_cotes as Q


def sample(fini=True):
    rosters=[]
    for side,tid in [('home','H'),('away','A')]:
        roster=[]
        for i in range(11):
            stats=[{'name':k,'value':v} for k,v in {'appearances':1,'totalGoals':int(tid=='H' and i in (0,1)),
                'ownGoals':0,'goalAssists':0,'totalShots':1,'shotsOnTarget':1}.items()]
            roster.append({'athlete':{'id':tid+str(i),'displayName':tid+str(i)},'position':{'abbreviation':'CF'},
                           'starter':True,'subbedIn':False,'subbedOut':False,'stats':stats})
        rosters.append({'team':{'id':tid},'roster':roster})
    return {'header':{'competitions':[{'id':'event','date':'2026-10-19T18:00Z',
        'status':{'type':{'completed':fini,'name':'STATUS_FULL_TIME' if fini else 'STATUS_SCHEDULED','state':'post' if fini else 'pre'}},
        'competitors':[{'id':t,'homeAway':side,'score':str(2 if t=='H' else 0),'team':{'id':t,'displayName':t}} for side,t in [('home','H'),('away','A')]]}]},
        'rosters':rosters,'keyEvents':[]}


class Buteurs(unittest.TestCase):
    def test_extraire_score_et_donnees_manquantes(self):
        s=sample();m=C.extraire(s,'E0');self.assertTrue(m['valide'])
        self.assertEqual(m['equipes']['home']['joueurs'][0]['minutes'],90)
        s['rosters'][0]['roster'][0]['stats']=[{'name':'appearances','value':1}]
        m=C.extraire(s,'E0');self.assertFalse(m['valide'])
        self.assertIsNone(m['equipes']['home']['joueurs'][0]['buts'])
        self.assertIsNone(m['equipes']['home']['joueurs'][0]['tirs'])

    def test_rejette_score_incoherent_et_prolongations(self):
        s=sample();s['header']['competitions'][0]['competitors'][0]['score']='8'
        self.assertFalse(C.extraire(s,'E0')['valide'])
        s['header']['competitions'][0]['status']['type']['name']='STATUS_FINAL_AET'
        self.assertIsNone(C.extraire(s,'E0'))

    def test_substitutions_minutes_et_minutes_inconnues(self):
        s=sample();j=s['rosters'][0]['roster'][0];j['subbedOut']=True
        self.assertIsNone(C.extraire(s,'E0')['equipes']['home']['joueurs'][0]['minutes'])
        s['keyEvents']=[{'type':{'text':'Substitution'},'period':{'number':2},'clock':{'value':4200},
                        'participants':[{'athlete':{'id':'HS'}},{'athlete':{'id':'H0'}}]}]
        sub=copy.deepcopy(j);sub['athlete']={'id':'HS','displayName':'Sub'};sub['starter']=False;sub['subbedOut']=False;sub['subbedIn']=True
        sub['stats']=[{'name':k,'value':v} for k,v in {'appearances':1,'totalGoals':0,'ownGoals':0}.items()]
        s['rosters'][0]['roster'].append(sub)
        pl=C.extraire(s,'E0')['equipes']['home']['joueurs']
        self.assertEqual(pl[0]['minutes'],70);self.assertEqual(pl[-1]['minutes'],20)
        self.assertEqual(C.minute({'period':{'number':1},'clock':{'value':2940}}),45)

    def test_non_partant_jamais_buteur(self):
        s=sample();sub=copy.deepcopy(s['rosters'][0]['roster'][0]);sub['athlete']['id']='bench';sub['starter']=False;sub['stats']=[]
        s['rosters'][0]['roster'].append(sub)
        p=C.extraire(s,'E0')['equipes']['home']['joueurs'][-1]
        self.assertFalse(p['joue']);self.assertEqual(p['minutes'],0)

    def test_csc_pas_un_but_personnel(self):
        s=sample();s['header']['competitions'][0]['competitors'][0]['score']='3'
        for st in s['rosters'][1]['roster'][0]['stats']:
            if st['name']=='ownGoals':st['value']=1
        m=C.extraire(s,'E0');self.assertTrue(m['valide']);self.assertEqual(m['equipes']['away']['joueurs'][0]['buts'],0)

    def test_historique_non_entraine_sur_un_match_avant_fin(self):
        m=C.extraire(sample(False),'E0');etat=M.vide();M.maj(etat,m);self.assertEqual(etat['joueurs'],{})

    def test_modele_actualise_et_petits_echantillons(self):
        m=C.extraire(sample(),'E0');etat=M.vide()
        for _ in range(4):M.maj(etat,m)
        self.assertIsNone(M.predire(etat,'E0','H','H0','F',450))
        for _ in range(4):M.maj(etat,m)
        p=M.predire(etat,'E0','H','H0','F',450)
        self.assertIsNotNone(p);self.assertTrue(0<p['p']<1)
        before=p['p'];m['equipes']['home']['joueurs'][0]['buts']=2;M.maj(etat,m)
        self.assertGreater(M.predire(etat,'E0','H','H0','F',450)['p'],before)

    def test_validation_ne_voit_pas_le_match_courant(self):
        events=[]
        for i in range(12):
            m=C.extraire(sample(),'E0');m['event_id']=str(i);m['date']=(dt.date(2026,9,1)+dt.timedelta(days=i)).isoformat();events.append(m)
        seen=[]
        real=M.predire
        def wrap(state,*args,**kw):
            seen.append(max((p['derniere_date'] for p in state['joueurs'].values()),default=''))
            return real(state,*args,**kw)
        with patch.object(M,'predire',side_effect=wrap):M.evaluer(events,450,'2026-09-08','2026-09-08')
        self.assertTrue(seen);self.assertTrue(all(d<'2026-09-08' for d in seen))

    def test_prevision_figee_et_resultat_non_retroactif(self):
        with tempfile.TemporaryDirectory() as t,patch.object(C,'DATA',Path(t)):
            m=C.extraire(sample(False),'E0',fetched='2026-10-19T16:50:00+00:00')
            hist={'matchs':{'event':m}};state=M.vide()
            for _ in range(8):M.maj(state,C.extraire(sample(),'E0'))
            model={'etat':state,'pseudo_minutes':450,'signature':'initial','version':'v',
                   'historique_matchs':8,'joueurs':22,'derniere_date':'2026-10-18','entraine_le':'x','evaluation':{'statut':'experimental'}}
            fx=[{'event_id':'event','div':'E0','home':'H','away':'A','date':'2026-10-19','heure':'19:00','debut_utc':'2026-10-19T18:00Z'}]
            now=dt.datetime(2026,10,19,17,tzinfo=dt.timezone.utc)
            buteurs.publier(fx,model,hist,now);old=C.lire('buteurs_suivi.json')['matchs']['event']
            model['signature']='new';hist['matchs']['event']=C.extraire(sample(),'E0')
            buteurs.publier([],model,hist,now+dt.timedelta(hours=3))
            actual=C.lire('buteurs_suivi.json')['matchs']['event']
            self.assertEqual(old['signature_modele'],actual['signature_modele'])
            self.assertEqual(next(p for p in actual['joueurs'] if p['id']=='H0')['resultat']['statut'],'gagne')

    def test_cotes_nom_complet_ambigu_rejete(self):
        now='2026-10-19T17:00:00+00:00';ev={'event_id':'event','debut_utc':'2026-10-19T18:00Z','joueurs':[{'id':'1','nom':'Éric Test'}]}
        raw={'id':'odds1','commence_time':ev['debut_utc'],'bookmakers':[{'key':'b','title':'B','last_update':now,
            'markets':[{'key':'player_goal_scorer_anytime','outcomes':[{'description':'Eric Test','name':'Yes','price':2.3}]}]}]}
        p=Q.extraire(raw,ev,now);self.assertEqual(p[0]['player_id'],'1');self.assertEqual(p[0]['price'],2.3)
        ev['joueurs'].append({'id':'2','nom':'Eric Test'});self.assertEqual(Q.extraire(raw,ev,now),[])

    def test_collecte_sans_quota_pas_de_cout(self):
        import cotes_live
        with tempfile.TemporaryDirectory() as t,patch.object(C,'DATA',Path(t)),patch.object(cotes_live,'cle',return_value='test'),patch.object(cotes_live,'_curl_json',return_value=(None,{})) as net:
            p={'matchs':[{'date':(C.maintenant()+dt.timedelta(hours=1)).date().isoformat(),'composition_confirmee':True,'joueurs':[{'analyse':{'p':.2}}]}]}
            self.assertEqual(Q.collecter(p)['statut'],'quota_inconnu');self.assertEqual(net.call_count,1)

    def test_memoire_echec_ne_marque_pas_synchronise(self):
        import db
        with tempfile.TemporaryDirectory() as t,patch.object(C,'DATA',Path(t)),patch.object(db,'disponible',return_value=True):
            row=C.extraire(sample(),'E0');C.sauver('joueurs_matchs.json',{'matchs':{'event':row}})
            C.sauver('joueurs_sync_meta.json',{'jour':C.maintenant().date().isoformat()})
            with patch.object(db,'_requete',return_value=('500','fail')):
                with self.assertRaises(RuntimeError):C.synchroniser()
            self.assertFalse(C.lire('joueurs_sync_meta.json').get('signatures'))
            with patch.object(db,'_requete',return_value=('201','')) as net:
                self.assertEqual(C.synchroniser()['sauvegardes'],1)
                self.assertEqual(C.synchroniser()['sauvegardes'],0)
                self.assertEqual(net.call_count,1)

    def test_signature_ignore_horodatage_mais_detecte_correction(self):
        m=C.extraire(sample(),'E0');h={'matchs':{'event':m}}
        sig=M.empreinte(h);m['collecte_le']='2030-01-01T00:00:00+00:00';m['recontrole']=True
        self.assertEqual(sig,M.empreinte(h))
        m['equipes']['home']['joueurs'][0]['buts']+=1
        self.assertNotEqual(sig,M.empreinte(h))

    def test_composition_prematch_reprise_apres_fin(self):
        import compos
        with tempfile.TemporaryDirectory() as t,patch.object(C,'DATA',Path(t)),patch.object(compos,'CHEMIN',str(Path(t)/'compos.json')),patch.object(compos,'ESPN_SLUGS',{'E0':'eng.1'}):
            pre=compos._extraire(sample(False),'event','E0','eng.1','2026-10-19','H','A',False)
            Path(compos.CHEMIN).write_text(json.dumps({'matchs':{'E0|2026-10-19|H|A':pre}}))
            ev={'id':'event','date':'2026-10-19','ko':'2026-10-19T18:00Z','home':'H','away':'A','fini':True}
            with patch.object(compos,'_evenements',return_value=[ev]),patch.object(compos,'_summary',return_value=sample()) as net:
                self.assertEqual(compos.collecter(),1);self.assertEqual(net.call_count,1)
                self.assertTrue(C.lire('joueurs_matchs.json')['matchs']['event']['fini'])
                self.assertEqual(compos.collecter(),0)

    def test_previsions_sauvees_ignore_doublons(self):
        import db
        with tempfile.TemporaryDirectory() as t,patch.object(C,'DATA',Path(t)),patch.object(db,'disponible',return_value=True):
            C.sauver('buteurs_suivi.json',{'matchs':{'event':{'event_id':'event','debut_utc':'2026-10-19T18:00Z','fige_le':'2026-10-19T17:00Z'}}})
            C.sauver('buteurs_suivi_sync_meta.json',{'jour':C.maintenant().date().isoformat()})
            with patch.object(db,'_requete',return_value=('201','')) as net:
                self.assertEqual(buteurs.synchroniser_suivi()['previsions'],1)
                self.assertEqual(net.call_args.kwargs['resolution'],'ignore-duplicates')
                self.assertEqual(buteurs.synchroniser_suivi()['previsions'],0)
                self.assertEqual(net.call_count,1)

if __name__=='__main__':unittest.main()
