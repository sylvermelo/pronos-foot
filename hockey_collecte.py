"""NHL : collecte mutualisée côté batch, aucune clé ni cote payante.
Routine : 3 semaines de calendrier, TTL 2 h, plafond 40 requêtes/jour.
Amorçage explicite : calendriers de clubs, plafond 100 appels par exécution.
"""
from __future__ import annotations
import datetime as dt
import json
import gzip
import subprocess
import time
import threading
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
UTC=dt.timezone.utc

def read(path,default):
    try: return json.loads(Path(path).read_text())
    except (OSError,ValueError): return default

def write(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False));tmp.replace(path)

def seed_history():
    try:
        with gzip.open(DATA/'nhl_historique_profond_seed.json.gz','rt') as f:return json.load(f)
    except (OSError,ValueError):return read(DATA/'nhl_historique_seed.json',{})

def instant(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(UTC)

def normalize(g):
    """Conserve les identités NHL et distingue score 60 min / score officiel."""
    if g.get('gameType')!=2 or g.get('gameScheduleState') not in (None,'OK'): return None
    try:
        h,a=g['homeTeam'],g['awayTeam']; start=instant(g['startTimeUTC'])
        if h['id']==a['id']: return None
        name=lambda t: (t.get('placeName',{}).get('default','')+' '+t.get('commonName',{}).get('fr',t.get('commonName',{}).get('default',t['abbrev']))).strip()
        out={'id':str(g['id']),'season':g['season'],'start':start.isoformat(),'date':(start+dt.timedelta(hours=1)).date().isoformat(),'heure':(start+dt.timedelta(hours=1)).strftime('%H:%M'),
             'date_nhl':g.get('gameDate') or start.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
             'h':str(h['id']),'a':str(a['id']),'home':name(h),'away':name(a),'home_abbr':h['abbrev'],'away_abbr':a['abbrev'],
             'neutral':bool(g.get('neutralSite')),'state':g['gameState']}
        if out['state'] in ('FINAL','OFF'):
            hg,ag=h.get('score'),a.get('score'); period=g.get('gameOutcome',{}).get('lastPeriodType')
            if type(hg)!=int or type(ag)!=int or min(hg,ag)<0 or hg==ag or period not in ('REG','OT','SO'): return None
            if period in ('OT','SO') and abs(hg-ag)!=1:return None
            # OT/SO : l'unique but décisif (artificiel en SO) ne fait pas partie des 60 minutes.
            rh,ra=(min(hg,ag),min(hg,ag)) if period!='REG' else (hg,ag)
            out.update(hg=hg,ag=ag,rh=rh,ra=ra,period=period)
        return out
    except (KeyError,ValueError,TypeError,AttributeError):return None

class Client:
    def __init__(self,bootstrap=False):
        self.calls=0;self.bootstrap=bootstrap;self.lock=threading.Lock()
        self.path=DATA/'hockey_collecte_etat.json'
        self.etat=read(self.path,{})
        today=dt.datetime.now(UTC).date().isoformat()
        if self.etat.get('jour')!=today:self.etat={'jour':today,'calls':0}
    def get(self,path):
        with self.lock:
            if self.calls>=(100 if self.bootstrap else 3) or (not self.bootstrap and self.etat['calls']>=40):raise RuntimeError('budget NHL atteint')
            self.calls+=1;self.etat['calls']+=1;write(self.path,self.etat)
        r=subprocess.run(['curl','-f','-sS','-L','--compressed','--max-time','10','https://api-web.nhle.com/v1/'+path],capture_output=True,text=True,timeout=14)
        if r.returncode:raise RuntimeError('NHL indisponible (code '+str(r.returncode)+')')
        j=json.loads(r.stdout)
        if not isinstance(j,dict):raise ValueError('NHL : réponse invalide')
        time.sleep(.15)
        return j

def collect(bootstrap=False,now=None):
    now=now or dt.datetime.now(UTC)
    path=DATA/'hockey_matchs.json';old=read(path,{})
    if not bootstrap and old.get('fetched_at') and (now-instant(old['fetched_at'])).total_seconds()<7200:return old
    games={g['id']:g for g in seed_history().get('games',[])}
    games.update({g['id']:g for g in old.get('games',[])})
    c=Client(bootstrap);errors=[];success=0
    def ingest(raw):
        for g in raw:
            n=normalize(g)
            if n:games[n['id']]=n
    if bootstrap:
        try:
            standing=c.get('standings/now')
            clubs=sorted({t['teamAbbrev']['default'] for t in standing['standings']})
            write(DATA/'nhl_clubs.json',clubs)
        except (RuntimeError,ValueError,subprocess.TimeoutExpired):
            clubs=read(DATA/'nhl_clubs.json',[])
            if len(clubs)<30:raise RuntimeError('Liste des clubs NHL indisponible')
        y=now.year if now.month>=7 else now.year-1
        paths=[f'club-schedule-season/{team}/{season}{season+1}' for season in range(y-2,y+1) for team in clubs]
    else:
        paths=[f'schedule/{(now.date()+dt.timedelta(days=d)).isoformat()}' for d in (-7,0,7)]
    def fetch(path_):
        try:
            j=c.get(path_)
            raw=j.get('games') if bootstrap else [g for day in j.get('gameWeek',[]) for g in day.get('games',[])]
            if not isinstance(raw,list):raise ValueError('calendrier NHL absent')
            return raw,None
        except (RuntimeError,ValueError,subprocess.TimeoutExpired) as e:return [],str(e)
    with ThreadPoolExecutor(max_workers=4 if bootstrap else 2) as executor:
        for raw,error in executor.map(fetch,paths):
            if error:errors.append(error)
            else:ingest(raw);success+=1
    # Ne jamais masquer une panne par un horodatage neuf.
    result={'games':sorted(games.values(),key=lambda g:(g['start'],g['id'])),
            'fetched_at':now.isoformat() if success==len(paths) else old.get('fetched_at'),
            'last_attempt':now.isoformat(),'sources_ok':success,'sources_expected':len(paths),'errors':errors[:4],'historique_partiel':bool(errors) if bootstrap else old.get('historique_partiel',False)}
    write(path,result)
    if bootstrap:
        finals=[g for g in result['games'] if g.get('rh') is not None]
        write(DATA/'nhl_historique_seed.json',{'source':'NHL calendriers officiels','collected_at':now.isoformat(),'games':finals})
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--bootstrap',action='store_true');a=p.parse_args()
    r=collect(a.bootstrap);print(f"NHL : {len(r['games'])} rencontres, {r['sources_ok']}/{r['sources_expected']} sources, {r['errors']}")
