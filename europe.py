"""UEFA : modèle dédié sur identités UEFA, abstention explicitée et calendrier de secours."""
import datetime as dt,hashlib,json
from pathlib import Path
import calendrier,coupes,fatigue
from hockey_collecte import write,read,DATA,instant,UTC
import europe_modele as M
import europe_profond as P
def modele():
    return max([read(DATA/'europe_modele_seed.json',{}),read(DATA/'europe_modele.json',{})],key=lambda m:m.get('asof',''))

def vue():
    import serveur as S
    now=dt.datetime.now(UTC);today=(now+dt.timedelta(hours=1)).date().isoformat();etat=fatigue.charger();history=P.lire();model=modele();official=[];archive=read(DATA/'europe_previsions.json',{})
    for g in history.get('games',[]):
        if not now<instant(g['start'])<=now+dt.timedelta(days=21) or g['state'] not in ('UPCOMING','SCHEDULED','NOT_STARTED'):continue
        m={'event_id':'uefa-'+g['id'],'div':g['div'],'ligue':coupes.COUPES[g['div']]['nom'],'home':g['home'],'away':g['away'],'date':g['date'],'heure':g['heure'],'debut_utc':g['start'],'disponible':False,'modele_uefa':False,'source':'UEFA'}
        snap=archive.get('uefa-'+g['id']);p=snap['prediction'] if snap and snap['start']==g['start'] and instant(snap['frozen_at'])<instant(g['start']) else M.predict(model,g,model.get('alpha',1)) if model else None
        m['frozen_at']=snap.get('frozen_at') if snap else None
        if p:
            m.update(p,disponible=True,modele_uefa=True,raison=f"Forces offensives et défensives apprises sur les matchs UEFA, avec référence par pays. {p['historique_home']} matchs historiques pour le domicile, {p['historique_away']} pour l’extérieur. Probabilités à 90 min, sans prolongation. Modèle expérimental ; sans prix exact, analyse seule.")
        else:
            counts=model.get('counts',{});m['raison']=f"Historique UEFA insuffisant : {g['home']} {counts.get(g['h'],0)} matchs ; {g['away']} {counts.get(g['a'],0)} matchs. Minimum 6 par club. Le robot ne remplace pas ces données par un pourcentage inventé."
        official.append(m)
    fixtures=calendrier.coupes_archive(S.DB,etat=etat);merged={}
    for fx in fixtures+S.DB.get('fixtures',[]):
        if fx.get('div') in ('UCL','UEL','UECL'):merged[(fx['div'],fx.get('event_id') or (fx['home'],fx['away'],fx['date']))]=fx
    fallback=S.api_matchs(fixtures=list(merged.values()));covered={(m['div'],m['date']) for m in official}
    # Une journée officielle partielle ne doit pas masquer les rencontres de secours.
    from collections import Counter
    oc=Counter((m['div'],m['date']) for m in official);fc=Counter((m['div'],m['date']) for m in fallback)
    partial={key for key,n in oc.items() if n<fc[key]}
    official=[m for m in official if (m['div'],m['date']) not in partial]
    covered-=partial
    fallback=[m for m in fallback if (m['div'],m['date']) not in covered and (m['date']>today or (m['date']==today and (m.get('heure') or '23:59')>(now+dt.timedelta(hours=1)).strftime('%H:%M')))]
    for m in fallback:
        m['raison']='Calendrier ESPN de secours ; identité UEFA non rapprochée. '+('Approximation inter-ligues issue des championnats domestiques, non validée pour cette coupe.' if m.get('disponible') else 'Au moins une équipe est absente des modèles domestiques. Aucune probabilité publiée.')
    rows=sorted(official+fallback,key=lambda m:(m['date'],m.get('heure') or '',m['home']));r=model.get('report',{});gaps=history.get('errors',[])
    return {'genere_le':now.isoformat(),'collecte_le':history.get('collected_at') or etat.get('genere_le'),'competitions':[{'id':k,'nom':coupes.COUPES[k]['nom'],'nb':sum(m['div']==k for m in rows)} for k in ('UCL','UEL','UECL')],'matchs':rows,'evaluation':r,'methode':f"{r.get('historique_n',0)} matchs UEFA historiques. Test : {r.get('n',0)} matchs analysables sur {r.get('total_matchs',0)} ; erreur {r.get('logloss',0):.4f}, référence {r.get('baseline_logloss',0):.4f}. {r.get('protocole','')} Les clubs sans 6 rencontres restent sans probabilités. Sources manquantes : {len(gaps)}.",'note':'Sources UEFA officielles et calendrier ESPN de secours. Modèle UEFA expérimental, ni blessures ni compositions futures dans le calcul. Les sources manquantes sont signalées dans la couverture. Aucune coupe dans les coupons automatiques.'}

def main():
    import europe_profond
    data=europe_profond.collect();games=[g for g in data['games'] if g.get('rh') is not None];sig=hashlib.sha256(json.dumps(games,sort_keys=True).encode()).hexdigest();m=modele()
    if m.get('version')!=M.VERSION or m.get('fingerprint')!=sig:
        m=M.train(data['games']);write(DATA/'europe_modele.json',m)
    payload=vue();archive=read(DATA/'europe_previsions.json',{});now=dt.datetime.now(UTC)
    for row in payload['matchs']:
        if row.get('modele_uefa') and instant(row['debut_utc'])>now and row['event_id'] not in archive:
            archive[row['event_id']]={'start':row['debut_utc'],'frozen_at':now.isoformat(),'version':M.VERSION,'prediction':{k:row[k] for k in ('p1','pX','p2','lambda_home','lambda_away','historique_home','historique_away')}}
    write(DATA/'europe_previsions.json',archive);payload=vue();write(DATA/'europe_jour.json',payload);print('Europe :',len(payload['matchs']),'rencontres visibles,',sum(m.get('modele_uefa',False) for m in payload['matchs']),'analyses UEFA')
if __name__=='__main__':main()
