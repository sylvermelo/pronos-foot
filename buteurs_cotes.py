"""Vraies cotes buteurs : un événement/jour maximum, budget partagé.
Marché US explicitement étiqueté. Aucune requête côté navigateur.
"""
import math
import unicodedata
import buteurs_collecte as C


def nom(s):
    s=unicodedata.normalize('NFKD',str(s or ''))
    return ''.join(c for c in s if c.isalnum()).lower()


def extraire(data,expected,now):
    """Rapprochement exact du nom complet, ambiguïtés rejetées."""
    lut={}
    for p in expected['joueurs']:lut.setdefault(nom(p['nom']),[]).append(p['id'])
    out=[]
    if data.get('commence_time') is None or C.dateutc(data['commence_time'])!=C.dateutc(expected['debut_utc']):return []
    for book in data.get('bookmakers',[]):
        for market in book.get('markets',[]):
            if market.get('key')!='player_goal_scorer_anytime':continue
            for o in market.get('outcomes',[]):
                if o.get('name') not in ('Yes','Over'):continue
                if o.get('name')=='Over' and o.get('point')!=.5:continue
                ids=lut.get(nom(o.get('description')),[])
                try:price=float(o['price'])
                except (KeyError,ValueError,TypeError):continue
                if len(ids)!=1 or not math.isfinite(price) or price<=1:continue
                out.append({'player_id':ids[0],'price':price,'bookmaker':book.get('key'),
                    'bookmaker_nom':book.get('title'),'market':'player_goal_scorer_anytime',
                    'outcome':o['name'],'line':o.get('point'),'event_id':data.get('id'),
                    'espn_event_id':expected['event_id'],'commence_time':data['commence_time'],
                    'last_update':market.get('last_update') or book.get('last_update'),
                    'fetched_at':now,'region':'us'})
    return out


def collecter(payload):
    import cotes_live as O
    key=O.cle()
    if not key:return {'statut':'cle_absente'}
    now=C.maintenant();jour=(now+__import__('datetime').timedelta(hours=1)).date().isoformat()
    candidates=[m for m in payload['matchs'] if m['date']==jour and m['composition_confirmee'] and any(p.get('analyse') for p in m['joueurs'])]
    if not candidates:return {'statut':'aucun_candidat_confirme'}
    ledger=C.lire('odds_budget.json',{'jours':{}})
    day=ledger.setdefault('jours',{}).setdefault(jour,{'tentatives':[],'credits_max':0})
    if day.get('buteur_tente'):return {'statut':'plafond_journalier'}
    _,headers=O._curl_json(f'{O.BASE}/sports/?apiKey={key}&all=false')
    try:remaining=int(headers['x-requests-remaining'])
    except (KeyError,TypeError,ValueError):return {'statut':'quota_inconnu'}
    if remaining-1<O.RESERVE:return {'statut':'reserve_atteinte'}
    # Réutiliser les IDs d'événements déjà collectés par le robot d'équipes.
    events=O.charger().get('evenements',[])
    for m in candidates:
        event=next((e for e in events if e['div']==m['div'] and e['home']==m['home'] and e['away']==m['away'] and C.dateutc(e['debut_utc'])==C.dateutc(m['debut_utc'])),None)
        if not event:continue
        day['buteur_tente']=event['event_id'];day['credits_max']+=1
        O._sauver(O.BUDGET,ledger) # réserver, même si le marché est absent
        data,headers=O._curl_json(f"{O.BASE}/sports/{O.SPORTS[m['div']]}/events/{event['event_id']}/odds?apiKey={key}&regions=us&markets=player_goal_scorer_anytime&oddsFormat=decimal")
        cache=C.lire('buteurs_cotes.json',{'prix':[]})
        prix=extraire(data,m,now.isoformat()) if isinstance(data,dict) else []
        cache['prix']=[p for p in cache['prix'] if C.dateutc(p['commence_time']) and C.dateutc(p['commence_time'])>now and p['espn_event_id']!=m['event_id']]+prix
        C.sauver('buteurs_cotes.json',cache)
        try:ledger['quota_restant_observe']=int(headers['x-requests-remaining'])
        except (KeyError,TypeError,ValueError):ledger['quota_restant_observe']=None
        O._sauver(O.BUDGET,ledger)
        return {'statut':'collecte','prix':len(prix)}
    return {'statut':'evenement_non_cote'}


def appliquer(payload,now=None):
    from cotation import valide
    now=now or C.maintenant()
    prix=C.lire('buteurs_cotes.json',{'prix':[]})['prix']
    for m in payload['matchs']:
        for p in m['joueurs']:
            qs=[q for q in prix if q.get('espn_event_id')==m['event_id'] and q.get('player_id')==p['id'] and valide(q,now)]
            # Prix de collecte, pas une promesse d'exécution chez le client.
            q=max(qs,key=lambda q:(q['last_update'],q['bookmaker'])) if qs else None
            p['cotation']=q;p['cote_marche']=q['price'] if q else None
            if q and p.get('analyse'):
                p['avantage_estime']=round(p['analyse']['p']*q['price']-1,4)
            p['statut']='analyse_seule' # Aucun coupon automatique durant validation.
    # Joindre uniquement les prix reçus AVANT le gel initial. Ne pas réécrire les probabilités.
    suivi=C.lire('buteurs_suivi.json',{'matchs':{}})
    for eid,event in suivi['matchs'].items():
        freeze=C.dateutc(event['fige_le'])
        for p in event['joueurs']:
            if p.get('cotation'):continue
            qs=[q for q in prix if q.get('espn_event_id')==eid and q.get('player_id')==p['id'] and C.dateutc(q['fetched_at']) and C.dateutc(q['fetched_at'])<=freeze]
            if qs:
                q=sorted(qs,key=lambda q:(q['fetched_at'],q['bookmaker']))[-1]
                p['cotation']=q;p['cote_marche']=q['price']
    C.sauver('buteurs_suivi.json',suivi)
