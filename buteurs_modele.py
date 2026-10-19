"""Modèle buteur Gamma-Poisson, temps de jeu empirique, validation chronologique.
Aucun bonus manuel, aucune cote calculée. Calcul Python pré-publié identique
pour serveur et navigateur : le client ne ré-entraîne pas le modèle joueurs.
"""
import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from scipy.stats import gamma

VERSION='buteurs-gamma-poisson-v1'
MIN_MATCHS_JOUEUR=5
MIN_MINUTES=180
MIN_REFERENCE=60


def vide():
    return {'joueurs':{},'references':{}}


def cle_ref(div,poste):return div+'|'+poste


def maj(etat,m):
    if not m.get('fini') or not m.get('valide'):return
    for t in m['equipes'].values():
        for p in t['joueurs']:
            if not p.get('joue') or p.get('minutes') is None or p['minutes']<=0 or p.get('buts') is None:continue
            key=m['div']+'|'+t['id']+'|'+p['id']
            j=etat['joueurs'].setdefault(key,{'buts':0,'minutes':0,'matchs':0,'scenarios':[],
                'id':p['id'],'nom':p['nom'],'poste':p['poste'],'div':m['div'],
                'equipe_id':t['id'],'equipe':t['nom'],'derniere_date':m['date'],
                'tirs':0,'n_tirs':0,'cadres':0,'n_cadres':0,'par_poste':{}})
            j['buts']+=p['buts'];j['minutes']+=p['minutes'];j['matchs']+=1
            j['scenarios'].append([p['titulaire'],p['minutes']])
            j['derniere_date']=max(j['derniere_date'],m['date'])
            j['nom']=p['nom'];j['poste']=p['poste']
            par=j['par_poste'].setdefault(p['poste'],{'buts':0,'minutes':0})
            par['buts']+=p['buts'];par['minutes']+=p['minutes']
            for field in ('tirs','cadres'):
                if p.get(field) is not None:j[field]+=p[field];j['n_'+field]+=1
            k=cle_ref(m['div'],p['poste'])
            r=etat['references'].setdefault(k,{'buts':0,'minutes':0,'n':0,'scores':0,'titulaires':0})
            r['buts']+=p['buts'];r['minutes']+=p['minutes'];r['n']+=1
            if p['titulaire']:r['titulaires']+=1;r['scores']+=p['buts']>0


def predire(etat,div,team,pid,poste,pseudo,intervalle=True):
    if poste in ('G','?'):return None
    j=etat['joueurs'].get(div+'|'+team+'|'+pid)
    r=etat['references'].get(cle_ref(div,poste))
    if not j or j['matchs']<MIN_MATCHS_JOUEUR or j['minutes']<MIN_MINUTES:return None
    if not r or r['n']<MIN_REFERENCE or not r['minutes'] or r['buts']<=0:return None
    # Référence en excluant ce joueur, pour ne pas doubler ses observations.
    par=j.get('par_poste',{}).get(poste,{'buts':j['buts'],'minutes':j['minutes']})
    g=r['buts']-par['buts'];mins=r['minutes']-par['minutes']
    if g<=0 or mins<=0:return None
    a=(g/mins)*pseudo+j['buts'];b=pseudo+j['minutes']
    scenarios=[m for start,m in j['scenarios'] if start]
    if len(scenarios)<3:return None
    p=sum(1-(b/(b+m))**a for m in scenarios)/len(scenarios)
    out={'p':round(p,4),'matchs':j['matchs'],'minutes_historique':round(j['minutes']),
         'minutes_si_titulaire':round(sum(scenarios)/len(scenarios),1),'buts':j['buts'],
         'tirs':j['tirs'] if j['n_tirs']==j['matchs'] else None,
         'cadres':j['cadres'] if j['n_cadres']==j['matchs'] else None,
         'baseline':r['scores']/r['titulaires'] if r['titulaires'] else None}
    if intervalle:
        low,high=gamma.ppf([.05,.95],a=a,scale=1/b)
        out['intervalle_taux_90']=[round(sum(1-math.exp(-low*m) for m in scenarios)/len(scenarios),4),
                                  round(sum(1-math.exp(-high*m) for m in scenarios)/len(scenarios),4)]
    return out


def pertes(rows):
    if not rows:return {'n':0,'matchs':0,'brier':None,'logloss':None,'baseline_brier':None,'baseline_logloss':None,'buts_observes':0}
    def ll(p,y):
        p=max(1e-9,min(1-1e-9,p));return -y*math.log(p)-(1-y)*math.log(1-p)
    n=len(rows)
    return {'n':n,'matchs':len({r[0] for r in rows}),
            'brier':round(sum((p-y)**2 for _,p,y,b in rows)/n,6),
            'logloss':round(sum(ll(p,y) for _,p,y,b in rows)/n,6),
            'baseline_brier':round(sum((b-y)**2 for _,p,y,b in rows)/n,6),
            'baseline_logloss':round(sum(ll(b,y) for _,p,y,b in rows)/n,6),
            'buts_observes':sum(y for _,p,y,b in rows)}


def evaluer(matchs,pseudo,debut,fin):
    etat=vide();rows=[]
    # Tous les matchs d'une même date évalués avant toute mise à jour du jour.
    bydate=defaultdict(list)
    for m in matchs:bydate[m['date']].append(m)
    for date,jour in sorted(bydate.items()):
        if debut<=date<=fin:
            for m in jour:
                for t in m['equipes'].values():
                    for p in t['joueurs']:
                        if not p['titulaire'] or p.get('buts') is None:continue
                        v=predire(etat,m['div'],t['id'],p['id'],p['poste'],pseudo,False)
                        if v and v['baseline'] is not None:rows.append((m['event_id'],v['p'],int(p['buts']>0),v['baseline']))
        for m in jour:maj(etat,m)
    return pertes(rows)


def empreinte(hist):
    matchs=sorted([{k:v for k,v in m.items() if k not in ('collecte_le','recontrole')}
                   for m in hist.get('matchs',{}).values() if m.get('fini') and m.get('valide')],key=lambda m:m['event_id'])
    return hashlib.sha256((VERSION+json.dumps(matchs,sort_keys=True)).encode()).hexdigest()


def entrainer(hist):
    matchs=sorted([m for m in hist.get('matchs',{}).values() if m.get('fini') and m.get('valide')],key=lambda m:(m['date'],m['event_id']))
    sig=empreinte(hist)
    dates=sorted({m['date'] for m in matchs});pseudo=450
    mesures={'statut':'historique_insuffisant'}
    if len(dates)>=10:
        debut_val=dates[int(len(dates)*.6)];debut_test=dates[int(len(dates)*.8)]
        tuning=[]
        for q in (90,450,900,1800):
            v=evaluer(matchs,q,debut_val,dates[max(0,dates.index(debut_test)-1)])
            if v['n']:tuning.append((v['brier'],v['logloss'],q,v))
        val=None
        if tuning:
            _,_,pseudo,val=min(tuning)
        test=evaluer(matchs,pseudo,debut_test,dates[-1])
        ok=(val is not None and test['matchs']>=60 and test['n']>=300 and test['buts_observes']>=20
            and test['brier']<test['baseline_brier'] and test['logloss']<test['baseline_logloss'])
        mesures={'statut':'validation_initiale' if ok else 'experimental',
                  'validation':val,'test':test,'validation_depuis':debut_val,'test_depuis':debut_test,
                  'parametre_ajuste':val is not None,
                  'note':'Découpage temporel 60/20/20 par dates ; référence fréquence des titulaires au même poste/ligue. Aucun ROI sans prix archivés.'}

    etat=vide()
    for m in matchs:maj(etat,m)
    return {'version':VERSION,'signature':sig,'pseudo_minutes':pseudo,'etat':etat,
            'historique_matchs':len(matchs),'joueurs':len(etat['joueurs']),
            'derniere_date':max(dates,default=None),'evaluation':mesures,
            'entraine_le':dt.datetime.now(dt.timezone.utc).isoformat()}
