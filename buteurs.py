"""Pipeline buteurs : mémoire, apprentissage, prévisions figées, export léger."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import buteurs_collecte as C
import buteurs_modele as M


def publier(fixtures, modele, hist, now=None, geler=True):
    now=now or C.maintenant();out=[]
    for f in sorted(fixtures,key=lambda f:(f.get('date',''),f.get('heure',''),f.get('home',''))):
        if f.get('div') not in C.BIG5:continue
        ko=C.dateutc(f.get('debut_utc'))
        if not ko or ko<=now or (ko-now).total_seconds()>7*86400:continue
        eid=str(f.get('event_id') or '');row=hist['matchs'].get(eid)
        # Une composition consultée pendant/après le match ne doit jamais servir de prévision.
        confirme=bool(row and not row['fini'] and C.dateutc(row['collecte_le'])<ko and row['debut_utc']==ko.isoformat())
        teams=row['equipes'] if confirme else {}
        if not teams:
            # Noms co.uk et ESPN rapprochés uniquement par le Mappeur déjà validé.
            from calendrier import Mappeur
            names={f['div']:[f['home'],f['away']]};mp=Mappeur(names)
            for side,name in [('home',f['home']),('away',f['away'])]:
                anciens=[m for m in hist['matchs'].values() if m['div']==f['div'] and m['fini'] and m['valide'] and m['date']<f['date']]
                for m in sorted(anciens,key=lambda m:m['date'],reverse=True):
                    t=next((t for t in m['equipes'].values() if mp.traduire(f['div'],t['nom'])==name),None)
                    if t:
                        # Dernier groupe connu : liste d'observation, pas composition probable.
                        teams[side]=t;break
        pl=[]
        for side,t in teams.items():
            for p in t['joueurs']:
                if confirme and not p['titulaire']:continue
                v=M.predire(modele['etat'],f['div'],t['id'],p['id'],p['poste'],modele['pseudo_minutes'],reference_minutes=modele.get('reference_minutes',0),xg_mix=modele.get('xg_mix',0),date=f['date'])
                pl.append({'id':p['id'],'nom':p['nom'],'poste':p['poste'],'equipe':f[side],
                           'titulaire_confirme':confirme,'analyse':v,'cotation':None,
                           'cote_marche':None,'statut':'analyse_seule','resultat':None})
        # Dédoublonner, ordre stable, aucune sélection sans statistique suffisante.
        pl=sorted({p['id']:p for p in pl}.values(),key=lambda p:(-(p.get('analyse') or {}).get('p',-1),p['nom']))
        out.append({'event_id':eid,'div':f['div'],'date':f['date'],'heure':f.get('heure'),
                    'home':f['home'],'away':f['away'],'debut_utc':ko.isoformat(),
                    'composition_confirmee':confirme,'joueurs':pl[:22 if confirme else 12],
                    'version':modele['version'],'signature_modele':modele['signature'],
                    'pseudo_minutes':modele['pseudo_minutes'],'evaluation':modele['evaluation']['statut']})
    suivi=C.lire('buteurs_suivi.json',{'matchs':{}})
    for event in out:
        eid=event['event_id']
        if geler and event['composition_confirmee'] and any(p.get('analyse') for p in event['joueurs']) and eid not in suivi['matchs']:
            suivi['matchs'][eid]={**event,'fige_le':now.isoformat(),'resolu':False}
    for eid,event in suivi['matchs'].items():
        actual=hist['matchs'].get(eid)
        if not actual or not actual['fini'] or not actual['valide']:continue
        players={p['id']:p for t in actual['equipes'].values() for p in t['joueurs']}
        event['resolu']=True
        for p in event['joueurs']:
            r=players.get(p['id'])
            # Non participant : annulé, pas artificiellement gagnant/perdant.
            p['resultat']=None if not r or r['buts'] is None else {'buts':r['buts'],
                'statut':'annule' if not r['joue'] else 'gagne' if r['buts']>0 else 'perdu'}
            if p['resultat'] is None:event['resolu']=False
    C.sauver('buteurs_suivi.json',suivi)
    results=[]
    for event in suivi['matchs'].values():
        for p in event['joueurs']:
            r=p.get('resultat');v=p.get('analyse')
            if r and v and r['statut']!='annule':results.append((event['event_id'],v['p'],int(r['buts']>0),v['baseline']))
    payload={'genere_le':now.isoformat(),'version':modele['version'],
        'historique':{'matchs':modele['historique_matchs'],'joueurs':modele['joueurs'],
                      'bilans_joueur_saison':modele.get('references_saisons',0),'poids_reference_minutes':modele.get('reference_minutes',0),'mix_xg':modele.get('xg_mix',0),
                      'dernier_match':modele['derniere_date'],'entraine_le':modele['entraine_le']},
        'collecte':{'objectif_annees':3,'curseur_historique':C.lire('joueurs_collecte_meta.json').get('curseur_historique'),'journees_a_reprendre':len(C.lire('joueurs_collecte_meta.json').get('scoreboards_a_reprendre',[])),'plus_ancien_match':min((m['date'] for m in hist['matchs'].values() if m.get('fini') and m.get('valide')),default=None)},
        'evaluation':modele['evaluation'],'suivi':M.pertes(results),'matchs':out,
        'note':'Probabilité conditionnelle à la titularisation ; minutes réglementaires reconstruites. Modèle individuel expérimental, adversaire et pénalties non ajustés séparément. Aucun coupon automatique. Sans prix bookmaker exact : analyse seule.'}
    C.sauver('buteurs_jour.json',payload)
    return payload


def synchroniser_suivi():
    """Snapshot immuable en base ; seules les résolutions enrichissent le local.
    Retour au snapshot enregistré en base si un cache CI a été perdu.
    """
    import db
    if not db.disponible():return {'statut':'ignore'}
    hist=C.lire('buteurs_suivi.json',{'matchs':{}})
    meta=C.lire('buteurs_suivi_sync_meta.json');jour=C.maintenant().date().isoformat()
    if meta.get('jour')!=jour:
        for offset in range(0,50000,100):
            code,body=db._requete('GET','buteurs_previsions',None,f'?select=event_id,brut&order=event_id&limit=100&offset={offset}')
            if code!='200':raise RuntimeError(f'Restauration prévisions HTTP {code}')
            rows=json.loads(body)
            for r in rows:
                old=hist['matchs'].get(r['event_id']);saved=r['brut']
                if not old or saved['fige_le']<old['fige_le']:hist['matchs'][r['event_id']]=saved
            if len(rows)<100:break
        else:raise RuntimeError('Restauration prévisions tronquée')
        meta['jour']=jour
    saved=set(meta.get('enregistres',[]));n=0
    for eid,event in hist['matchs'].items():
        if eid in saved:continue
        code,_=db._requete('POST','buteurs_previsions',[{'event_id':eid,
            'debut_utc':event['debut_utc'],'brut':event}], '?on_conflict=event_id',resolution='ignore-duplicates')
        if code not in db.OK_HTTP:raise RuntimeError(f'Sauvegarde prévisions HTTP {code}')
        saved.add(eid);n+=1
        meta['enregistres']=sorted(saved);C.sauver('buteurs_suivi_sync_meta.json',meta)
    C.sauver('buteurs_suivi.json',hist);C.sauver('buteurs_suivi_sync_meta.json',meta)
    return {'statut':'ok','previsions':n}


def vue():
    return C.lire('buteurs_jour.json',{'matchs':[],'historique':{},'evaluation':{'statut':'collecte_en_cours'},'suivi':{'n':0},'note':'Collecte et apprentissage des buteurs en cours.'})


def main(amorcage=False):
    # Restaurer avant de collecter/apprendre. Toute erreur reste visible au journal.
    errors=[]
    for fn in (C.synchroniser,synchroniser_suivi):
        try:print(fn())
        except Exception as e:errors.append(str(e));print('buteurs :',e,file=sys.stderr)
    db=C.lire('modeles.json');fixtures=C.lire('calendrier.json').get('matchs') or db.get('fixtures',[])
    print('buteurs collecte :',C.collecter(fixtures,amorcage),flush=True)
    hist=C.lire('joueurs_matchs.json',{'matchs':{}})
    modele=C.lire('buteurs_modele.json')
    if modele.get('signature')!=M.empreinte(hist):
        modele=M.entrainer(hist)
        C.sauver('buteurs_modele.json',modele)
    payload=publier(fixtures,modele,hist,geler=False)
    try:
        import buteurs_cotes
        print('buteurs cotes :',buteurs_cotes.collecter(payload))
        buteurs_cotes.appliquer(payload)
        C.sauver('buteurs_jour.json',payload)
    except Exception as e:errors.append(str(e));print('buteurs prix :',e,file=sys.stderr)
    # Figer après réception éventuelle du prix et toujours avant coup d'envoi.
    suivi=C.lire('buteurs_suivi.json',{'matchs':{}})
    freeze=C.maintenant()
    for event in payload['matchs']:
        if (event['composition_confirmee'] and C.dateutc(event['debut_utc'])>freeze
                and any(p.get('analyse') for p in event['joueurs'])
                and event['event_id'] not in suivi['matchs']):
            suivi['matchs'][event['event_id']]={**event,'fige_le':freeze.isoformat(),'resolu':False}
    C.sauver('buteurs_suivi.json',suivi)
    for fn in (C.synchroniser,synchroniser_suivi):
        try:print(fn())
        except Exception as e:errors.append(str(e));print('buteurs mémoire :',e,file=sys.stderr)
    print('buteurs apprentissage :',modele['historique_matchs'],'matchs,',modele['joueurs'],'joueurs ;',modele['evaluation'])
    payload['sauvegarde_statut']='a_retenter' if errors else 'ok' if __import__('db').disponible() else 'non_configuree'
    C.sauver('buteurs_jour.json',payload)
    if errors:print('buteurs :',len(errors),'incident(s) à retenter ; données locales préservées',file=sys.stderr)
    return payload

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--amorcage',action='store_true')
    args=parser.parse_args();main(args.amorcage)
