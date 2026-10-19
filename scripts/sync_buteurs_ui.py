"""Recopie la vue canonique dans les deux interfaces sans dépendance réseau."""
from pathlib import Path
import argparse
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--vitrine',type=Path,default=root.parent/'vitrine')
args=parser.parse_args()
js=(root/'ui/buteurs-conseils.js').read_text()
marker='/* Vue partagée robot/vitrine.'
p=root/'static/index.html';s=p.read_text()
a=s.index(marker) if marker in s else s.index('function tabButeurs(){')
b=s.index('function tabSeries(){',a)
s=s[:a]+js+'''
const BUTEURS_FILTRE={min:20,max:100,jour:'auj',confirmes:false,limite:12};
let BUTEURS_DONNEES=null;
function buteursRafraichir(){
  const root=$("#main");root.innerHTML=buteursConseilsHTML(BUTEURS_DONNEES,BUTEURS_FILTRE);
  buteursConseilsBind(root,BUTEURS_FILTRE,buteursRafraichir);
}
function tabButeurs(){
  if(BUTEURS_DONNEES)buteursRafraichir();
  else $("#main").innerHTML='<div class="empty">Le bot prépare les profils buteurs…</div>';
  return api('/api/buteurs').then(data=>{BUTEURS_DONNEES=data;if(ETAT.onglet==='buteurs')buteursRafraichir();})
    .catch(()=>{if(ETAT.onglet==='buteurs'&&!BUTEURS_DONNEES)$("#main").innerHTML='<div class="empty">Conseils temporairement indisponibles. Réessaie après la prochaine mise à jour.</div>';});
}

''' +s[b:];p.write_text(s)
p=args.vitrine/'docs/assets/app.js'
if p.exists():
 s=p.read_text();a=s.index(marker) if marker in s else s.index('  function renduButeurs(B)')
 b=s.index('  function pageSelections(D)',a)
 s=s[:a]+js+'''
  const BUTEURS_FILTRE={min:20,max:100,jour:'auj',confirmes:false,limite:12};
  function renduButeurs(B){
    if(!B)return '<div class="card"><div class="small mut">Le bot prépare les profils buteurs…</div></div>';
    return buteursConseilsHTML(B,BUTEURS_FILTRE);
  }

''' +s[b:];p.write_text(s)
