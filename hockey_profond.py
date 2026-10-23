"""Historique NHL en lots : équipes depuis 2019, patineurs depuis 2023.
Chaque requête est contrôlée contre la borne de 10 000 lignes de l'API.
Amorçage manuel borné ; routine quotidienne 2 requêtes dans le budget partagé.
"""
import calendar,datetime as dt,gzip,json,subprocess,time,urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hockey_collecte as C

CACHE=C.DATA/'nhl_stats_cache'
SEED=C.DATA/'nhl_profonds_seed.json.gz'
FIELDS=['playerId','gameId','gameDate','teamAbbrev','opponentTeamAbbrev','positionCode','homeRoad','goals','assists','shots','timeOnIcePerGame','ppGoals','otGoals']

class StatsClient(C.Client):
    def __init__(self,bootstrap=False):
        super().__init__(bootstrap);self.limit=100 if bootstrap else 2
    def stats(self,report,expr,key,cache=True):
        p=CACHE/(key+'.json.gz')
        if cache and p.exists():
            with gzip.open(p,'rt') as f:return json.load(f)
        with self.lock:
            if self.calls>=self.limit or (not self.bootstrap and self.etat['calls']>=40):raise RuntimeError('budget NHL partagé atteint')
            self.calls+=1;self.etat['calls']+=1;C.write(self.path,self.etat)
        u='https://api.nhle.com/stats/rest/en/'+report+'?isAggregate=false&isGame=true&start=0&limit=-1&cayenneExp='+urllib.parse.quote(expr)
        r=subprocess.run(['curl','--http1.1','-fsSL','--compressed','--max-time','30',u],capture_output=True,text=True,timeout=34)
        if r.returncode:raise RuntimeError('rapport NHL indisponible '+str(r.returncode))
        j=json.loads(r.stdout);rows=j.get('data')
        if not isinstance(rows,list) or len(rows)>=10000 or j.get('total',len(rows))!=len(rows):raise ValueError('rapport NHL tronqué : fractionner la période')
        CACHE.mkdir(parents=True,exist_ok=True)
        with gzip.open(p,'wt') as f:json.dump(rows,f,separators=(',',':'))
        time.sleep(.25)
        return rows

def read_seed():
    candidates=[]
    for path in (SEED,C.DATA/'hockey_profonds.json.gz'):
        try:
            with gzip.open(path,'rt') as f:candidates.append(json.load(f))
        except (OSError,ValueError):pass
    return max(candidates,key=lambda x:x.get('collected_at','')) if candidates else {'players':[],'teams':[],'names':{},'errors':[]}

def team_games(rows,old=None):
    """Rapports appariés domicile/extérieur ; ne confond pas buts SO et buts réels."""
    by=defaultdict(list);out={};old=old or {}
    for r in rows:
        if r.get('gamesPlayed')==1:by[str(r['gameId'])].append(r)
    for gid,pair in by.items():
        if len(pair)!=2 or {r.get('homeRoad') for r in pair}!={'H','R'}:continue
        h=next(r for r in pair if r['homeRoad']=='H');a=next(r for r in pair if r['homeRoad']=='R')
        if h['goalsFor']!=a['goalsAgainst'] or a['goalsFor']!=h['goalsAgainst']:continue
        winner=h if h.get('wins')==1 else a if a.get('wins')==1 else None
        if not winner:continue
        period='REG' if winner.get('winsInRegulation')==1 else 'SO' if winner.get('winsInShootout')==1 else 'OT'
        hg,ag=int(h['goalsFor']),int(a['goalsFor'])
        if period=='SO' and hg==ag:
            if winner is h:hg+=1
            else:ag+=1
        if (hg<=ag and winner is h) or (ag<=hg and winner is a):continue
        if period!='REG' and abs(hg-ag)!=1:continue
        date=h['gameDate'][:10]
        # Heure inconnue dans le rapport : date seulement, jamais utilisée pour un conseil historique en direct.
        g={'id':gid,'season':int(gid[:4]+str(int(gid[:4])+1)),'start':date+'T12:00:00+00:00','date':date,'date_nhl':date,'heure':'','start_precision':'date',
           'h':str(h['teamId']),'a':str(a['teamId']),'home':h['teamFullName'],'away':a['teamFullName'],
           'home_abbr':a['opponentTeamAbbrev'],'away_abbr':h['opponentTeamAbbrev'],'state':'OFF','neutral':False,
           'hg':hg,'ag':ag,'rh':min(hg,ag) if period!='REG' else hg,'ra':min(hg,ag) if period!='REG' else ag,'period':period,
           'shots_home':h.get('shotsForPerGame'),'shots_away':a.get('shotsForPerGame'),'pp_home':h.get('powerPlayPct'),'pp_away':a.get('powerPlayPct'),
           'pk_home':h.get('penaltyKillPct'),'pk_away':a.get('penaltyKillPct')}
        if gid in old:
            o=old[gid]
            # Contrôle indépendant des scores contre le calendrier quand présent.
            if o.get('rh') is not None and (o['hg'],o['ag'],o['rh'],o['ra'])!=(hg,ag,g['rh'],g['ra']):continue
            g={**g,**o,'date_nhl':date,**{k:g[k] for k in ('shots_home','shots_away','pp_home','pp_away','pk_home','pk_away')}}
        out[gid]=g
    return out

def player_row(r):
    try:
        if r['gamesPlayed']!=1 or r['positionCode']=='G' or not r.get('timeOnIcePerGame') or not r.get('skaterFullName'):return None
        for k in ('goals','assists','shots'):
            if type(r.get(k))!=int or r[k]<0:return None
        if r['goals']>r['shots']:return None
        return [str(r['playerId']),str(r['gameId']),r['gameDate'][:10],r['teamAbbrev'],r['opponentTeamAbbrev'],'D' if r['positionCode']=='D' else 'F',r['homeRoad'],r['goals'],r['assists'],r['shots'],round(float(r['timeOnIcePerGame'])/60,3),r.get('ppGoals'),r.get('otGoals')]
    except (KeyError,TypeError,ValueError):return None

def collect(bootstrap=False):
    now=dt.datetime.now(C.UTC);old=read_seed();meta=C.read(C.DATA/'hockey_profonds_meta.json',{})
    if not bootstrap and meta.get('last_attempt') and (now-C.instant(meta['last_attempt'])).total_seconds()<86400:return old
    client=StatsClient(bootstrap);tasks=[]
    if bootstrap:
        for year in range(2019,2027):tasks.append(('team/summary',f'seasonId={year}{year+1} and gameTypeId=2',f'team-{year}',True))
        for year in range(2023,2027):
            for y,months in [(year,range(7,13)),(year+1,range(1,7))]:
                for month in months:
                    first=dt.date(y,month,1)
                    if first>now.date():continue
                    end=min(dt.date(y,month,calendar.monthrange(y,month)[1]),now.date())
                    expr=f'seasonId={year}{year+1} and gameTypeId=2 and gameDate>="{first}" and gameDate<="{end}"'
                    tasks.append(('skater/summary',expr,f'players-{year}-{y}-{month}-{end}',True))
    else:
        first=(now.date()-dt.timedelta(days=3)).isoformat();end=now.date().isoformat();exp=f'gameTypeId=2 and gameDate>="{first}" and gameDate<="{end}"'
        tasks=[(r,exp,r.split('/')[0]+'-'+end,False) for r in ('team/summary','skater/summary')]
    players={(r[0],r[1]):r for r in old['players']};teams={str(r['gameId'])+'|'+r['homeRoad']:r for r in old['teams']};names=old['names'];errors=[]
    def fetch(t):
        try:return t,client.stats(*t),None
        except (RuntimeError,ValueError,subprocess.TimeoutExpired) as e:return t,[],str(e)
    with ThreadPoolExecutor(max_workers=2) as ex:
        for task,rows,error in ex.map(fetch,tasks):
            if error:errors.append(task[2]+': '+error);continue
            if task[0].startswith('team'):
                for r in rows:teams[str(r['gameId'])+'|'+r['homeRoad']]=r
            else:
                for r in rows:
                    p=player_row(r)
                    if p:players[(p[0],p[1])]=p;names[p[0]]=r['skaterFullName']
            print('NHL profondeur',task[2],len(rows),flush=True)
    result={'players':sorted(players.values(),key=lambda r:(r[2],r[1],r[0])),'teams':list(teams.values()),'names':names,
            'source':'NHL Stats REST, rapports officiels','collected_at':now.isoformat(),'errors':errors,'source_complete':not errors,'schema':1}
    # Seed reproductible compact ; aucun secret ou compte utilisateur.
    with gzip.open(SEED if bootstrap else C.DATA/'hockey_profonds.json.gz','wt',compresslevel=9) as f:json.dump(result,f,ensure_ascii=False,separators=(',',':'))
    C.write(C.DATA/'hockey_profonds_meta.json',{'last_attempt':now.isoformat(),'calls':client.calls,'errors':errors[:8]})
    # Enrichit la mémoire existante sans effacer rencontres à venir ni prévisions.
    hist=C.read(C.DATA/'hockey_matchs.json',{});known={g['id']:g for g in C.seed_history().get('games',[])};known.update({g['id']:g for g in hist.get('games',[])})
    known.update(team_games(result['teams'],known));hist['games']=sorted(known.values(),key=lambda g:(g['start'],g['id']));C.write(C.DATA/'hockey_matchs.json',hist)
    if bootstrap:
        with gzip.open(C.DATA/'nhl_historique_profond_seed.json.gz','wt',compresslevel=9) as f:json.dump({'source':'NHL calendrier + rapports équipes','collected_at':now.isoformat(),'games':[g for g in hist['games'] if g.get('rh') is not None]},f,ensure_ascii=False,separators=(',',':'))
    print('NHL profondeur total',len(result['players']),'observations joueurs',len(result['names']),'joueurs',len(team_games(result['teams'])),'matchs équipes',len(errors),'erreurs',flush=True)
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--bootstrap',action='store_true');a=p.parse_args();collect(a.bootstrap)
