"""Références individuelles Understat : saisons closes et contexte par match.
Jamais un total de fin de saison dans une prévision antérieure à sa clôture.
"""
import datetime as dt,gzip,json,subprocess,time,unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import buteurs_collecte as C

SEED=C.DATA/'buteurs_references_seed.json.gz'
LIGUES={'EPL':'E0','La_liga':'SP1','Bundesliga':'D1','Serie_A':'I1','Ligue_1':'F1'}
# Le slug officiel est La_liga dans le collecteur xG existant.

def lire():
    try:
        with gzip.open(SEED,'rt') as f:return json.load(f)
    except (OSError,ValueError):return {'players':[],'teams':[],'errors':[]}

def nom(s):return ''.join(c.lower() for c in unicodedata.normalize('NFKD',s or '') if c.isalnum())

def collecter():
    old=lire();players={(p['div'],p['season'],p['id']):p for p in old['players']};teams={(p['div'],p['date'],p['team']):p for p in old['teams']};errors=[]
    cache=C.DATA/'profondeur_understat';cache.mkdir(exist_ok=True)
    def fetch(t):
        slug,div,season=t;p=cache/(slug+'-'+str(season)+'.json.gz')
        try:
            if p.exists():
                with gzip.open(p,'rt') as f:j=json.load(f)
            else:
                r=subprocess.run(['curl','--http1.1','-fsSL','--compressed','--max-time','25','-H','User-Agent: Mozilla/5.0','-H','X-Requested-With: XMLHttpRequest',f'https://understat.com/getLeagueData/{slug}/{season}'],capture_output=True,text=True,timeout=30)
                if r.returncode:raise ValueError('HTTP source '+str(r.returncode))
                j=json.loads(r.stdout)
                if not isinstance(j.get('players'),list) or not isinstance(j.get('teams'),dict):raise ValueError('données absentes')
                with gzip.open(p,'wt') as f:json.dump(j,f,separators=(',',':'))
                time.sleep(.25)
            return t,j,None
        except (ValueError,OSError,subprocess.TimeoutExpired) as e:return t,{},str(e)
    tasks=[(slug,div,season) for slug,div in LIGUES.items() for season in (2023,2024,2025)]
    with ThreadPoolExecutor(max_workers=2) as ex:
        for (slug,div,season),j,error in ex.map(fetch,tasks):
            if error:errors.append(f'{div} {season}: {error}');continue
            end=f'{season+1}-07-01'
            for r in j['players']:
                try:
                    n=int(r['games']);minutes=int(r['time']);goals=int(r['goals']);xg=float(r['xG'])
                    if n<=0 or minutes<=0 or min(goals,xg)<0:continue
                    p={'id':r['id'],'nom':r['player_name'],'key':nom(r['player_name']),'div':div,'season':season,'available_from':end,'games':n,'minutes':minutes,'goals':goals,'xg':xg,'assists':int(r['assists']),'xa':float(r['xA']),'shots':int(r['shots']),'team':r['team_title'],'position':r['position']}
                    players[(div,season,p['id'])]=p
                except (KeyError,ValueError,TypeError):continue
            for r in j['teams'].values():
                for h in r.get('history',[]):
                    try:
                        t={'div':div,'team':r['title'],'date':h['date'][:10],'goals_against':float(h['missed']),'xga':float(h['xGA']),'goals_for':float(h['scored']),'xg':float(h['xG'])}
                        teams[(div,t['date'],t['team'])]=t
                    except (KeyError,ValueError,TypeError):continue
            print('Références buteurs',div,season,len(j['players']),flush=True)
    out={'players':list(players.values()),'teams':list(teams.values()),'errors':errors,'collected_at':C.maintenant().isoformat(),'source':'Understat saisons 2023/24 à 2025/26','schema':1}
    with gzip.open(SEED,'wt',compresslevel=9) as f:json.dump(out,f,ensure_ascii=False,separators=(',',':'))
    print('Références buteurs total',len(out['players']),'lignes joueur-saison',len(out['teams']),'observations équipes',len(errors),'sources manquantes',flush=True)
    return out

_INDEX=None
def reference(name,div,date,data=None):
    global _INDEX
    if data is not None:pool=data['players']
    else:
        if _INDEX is None:
            _INDEX={}
            for p in lire()['players']:_INDEX.setdefault(p['key'],[]).append(p)
        pool=_INDEX.get(nom(name),[])
    key=nom(name)
    rows=[p for p in pool if p['key']==key and p['available_from']<=date]
    # Une identité Understat unique ; jamais rapprochement approximatif d'homonymes.
    if len({p['id'] for p in rows})!=1:return None
    # Les saisons antérieures dans d'autres ligues sont décrites mais non
    # assimilées automatiquement à la difficulté de la nouvelle ligue.
    rows=[p for p in rows if p['div']==div]
    if not rows:return None
    return {k:sum(p[k] for p in rows) for k in ('games','minutes','goals','xg','assists','xa','shots')}|{'seasons':len(rows),'latest':max(p['available_from'] for p in rows),'source_id':rows[0]['id']}

if __name__=='__main__':collecter()
