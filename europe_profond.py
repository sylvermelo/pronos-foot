"""Historique UEFA officiel paginé ; cache fermé, actualisation courante bornée."""
import datetime as dt,json,time,subprocess,threading
from concurrent.futures import ThreadPoolExecutor
from hockey_collecte import DATA,read,write,instant,UTC
COMP={'UCL':1,'UEL':14,'UECL':2019}
SEED=DATA/'europe_historique_seed.json'
def lire():
    candidates=[read(p,{'games':[]}) for p in (SEED,DATA/'europe_historique.json')]
    return max(candidates,key=lambda j:j.get('last_attempt',''))

def normalize(r,div):
    try:
        if str(r.get('competition',{}).get('id'))!=str(COMP[div]):return None
        h,a=r['homeTeam'],r['awayTeam'];start=instant(r['kickOffTime']['dateTime']);score=r.get('score',{}).get('regular',{})
        g={'id':str(r['id']),'source_competition':str(COMP[div]),'div':div,'season':r['seasonYear'],'h':str(h['id']),'a':str(a['id']),'home':h['internationalName'],'away':a['internationalName'],'hc':h['countryCode'],'ac':a['countryCode'],'start':start.isoformat(),'date':(start+dt.timedelta(hours=1)).date().isoformat(),'heure':(start+dt.timedelta(hours=1)).strftime('%H:%M'),'state':r['status'],'neutral':False}
        if r['status']=='FINISHED' and type(score.get('home'))==int and type(score.get('away'))==int:g.update(rh=score['home'],ra=score['away'])
        return g
    except (KeyError,TypeError,ValueError):return None

def collect(bootstrap=False):
    now=dt.datetime.now(UTC);old=lire();meta=read(DATA/'europe_collecte_meta.json',{})
    if not bootstrap and meta.get('last_attempt') and (now-instant(meta['last_attempt'])).total_seconds()<21600:return old
    calls=[0];lock=threading.Lock()
    cache=DATA/'europe_sources';cache.mkdir(exist_ok=True);year=now.year+int(now.month>=7);tasks=[(d,s) for d in COMP for s in (range(2023,year+1) if bootstrap else [year])]
    def fetch(t):
        div,s=t;out=[]
        try:
            p=cache/f'{COMP[div]}-{s}.json'
            if p.exists() and s<year:
                cached=json.loads(p.read_text())
                return t,cached,None if cached else 'saison fermée vide, couverture manquante'
            complete=False
            for offset in range(0,1000,100):
                with lock:
                    if calls[0]>=(100 if bootstrap else 24):raise ValueError('budget UEFA atteint, reprise ultérieure')
                    calls[0]+=1
                url=f'https://match.uefa.com/v5/matches?competitionId={COMP[div]}&seasonYear={s}&limit=100&offset={offset}'
                r=subprocess.run(['curl','--http1.1','-fsSL','--compressed','--max-time','25',url],capture_output=True,text=True,timeout=30)
                if r.returncode:raise ValueError('source HTTP '+str(r.returncode))
                rows=json.loads(r.stdout)
                if not isinstance(rows,list):raise ValueError('format UEFA invalide')
                for row in rows:
                    g=normalize(row,div)
                    if g:out.append(g)
                if len(rows)<100:complete=True;break
                time.sleep(.2)
            if not complete:raise ValueError('pagination incomplète')
            write(p,out);return t,out,None if out else 'saison vide, couverture manquante'
        except (ValueError,OSError,subprocess.TimeoutExpired) as e:return t,out,str(e)
    games={g['id']:g for g in old['games']};errors=[]
    with ThreadPoolExecutor(max_workers=2) as ex:
        for (d,s),rows,error in ex.map(fetch,tasks):
            for g in rows:games[g['id']]=g
            if error:errors.append(f'{d} {s}: {error}')
            print('UEFA',d,s,len(rows),error or 'OK',flush=True)
    out={'games':sorted(games.values(),key=lambda g:(g['start'],g['id'])),'collected_at':now.isoformat() if not errors else old.get('collected_at'),'last_attempt':now.isoformat(),'errors':errors,'source':'UEFA Match API, scores réglementaires'}
    write(SEED if bootstrap else DATA/'europe_historique.json',out);write(DATA/'europe_collecte_meta.json',{'last_attempt':now.isoformat(),'errors':errors});return out
if __name__=='__main__':
    import sys
    collect('--bootstrap' in sys.argv)
