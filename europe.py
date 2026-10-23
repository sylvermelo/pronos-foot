"""Vue UEFA dédiée, calendrier visible même sans modèle pour un club."""
import datetime as dt
from pathlib import Path
import calendrier,coupes,fatigue
from hockey_collecte import write

def vue():
    import serveur as S
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=1)));today=now.date().isoformat()
    etat=fatigue.charger();fixtures=calendrier.coupes_archive(S.DB,etat=etat)
    # La collecte principale plus récente a priorité sur l'archive fatigue.
    merged={}
    for fx in fixtures+S.DB.get('fixtures',[]):
        if fx.get('div') not in ('UCL','UEL','UECL'):continue
        key=(fx['div'],fx.get('event_id') or (fx['home'],fx['away'],fx['date']))
        merged[key]=fx
    rows=S.api_matchs(fixtures=list(merged.values()))
    rows=[m for m in rows if m['date']>today or (m['date']==today and (m.get('heure') or '23:59')>now.strftime('%H:%M'))]
    return {'genere_le':now.isoformat(),'collecte_le':etat.get('genere_le'),'sources':etat.get('sources',{}),'competitions':[
        {'id':key,'nom':coupes.COUPES[key]['nom'],'nb':sum(m['div']==key for m in rows)} for key in ('UCL','UEL','UECL')],
        'matchs':rows,'note':'Calendrier UEFA à venir. Les pourcentages éventuels sont indicatifs : le modèle inter-ligues n’est pas calibré pour ces coupes. Les rencontres sans modèle restent affichées. Aucune coupe dans les coupons automatiques.'}

def main():
    payload=vue();write(Path(__file__).resolve().parent/'data/europe_jour.json',payload);print('Europe :',len(payload['matchs']),'rencontres visibles')

if __name__=='__main__':main()
