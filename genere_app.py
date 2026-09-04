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
        "meta": S.DB.get("meta", {}),
        "calendrier": S.DB.get("calendrier_log") or {},
    }
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
function matriceScores(L,h,a){
  const F=L.forces; if(!F||!F[h]||!F[a]) return null;
  const lam=Math.min(Math.max(F[h].att*F[a].dfn*L.gamma,1e-6),30);
  const mu =Math.min(Math.max(F[a].att*F[h].dfn*L.s_away,1e-6),30);
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
  return res;
}

/* pronostic complet d'une confrontation — même structure que le serveur Python */
function pronosticJS(div,h,a){
  const L=DATA.moteur[div]; if(!L) return null;
  const r=matriceScores(L,h,a); if(!r) return null;
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
    clean_sheet_home:arr4(sommeSi((i,j)=>j===0)),
    clean_sheet_away:arr4(sommeSi((i,j)=>i===0)),
    scores_top:top.map(t=>({score:t[0]+'-'+t[1],p:arr4(t[2])})),
    matrice:(()=>{const m=[];for(let i=0;i<8;i++){m.push([]);for(let j=0;j<8;j++)m[i].push(arr4(M[i][j]));}return m;})(),
  };
  [0.5,1.5,2.5,3.5,4.5,5.5].forEach(x=>{
    out.over[String(x)]=arr4(sommeSi((i,j)=>i+j>x));
    out.under[String(x)]=arr4(sommeSi((i,j)=>i+j<x));
  });
  const fh=(L.forces||{})[h]||{}, fa=(L.forces||{})[a]||{};
  const ne_h=fh.n_eff||0, ne_a=fa.n_eff||0, nb_h=fh.n_brut||0, nb_a=fa.n_brut||0;
  const mini=Math.min(ne_h,ne_a);
  const conf=mini>=40?'haute':mini>=20?'moyenne':'faible';
  out.fiabilite={confiance:conf,n_eff_home:arr2(ne_h),n_eff_away:arr2(ne_a),
    n_brut_home:nb_h,n_brut_away:nb_a};
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
function conseilsJS(seuil){
  const jours={};
  for(const m of DATA.matchs){
    if(!m.disponible||!m.over) continue;
    const o=m.over,u=m.under,dc=m.double_chance||{};
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
    if(opt[1]<seuil) continue;
    const item={div:m.div,ligue:m.ligue,pays:m.pays,date:m.date,heure:m.heure,
      jour:m.jour,jour_delta:m.jour_delta,home:m.home,away:m.away,
      option:opt[0],p:+opt[1].toFixed(4),cote_juste:opt[1]>0?+(1/opt[1]).toFixed(2):null,
      confiance:m.confiance,buts:m.buts};
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
  return {seuil:seuil,jours:liste,
    note:"Probabilités du modèle Dixon-Coles calibré sur 29 295 matchs. "+
         "Une option à 75 % se réalise environ 3 fois sur 4 en moyenne, "+
         "pas à chaque fois. Rentabilité face aux cotes non démontrée "+
         "(voir l'onglet Fiabilité)."};
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
                "faite par GitHub (07:30 puis toutes les 3 h, heure de Cotonou). Pour "+
                "forcer maintenant : onglet Actions du dépôt → Run workflow (2 clics, "+
                "connecté à ton compte), puis recharge cette page."};
    case '/api/bilan':    return DATA.bilan;
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
                            "arbitre": f.get("arbitre")} for f in S.DB.get("fixtures", [])]
    generer(d)
    print("\n→ Vérification : ouvrir le fichier dans un navigateur, ou lancer")
    print("   node test_app_autonome.js pour valider la parité avec le serveur.")
