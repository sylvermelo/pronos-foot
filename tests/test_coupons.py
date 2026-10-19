"""Coupons : oracle exhaustif et parité JS sur entrées non vides, sans réseau."""
import datetime
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest
os.environ['PRONOS_SANS_CALENDRIER']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import serveur as S

class Coupons(unittest.TestCase):
    def test_recherche_oracle_et_parite(self):
        rng=random.Random(19)
        cases=[]
        for _ in range(40):
            pool=[dict(date='2026-10-19',home=str(i),away='Away',div='E0',ligue='EPL',
                       option='1',p=rng.uniform(.75,.97),cote_marche=rng.uniform(1.15,2.1),
                       avantage_estime=.1,cotation={'bookmaker':rng.choice(['A','B'])})
                  for i in range(10)]
            cases.append(pool)
        py=[S._combinaisons(p,.75,[],datetime.date(2026,10,19)) for p in cases]
        for pool,out in zip(cases,py):
            for nom,lo,hi,mini,maxi in [('cote2',1.9,2.35,1,2),('cote5',4.6,5.9,3,4)]:
                possibles=[]
                for n in range(mini,maxi+1):
                    for legs in itertools.combinations(pool,n):
                        if len({s['cotation']['bookmaker'] for s in legs})!=1: continue
                        prod=1;prob=1
                        for s in legs: prod*=s['cote_marche'];prob*=s['p']
                        if lo<=prod<=hi: possibles.append(prob)
                self.assertEqual(out[nom] is not None,bool(possibles))
                if possibles: self.assertEqual(out[nom]['p_combine'],round(max(possibles),4))
        src=(Path(__file__).resolve().parents[1]/'genere_app.py').read_text()
        js=src[src.index('function joursWeekendJS('):src.index('function conseilsJS(')]
        js=js.replace('const auj=new Date();','const auj=new Date(2026,9,19);')
        script=js+'\nconst cases='+json.dumps(cases)+';console.log(JSON.stringify(cases.map(p=>combinaisonsJS(p,.75,[]))));'
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,check=True)
        self.assertEqual(py,json.loads(result.stdout))
