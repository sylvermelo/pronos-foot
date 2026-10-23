"""Synchronise les vues hockey/Europe dans les deux interfaces."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
js=(root/'ui/multisport.js').read_text()
robot='''
const HOCKEY_FILTRE={min:50,max:100,day:'tous',market:'ml',sort:'desc',limit:12};
let HOCKEY_DATA=null,EUROPE_DATA=null,EUROPE_COMP='toutes';
function hockeyRefresh(){if(ETAT.onglet!=='hockey')return;const r=$("#main");r.innerHTML=hockeyHTML(HOCKEY_DATA,HOCKEY_FILTRE);hockeyBind(r,HOCKEY_FILTRE,hockeyRefresh);}
function tabHockey(){hockeyRefresh();return api('/api/hockey').then(d=>{HOCKEY_DATA=d;hockeyRefresh();}).catch(()=>{if(ETAT.onglet==='hockey')$("#main").innerHTML='<div class="empty">Analyse hockey momentanément indisponible.</div>';});}
function europeRefresh(comp){if(ETAT.onglet!=='europe')return;if(comp)EUROPE_COMP=comp;const r=$("#main");r.innerHTML=europeHTML(EUROPE_DATA,EUROPE_COMP);europeBind(r,europeRefresh);}
function tabEurope(){europeRefresh();return api('/api/europe').then(d=>{EUROPE_DATA=d;europeRefresh();}).catch(()=>{if(ETAT.onglet==='europe')$("#main").innerHTML='<div class="empty">Calendrier européen momentanément indisponible.</div>';});}
'''
vitrine='''
const HOCKEY_FILTRE={min:50,max:100,day:'tous',market:'ml',sort:'desc',limit:12};
async function pageHockey(){const data=await chargeJson(ROBOT_BASE+'/hockey_jour.json');const r=document.getElementById('z-contenu');if(!r)return;const render=()=>{r.innerHTML=hockeyHTML(data,HOCKEY_FILTRE);hockeyBind(r,HOCKEY_FILTRE,render);};render();}
async function pageEurope(){const data=await chargeJson(ROBOT_BASE+'/europe_jour.json');const r=document.getElementById('z-contenu');if(!r)return;const render=(comp='toutes')=>{r.innerHTML=europeHTML(data,comp);europeBind(r,render);};render();}
'''
for path,anchor,wrapper in [(root/'static/index.html','async function init(){',robot),(root.parent/'vitrine/docs/assets/app.js','  const ICONES =',vitrine)]:
 s=path.read_text()
 if '/* MULTISPORT_INTEGRATION_BEGIN */' in s:
  a=s.index('/* MULTISPORT_INTEGRATION_BEGIN */');b=s.index('/* MULTISPORT_INTEGRATION_END */',a)+len('/* MULTISPORT_INTEGRATION_END */');s=s[:a]+s[b:]
 s=s.replace(anchor,'/* MULTISPORT_INTEGRATION_BEGIN */\n'+js+'\n'+wrapper+'\n/* MULTISPORT_INTEGRATION_END */\n'+anchor,1)
 path.write_text(s)
