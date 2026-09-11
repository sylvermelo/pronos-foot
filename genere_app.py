"""
Génère une version AUTONOME de l'application : un seul fichier HTML
que l'on ouvre d'un double-clic, sans Python, sans serveur, sans internet.
================================================================================
Comment ça marche :
  · les données et les modèles sont pré-calculés ici puis embarqués dans le HTML
  · le moteur Dixon-Coles est réécrit en JavaScript (identique au Python)
  · la fonction api() de l'interface est remplacée : au lieu d'interroger le
    serveur, elle calcule localement. Tout le reste de l'interface est inchangé.

Une vérification de parité est lancée à la fin : le JavaScript doit produire
exactement les mêmes chiffres que le serveur Python.

Usage : python3 genere_app.py
Sortie : pronos-foot-autonome.html
"""
import json
import os
from pathlib import Path

os.environ["PRONOS_SANS_CALENDRIER"] = "1"   # pas de re-téléchargement ESPN ici
import serveur as S

RACINE = Path(__file__).resolve().parent
SORTIE = RACINE / "pronos-foot-autonome.html"


# --------------------------------------------------------------------------- 1
def precalculer():
    """Exécute toutes les routes du serveur une fois et conserve les réponses."""
    print("→ pré-calcul des données...")
    data = {
        "ligues": S.api_ligues(),
        "matchs": S.api_matchs(),
        "bilan": S.api_bilan(),
        "classements": {},
        "fleuves": {},
        "moteur": {},
        "arbitres": S.DB.get("arbitres", {}),
        "index_equipes": S.DB.get("index_equipes", {}),
        "meta": S.DB.get("meta", {}),
        "calendrier": S.DB.get("calendrier_log") or {},
        "suivi": __import__("suivi").vue(),
        "corners_cal": S.api_corners(),
        "fatigue": __import__("fatigue").export_app(),
        "absences": __import__("compos").export_app(),
    }
    # analyse corners poussée : fréquences RÉELLES par division et par ligne
    # (data/analyse_corners.json, généré par analyse_corners.py sur les CSV co.uk)
    try:
        with open("data/analyse_corners.json", encoding="utf-8") as f:
            data["corners_histo"] = json.load(f)
    except (OSError, ValueError):
        data["corners_histo"] = None
    for div, L in S.DB["ligues"].items():
        try:
            data["classements"][div] = S.api_classement(div)
        except Exception:
            data["classements"][div] = None
        try:
            data["fleuves"][div] = S.api_fleuves(div, top=12)
        except Exception:
            data["fleuves"][div] = None
        # ce dont le moteur JS a besoin pour recalculer n'importe quel match
        data["moteur"][div] = {
            "nom": L["nom"], "pays": L["pays"], "saison": L.get("saison"),
            "gamma": L["gamma"], "s_away": L["s_away"], "rho": L["rho"],
            "forces": L["forces"],
            "equipes_actuelles": L.get("equipes_actuelles", []),
            "secondaires": L.get("secondaires"),
            "coupe": bool(L.get("coupe")),
        }
    print(f"   {len(data['ligues'])} ligues | {len(data['matchs'])} matchs | "
          f"{len(data['arbitres'])} arbitres")
    return data


# --------------------------------------------------------------------------- 2
MOTEUR_JS = r"""
/* ============================================================================
   MOTEUR — portée fidèle du code Python (serveur.py + modeles_secondaires.py)
   ============================================================================ */
const MAXG=10;

function logFact(n){let s=0;for(let i=2;i<=n;i++)s+=Math.log(i);return s;}

/* approximation de Lanczos pour log(Gamma) — nécessaire à la binomiale négative */
function logGamma(x){
  const g=[676.5203681218851,-1259.1392167224028,771.32342877765313,
           -176.61502916214059,12.507343278686905,-0.13857109526572012,
           9.9843695780195716e-6,1.5056327351493116e-7];
  if(x<0.5) return Math.log(Math.PI/Math.sin(Math.PI*x))-logGamma(1-x);
  x-=1; let a=0.99999999999980993; const t=x+7.5;
  for(let i=0;i<8;i++) a+=g[i]/(x+i+1);
  return 0.5*Math.log(2*Math.PI)+(x+0.5)*Math.log(t)-t+Math.log(a);
}

function poissonPmf(k,lam){
  if(lam<=0) return k===0?1:0;
  return Math.exp(-lam + k*Math.log(lam) - logFact(k));
}

/* binomiale négative paramétrée par la moyenne et la sur-dispersion */
function nbinomPmf(k,mu,disp){
  if(disp<=1.0001) return poissonPmf(k,mu);
  const r=mu/(disp-1.0), p=r/(r+mu);
  if(p<=0||p>=1) return 0;
  return Math.exp(logGamma(k+r)-logGamma(r)-logFact(k)
                  +r*Math.log(p)+k*Math.log(1-p));
}

function pmfMarche(lam,disp,kmax){
  kmax=kmax||60; const p=[]; let s=0;
  for(let k=0;k<=kmax;k++){const v=Math.max(nbinomPmf(k,lam,disp),0);p.push(v);s+=v;}
  for(let k=0;k<=kmax;k++) p[k]/=Math.max(s,1e-12);
  return p;
}

/* matrice 11x11 des scores exacts, correction Dixon-Coles sur les 4 premières cases */
function matriceScores(L,h,a,mh,ma){
  const F=L.forces; if(!F||!F[h]||!F[a]) return null;
  let lam=Math.min(Math.max(F[h].att*F[a].dfn*L.gamma,1e-6),30);
  let mu =Math.min(Math.max(F[a].att*F[h].dfn*L.s_away,1e-6),30);
  /* fatigue européenne (miroir de serveur.matrice_scores, fat=(mh,ma)) */
  if(mh!=null&&ma!=null){
    lam=Math.min(Math.max(lam*mh,1e-6),30);
    mu =Math.min(Math.max(mu*ma,1e-6),30);
  }
  const rho=L.rho, ph=[], pm=[];
  for(let i=0;i<=MAXG;i++){ph.push(poissonPmf(i,lam));pm.push(poissonPmf(i,mu));}
  const M=[];
  for(let i=0;i<=MAXG;i++){M.push([]);for(let j=0;j<=MAXG;j++)M[i].push(ph[i]*pm[j]);}
  M[0][0]*=Math.max(1-lam*mu*rho,1e-9);
  M[0][1]*=Math.max(1+lam*rho,1e-9);
  M[1][0]*=Math.max(1+mu*rho,1e-9);
  M[1][1]*=Math.max(1-rho,1e-9);
  let s=0;
  for(let i=0;i<=MAXG;i++)for(let j=0;j<=MAXG;j++){M[i][j]=Math.max(M[i][j],0);s+=M[i][j];}
  for(let i=0;i<=MAXG;i++)for(let j=0;j<=MAXG;j++)M[i][j]/=Math.max(s,1e-12);
  return {M,lam,mu};
}

function arr4(x){return Math.round(x*1e4)/1e4;}
/* BUTS D'AFFILÉE — miroir EXACT de series_buts.py : mêmes opérations,
   même ordre (parité REGLES §5). Ne pas modifier sans l'autre fichier. */
function pNoRun(N,p,k){
  if(N===0) return 1;
  const q=1-p;
  let dp=Array.from({length:2},()=>new Array(k).fill(0));
  dp[1][1]=p; dp[0][1]=q;
  for(let step=1;step<N;step++){
    const nd=Array.from({length:2},()=>new Array(k).fill(0));
    for(let c=0;c<=1;c++){
      for(let r=1;r<k;r++){
        const w=dp[c][r];
        if(w===0) continue;
        if(c===1){
          if(r+1<k) nd[1][r+1]+=w*p;
          nd[0][1]+=w*q;
        }else{
          nd[1][1]+=w*p;
          if(r+1<k) nd[0][r+1]+=w*q;
        }
      }
    }
    dp=nd;
  }
  let tot=0;
  for(let c=0;c<=1;c++) for(let r=1;r<k;r++) tot+=dp[c][r];
  return tot;
}
function pSerie(lam,mu,k){
  const tot=lam+mu;
  if(tot<=0) return 0;
  const p=lam/tot;
  let s=0, pn=Math.exp(-tot);
  for(let N=0;N<=40;N++){
    s+=pn*(1-pNoRun(N,p,k));
    pn=pn*tot/(N+1);
  }
  return s;
}
/* Correction du biais walk-forward — mêmes points, mêmes opérations que
   series_buts.py (CORRECTION_SERIE2). Voir docs/SPEC-BUTS-AFFILEE.md. */
const CORR_SERIE2=[[0,0],[0.3518,0.4897],[0.4185,0.4897],[0.4531,0.4932],[0.4825,0.5171],[0.5085,0.5788],[0.5332,0.5788],[0.559,0.6096],[0.5919,0.6199],[0.6326,0.6267],[0.7215,0.7492],[1,1]];
function interpCorr(p,pts){
  if(p<=pts[0][0]) return pts[0][1];
  for(let i=1;i<pts.length;i++){
    const x1=pts[i-1][0],y1=pts[i-1][1],x2=pts[i][0],y2=pts[i][1];
    if(p<=x2) return y1+(y2-y1)*((p-x1)/(x2-x1));
  }
  return pts[pts.length-1][1];
}
function pSerie2(lam,mu){return interpCorr(pSerie(lam,mu,2),CORR_SERIE2);}
/* Séries PAR ÉQUIPE — miroir exact de series_buts.py (mêmes opérations,
   même ordre). Corrections figées le 10/09 (docs/SPEC-BUTS-AFFILEE.md §8.5) :
   dom 2+ brute ; ext 2+ et dom/ext 3+ corrigées des biais walk-forward. */
function pNoRunTeam(N,p,k,home){
  if(N===0) return 1;
  const pe=home?p:1-p;
  const autre=1-pe;
  let dp=new Array(k).fill(0);
  dp[0]=1;
  for(let i=0;i<N;i++){
    const nd=new Array(k).fill(0);
    for(let r=0;r<k;r++){
      const w=dp[r];
      if(w===0) continue;
      nd[0]+=w*autre;
      if(r+1<k) nd[r+1]+=w*pe;
    }
    dp=nd;
  }
  let t=0;
  for(let r=0;r<k;r++) t+=dp[r];
  return t;
}
function pSerieTeam(lam,mu,k,home){
  const tot=lam+mu;
  if(tot<=0) return 0;
  const p=lam/tot;
  let s=0, pn=Math.exp(-tot);
  for(let N=0;N<=40;N++){
    s+=pn*(1-pNoRunTeam(N,p,k,home));
    pn=pn*tot/(N+1);
  }
  return s;
}
const CORR_SERIE2_EXT=[[0,0],[0.0613,0.1678],[0.0957,0.1986],[0.1204,0.1986],[0.1424,0.2021],[0.1645,0.25],[0.1878,0.25],[0.2171,0.3151],[0.2608,0.3733],[0.3134,0.4247],[0.4216,0.4949],[1,1]];
const CORR_SERIE3_DOM=[[0,0],[0.0278,0.0342],[0.0505,0.0479],[0.0697,0.0719],[0.0893,0.0719],[0.1095,0.0788],[0.1317,0.0993],[0.1628,0.1267],[0.2037,0.1815],[0.2632,0.2226],[0.3905,0.3627],[1,1]];
const CORR_SERIE3_EXT=[[0,0],[0.0074,0.0205],[0.0145,0.0514],[0.021,0.0514],[0.0274,0.0548],[0.0346,0.0548],[0.0428,0.0548],[0.0544,0.1096],[0.0737,0.1199],[0.1005,0.161],[0.1688,0.2203],[1,1]];
function pSerie2Dom(lam,mu){return pSerieTeam(lam,mu,2,true);}
function pSerie2Ext(lam,mu){return interpCorr(pSerieTeam(lam,mu,2,false),CORR_SERIE2_EXT);}
function pSerie3Dom(lam,mu){return interpCorr(pSerieTeam(lam,mu,3,true),CORR_SERIE3_DOM);}
function pSerie3Ext(lam,mu){return interpCorr(pSerieTeam(lam,mu,3,false),CORR_SERIE3_EXT);}
function arr3(x){return Math.round(x*1e3)/1e3;}
function arr2(x){return Math.round(x*1e2)/1e2;}

/* marchés secondaires : fautes, corners, cartons */
function secondairesJS(div,h,a,arbitre){
  const L=DATA.moteur[div]; if(!L||!L.secondaires) return null;
  const sec=L.secondaires, E=sec.equipes||{};
  if(!E[h]||!E[a]) return null;
  if(!arbitre){
    for(const fx of (DATA.fixturesBrutes||[])){
      if(fx.div===div&&fx.home===h&&fx.away===a){arbitre=fx.arbitre||null;break;}
    }
  }
  const A=arbitre?(DATA.arbitres||{})[arbitre]:null;
  const MARCHES={
    fautes :{arb:true ,disp:1.52,seuils:[19.5,21.5,23.5,25.5,27.5]},
    corners:{arb:false,disp:1.18,seuils:[7.5,8.5,9.5,10.5,11.5]},
    jaunes :{arb:true ,disp:1.17,seuils:[1.5,2.5,3.5,4.5,5.5]},
  };
  const res={arbitre:arbitre||null,arbitre_couvert:!!A,arbitre_info:A||null,marches:{}};
  for(const mk in MARCHES){
    const cfg=MARCHES[mk];
    if(sec.base[mk]==null) continue;
    const base=sec.base[mk], disp=cfg.disp;
    let mult=1.0;
    if(cfg.arb&&A) mult=(mk==='fautes')?A.fautes:A.jaunes;
    let lh=Math.min(Math.max(base*E[h][mk+'_em']*E[a][mk+'_rc']*mult,0.05),60);
    let la=Math.min(Math.max(base*E[a][mk+'_em']*E[h][mk+'_rc']*mult,0.05),60);
    const ph=pmfMarche(lh,disp,60), pa=pmfMarche(la,disp,60);
    const tot=new Array(61).fill(0);
    for(let i=0;i<=60;i++)for(let j=0;j<=60&&i+j<=60;j++) tot[i+j]+=ph[i]*pa[j];
    let st=0; for(let k=0;k<=61-1;k++) st+=tot[k];
    for(let k=0;k<=60;k++) tot[k]/=Math.max(st,1e-12);
    let pk=0,pv=-1; for(let k=0;k<=60;k++) if(tot[k]>pv){pv=tot[k];pk=k;}
    const over={},under={};
    for(const s of cfg.seuils){
      let so=0,su=0;
      for(let k=0;k<=60;k++){ if(k>s) so+=tot[k]; if(k<s) su+=tot[k]; }
      over[String(s)]=arr4(so); under[String(s)]=arr4(su);
    }
    res.marches[mk]={lambda_home:arr2(lh),lambda_away:arr2(la),
      total_attendu:arr2(lh+la),dispersion:disp,over,under,plus_probable:pk};
  }
  /* CONFRONTATION CORNERS — miroir de serveur.enrichir_secondaires */
  const cf=confrontationCornersJS(div,h,a,sec);
  if(cf){
    const cor=res.marches.corners;
    if(cor){
      cf.over_cal={}; for(const k in cor.over) cf.over_cal[k]=cornCalibrerTotal(cor.over[k]);
      cf.under_cal={}; for(const k in cor.under) cf.under_cal[k]=cornCalibrerTotal(cor.under[k]);
    }
    res.confrontation=cf;
  }
  /* CORNERS 1re MI-TEMPS — miroir de serveur.api_secondaires (res.cmt1) */
  res.cmt1=cmt1JS(div,h,a,sec);
  return res;
}

/* Qui obtient le PLUS de corners en 1re mi-temps ? Miroir exact de
   corners_mt.pronostic : convolution des deux lois binomiales négatives
   (mêmes formules, KMAX=14, lignes 3.5/4.5). Données : fil commentary
   ESPN vérifié contre boxscore — 8 divisions couvertes. */
function cmt1JS(div,h,a,sec){
  sec=sec||((DATA.moteur[div]||{}).secondaires);
  if(!sec||!sec.base||sec.base.cmt1==null) return null;
  const E=sec.equipes||{};
  if(!E[h]||!E[a]) return null;
  const eh=E[h].cmt1_em, rh=E[h].cmt1_rc, ea=E[a].cmt1_em, ra=E[a].cmt1_rc;
  if([eh,rh,ea,ra].some(v=>typeof v!=='number'||!isFinite(v))) return null;
  const base=sec.base.cmt1, disp=sec.base.cmt1_dispersion||1.15;
  const lh=Math.min(Math.max(base*eh*ra,0.05),12), la=Math.min(Math.max(base*ea*rh,0.05),12);
  const KMAX=14;
  const ph=pmfMarche(lh,disp,KMAX), pa=pmfMarche(la,disp,KMAX);
  let pH=0,pN=0,pA=0; const tot=new Array(2*KMAX+1).fill(0);
  for(let i=0;i<=KMAX;i++)for(let j=0;j<=KMAX;j++){
    const v=ph[i]*pa[j]; tot[i+j]+=v;
    if(i>j)pH+=v; else if(i===j)pN+=v; else pA+=v;
  }
  const over={},under={};
  for(const l of [3.5,4.5]){ let so=0,su=0;
    for(let k=0;k<=2*KMAX;k++){ if(k>l)so+=tot[k]; if(k<l)su+=tot[k]; }
    over[String(l)]=arr4(so); under[String(l)]=arr4(su); }
  return {lambda_home:arr2(lh),lambda_away:arr2(la),
    p_home:arr4(pH),p_nul:arr4(pN),p_away:arr4(pA),
    over,under,dispersion:disp,
    n_h:E[h].cmt1_n,n_a:E[a].cmt1_n,n_base:sec.base.cmt1_n};
}

/* CALIBRATION CORNERS — miroir de corners.py (bandes walk-forward de
   DATA.corners_cal, sérialisation exacte de corners._bandes()). */
function cornCalibrer(fam,p){
  if(p==null||p<0.5) return p;
  const cells=((DATA.corners_cal||{}).bandes||{})[fam]||[];
  let chosen=null;
  for(const c of cells) if(p>=c[0]) chosen=c[2];
  if(chosen==null) return arr4(p);
  return arr4(Math.min(p,chosen));
}
function cornCalibrerTotal(p){
  if(p==null) return null;
  return arr4(p>=0.90?Math.min(p,p-0.01):p);
}
/* CONFRONTATION CORNERS — miroir exact de modeles_secondaires.confrontation :
   D = corners(home) − corners(away) par convolution de binomiales négatives,
   échelle d'handicaps relative à la dominante + calibration de production. */
function confrontationCornersJS(div,h,a,sec){
  sec=sec||((DATA.moteur[div]||{}).secondaires); if(!sec||!sec.base) return null;
  const E=sec.equipes||{};
  if(!E[h]||!E[a]||sec.base.corners==null) return null;
  const eh=E[h].corners_em, rh=E[h].corners_rc, ea=E[a].corners_em, ra=E[a].corners_rc;
  if([eh,rh,ea,ra].some(v=>typeof v!=='number'||!isFinite(v))) return null;
  const base=sec.base.corners, disp=sec.base.corners_dispersion||1.18;
  const lh=Math.min(Math.max(base*eh*ra,0.05),60), la=Math.min(Math.max(base*ea*rh,0.05),60);
  const KMAX=40;
  const ph=pmfMarche(lh,disp,KMAX), pa=pmfMarche(la,disp,KMAX);
  const dist=new Array(2*KMAX+1).fill(0);
  for(let i=0;i<=KMAX;i++)for(let j=0;j<=KMAX;j++) dist[i-j+KMAX]+=ph[i]*pa[j];
  const domHome=lh>=la;
  const queue=t=>{ let s2=0;
    if(domHome){for(let k=KMAX+t;k<=2*KMAX;k++)s2+=dist[k];}
    else{for(let k=0;k<=KMAX-t;k++)s2+=dist[k];}
    return s2; };
  const pNul=dist[KMAX], pVict=queue(1);
  const ech={'+2':queue(-1),'+1':queue(0),'victoire':pVict,'-1':queue(2),'-2':queue(3),'-3':queue(4),'-4':queue(5)};
  const echelle={}; for(const k in ech) echelle[k]=arr4(Math.min(Math.max(ech[k],0),1));
  const lamD=domHome?lh:la, lamF=domHome?la:lh;
  const cf={lambda_home:arr2(lh),lambda_away:arr2(la),dom:domHome?'home':'away',
    partage_dom:arr4(lamD/Math.max(lamD+lamF,1e-9)),p_vict_dom:arr4(pVict),
    p_nul:arr4(pNul),p_vict_autre:arr4(Math.max(0,1-pVict-pNul)),echelle};
  cf.echelle_cal={}; for(const k in echelle) cf.echelle_cal[k]=cornCalibrer(k,echelle[k]);
  return cf;
}

/* pronostic complet d'une confrontation — même structure que le serveur Python */
/* FATIGUE EUROPÉENNE — miroir exact de fatigue.coeffs_match (Python) :
   dernier match de C1/C2/C3 joué dans la fenêtre (7 j) avant le match,
   multiplicateurs mesurés par seau de repos, appliqués dans le sens de la
   fatigue uniquement. Retourne null sans effet. */
function fatigueCoeffsJS(h,a,dateMatch){
  const F=DATA.fatigue;
  if(!F||!F.bareme||!dateMatch) return null;
  const dm=Date.parse(dateMatch+"T12:00:00Z");
  if(isNaN(dm)) return null;
  const dernier=(eq)=>{
    const lst=(F.equipes||{})[eq]; if(!lst) return null;
    let best=null;
    for(const x of lst){
      if(x[2]!==1) continue;                     // joué seulement
      const dc=Date.parse(x[0]+"T12:00:00Z"); if(isNaN(dc)) continue;
      const delta=Math.round((dm-dc)/86400000);
      if(delta>=0&&delta<=F.fenetre){ if(!best||x[0]>best[0]) best=[x[0],x[1],delta]; }
    }
    return best;
  };
  const info={}; let mh=1, ma=1;
  const roles=[[h,'home'],[a,'away']];
  for(const rl of roles){
    const eq=rl[0], role=rl[1];
    const d=dernier(eq); if(!d) continue;
    const cel=F.bareme[String(Math.max(d[2],1))]; if(!cel) continue;
    if(role==='home'){ mh*=cel.f_att; ma*=cel.f_def; }
    else             { ma*=cel.f_att; mh*=cel.f_def; }
    info[role]={equipe:eq,comp:d[1],comp_nom:(F.noms||{})[d[1]]||d[1],
      date_coupe:d[0],repos_j:d[2],f_att:cel.f_att,f_def:cel.f_def,n:cel.n};
  }
  if(!info.home&&!info.away) return null;
  mh=Math.round(Math.min(Math.max(mh,0.7),1.4)*1e4)/1e4;
  ma=Math.round(Math.min(Math.max(ma,0.7),1.4)*1e4)/1e4;
  if(mh===1&&ma===1) return null;
  return {mh:mh,ma:ma,info:{home:info.home||null,away:info.away||null}};
}

function pronosticJS(div,h,a){
  let L=DATA.moteur[div]; if(!L) return null;
  let coupeInter=false;
  if(L.coupe){
    /* coupe : paramètres empruntés aux divisions domestiques (miroir exact de
       serveur.matrice_scores + coupes.parametres). Même division = modèle du
       championnat ; divisions différentes = approximation inter-ligues. */
    const idx=DATA.index_equipes||{};
    const dh=idx[h],da=idx[a];
    if(!dh||!da) return null;
    const Lh=DATA.moteur[dh],La=DATA.moteur[da];
    if(!Lh||!La) return null;
    if(dh===da){
      if(!(Lh.forces||{})[h]||!(Lh.forces||{})[a]) return null;
      L=Lh;
    }else{
      if(!(Lh.forces||{})[h]||!(La.forces||{})[a]) return null;
      coupeInter=true;
      const fQ={};fQ[h]=Lh.forces[h];fQ[a]=La.forces[a];
      L={forces:fQ,gamma:(Lh.gamma+La.gamma)/2,s_away:(Lh.s_away+La.s_away)/2,
         rho:(Lh.rho+La.rho)/2,coupe:true};
    }
  }
  let fat=null,ab=null;
  if(!L.coupe){
    const fxb=(DATA.fixturesBrutes||[]).find(x=>x.div===div&&x.home===h&&x.away===a);
    fat=fatigueCoeffsJS(h,a,fxb?fxb.date:null);
    /* ÉTAPE ④ — compositions H−1 : même source que serveur (export compos).
       Coefficients appliqués seulement si mesurés (sinon info seule). */
    if(fxb&&fxb.date) ab=((DATA.absences||{}).matchs||{})[div+"|"+fxb.date+"|"+h+"|"+a]||null;
  }
  let mh=fat?fat.mh:null, ma=fat?fat.ma:null;
  if(ab&&ab.mh!=null){
    mh=Math.round(Math.min(Math.max((mh==null?1:mh)*ab.mh,0.7),1.4)*1e4)/1e4;
    ma=Math.round(Math.min(Math.max((ma==null?1:ma)*ab.ma,0.7),1.4)*1e4)/1e4;
  }
  const r=matriceScores(L,h,a,mh,ma); if(!r) return null;
  const M=r.M, lam=r.lam, mu=r.mu;
  let tri=0,dg=0;
  for(let i=0;i<=MAXG;i++)for(let j=0;j<=MAXG;j++){
    if(i>j) tri+=M[i][j];
    if(i===j) dg+=M[i][j];
  }
  const cases=[];
  for(let i=0;i<=MAXG;i++)for(let j=0;j<=MAXG;j++) cases.push([i,j,M[i][j]]);
  cases.sort((x,y)=>y[2]-x[2]);
  const top=cases.slice(0,6);
  const sommeSi=(f)=>{let s=0;for(let i=0;i<=MAXG;i++)for(let j=0;j<=MAXG;j++)if(f(i,j))s+=M[i][j];return s;};
  const out={ligue:div,home:h,away:a,
    lambda_home:arr3(lam),lambda_away:arr3(mu),buts_attendus:arr2(lam+mu),
    victoire_1:arr4(tri),nul:arr4(dg),victoire_2:arr4(1-tri-dg),
    double_chance_1X:arr4(tri+dg),double_chance_12:arr4(1-dg),double_chance_X2:arr4(1-tri),
    over:{},under:{},
    btts_oui:arr4(sommeSi((i,j)=>i>=1&&j>=1)),
    btts_non:arr4(sommeSi((i,j)=>i===0||j===0)),
    score_fleuve_5plus:arr4(sommeSi((i,j)=>i+j>=5)),
    score_fleuve_6plus:arr4(sommeSi((i,j)=>i+j>=6)),
    eclat_3plus:arr4(sommeSi((i,j)=>Math.abs(i-j)>=3)),
    eclat_4plus:arr4(sommeSi((i,j)=>Math.abs(i-j)>=4)),
    serie2:arr4(pSerie2(lam,mu)),serie3:arr4(pSerie(lam,mu,3)),
    serie2_dom:arr4(pSerie2Dom(lam,mu)),serie2_ext:arr4(pSerie2Ext(lam,mu)),
    serie3_dom:arr4(pSerie3Dom(lam,mu)),serie3_ext:arr4(pSerie3Ext(lam,mu)),
    clean_sheet_home:arr4(sommeSi((i,j)=>j===0)),
    clean_sheet_away:arr4(sommeSi((i,j)=>i===0)),
    scores_top:top.map(t=>({score:t[0]+'-'+t[1],p:arr4(t[2])})),
    matrice:(()=>{const m=[];for(let i=0;i<8;i++){m.push([]);for(let j=0;j<8;j++)m[i].push(arr4(M[i][j]));}return m;})(),
  };
  [0.5,1.5,2.5,3.5,4.5,5.5].forEach(x=>{
    out.over[String(x)]=arr4(sommeSi((i,j)=>i+j>x));
    out.under[String(x)]=arr4(sommeSi((i,j)=>i+j<x));
  });
  /* fiabilité : pour une COUPE, les forces viennent d'ailleurs — comme côté
     Python (DB["ligues"][lig].forces vide), n_eff = 0 → confiance « faible »,
     plus un drapeau inter_ligues pour l'avertissement du panneau. */
  const Lf=DATA.moteur[div];
  const fh=(Lf.coupe?{}:(Lf.forces||{})[h])||{}, fa=(Lf.coupe?{}:(Lf.forces||{})[a])||{};
  const ne_h=fh.n_eff||0, ne_a=fa.n_eff||0, nb_h=fh.n_brut||0, nb_a=fa.n_brut||0;
  const mini=Math.min(ne_h,ne_a);
  const conf=mini>=40?'haute':mini>=20?'moyenne':'faible';
  out.fiabilite={confiance:conf,n_eff_home:arr2(ne_h),n_eff_away:arr2(ne_a),
    n_brut_home:nb_h,n_brut_away:nb_a};
  if(Lf.coupe) out.fiabilite.inter_ligues=coupeInter;
  if(fat) out.fatigue=fat.info;
  if(ab) out.absences={home:ab.home,away:ab.away};
  /* confrontation au marché si des cotes existent pour ce match */
  for(const m of (DATA.matchs||[])){
    if(m.div===div&&m.home===h&&m.away===a){
      out.marche={victoire_1:m.p1,nul:m.pX,victoire_2:m.p2,
        cote_1:m.cote_1,cote_X:m.cote_X,cote_2:m.cote_2,cote_max_1:m.cote_meilleur,
        cote_over:m.cote_over,cote_under:m.cote_under,
        ecart_1:arr4(out.victoire_1-(m.p1||0)),ecart_X:arr4(out.nul-(m.pX||0)),
        ecart_2:arr4(out.victoire_2-(m.p2||0)),date:m.date,heure:m.heure};
      out.arbitre=m.arbitre||null;
      break;
    }
  }
  const sec=secondairesJS(div,h,a,out.arbitre);
  if(sec) out.secondaires=sec;
  return out;
}

/* Sélection conseillée : même formule que le serveur Python (parité garantie). */
/* Mêmes marges que le serveur Python : les unders sont durcis car le modèle
   les surestime (queues trop fines sur les matchs à 4-5 buts). Mesuré sur le
   suivi réel (58 % de réussite aux unders vs 92 % aux overs) et sur les
   fréquences historiques co.uk 2023-2026. */
const MARGES_MARCHE={"under 3.5":0.13,"under 2.5":0.05,"under 1.5":0.02};

function joursWeekendJS(auj){
  /* vendredi, samedi, dimanche du week-end courant (ou à venir si lun-jeu).
     Miroir exact de serveur._jours_weekend : lundi=0 … dimanche=6. */
  const wd=(auj.getDay()+6)%7;
  const j0=new Date(auj.getFullYear(),auj.getMonth(),auj.getDate());
  let ven;
  if(wd<=3) ven=new Date(j0.getFullYear(),j0.getMonth(),j0.getDate()+(4-wd));
  else if(wd===4) ven=j0;
  else ven=new Date(j0.getFullYear(),j0.getMonth(),j0.getDate()-(wd-4));
  const p=n=>String(n).padStart(2,"0");
  const iso=d=>d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());
  return [0,1,2].map(i=>iso(new Date(ven.getFullYear(),ven.getMonth(),ven.getDate()+i)));
}

function combinaisonsJS(sels,seuil,poolRisque){
  /* RÈGLE UTILISATEUR 07/09 — parité serveur.py _combinaisons : les divisions
     instables (2es/3es échelons, surestime mesurée 4-8 pts) n'entrent dans
     AUCUN combiné sous 90 %. (Bug du 11/09/2026 : le site proposait une
     cote 5 avec 5 jambes instables à 78-84 % que l'archive refusait.) */
  const DIVS_INST=new Set(["E1","E2","E3","SP2","I2","D2","F2","SC1","SC2","SC3"]);
  sels=sels.filter(x=>!DIVS_INST.has(x.div)||x.p>=0.90);
  poolRisque=(poolRisque||[]).filter(x=>!DIVS_INST.has(x.div)||x.p>=0.90);
  const auj=new Date();
  const p=n=>String(n).padStart(2,"0");
  const aujIso=auj.getFullYear()+"-"+p(auj.getMonth()+1)+"-"+p(auj.getDate());
  function cmp(a,b){return a<b?-1:a>b?1:0;}
  function construire(pool_,cle,miniP,maxLegs){
    maxLegs=maxLegs||3;
    let legs=[];
    for(const diversifie of [true,false]){
      legs=[];const vus=new Set(),ligues=new Set();
      const tri=pool_.slice().sort((a,b)=>((b[cle]||0)-(a[cle]||0))||(b.p-a.p)||
        cmp(a.date,b.date)||cmp(a.home,b.home)||cmp(a.away,b.away));
      for(const s of tri){
        if(legs.length>=maxLegs)break;
        if(!((s[cle]||0)>0)||s.p<miniP)continue;
        const mid=s.date+"|"+s.home+"|"+s.away;
        if(vus.has(mid)||(diversifie&&ligues.has(s.ligue)))continue;
        legs.push(s);vus.add(mid);ligues.add(s.ligue);
      }
      if(legs.length>=2)break;
    }
    return legs;
  }
  function finaliser(legs,parJour){
    if(!legs.length)return null;
    let pr_=1,cote=1,toutes=true;
    for(const s of legs){pr_*=s.p;if(s.cote_marche)cote*=s.cote_marche;else toutes=false;}
    const out={legs:legs,p_combine:+pr_.toFixed(4),cote_combine:toutes?+cote.toFixed(2):null,
      cote_juste_combine:pr_>0?+(1/pr_).toFixed(2):null};
    if(parJour)out.par_jour=parJour;
    return out;
  }
  function construireCible(pool_,cMin,cMax,maxLegs,pAsc){
    /* combiné « à cote cible » : idem serveur.py _combinaisons.construire_cible.
       cote jambe = cote marché sinon cote juste (1/p). Jamais forcé : null si
       la cible minimale n'est pas atteinte dans la limite de jambes. */
    const tri=pool_.slice().sort(pAsc
      ?((a,b)=>(a.p-b.p)||cmp(a.date,b.date)||cmp(a.home,b.home)||cmp(a.away,b.away))
      :((a,b)=>(b.p-a.p)||cmp(a.date,b.date)||cmp(a.home,b.home)||cmp(a.away,b.away)));
    const legs=[],vus=new Set();let prod=1,nM=0,nJ=0;
    for(const s of tri){
      if(legs.length>=maxLegs||prod>=cMin)break;
      const cl=s.cote_marche||s.cote_juste;
      if(!cl||cl<=1.0)continue;
      const mid=s.date+"|"+s.home+"|"+s.away;
      if(vus.has(mid)||prod*cl>cMax)continue;
      legs.push(s);vus.add(mid);prod*=cl;
      if(s.cote_marche)nM++;else nJ++;
    }
    if(!legs.length||prod<cMin)return null;
    let pr_=1;for(const s of legs)pr_*=s.p;
    return {legs:legs,p_combine:+pr_.toFixed(4),cote_combine:+prod.toFixed(2),
      cote_juste_combine:pr_>0?+(1/pr_).toFixed(2):null,
      cote_type:nJ===0?"marché":nM===0?"juste":"mixte",cible:[cMin,cMax]};
  }
  /* SAFE DU JOUR : aujourd'hui UNIQUEMENT, 1 à 3 jambes, jamais le lendemain */
  const safe=finaliser(construire(sels.filter(s=>s.date===aujIso),"p",seuil));
  /* SAFE WEEK-END : ven+sam+dim, 3 maximum par jour, 9 au total */
  const jw=joursWeekendJS(auj);
  let legsW=[];const parJour={};
  for(const d of jw){
    const ld=construire(sels.filter(s=>s.date===d),"p",seuil);
    parJour[d]=ld.length;
    legsW=legsW.concat(ld);
  }
  const safeWeekend=finaliser(legsW,parJour);
  /* RISQUE : aujourd'hui+demain, options cotées, jambes des SAFE exclues */
  const exclus=new Set(legsW.map(l=>l.date+"|"+l.home+"|"+l.away));
  if(safe)for(const l of safe.legs)exclus.add(l.date+"|"+l.home+"|"+l.away);
  const pr=(poolRisque||[]).filter(s=>!exclus.has(s.date+"|"+s.home+"|"+s.away));
  const lr=construire(pr,"cote_marche",0.55);
  /* COTE 2 / COTE 5 / FUN DU JOUR : aujourd'hui uniquement, SAFE exclu */
  const exj=new Set(safe?safe.legs.map(l=>l.date+"|"+l.home+"|"+l.away):[]);
  const pj=sels.filter(s=>s.date===aujIso&&!exj.has(s.date+"|"+s.home+"|"+s.away));
  return {safe:safe,safe_weekend:safeWeekend,risque:lr.length>=2?finaliser(lr):null,
    cote2:construireCible(pj,1.90,2.35,10,false),
    cote5:construireCible(pj,4.60,5.90,10,false),
    fun:construireCible(pj,20.0,50.0,15,true)};
}

function conseilsJS(seuil){
  const jours={};
  const poolRisque=[];
  /* Parité serveur.py api_conseils : divisions instables → conseils ≥ 85 % */
  const DIVS_INST=new Set(["E1","E2","E3","SP2","I2","D2","F2","SC1","SC2","SC3"]);
  /* heure de Cotonou (UTC+1) : jamais de conseil pour un match déjà commencé */
  const nowC=new Date(Date.now()+3600000).toISOString().slice(0,16);
  for(const m of DATA.matchs){
    if(!m.disponible||!m.over) continue;
    if(m.coupe) continue;   /* coupes : jamais dans les sélections suivies */
    if(m.heure&&m.date&&(m.date+"T"+m.heure)<nowC) continue;
    const o=m.over,u=m.under,dc=m.double_chance||{};
    const base={div:m.div,ligue:m.ligue,pays:m.pays,date:m.date,heure:m.heure,
      jour:m.jour,jour_delta:m.jour_delta,home:m.home,away:m.away,
      confiance:m.confiance,buts:m.buts,cotes_source:m.source_cotes};
    if((m.jour_delta==null?9:m.jour_delta)<=1){
      const oc=[["1",m.p1,m.cote_1],["X",m.pX,m.cote_X],["2",m.p2,m.cote_2],
        ["over 2.5",o["2.5"],m.cote_over],["under 2.5",u["2.5"],m.cote_under]];
      let bq=null;
      for(const c of oc){
        if(!c[2]||c[1]==null) continue;
        if(c[1]<(c[0]==="under 2.5"?0.65:0.55)) continue;
        if(!bq||c[1]>bq[1]) bq=c;
      }
      if(bq) poolRisque.push(Object.assign({},base,{option:bq[0],p:+bq[1].toFixed(4),
        cote_juste:bq[1]>0?+(1/bq[1]).toFixed(2):null,cote_marche:bq[2]}));
    }
    const cands=[["1",m.p1],["X",m.pX],["2",m.p2],
      ["over 1.5",o["1.5"]],["over 2.5",o["2.5"]],["over 3.5",o["3.5"]],
      ["under 1.5",u["1.5"]],["under 2.5",u["2.5"]],["under 3.5",u["3.5"]],
      ["les deux marquent",m.btts],
      ["les deux ne marquent pas",m.btts!=null?+(1-m.btts).toFixed(4):null],
      ["double chance 1X",dc["1X"]],["double chance 12",dc["12"]],["double chance X2",dc["X2"]]]
      .filter(c=>c[1]!=null);
    let opt=cands[0],best=cands[0];
    for(const c of cands) if(c[1]>best[1]) best=c;
    opt=best;
    const pl=DIVS_INST.has(m.div)?0.85:0;
    if(opt[1]<Math.max(seuil,pl)+(MARGES_MARCHE[opt[0]]||0)-1e-9) continue;
    const item=Object.assign({},base,{option:opt[0],p:+opt[1].toFixed(4),
      cote_juste:opt[1]>0?+(1/opt[1]).toFixed(2):null});
    if(opt[0]==="1")item.cote_marche=m.cote_1;
    else if(opt[0]==="X")item.cote_marche=m.cote_X;
    else if(opt[0]==="2")item.cote_marche=m.cote_2;
    else if(opt[0]==="over 2.5")item.cote_marche=m.cote_over;
    else if(opt[0]==="under 2.5")item.cote_marche=m.cote_under;
    (jours[m.jour_delta]=jours[m.jour_delta]||[]).push(item);
  }
  const liste=Object.keys(jours).map(Number).sort((a,b)=>a-b).map(d=>{
    const sel=jours[d].sort((a,b)=>b.p-a.p);
    return {jour:sel[0].jour,jour_delta:d,date:sel[0].date,nb:sel.length,selections:sel};
  });
  const aPlat=[];for(const j of liste)for(const s of j.selections)aPlat.push(s);
  return {seuil:seuil,jours:liste,combines:combinaisonsJS(aPlat,seuil,poolRisque),
    note:"Probabilités du moteur : pour les 5 grandes ligues (Angleterre, Espagne, Italie, Allemagne, France), les forces des équipes sont estimées sur les xG RÉELS d'Understat puis recalées sur les buts observés — gain validé par un test A/B en walk-forward sur 7 118 matchs (2022-2026). Ailleurs : Dixon-Coles sur les buts réels. Ensemble calibré sur 29 295 matchs. "+
         "Une option à 75 % se réalise environ 3 fois sur 4 en moyenne, "+
         "pas à chaque fois. Les unders sont DURCIS (marge exigée au-dessus "+
         "du seuil) : le suivi réel et les fréquences historiques montrent "+
         "que le modèle les surestime — il sous-estime les matchs à 4-5 buts. "+
         "Rentabilité face aux cotes non démontrée (voir l'onglet Fiabilité)."};
}

/* ---------------------------------------------------------------------------
   api() LOCAL : remplace les appels au serveur par un calcul sur place.
   L'interface est inchangée, seul ce point d'entrée diffère.
   --------------------------------------------------------------------------- */
async function api(p){
  const [chemin,qs]=String(p).split('?');
  const q=new URLSearchParams(qs||'');
  const g=k=>q.get(k)||'';
  switch(chemin){
    case '/api/ligues':   return DATA.ligues;
    case '/api/matchs':   return DATA.matchs;
    case '/api/conseils': return conseilsJS(parseFloat(q.get('seuil')||'0.75'));
    case '/api/refresh':
    case '/api/maj':
      return {impossible:true,
        message:"Version web / autonome : les données sont embarquées dans le fichier, "+
                "un navigateur ne peut pas ré-entraîner le modèle. La mise à jour est "+
                "faite par GitHub (toutes les heures, automatiquement). Pour "+
                "forcer maintenant : onglet Actions du dépôt → Run workflow (2 clics, "+
                "connecté à ton compte), puis recharge cette page."};
    case '/api/bilan':    return DATA.bilan;
    case '/api/corners':  return DATA.corners_cal;
    case '/api/suivi':    return DATA.suivi;
    case '/api/classement': return DATA.classements[g('div')]||null;
    case '/api/fleuves':  return DATA.fleuves[g('div')]||null;
    case '/api/pronostic':{
      const r=pronosticJS(g('div'),decodeURIComponent(g('home')),decodeURIComponent(g('away')));
      if(!r) throw new Error(p);
      return r;
    }
    case '/api/secondaires':{
      const r=secondairesJS(g('div'),decodeURIComponent(g('home')),decodeURIComponent(g('away')),g('arbitre')||null);
      if(!r) throw new Error(p);
      return r;
    }
    default: throw new Error('route inconnue : '+chemin);
  }
}
"""


# --------------------------------------------------------------------------- 3
def generer(data):
    print("→ assemblage du fichier autonome...")
    html = (RACINE / "static/index.html").read_text(encoding="utf-8")

    # la fonction api() d'origine interroge le serveur : on la retire
    ancienne = "async function api(p){const r=await fetch(p);if(!r.ok)throw new Error(p);return r.json();}"
    assert ancienne in html, "la fonction api() d'origine est introuvable"
    html = html.replace(ancienne, "/* api() est fournie par le moteur autonome ci-dessous */", 1)

    # injection des données + du moteur, juste après <script>
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    bandeau = (
        "\n/* =====================================================================\n"
        "   APPLICATION AUTONOME — données et moteur embarqués dans ce fichier.\n"
        "   Aucun serveur, aucune connexion internet, aucune installation.\n"
        "   Générée par genere_app.py le " + data["meta"].get("genere_le", "?")[:10] + "\n"
        "   ===================================================================== */\n"
        "const DATA = " + payload + ";\n" + MOTEUR_JS + "\n"
    )
    html = html.replace("<script>", "<script>" + bandeau, 1)

    # l'entête doit signaler que c'est la version hors-ligne
    html = html.replace("<title>Pronos Foot — moteur Dixon-Coles</title>",
                        "<title>Pronos Foot — version autonome hors-ligne</title>", 1)

    SORTIE.write_text(html, encoding="utf-8")
    taille = SORTIE.stat().st_size / 1024
    print(f"   {SORTIE.name} : {taille:,.0f} Ko")
    return SORTIE


if __name__ == "__main__":
    d = precalculer()
    # les fixtures brutes servent à retrouver l'arbitre dans le moteur JS
    d["fixturesBrutes"] = [{"div": f["div"], "home": f["home"], "away": f["away"],
                            "arbitre": f.get("arbitre"), "date": f.get("date")}
                           for f in S.DB.get("fixtures", [])]
    generer(d)
    print("\n→ Vérification : ouvrir le fichier dans un navigateur, ou lancer")
    print("   node test_app_autonome.js pour valider la parité avec le serveur.")
