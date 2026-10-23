"""Poisson UEFA régularisé, forces clubs et pays apprises sur scores UEFA seuls."""
import datetime as dt,math,hashlib,json
from collections import Counter
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson
from hockey_collecte import DATA,read,write,instant,UTC
VERSION='uefa-1.0.0'
def fit(gs,ridge=5,half_life=480):
    teams=sorted({g[k] for g in gs for k in ('h','a')});countries=sorted({g[k] for g in gs for k in ('hc','ac')});comps=sorted({g['div'] for g in gs});ti={t:i for i,t in enumerate(teams)};ci={t:i for i,t in enumerate(countries)};di={t:i for i,t in enumerate(comps)};n=len(teams);nc=len(countries);nd=len(comps);size=nd+1+2*n+2*nc
    rows=[];y=[];age=[];asof=max(g['start'] for g in gs)
    for g in gs:
        for side,other,cc,oc,home,score in [('h','a','hc','ac',1,g['rh']),('a','h','ac','hc',0,g['ra'])]:
            rows.append([di[g['div']],nd,nd+1+ti[g[side]],nd+1+n+ti[g[other]],nd+1+2*n+ci[g[cc]],nd+1+2*n+nc+ci[g[oc]]]);y.append(score);age.append((instant(asof)-instant(g['start'])).total_seconds()/86400)
    ix=np.array(rows);x=np.zeros((len(rows),size));x[np.arange(len(rows))[:,None],ix]=1;x[1::2,nd]=0;y=np.array(y);w=np.exp(-np.log(2)*np.array(age)/half_life);pen=np.ones(size)*ridge;pen[:nd+1]=0
    def obj(v):
        z=x@v;mu=np.exp(z);return np.sum(w*(mu-y*z))+.5*np.sum(pen*v*v),x.T@(w*(mu-y))+pen*v
    v=np.zeros(size);v[:nd]=math.log(max(np.mean(y),.1));res=minimize(obj,v,jac=True,method='L-BFGS-B',bounds=[(-2,2)]*size,options={'maxiter':600})
    if not res.success:raise ValueError('Modèle UEFA non convergé')
    counts=Counter(t for g in gs for t in (g['h'],g['a']));emp={d:np.mean([[g['rh']>g['ra'],g['rh']==g['ra'],g['rh']<g['ra']] for g in gs if g['div']==d],axis=0).tolist() for d in comps}
    return {'teams':teams,'countries':countries,'comps':comps,'v':res.x.tolist(),'counts':dict(counts),'empirical':emp,'n':len(gs),'asof':asof,'version':VERSION,'ridge':ridge,'half_life':half_life}
def predict(m,g,alpha=1):
    counts=[m['counts'].get(g[k],0) for k in ('h','a')]
    if min(counts)<6:return None
    if any(g[k] not in m['countries'] for k in ('hc','ac')) or g['div'] not in m['comps']:return None
    n=len(m['teams']);nc=len(m['countries']);nd=len(m['comps']);v=m['v'];rates=[]
    for side,other,cc,oc,home in [('h','a','hc','ac',1),('a','h','ac','hc',0)]:
        z=v[m['comps'].index(g['div'])]+v[nd]*home+v[nd+1+m['teams'].index(g[side])]+v[nd+1+n+m['teams'].index(g[other])]+v[nd+1+2*n+m['countries'].index(g[cc])]+v[nd+1+2*n+nc+m['countries'].index(g[oc])];rates.append(math.exp(z))
    matrix=np.outer(poisson.pmf(np.arange(41),rates[0]),poisson.pmf(np.arange(41),rates[1]));p=np.array([np.tril(matrix,-1).sum(),np.trace(matrix),np.triu(matrix,1).sum()]);p/=p.sum();p=alpha*p+(1-alpha)*np.array(m['empirical'][g['div']]);return {'p1':float(p[0]),'pX':float(p[1]),'p2':float(p[2]),'lambda_home':rates[0],'lambda_away':rates[1],'historique_home':counts[0],'historique_away':counts[1]}
def evaluate(m,gs,alpha=1):
    rows=[]
    for g in gs:
        p=predict(m,g,alpha)
        if not p:continue
        probs=[p[k] for k in ('p1','pX','p2')];y=0 if g['rh']>g['ra'] else 1 if g['rh']==g['ra'] else 2;rows.append((-math.log(max(probs[y],1e-9)),-math.log(max(m['empirical'][g['div']][y],1e-9)),int(np.argmax(probs)==y)))
    return {'n':len(rows),'total_matchs':len(gs),'logloss':float(np.mean([x[0] for x in rows])) if rows else None,'baseline_logloss':float(np.mean([x[1] for x in rows])) if rows else None,'accuracy':float(np.mean([x[2] for x in rows])) if rows else None}
def train(games):
    now=dt.datetime.now(UTC);gs=[g for g in games if g.get('rh') is not None and instant(g['start'])+dt.timedelta(hours=4)<now];dates=sorted({g['date'] for g in gs});dv=dates[int(len(dates)*.6)];dtest=dates[int(len(dates)*.8)];initial=[g for g in gs if g['date']<dv];val=[g for g in gs if dv<=g['date']<dtest];test=[g for g in gs if g['date']>=dtest];tuning=[]
    for hl in (240,480):
        for ridge in (1,5,20):
            m=fit(initial,ridge,hl)
            for alpha in (0,.25,.5,.75,1):
                r=evaluate(m,val,alpha)
                if r['n']:tuning.append((r['logloss'],ridge,hl,alpha,r))
    _,ridge,hl,alpha,vr=min(tuning,key=lambda x:x[0]);tm=fit([g for g in gs if g['date']<dtest],ridge,hl);report=evaluate(tm,test,alpha);report.update(validation=vr,test_depuis=dtest,validation_depuis=dv,historique_n=len(gs),apprentissage_initial_n=len(initial),protocole='60/20/20 par dates, paramètres et mélange choisis sur validation, test ultérieur séparé.',alpha=alpha,statut='experimental',note='Modèle UEFA dédié ; 6 rencontres par club minimum. Qualifications incluses. Sans prix archivés, aucune rentabilité mesurée. Finales sur terrain neutre non ajustées séparément.')
    m=fit(gs,ridge,hl);m.update(report=report,alpha=alpha,trained_at=now.isoformat(),fingerprint=hashlib.sha256(json.dumps(gs,sort_keys=True).encode()).hexdigest());return m
if __name__=='__main__':
    m=train(read(DATA/'europe_historique_seed.json',{})['games']);write(DATA/'europe_modele_seed.json',m);print(m['report'])
