"""Orchestrateur NHL : mémoire locale CI, apprentissage hors-ligne, prévisions figées.
Aucun appel fournisseur depuis la vue ou le navigateur. Aucun coupon sans prix.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from hockey_collecte import DATA,UTC,collect,read,write,instant
import hockey_modele as M


def signature(games):return hashlib.sha256(json.dumps([(g['id'],g['rh'],g['ra'],g['hg'],g['ag']) for g in games]).encode()).hexdigest()

def freeze(games,model,archive,now):
    """Ne prédit jamais une rencontre commencée ; aucune réécriture des pronostics."""
    for g in games:
        old=archive.get(g['id'])
        if old and instant(old['frozen_at'])>=instant(g['start']):old['invalid_schedule']=True
        if old:
            if g.get('rh') is not None:
                old['resultat']={k:g[k] for k in ('rh','ra','hg','ag','period')}
            continue
        if not model or g.get('rh') is not None or g['state'] not in ('FUT','PRE') or instant(g['start'])<=now:continue
        if (instant(g['start'])-now).total_seconds()>8*86400:continue
        if model.get('asof','')>=g['start']:continue
        p=M.predict(model,g,games,model['blend'])
        if p:
            archive[g['id']]={'id':g['id'],'start':g['start'],'frozen_at':now.isoformat(),'version':M.VERSION,
                'trained_until':model['asof'],'home':g['home'],'away':g['away'],'p':p,'model_fingerprint':model['fingerprint']}
    return archive

def export(games,model,archive,collection,now):
    upcoming=[]
    for g in games:
        if g.get('rh') is not None or instant(g['start'])<=now or instant(g['start'])>now+dt.timedelta(days=8):continue
        snap=archive.get(g['id']);valid=snap and not snap.get('invalid_schedule')
        upcoming.append({**{k:g[k] for k in ('id','home','away','date','heure','start','home_abbr','away_abbr')},
            'date_nhl':g.get('date_nhl') or instant(g['start']).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date().isoformat(),
            'prediction':snap['p'] if valid else None,'frozen_at':snap['frozen_at'] if valid else None,'version_prevision':snap.get('version') if valid else None,
            'cote_marche':None,'statut':'analyse_seule' if valid else 'donnees_insuffisantes'})
    resolved=[x for x in archive.values() if x.get('resultat') and not x.get('invalid_schedule')]
    hits=sum((x['p']['ml']>=.5)==(x['resultat']['hg']>x['resultat']['ag']) for x in resolved)
    ll=sum(M.binary_loss(x['p']['ml'],x['resultat']['hg']>x['resultat']['ag']) for x in resolved)
    age=(now-instant(collection['fetched_at'])).total_seconds() if collection.get('fetched_at') else None
    recent=sorted(resolved,key=lambda x:x['start'],reverse=True)[:20]
    return {'sport':'hockey','competition':'NHL','version':M.VERSION,'genere_le':now.isoformat(),'source':'NHL — calendriers officiels',
        'collecte_le':collection.get('fetched_at'),'source_age_heures':round(age/3600,1) if age is not None else None,
        'source_incomplete':bool(collection.get('errors')) or age is None or age>12*3600,
        'historique_n':len(M.finals(games,now)),'matchs':upcoming,
        'evaluation':model.get('report',{}) if model else {'statut':'historique_insuffisant','n':0},
        'suivi':{'n':len(resolved),'touches':int(hits),'accuracy':hits/len(resolved) if resolved else None,'logloss':ll/len(resolved) if resolved else None},
        'derniers_resultats':[{'id':x['id'],'home':x['home'],'away':x['away'],'start':x['start'],'p':x['p']['ml'],'resultat':x['resultat'],'frozen_at':x['frozen_at']} for x in recent],
        'note':'Analyse expérimentale NHL. Probabilités estimées, aucune garantie. Vainqueur final : prolongation et tirs au but inclus. Issues et totaux 60 min : hors prolongation. Gardien titulaire et blessures non intégrés sans données fiables. Cote indisponible : aucun coupon hockey.'}

def vue():return read(DATA/'hockey_jour.json',{'sport':'hockey','competition':'NHL','matchs':[],'evaluation':{'statut':'collecte_en_cours'},'suivi':{'n':0},'note':'Le robot prépare son historique NHL. Aucune probabilité publiée sans apprentissage.'})

def main(bootstrap=False,offline=False):
    now=dt.datetime.now(UTC);collection=read(DATA/'hockey_matchs.json',{}) if offline else collect(bootstrap)
    if not offline:
        import hockey_profond
        hockey_profond.collect()
        collection=read(DATA/'hockey_matchs.json',collection)
    games=collection.get('games',[]);model=read(DATA/'hockey_modele.json',{})
    if not model:model=read(DATA/'nhl_modele_seed.json',{})
    history=M.finals(games,now);changed=model.get('fingerprint')!=signature(history)
    age=(now-instant(model['trained_at'])).total_seconds() if model.get('trained_at') else float('inf')
    if model.get('version')!=M.VERSION or (changed and age>=21600):
        try:
            model=M.train(games,now);write(DATA/'hockey_modele.json',model)
        except ValueError as e:print('NHL : modèle conservé / abstention :',str(e))
    archive=read(DATA/'hockey_previsions.json',{})
    archive=freeze(games,model,archive,now);write(DATA/'hockey_previsions.json',archive)
    payload=export(games,model,archive,collection,now)
    import hockey_joueurs
    payload['joueurs']=hockey_joueurs.main(games,now)
    write(DATA/'hockey_jour.json',payload)
    print(f"NHL : {len(history)} historiques, {len(payload['matchs'])} rencontres à venir, {len(archive)} prévisions figées, {payload['suivi']['n']} résultats prospectifs")
    return payload

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--bootstrap',action='store_true');parser.add_argument('--offline',action='store_true');args=parser.parse_args()
    main(args.bootstrap,args.offline)
