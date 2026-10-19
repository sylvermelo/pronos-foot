const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('ui/buteurs-conseils.js','utf8');
const ctx=vm.createContext({console,Date,Set,Number,Math});vm.runInContext(source,ctx);
const now=Date.parse('2030-01-01T12:00:00Z');
const player=(id,p)=>({id,nom:id,equipe:'Club',analyse:{p,buts:5,matchs:10,minutes_si_titulaire:75}});
const match=(id,date,ps,confirmed=false)=>({event_id:id,home:'Club',away:'Autre',date,heure:'20:00',debut_utc:date+'T19:00:00Z',composition_confirmee:confirmed,joueurs:ps});
const data={matchs:[match('a','2030-01-01',[player('Low',.3),player('High',.6)]),match('b','2030-01-01',[player('Middle',.45)],true),match('c','2030-01-02',[player('Tomorrow',.7)])]};
const f={min:30,max:60,jour:'auj',confirmes:false,limite:12};
let result=ctx.buteursChoix(data,f,now);
assert.deepStrictEqual(Array.from(result.lignes,x=>x.p.nom),['High','Middle','Low']);
assert.strictEqual(ctx.buteursChoix(data,{...f,confirmes:true},now).lignes[0].p.nom,'Middle');
assert.strictEqual(ctx.buteursChoix(data,{...f,min:0,max:100,jour:'demain'},now).lignes[0].p.nom,'Tomorrow');
assert.strictEqual(ctx.buteursChoix(data,{...f,min:70,max:60},now).lignes.length,0);
assert(ctx.buteursChoix(data,{...f,min:70,max:60},now).erreur);
assert(ctx.buteursChoix(data,{...f,min:''},now).erreur);
assert.strictEqual(ctx.buteursChoix(data,{...f,min:80,max:100},now).lignes.length,0);
const stale={...data,matchs:[{...data.matchs[0],debut_utc:'2029-12-31T19:00:00Z'}]};
assert.strictEqual(ctx.buteursChoix(stale,f,now).lignes.length,0);
const unknown=JSON.parse(JSON.stringify(data));unknown.matchs[0].joueurs.push({id:'missing',nom:'Manquant',analyse:null});
assert.strictEqual(ctx.buteursChoix(unknown,f,now).lignes.length,3);
// Le filtre ne modifie jamais les données source.
assert.strictEqual(data.matchs[0].joueurs[0].analyse.p,.3);
const elements=[{dataset:{bc:'min'},type:'number',value:'40'},{dataset:{bcRange:'40,60'}}];
for(const el of elements)el.addEventListener=(type,fn)=>{el.click=fn;};
const root={querySelectorAll(sel){return sel==='[data-bc]'?[elements[0]]:sel==='[data-bc-range]'?[elements[1]]:[];}};
let refreshed=0;ctx.buteursConseilsBind(root,f,()=>refreshed++);elements[0].click();assert.strictEqual(f.min,'40');elements[1].click();assert.strictEqual(f.max,60);assert.strictEqual(refreshed,2);
for(const file of ['static/index.html','../vitrine/docs/assets/app.js']){
 if(!fs.existsSync(file)&&file.startsWith('../vitrine/'))continue;
 const built=fs.readFileSync(file,'utf8');assert(built.includes(source),file+' : la vue canonique doit être synchronisée');
}
console.log('Buteurs : plage inclusive, tri global, jour, titulaires, reprise des filtres et vues synchronisées OK');
