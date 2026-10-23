"""Historique individuel ESPN : données manquantes distinctes des zéros.
Partage le cache HTTP avec compos.py. Quatre connexions, budgets persistants.
"""
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import time

DATA = Path(__file__).resolve().parent / 'data'
BIG5 = {'E0':'eng.1','SP1':'esp.1','I1':'ita.1','D1':'ger.1','F1':'fra.1'}
VERSION = 1
MAX_PAR_RUN = 16
MAX_PAR_JOUR = 160


def lire(nom, defaut=None):
    try:
        return json.loads((DATA/nom).read_text())
    except (OSError, ValueError):
        return {} if defaut is None else defaut


def sauver(nom, valeur):
    DATA.mkdir(exist_ok=True)
    path = DATA/nom
    tmp = path.with_suffix('.part')
    tmp.write_text(json.dumps(valeur, ensure_ascii=False, separators=(',',':')))
    os.replace(tmp,path)


def maintenant():
    return dt.datetime.now(dt.timezone.utc)


def dateutc(s):
    try:
        return dt.datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(dt.timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def entier(x):
    try:
        v=float(x)
        return int(v) if math.isfinite(v) and v>=0 and v.is_integer() else None
    except (TypeError,ValueError):
        return None


def minute(e):
    """Temps d'exposition réglementaire, sans compter deux fois les arrêts."""
    per=entier(e.get('period',{}).get('number'))
    if per not in (1,2): return None
    c=e.get('clock',{})
    try:
        v=float(c.get('value'))/60
    except (TypeError,ValueError): return None
    if not math.isfinite(v) or v<0: return None
    return min(v,45 if per==1 else 90)


def extraire(s, div, fetched=None):
    """N'accepte que les statistiques de match complètes et vérifiées.
    Les minutes reconstruites sont des minutes réglementaires approximées.
    Les tirs/assists absents restent None ; aucun coefficient tir inventé.
    """
    if div not in BIG5 or not isinstance(s,dict): return None
    slug=s.get('header',{}).get('league',{}).get('slug')
    if slug and slug!=BIG5[div]:return None
    comp=(s.get('header',{}).get('competitions') or [{}])[0]
    event=str(comp.get('id') or s.get('header',{}).get('id') or '')
    ko=dateutc(comp.get('date'))
    if not event or not ko: return None
    status=comp.get('status',{}).get('type',{})
    fini=status.get('completed') is True
    # Les prolongations/tirs au but demandent un autre périmètre : exclure.
    if fini and status.get('name') not in ('STATUS_FULL_TIME',): return None
    if not fini and status.get('state')!='pre': return None
    sides={str(c.get('id') or c.get('team',{}).get('id')):c for c in comp.get('competitors',[])}
    if len(sides)!=2: return None
    home=next((c for c in sides.values() if c.get('homeAway')=='home'),None)
    away=next((c for c in sides.values() if c.get('homeAway')=='away'),None)
    if not home or not away:return None
    events=s.get('keyEvents') or []
    changes={}; sentoff={}; own={'home':0,'away':0}; penalties={}
    for e in events:
        if e.get('shootout') or e.get('period',{}).get('number') not in (1,2):continue
        typ=e.get('type',{}).get('text','').lower()
        ids=[str(p.get('athlete',{}).get('id','')) for p in e.get('participants',[])]
        m=minute(e)
        if typ=='substitution' and len(ids)==2 and m is not None:
            # Ordre ESPN entrant/sortant contrôlé aussi par flags du roster.
            changes.setdefault(ids[0],{})['in']=m
            changes.setdefault(ids[1],{})['out']=m
        if ('red card' in typ or 'second yellow' in typ) and ids and m is not None: sentoff[ids[0]]=m
        if 'own goal' in typ:
            side=sides.get(str(e.get('team',{}).get('id')),{}).get('homeAway')
            if side in own:own[side]+=1
        if 'penalty' in typ and e.get('scoringPlay') and ids:
            penalties[ids[0]]=penalties.get(ids[0],0)+1
    teams={}
    for roster in s.get('rosters') or []:
        team=sides.get(str(roster.get('team',{}).get('id')),{})
        side=team.get('homeAway')
        if side not in ('home','away'):continue
        players=[]
        for j in roster.get('roster',[]):
            a=j.get('athlete',{});pid=str(a.get('id') or '')
            if not pid:continue
            stats={v.get('name'):entier(v.get('value')) for v in j.get('stats',[])}
            starter=j.get('starter') is True
            played=starter or j.get('subbedIn') is True or (stats.get('appearances') or 0)>0
            mins=None
            if fini:
                if not played:mins=0
                else:
                    ch=changes.get(pid,{})
                    start=0 if starter else ch.get('in')
                    end=sentoff.get(pid,ch.get('out',90 if not j.get('subbedOut') and not (stats.get('redCards') or 0)>0 else None))
                    # Une substitution non renseignée ne devient jamais 90 minutes.
                    if start is not None and end is not None and end>=start:
                        mins=round(end-start,3)
            pos=(j.get('position') or {}).get('abbreviation') or '?'
            group='G' if pos=='G' else 'D' if 'B' in pos or 'D' in pos else 'M' if 'M' in pos else 'F' if 'F' in pos or 'W' in pos else '?'
            g=stats.get('totalGoals') if played else (0 if fini else None)
            players.append({'id':pid,'nom':a.get('displayName') or '?','poste':group,
                'titulaire':starter,'joue':played,'minutes':mins,'buts':g,
                'passes':stats.get('goalAssists') if played else None,
                'tirs':stats.get('totalShots') if played else None,
                'cadres':stats.get('shotsOnTarget') if played else None,
                'penalties':penalties.get(pid,0) if fini else None,
                'csc':stats.get('ownGoals') if played else None})
        if sum(p['titulaire'] for p in players)!=11:return None
        teams[side]={'id':str(team.get('id')),'nom':team.get('team',{}).get('displayName'),
                     'score':entier(team.get('score')),'joueurs':players}
    if set(teams)!= {'home','away'}:return None
    valid=True
    if fini:
        for side,opp in [('home','away'),('away','home')]:
            pl=teams[side]['joueurs'];opp_pl=teams[opp]['joueurs']
            if any(p['joue'] and p['buts'] is None for p in pl):valid=False;continue
            # Les buts contre son camp sont attribués à l'adversaire au score.
            if any(p['joue'] and p['csc'] is None for p in opp_pl):valid=False;continue
            score=sum(p['buts'] or 0 for p in pl)+sum(p['csc'] or 0 for p in opp_pl)
            if teams[side]['score'] is None or score!=teams[side]['score']: valid=False
    return {'event_id':event,'div':div,'debut_utc':ko.isoformat(),'date':ko.date().isoformat(),
            'fini':fini,'valide':valid,'equipes':teams,'schema':VERSION,
            'collecte_le':fetched or maintenant().isoformat()}


def ingere_compos(etat):
    hist=lire('joueurs_matchs.json',{'matchs':{}});n=0
    for m in etat.get('matchs',{}).values():
        row=m.get('joueurs')
        if row and row.get('schema')==VERSION:
            old=hist['matchs'].get(row['event_id'])
            if old is None or row['collecte_le']>old['collecte_le']:
                hist['matchs'][row['event_id']]=row;n+=1
    if n:sauver('joueurs_matchs.json',hist)
    return n


def collecter(fixtures, amorcage=False):
    """16 summaries/passage ; 160 historiques + 80 récents/jour. Amorçage : 320 historiques.
    Scoreboards Big5 hier/aujourd'hui au plus une fois toutes les 6 heures.
    Les pré-matchs sont retentés dans la fenêtre H−2, au plus toutes les 15 min.
    """
    import calendrier,compos
    hist=lire('joueurs_matchs.json',{'matchs':{}})
    meta=lire('joueurs_collecte_meta.json');now=maintenant();jour=now.date().isoformat()
    if meta.get('jour')!=jour:meta.update(jour=jour,appels=0,historique_appels=0,live_appels=0)
    candidates=lire('joueurs_candidats.json')
    for m in compos.charger().get('matchs',{}).values():
        if m.get('div') in BIG5 and m.get('evt'):
            candidates[str(m['evt'])]={'div':m['div'],'ko':m['date']+'T00:00:00Z','fini':bool(m.get('fini'))}
    for f in fixtures:
        if f.get('div') in BIG5 and f.get('event_id') and f.get('debut_utc'):
            candidates[str(f['event_id'])]={'div':f['div'],'ko':f['debut_utc'],'fini':False}
    if amorcage or time.time()-meta.get('scoreboards_le',0)>=21600:
        # Rattrapage progressif : trois jours historiques par passage lourd.
        cursor=dt.date.fromisoformat(meta.get('curseur_historique',(now.date()-dt.timedelta(days=2)).isoformat()))
        anciens=[cursor-dt.timedelta(days=i) for i in range(21 if amorcage else 3)] if cursor>=now.date()-dt.timedelta(days=1095) else []
        reprises=meta.get('scoreboards_a_reprendre',[])[:15]
        dates=sorted({now.date().isoformat(),(now.date()-dt.timedelta(days=1)).isoformat()}|{d.isoformat() for d in anciens})
        tasks=[(div,slug,date) for div,slug in BIG5.items() for date in dates]
        def board(t):
            div,slug,date=t
            d=calendrier.scoreboard_jours(slug,date)
            if d is None:return t,None
            out=[]
            for e in d.get('events',[]):
                c=(e.get('competitions') or [{}])[0]
                out.append((str(e.get('id')),{'div':div,'ko':c.get('date') or e.get('date'),'fini':c.get('status',{}).get('type',{}).get('completed') is True}))
            return t,out
        pending={tuple(t) for t in meta.get('scoreboards_a_reprendre',[])}
        tasks=list(dict.fromkeys(tasks+[tuple(t) for t in reprises]))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            for task,rows in ex.map(board,tasks):
                if rows is None:pending.add(task)
                else:candidates.update(rows);pending.discard(task)
        meta['scoreboards_a_reprendre']=[list(t) for t in sorted(pending)]
        meta['scoreboards_le']=time.time()
        if anciens:meta['curseur_historique']=(min(anciens)-dt.timedelta(days=1)).isoformat()
        sauver('joueurs_candidats.json',candidates)
    # Reprendre les matchs déjà connus après leur fin, même après disparition du calendrier.
    for eid,m in hist['matchs'].items():
        if not m['fini']:
            candidates[eid]={'div':m['div'],'ko':m['debut_utc'],'fini':now>(dateutc(m['debut_utc'])+dt.timedelta(hours=3))}
    tasks=[]
    attempts=meta.setdefault('tentatives',{})
    for eid,m in candidates.items():
        ko=dateutc(m['ko']);old=hist['matchs'].get(eid)
        if not ko:continue
        if old and old.get('fini') and old.get('valide') and old.get('schema')==VERSION:
            # Une seconde lecture après 24 h peut récupérer une correction statistique.
            last=dateutc(old['collecte_le'])
            if old.get('recontrole') or not last or (now-last).total_seconds()<86400:continue
        if old and old.get('fini') and not old.get('valide') and time.time()-attempts.get(eid,0)<21600:continue
        if not m['fini'] and not -10800<=(ko-now).total_seconds()<=7200:continue
        if time.time()-attempts.get(eid,0)<900:continue
        tasks.append((eid,m))
    # Priorité aux compos imminentes, puis scores récents, puis amorçage.
    tasks.sort(key=lambda t:(t[1]['fini'],attempts.get(t[0],0), -dateutc(t[1]['ko']).timestamp(), t[0]))
    # Réserver 80 appels/jour aux compositions et résultats récents,
    # même après l'amorçage historique exceptionnel (320 summaries).
    meta.setdefault('historique_appels',meta.get('appels',0))
    meta.setdefault('live_appels',0)
    live_left=max(0,80-meta['live_appels'])
    hist_left=max(0,(320 if amorcage else MAX_PAR_JOUR)-meta['historique_appels'])
    choisis=[];n_live=0;n_hist=0
    for task in tasks:
        ko=dateutc(task[1]['ko'])
        live=abs((now-ko).total_seconds())<=3*86400
        if live and n_live<live_left:n_live+=1;choisis.append(task)
        elif not live and n_hist<hist_left:n_hist+=1;choisis.append(task)
        if len(choisis)>=(320 if amorcage else MAX_PAR_RUN):break
    tasks=choisis
    for eid,_ in tasks:attempts[eid]=time.time()
    meta['appels']=meta.get('appels',0)+len(tasks)
    meta['live_appels']+=n_live;meta['historique_appels']+=n_hist
    sauver('joueurs_collecte_meta.json',meta) # réserver avant les appels
    def summary(t):
        eid,m=t
        try:
            s=compos._summary(BIG5[m['div']],eid)
            row=extraire(s,m['div'])
        except (KeyError,TypeError,ValueError,AttributeError,IndexError):
            print(f'buteurs : résumé {eid} incomplet, à retenter',flush=True)
            return None
        if row and row['fini'] and hist['matchs'].get(eid,{}).get('fini'):
            row['recontrole']=True
        return row
    n=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for row in ex.map(summary,tasks):
            if row:
                hist['matchs'][row['event_id']]=row;n+=1
                if n%20==0:
                    sauver('joueurs_matchs.json',hist)
                    print(f'buteurs : {n}/{len(tasks)} résumés conservés',flush=True)
    sauver('joueurs_matchs.json',hist)
    return {'appels':len(tasks),'captures':n,'total':len(hist['matchs']),
            'valides':sum(m['fini'] and m['valide'] for m in hist['matchs'].values())}


def signature(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()


def synchroniser():
    """Sauvegarde delta privée et restauration quotidienne sans écraser le local."""
    import db
    if not db.disponible():return {'statut':'ignore'}
    hist=lire('joueurs_matchs.json',{'matchs':{}})
    meta=lire('joueurs_sync_meta.json');now=maintenant().isoformat();jour=now[:10]
    if meta.get('jour')!=jour:
        cursor=meta.get('curseur','1970-01-01T00:00:00+00:00').replace('+','%2B')
        for offset in range(0,50000,250):
            code,body=db._requete('GET','joueurs_matchs',None,
                f'?select=event_id,brut&modifie_le=gt.{cursor}&order=event_id&limit=250&offset={offset}')
            if code!='200':raise RuntimeError(f'Restauration joueurs HTTP {code}')
            rows=json.loads(body)
            for r in rows:
                m=r['brut'];old=hist['matchs'].get(r['event_id'])
                if old is None or m['collecte_le']>old['collecte_le']:hist['matchs'][r['event_id']]=m
            if len(rows)<250:break
        else:raise RuntimeError('Pagination joueurs incomplète')
        meta.update(jour=jour,curseur=now)
    connus=meta.setdefault('signatures',{});pending=[]
    for eid,m in hist['matchs'].items():
        sig=signature(m)
        if connus.get(eid)!=sig:
            pending.append((eid,sig,{'event_id':eid,'division':m['div'],'date_match':m['date'],
                                     'brut':m,'modifie_le':now}))
    sauver('joueurs_matchs.json',hist)
    for offset in range(0,len(pending),50):
        lot=pending[offset:offset+50]
        code,_=db._requete('POST','joueurs_matchs',[r for _,_,r in lot],'?on_conflict=event_id')
        if code not in db.OK_HTTP:raise RuntimeError(f'Sauvegarde joueurs HTTP {code}')
        connus.update({eid:sig for eid,sig,_ in lot})
        sauver('joueurs_sync_meta.json',meta)
    sauver('joueurs_sync_meta.json',meta)
    return {'statut':'ok','sauvegardes':len(pending),'total':len(hist['matchs'])}
