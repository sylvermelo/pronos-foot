"""Modèle NHL indépendant : attaque/défense Poisson régularisées, repos appris,
OT conditionnelle apprise, calibration par mélange à une référence empirique.
Réglage validation puis test chronologique distinct, réentraînement par blocs.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import poisson
from hockey_collecte import instant

VERSION='nhl-1.0.0'
LINES=(4.5,5.5,6.5,7.5)

def ordered(games):return sorted(games,key=lambda g:(g['start'],g['id']))
def finals(games,now):
    return ordered([g for g in games if g.get('rh') is not None and instant(g['start'])+dt.timedelta(hours=8)<now])

def rest_features(games):
    """Dates des rencontres déjà programmées, jamais leurs scores futurs."""
    last={};out={}
    for g in ordered(games):
        t=instant(g['start']);r=[]
        for team in (g['h'],g['a']):
            hours=(t-last[team]).total_seconds()/3600 if team in last else None
            r.append((min(hours/24,7) if hours is not None else 7, float(hours is not None and hours<36)))
            last[team]=t
        out[g['id']]=[(r[0][0]-r[1][0])/7,r[0][1]-r[1][1]]
    return out

def fit(games,half_life=120,ridge=5):
    games=ordered(games)
    if len(games)<400:raise ValueError('Historique NHL insuffisant : 400 rencontres minimum')
    teams=sorted({g[k] for g in games for k in ('h','a')});index={t:i for i,t in enumerate(teams)};n=len(teams)
    h=np.array([index[g['h']] for g in games]);a=np.array([index[g['a']] for g in games])
    y=np.array([[g['rh'],g['ra']] for g in games],float)
    home=np.array([not g['neutral'] for g in games],float)
    rest=rest_features(games);x=np.array([rest[g['id']] for g in games])
    ref=instant(games[-1]['start']);age=np.array([(ref-instant(g['start'])).total_seconds()/86400 for g in games])
    w=np.exp(-math.log(2)*age/half_life)
    def rates(v):
        attack=v[2:2+n];defense=v[2+n:2+2*n];b=v[-2:]
        return np.exp(v[0]+v[1]*home+attack[h]+defense[a]+x@b),np.exp(v[0]+attack[a]+defense[h]-x@b)
    def objective(v):
        lh,la=rates(v);rh=w*(lh-y[:,0]);ra=w*(la-y[:,1])
        loss=np.sum(w*(lh-y[:,0]*np.log(lh)+la-y[:,1]*np.log(la)))+ridge*np.sum(v[2:]**2)/2
        grad=np.zeros_like(v);grad[0]=np.sum(rh+ra);grad[1]=rh@home
        grad[2:2+n]=np.bincount(h,rh,minlength=n)+np.bincount(a,ra,minlength=n)
        grad[2+n:2+2*n]=np.bincount(a,rh,minlength=n)+np.bincount(h,ra,minlength=n)
        grad[-2:]=x.T@(rh-ra);grad[2:]+=ridge*v[2:]
        return loss,grad
    init=np.zeros(2+2*n+2);init[0]=math.log(max(np.average(y[:,1],weights=w),.1));init[1]=math.log(max(np.average(y[:,0],weights=w),.1))-init[0]
    bounds=[(math.log(.2),math.log(10)),(-1,1)]+[(-2,2)]*(2*n)+[(-1,1)]*2
    result=minimize(objective,init,jac=True,method='L-BFGS-B',bounds=bounds,options={'maxiter':400,'ftol':1e-10})
    if not result.success or not np.all(np.isfinite(result.x)):raise ValueError('Entraînement NHL non convergé')
    lh,la=rates(result.x);mask=y[:,0]==y[:,1]
    otx=np.column_stack([np.ones(np.sum(mask)),np.log(lh[mask]/la[mask])]);oty=np.array([g['hg']>g['ag'] for g in games],float)[mask];otw=w[mask]
    if np.sum(mask)<60:raise ValueError('Historique de prolongations insuffisant')
    def otloss(v):
        z=otx@v;p=expit(z)
        return np.sum(otw*(np.logaddexp(0,z)-oty*z))+ridge*np.sum(v*v)/2,otx.T@(otw*(p-oty))+ridge*v
    ot=minimize(otloss,np.zeros(2),jac=True,method='L-BFGS-B')
    if not ot.success:raise ValueError('Modèle prolongations non convergé')
    empirical={'reg':np.average(np.column_stack([y[:,0]>y[:,1],y[:,0]==y[:,1],y[:,0]<y[:,1]]),axis=0,weights=w).tolist(),
               'ml':float(np.average([g['hg']>g['ag'] for g in games],weights=w)),
               'over':{str(line):float(np.average(y.sum(axis=1)>line,weights=w)) for line in LINES}}
    return {'teams':teams,'v':result.x.tolist(),'ot':ot.x.tolist(),'half_life':half_life,'ridge':ridge,'empirical':empirical,
            'counts':{t:sum(g['h']==t or g['a']==t for g in games) for t in teams},'n':len(games),'asof':games[-1]['start'],'version':VERSION}

def predict(model,g,history,blend=None,rest_override=None):
    if g['h'] not in model['teams'] or g['a'] not in model['teams']:return None
    if min(model['counts'][g['h']],model['counts'][g['a']])<20:return None
    n=len(model['teams']);v=np.array(model['v']);h=model['teams'].index(g['h']);a=model['teams'].index(g['a'])
    # Les matchs futurs ne sont utilisés que pour calculer le repos connu au calendrier.
    rest=rest_override if rest_override is not None else rest_features([x for x in history if x['start']<g['start']]+[g])[g['id']];b=float(np.dot(rest,v[-2:]))
    lh=math.exp(v[0]+v[1]*(not g['neutral'])+v[2+h]+v[2+n+a]+b)
    la=math.exp(v[0]+v[2+a]+v[2+n+h]-b)
    ph=poisson.pmf(np.arange(81),lh);pa=poisson.pmf(np.arange(81),la);m=np.outer(ph,pa)
    if not np.isfinite(m).all() or m.sum()<.999999: return None
    m/=m.sum();reg=np.array([np.tril(m,-1).sum(),np.trace(m),np.triu(m,1).sum()])
    q=float(expit(model['ot'][0]+model['ot'][1]*math.log(lh/la)));ml=float(reg[0]+reg[1]*q)
    over={str(l):float(poisson.sf(math.floor(l),lh+la)) for l in LINES}
    if blend is not None:
        base=model['empirical'];reg=blend['reg']*reg+(1-blend['reg'])*np.array(base['reg']);ml=blend['ml']*ml+(1-blend['ml'])*base['ml']
        over={k:blend['total']*p+(1-blend['total'])*base['over'][k] for k,p in over.items()}
    return {'reg':reg.tolist(),'ml':ml,'over':over,'lambda_home':lh,'lambda_away':la,'rest':rest,'ot_home':q}

def truth(g):return {'reg':0 if g['rh']>g['ra'] else 1 if g['rh']==g['ra'] else 2,'ml':int(g['hg']>g['ag']),'over':{str(l):int(g['rh']+g['ra']>l) for l in LINES}}
def binary_loss(p,y):return -math.log(max(min(p if y else 1-p,1-1e-10),1e-10))
def loss(p,g):
    y=truth(g)
    return (-math.log(max(p['reg'][y['reg']],1e-10))+binary_loss(p['ml'],y['ml'])+sum(binary_loss(p['over'][k],t) for k,t in y['over'].items())/len(LINES))/3

def walk(games,eval_games,params):
    """Blocs de 28 jours ; chaque fit ne lit que les dates précédant le bloc."""
    out=[];model=None;block_end=None;rests=rest_features(games)
    for g in eval_games:
        day=g['start'][:10]
        if model is None or day>=block_end:
            training=[x for x in games if x['start'][:10]<day]
            model=fit(training,**params);block_end=(dt.date.fromisoformat(day)+dt.timedelta(days=28)).isoformat()
        p=predict(model,g,games,rest_override=rests[g['id']])
        if p:out.append((g,p,model['empirical']))
    return out

def calibrate(rows):
    """Poids de mélange choisis sur la validation seule ; zéro autorise l'abstention du modèle face à la référence."""
    result={}
    for kind in ('reg','ml','total'):
        def score(alpha):
            vals=[]
            for g,p,base in rows:
                y=truth(g)
                if kind=='reg':vals.append(-math.log(max(alpha*p['reg'][y['reg']]+(1-alpha)*base['reg'][y['reg']],1e-10)))
                elif kind=='ml':vals.append(binary_loss(alpha*p['ml']+(1-alpha)*base['ml'],y['ml']))
                else:vals.extend(binary_loss(alpha*p['over'][k]+(1-alpha)*base['over'][k],t) for k,t in y['over'].items())
            return float(np.mean(vals))
        result[kind]=min([0,.25,.5,.75,1],key=score)
    return result

def blended(p,base,b):return {**p,'reg':(b['reg']*np.array(p['reg'])+(1-b['reg'])*np.array(base['reg'])).tolist(),'ml':b['ml']*p['ml']+(1-b['ml'])*base['ml'],'over':{k:b['total']*v+(1-b['total'])*base['over'][k] for k,v in p['over'].items()}}

def metrics(rows,blend):
    if not rows:return {'n':0}
    ml=[];base=[];briers=[];correct=[];bins=[];paired={}
    regloss=[];totloss=[];regbase=[];totbase=[]
    for g,p,emp in rows:
        p=blended(p,emp,blend);y=truth(g)
        l=binary_loss(p['ml'],y['ml']);l0=binary_loss(emp['ml'],y['ml']);ml.append(l);base.append(l0);briers.append((p['ml']-y['ml'])**2);correct.append(int((p['ml']>=.5)==bool(y['ml'])))
        paired.setdefault(g['date'],[]).append(l0-l)
        prob=max(p['ml'],1-p['ml']);bins.append((prob,correct[-1]))
        regloss.append(-math.log(max(p['reg'][y['reg']],1e-10)));regbase.append(-math.log(max(emp['reg'][y['reg']],1e-10)))
        totloss.extend(binary_loss(p['over'][k],v) for k,v in y['over'].items());totbase.extend(binary_loss(emp['over'][k],v) for k,v in y['over'].items())
    dates=list(paired);rng=np.random.default_rng(42)
    boot=[np.mean([z for d in rng.choice(dates,len(dates),replace=True) for z in paired[d]]) for _ in range(500)]
    calibration=[]
    for lo,hi in [(.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.00001)]:
        obs=[x for x in bins if lo<=x[0]<hi]
        if obs:calibration.append({'min':lo,'max':min(hi,1),'n':len(obs),'annonce':float(np.mean([x[0] for x in obs])),'observe':float(np.mean([x[1] for x in obs]))})
    return {'n':len(rows),'du':rows[0][0]['date'],'au':rows[-1][0]['date'],'logloss':float(np.mean(ml)),'baseline_logloss':float(np.mean(base)),
            'brier':float(np.mean(briers)),'accuracy':float(np.mean(correct)),
            'reg_logloss':float(np.mean(regloss)),'reg_baseline_logloss':float(np.mean(regbase)),
            'total_logloss':float(np.mean(totloss)),'total_baseline_logloss':float(np.mean(totbase)),
            'skill_ci95':np.quantile(boot,[.025,.975]).tolist(),'calibration':calibration}

def train(games,now):
    gs=finals(games,now);dates=sorted({g['start'][:10] for g in gs})
    if len(gs)<1200 or len(dates)<120:raise ValueError('Au moins 1200 rencontres et 120 dates pour la validation séparée')
    dval=dates[int(len(dates)*.6)];dtest=dates[int(len(dates)*.8)]
    val=[g for g in gs if dval<=g['start'][:10]<dtest];test=[g for g in gs if g['start'][:10]>=dtest]
    candidates=[]
    for half_life in (60,120,240):
        for ridge in (1,5,20):
            params={'half_life':half_life,'ridge':ridge};rows=walk(gs,val,params)
            if len(rows)<100:raise ValueError('Validation trop courte')
            candidates.append((float(np.mean([loss(p,g) for g,p,_ in rows])),params,rows))
    score,params,vr=min(candidates,key=lambda x:x[0]);blend=calibrate(vr)
    tr=walk(gs,test,params);report=metrics(tr,blend)
    report.update(version=VERSION,protocole='60 % dates entraînement / 20 % validation / 20 % test, réentraînement passé seul par blocs de 28 jours',validation_n=len(vr),params=params,blend=blend,
                  baseline='Fréquences de victoire domicile, issue 60 min et totaux apprises sur le passé du même bloc',
                  statut='expérimental',note='Test historique hors réglage. Pas de cote historique : aucune rentabilité mesurée. Pas de supériorité démontrée face au robot football.')
    model=fit(gs,**params);model['blend']=blend;model['report']=report
    model['fingerprint']=hashlib.sha256(json.dumps([(g['id'],g['rh'],g['ra'],g['hg'],g['ag']) for g in gs]).encode()).hexdigest()
    model['trained_at']=now.isoformat()
    return model
