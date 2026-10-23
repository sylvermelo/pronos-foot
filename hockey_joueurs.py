"""Patineurs NHL : Gamma-Poisson et tirs/conversion, tests par dates.
Temps de glace estimé sur les dix apparitions passées, jamais celui du match évalué.
Probabilités conditionnelles à une participation ; pas de composition confirmée.
"""
import datetime as dt,math
from collections import defaultdict
import numpy as np
from hockey_collecte import DATA,read,write,instant,UTC
from hockey_profond import read_seed,team_games
VERSION='nhl-joueurs-1.0.1'
MARKETS={'but':7,'passe':8,'point':None}
def empty():return {'players':{},'roles':{}}
def update(state,r):
    p=state['players'].setdefault(r[0],{'n':0,'mins':0.,'goals':0,'assists':0,'shots':0,'toi':[]})
    p['n']+=1;p['mins']+=r[10];p['goals']+=r[7];p['assists']+=r[8];p['shots']+=r[9];p['toi']=(p['toi']+[r[10]])[-10:];p['last']=r[2];p['team']=r[3];p['position']=r[5]
    role=state['roles'].setdefault(r[5],{'n':0,'mins':0.,'goals':0,'assists':0,'shots':0,'hits':{'but':0,'passe':0,'point':0}})
    role['n']+=1;role['mins']+=r[10];role['goals']+=r[7];role['assists']+=r[8];role['shots']+=r[9]
    for k,idx in MARKETS.items():role['hits'][k]+=int((r[idx] if idx else r[7]+r[8])>0)
def predict(state,pid,market,pseudo=600,mix=0):
    p=state['players'].get(pid)
    if not p or p['n']<10 or p['mins']<120:return None
    r=state['roles'][p['position']]
    if r['n']<60 or r['mins']<=p['mins']:return None
    field='goals' if market=='but' else 'assists'
    count=p[field] if market!='point' else p['goals']+p['assists'];total=r[field] if market!='point' else r['goals']+r['assists']
    rate=(total-count)/(r['mins']-p['mins']);a=rate*pseudo+count;b=pseudo+p['mins'];toi=sum(p['toi'])/len(p['toi']);prob=1-(b/(b+toi))**a
    if market=='but' and mix:
        # Conversion stabilisée par le même poste, en excluant le joueur.
        shotrate=((r['shots']-p['shots'])/(r['mins']-p['mins'])*pseudo+p['shots'])/b
        prior_conversion=(r['goals']-p['goals'])/max(1,r['shots']-p['shots'])
        conversion=(prior_conversion*60+p['goals'])/(60+p['shots'])
        prob=(1-mix)*prob+mix*(1-math.exp(-shotrate*conversion*toi))
    return {'p':float(prob),'baseline':r['hits'][market]/r['n'],'toi_estime':round(toi,1),'matchs':p['n'],'minutes':round(p['mins']),'buts':p['goals'],'passes':p['assists'],'tirs':p['shots']}
def losses(rows):
    if not rows:return {'n':0,'matchs':0}
    p=np.array([x[1] for x in rows]);y=np.array([x[2] for x in rows]);b=np.array([x[3] for x in rows]);ll=lambda q:float(np.mean(-y*np.log(np.clip(q,1e-9,1-1e-9))-(1-y)*np.log(np.clip(1-q,1e-9,1))))
    return {'n':len(rows),'matchs':len({r[0] for r in rows}),'brier':float(np.mean((p-y)**2)),'baseline_brier':float(np.mean((b-y)**2)),'logloss':ll(p),'baseline_logloss':ll(b),'positifs':int(y.sum())}
def train(data):
    rows=data['players'];dates=sorted({r[2] for r in rows});dv=dates[int(len(dates)*.6)];dtst=dates[int(len(dates)*.8)]
    candidates={m:[(q,mix) for q in (180,600,1800) for mix in ((0,.5,1) if m=='but' else (0,))] for m in MARKETS}
    val={m:{par:[] for par in pars} for m,pars in candidates.items()};test={m:{par:[] for par in pars} for m,pars in candidates.items()};state=empty();by=defaultdict(list)
    for r in rows:by[r[2]].append(r)
    for date,day in sorted(by.items()):
        if date>=dv:
            target=val if date<dtst else test
            for r in day:
                for m,pars in candidates.items():
                    y=int((r[MARKETS[m]] if MARKETS[m] else r[7]+r[8])>0)
                    for q,mix in pars:
                        p=predict(state,r[0],m,q,mix)
                        if p:target[m][(q,mix)].append((r[1],p['p'],y,p['baseline']))
        for r in day:update(state,r)
    params={};report={}
    for m,pars in candidates.items():
        scored={par:losses(val[m][par]) for par in pars};best=min(pars,key=lambda par:scored[par].get('logloss',float('inf')));params[m]={'pseudo':best[0],'mix':best[1]};report[m]={'validation':scored[best],'test':losses(test[m][best])}
    return {'version':VERSION,'state':state,'params':params,'evaluation':report,'validation_depuis':dv,'test_depuis':dtst,'historique_n':len(rows),'matchs_n':len({r[1] for r in rows}),'joueurs_n':len(state['players']),'du':dates[0],'au':dates[-1],'trained_at':dt.datetime.now(UTC).isoformat(),'source_at':data.get('collected_at'),'protocole':'60/20/20 par dates ; tous les joueurs du jour prédits avant les résultats du jour ; temps de glace estimé sur le passé.'}
def main(games,now=None):
    now=now or dt.datetime.now(UTC);data=read_seed()
    final_ids=set(team_games(data['teams']));data={**data,'players':[r for r in data['players'] if r[1] in final_ids]}
    model=read(DATA/'hockey_joueurs_modele.json',{})
    if not data['players']:return {'profils':[],'statut':'historique_absent'}
    if model.get('version')!=VERSION or model.get('source_at')!=data.get('collected_at'):
        model=train(data);write(DATA/'hockey_joueurs_modele.json',model)
    archive=read(DATA/'hockey_joueurs_previsions.json',{});profiles=[]
    source_age=(now-instant(data['collected_at'])).total_seconds()/3600 if data.get('collected_at') else float('inf')
    for g in games:
        if g.get('rh') is not None or not now<instant(g['start'])<=now+dt.timedelta(days=8):continue
        if model['au']>=g['start'][:10]:continue
        for pid,p in model['state']['players'].items():
            if p['team'] not in (g['home_abbr'],g['away_abbr']) or (now.date()-dt.date.fromisoformat(p['last'])).days>21:continue
            for market,par in model['params'].items():
                key=g['id']+'|'+pid+'|'+market;snap=archive.get(key)
                if snap and snap['start']!=g['start']:snap['invalid_schedule']=True
                if not snap:
                    pred=predict(model['state'],pid,market,**par)
                    if not pred:continue
                    snap={'id':key,'game_id':g['id'],'player_id':pid,'nom':data['names'].get(pid,pid),'equipe':p['team'],'marche':market,'date':g['date'],'date_nhl':g.get('date_nhl') or instant(g['start']).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date().isoformat(),'heure':g['heure'],'start':g['start'],'home':g['home'],'away':g['away'],'prediction':pred,'frozen_at':now.isoformat(),'trained_until':model['au'],'version':VERSION,'condition':'Si le joueur participe ; présence et temps de glace non confirmés. Prolongation incluse, tirs au but exclus.','cote':None}
                    archive[key]=snap
                if not snap.get('invalid_schedule') and snap['start']==g['start'] and instant(snap['frozen_at'])<instant(g['start']) and instant(g['start'])<=now+dt.timedelta(hours=48) and source_age<=48:profiles.append({k:v for k,v in snap.items() if k not in ('condition','version')})
    # Résolution sans assimiler une absence à zéro, résultats du rapport officiel seulement.
    results={(r[1],r[0]):r for r in data['players']}
    for snap in archive.values():
        r=results.get((snap['game_id'],snap['player_id']))
        if r:
            idx=MARKETS[snap['marche']];snap['resultat']=int((r[idx] if idx else r[7]+r[8])>0)
    write(DATA/'hockey_joueurs_previsions.json',archive)
    report={k:v for k,v in model.items() if k not in ('state','params')};report.update(suivi={k:losses([(v['game_id'],v['prediction']['p'],v['resultat'],v['prediction']['baseline']) for v in archive.values() if v.get('marche')==k and 'resultat' in v and not v.get('invalid_schedule')]) for k in MARKETS},source_age_heures=round(source_age,1) if math.isfinite(source_age) else None,source_incomplete=bool(data.get('errors')) or source_age>48,fenetre_heures=48,profils=profiles,statut='experimental',note='Buts, passes et points individuels. Pas de prix bookmaker : analyses seules. Ni blessures, ni lignes/avantage numérique futurs, ni gardien adverse confirmé dans le calcul. Aucun avantage financier démontré.')
    return report
if __name__=='__main__':
    p=main(read(DATA/'hockey_matchs.json',{}).get('games',[]));write(DATA/'hockey_joueurs_jour.json',p);print({k:v for k,v in p.items() if k!='profils'})
