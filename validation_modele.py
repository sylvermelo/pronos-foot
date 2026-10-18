"""Comparaison chronologique reproductible ; jamais utilisée pour régler le test.

Derniers 120 matchs par ligue gardés à part, entraînement strictement antérieur.
Compare buts corrigés, ancienne exportation et xG recalés. Aucun ROI sans prix.
Usage : python validation_modele.py (quelques minutes, aucune écriture métier).
"""
import datetime
import json
from pathlib import Path
import numpy as np
import entraine as E
import moteur_v3 as V


def mesures(rows):
    if not rows:
        return None
    return {"n":len(rows), "logloss_1x2":float(np.mean([r[0] for r in rows])),
            "logloss_ou25":float(np.mean([r[1] for r in rows])),
            "brier_ou25":float(np.mean([r[2] for r in rows])),
            "precision_favori":float(np.mean([r[3] for r in rows]))}


def main():
    df=E.charger()
    sorties=[]
    total={k:[] for k in ("buts_corriges","buts_avant","xg_recales")}
    for div in sorted(E.NOMS):
        sub=df[df.league==div].sort_values(["date","home","away"])
        if len(sub)<500:
            continue
        test=sub.tail(120)
        train=sub[sub.date<test.date.min()]
        train=train[train.season.isin(sorted(train.season.unique())[-5:])]
        if len(train)<300:
            continue
        teams=sorted(set(train.home)|set(train.away))
        saved=[]
        minimize=V.minimize
        def cap(*args,**kwargs):
            r=minimize(*args,**kwargs)
            saved.append(r)
            return r
        V.minimize=cap
        try:
            mg=V.fit_goals(train,teams,shrink=20.)
        finally:
            V.minimize=minimize
        if not saved[0].success:
            print(div,"optimisation non convergée ; exclue",flush=True)
            continue
        # Ancienne version : même optimum, seule l'exportation s était erronée.
        ancien=dict(mg)
        ancien["s"]=float(np.exp(saved[0].x[2*len(teams)+2]))
        configs={"buts_corriges":mg,"buts_avant":ancien}
        hr=train.dropna(subset=["xgRH","xgRA"]).copy()
        if div in E.XG_REEL_DIVS and len(hr)>=300:
            hr["xgH"]=hr.xgRH;hr["xgA"]=hr.xgRA
            mx=V.fit_xg(hr,teams)
            if mx:
                hi=train.home.map(mx["idx"]).values; aw=train.away.map(mx["idx"]).values
                pred=mx["gh"]*mx["att"][hi]*mx["dfn"][aw]+mx["ga"]*mx["att"][aw]*mx["dfn"][hi]
                k=float((train.hg+train.ag).mean()/pred.mean())
                m=V.combine(mg,mx,0.)
                m["gamma"]*=k;m["s"]*=k
                configs["xg_recales"]=m
        rows={k:[] for k in configs}
        for r in test.itertuples():
            for nom,m in configs.items():
                mat=V.score_matrix(m,r.home,r.away)
                if mat is None:
                    continue
                p=V.derive(mat)
                y=0 if r.hg>r.ag else 1 if r.hg==r.ag else 2
                p3=np.array([p["p1"],p["pX"],p["p2"]])
                over=int(r.hg+r.ag>2.5)
                po=p["pO25"]
                row=(-np.log(max(p3[y],1e-12)),-np.log(max(po if over else 1-po,1e-12)),(po-over)**2,int(np.argmax(p3)==y))
                rows[nom].append(row);total[nom].append(row)
        out={"division":div,"train_n":len(train),"train_fin":str(train.date.max().date()),
             "test_debut":str(test.date.min().date()),"test_fin":str(test.date.max().date()),
             "mesures":{k:mesures(v) for k,v in rows.items()}}
        sorties.append(out)
        print(json.dumps(out,ensure_ascii=False),flush=True)
    rapport={"genere_le":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "protocole":"Holdout chronologique, derniers 120 matchs par division, sans réajustement dans le test. Comparaison du cœur statistique ; ne simule pas toute la stratégie de production, fatigue/compositions/lissage/cotes exclus. xG seulement sur son sous-ensemble : comparer par ligue, pas ses agrégats au groupe complet.",
        "divisions":sorties,"total":{k:mesures(v) for k,v in total.items()}}
    Path("docs/VALIDATION-2026-10-18.json").write_text(json.dumps(rapport,indent=2,ensure_ascii=False))
    print(json.dumps(rapport["total"],indent=2),flush=True)


if __name__=="__main__":
    main()
