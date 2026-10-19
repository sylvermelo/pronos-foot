/* Vue partagée robot/vitrine. Générée en ligne par sync_buteurs_ui.py.
   Aucun appel réseau, aucun changement des probabilités ou de l'archivage. */
function buteursChoix(data, filtre, now=Date.now()) {
  const jour=new Date(now+3600000).toISOString().slice(0,10);
  const demain=new Date(now+3600000+86400000).toISOString().slice(0,10);
  const min=Number(filtre.min),max=Number(filtre.max);
  if(filtre.min===''||filtre.max===''||!Number.isFinite(min)||!Number.isFinite(max)||min<0||max>100||min>max)return {erreur:'Choisis un minimum inférieur ou égal au maximum, entre 0 et 100.',lignes:[]};
  const lignes=[],vus=new Set();
  for(const m of (data&&data.matchs)||[]){
    const debut=Date.parse(m.debut_utc);
    if(!Number.isFinite(debut)||debut<=now)continue;
    if(filtre.jour==='auj'&&m.date!==jour)continue;
    if(filtre.jour==='demain'&&m.date!==demain)continue;
    if(filtre.confirmes&&!m.composition_confirmee)continue;
    for(const p of m.joueurs||[]){
      const a=p.analyse;if(!a||!Number.isFinite(a.p)||a.p<0||a.p>1)continue;
      if(a.p*100+1e-9<min||a.p*100-1e-9>max)continue;
      const id=m.event_id+'|'+p.id;if(vus.has(id))continue;vus.add(id);
      const q=p.cotation,age=q?now-Date.parse(q.last_update):NaN;
      const prix=q&&q.bookmaker&&q.event_id&&Number.isFinite(q.price)&&q.price>1&&age>=0&&age<=86400000&&Date.parse(q.commence_time)===debut?q:null;
      lignes.push({m,p,a,prix});
    }
  }
  lignes.sort((x,y)=>(y.a.p-x.a.p)||(Number(y.m.composition_confirmee)-Number(x.m.composition_confirmee))||(Date.parse(x.m.debut_utc)-Date.parse(y.m.debut_utc))||x.p.nom.localeCompare(y.p.nom));
  return {lignes,erreur:null};
}
function buteursConseilsHTML(data,filtre) {
  const e=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=p=>(p*100).toFixed(1).replace('.',',')+' %';
  const {lignes,erreur}=buteursChoix(data,filtre),limit=filtre.limite||12;
  const cards=lignes.slice(0,limit).map(({m,p,a,prix},i)=>{
    const initials=p.nom.trim().split(/\s+/).map(x=>x[0]).slice(0,2).join('');
    const confirme=m.composition_confirmee;
    return `<article class="bc-card ${i===0?'bc-first':''}">
      <div class="bc-cardtop"><span class="bc-rank">#${i+1} ${i===0?'· En tête de ta sélection':''}</span><span class="bc-status ${confirme?'bc-ok':''}">${confirme?'Titulaire confirmé':'Titularisation à confirmer'}</span></div>
      <div class="bc-player"><div class="bc-avatar" aria-hidden="true">${e(initials)}</div><div class="bc-name"><h3>${e(p.nom)}</h3><span>${e(p.equipe)}</span></div><div class="bc-score"><b>${fmt(a.p)}</b><span>chance de marquer*</span></div></div>
      <div class="bc-track" aria-hidden="true"><span style="width:${Math.max(0,Math.min(100,a.p*100))}%"></span></div>
      <div class="bc-fixture"><span>${e(m.home)} <span class="bc-muted">vs</span> ${e(m.away)}</span><b>${e(m.date.slice(8,10)+'/'+m.date.slice(5,7))} · ${e(m.heure||'Horaire à confirmer')}</b></div>
      <p class="bc-advice">${confirme?'À examiner en priorité dans cette plage : il figure dans le onze annoncé.':'À surveiller : vérifie sa présence dans le onze avant de retenir ce profil.'}</p>
      <div class="bc-bottom"><span>${a.buts} buts · ${a.matchs} matchs observés</span><span>${prix?'Cote '+Number(prix.price).toFixed(2)+' · '+e(prix.bookmaker_nom||prix.bookmaker)+' (US)':'Analyse sans cote disponible'}</span></div>
      <details class="bc-detail"><summary>Pourquoi ce profil ?</summary><p>Le modèle croise son rythme de buts avec une référence à son poste et ses minutes jouées. En cas de titularisation, son historique représente ${e(a.minutes_si_titulaire)} minutes en moyenne. Son rang compare uniquement les profils de ta sélection ; il ne démontre pas la rentabilité du pari.</p></details>
    </article>`;
  }).join('');
  const h=data&&data.historique||{},ev=data&&data.evaluation||{},t=ev.test||{};
  const plages=[['Tout',0,100],['20–40 %',20,40],['40–60 %',40,60],['60–100 %',60,100]];
  return `<style>
    .bc{--bc-line:rgba(150,170,195,.19);--bc-muted:#a2afc1;--bc-accent:#6fe2be;color:inherit;font-family:inherit;max-width:1200px;margin:auto}.bc *{box-sizing:border-box}.bc-hero{padding:26px;border:1px solid var(--bc-line);border-radius:22px;background:radial-gradient(ellipse at 95% 0%,rgba(65,174,140,.18),transparent 65%),#101923;margin-bottom:18px}.bc-kicker{color:var(--bc-accent);font-size:11px;letter-spacing:.15em;text-transform:uppercase;font-weight:750}.bc h2{font-size:clamp(25px,4vw,36px);letter-spacing:-.04em;margin:10px 0;color:#f5f7fb}.bc-hero p{max-width:620px;color:var(--bc-muted);font-size:14px;line-height:1.7;margin:0}.bc-controls{padding:18px;border:1px solid var(--bc-line);border-radius:18px;background:#111923;margin-bottom:18px}.bc-controlrow{display:flex;flex-wrap:wrap;gap:14px;align-items:end}.bc label{font-size:12px;color:var(--bc-muted);display:flex;flex-direction:column;gap:7px}.bc input[type=number],.bc select{border:1px solid var(--bc-line);background:#0b121b;color:#f5f7fb;border-radius:10px;min-height:44px;padding:9px 12px;font:inherit;max-width:100%}.bc input[type=number]{width:94px}.bc select{min-width:150px}.bc button{cursor:pointer;font:inherit}.bc input:focus-visible,.bc select:focus-visible,.bc button:focus-visible,.bc summary:focus-visible{outline:2px solid var(--bc-accent);outline-offset:3px}.bc .bc-check{flex-direction:row;align-items:center;gap:8px;min-height:44px}.bc-check input{accent-color:#6fe2be;width:18px;height:18px}.bc-range{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.bc-chip{border:1px solid var(--bc-line);background:transparent;color:var(--bc-muted);border-radius:30px;padding:9px 14px;min-height:40px;font-size:12px}.bc-chip.on{color:#081a14;background:var(--bc-accent);border-color:var(--bc-accent);font-weight:700}.bc-results{display:flex;align-items:center;justify-content:space-between;gap:15px;margin:22px 2px 12px}.bc-results b{font-size:16px}.bc-results span{color:var(--bc-muted);font-size:12px}.bc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr));gap:14px}.bc-card{min-width:0;border:1px solid var(--bc-line);border-radius:18px;padding:20px;background:#111923}.bc-first{border-color:rgba(111,226,190,.48);background:linear-gradient(150deg,rgba(41,98,79,.22),transparent 65%),#111923}.bc-cardtop{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:19px;font-size:10px}.bc-rank{font-weight:700;color:var(--bc-accent)}.bc-status{background:rgba(241,189,90,.09);border-radius:6px;color:#e0be80;padding:5px 7px}.bc-status.bc-ok{color:var(--bc-accent);background:rgba(111,226,190,.08)}.bc-player{display:flex;gap:12px;align-items:center}.bc-avatar{width:44px;height:44px;flex-shrink:0;display:grid;place-items:center;border-radius:14px;background:rgba(111,226,190,.1);color:var(--bc-accent);font-weight:750}.bc-name{flex:1;min-width:0}.bc-name h3{color:#f5f7fb;font-size:18px;margin:0 0 5px;font-weight:750;overflow-wrap:anywhere}.bc-name>span{font-size:12px;color:var(--bc-muted)}.bc-score{text-align:right;flex-shrink:0}.bc-score b{color:var(--bc-accent);font-size:25px;letter-spacing:-.04em;display:block}.bc-score>span{display:block;font-size:9px;color:var(--bc-muted);margin-top:4px}.bc-track{height:4px;border-radius:4px;background:rgba(255,255,255,.07);overflow:hidden;margin:18px 0}.bc-track>span{display:block;height:100%;border-radius:4px;background:var(--bc-accent)}.bc-fixture{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;color:#d9e0e9;font-size:12px}.bc-fixture b{font-size:11px;color:var(--bc-muted);font-weight:500}.bc-muted{color:var(--bc-muted)}.bc-advice{font-size:12px;line-height:1.65;color:#d0d9e6;margin:14px 0}.bc-bottom{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;color:var(--bc-muted);font-size:10px;padding-top:12px;border-top:1px solid var(--bc-line)}.bc-detail{font-size:11px;color:var(--bc-muted);margin-top:13px}.bc-detail summary{cursor:pointer;min-height:24px}.bc-detail p{line-height:1.8}.bc-empty{border:1px dashed var(--bc-line);border-radius:18px;text-align:center;padding:35px 20px}.bc-empty b{display:block;font-size:17px;color:#e0e8f2;margin-bottom:10px}.bc-empty p{font-size:13px;line-height:1.7;color:var(--bc-muted);max-width:520px;margin:0 auto 18px}.bc-more{display:block;margin:20px auto;border:1px solid var(--bc-line);background:#14241f;color:var(--bc-accent);padding:12px 24px;border-radius:12px;min-height:44px}.bc-foot{font-size:11px;color:var(--bc-muted);line-height:1.8;margin:22px 2px}.bc-method{border-top:1px solid var(--bc-line);padding-top:15px}.bc-method summary{cursor:pointer;font-size:12px;color:#c9d5e4;min-height:32px}.bc-method p{font-size:12px;line-height:1.8;color:var(--bc-muted)}@media(max-width:700px){.bc-grid{grid-template-columns:1fr}.bc-hero{padding:21px}.bc-card{padding:16px}.bc-controls{padding:14px}.bc-name h3{font-size:16px}.bc-score b{font-size:23px}.bc-controlrow{gap:10px}.bc-results{align-items:start}.bc-results span{max-width:140px;text-align:right}.bc-cardtop{font-size:9px}.bc-avatar{width:38px;height:38px}.bc-hero p{font-size:13px}}
    </style><section class="bc">
    <div class="bc-hero"><span class="bc-kicker">LES PROFILS À SUIVRE</span><h2>Trouve ton buteur.</h2><p>Choisis ta plage de probabilité. Le bot classe les profils du plus probable au moins probable et t’indique ceux dont la titularisation reste à vérifier.</p></div>
    <div class="bc-controls" aria-label="Filtrer les conseils buteurs"><div class="bc-controlrow">
      <label>Quand ?<select data-bc="jour"><option value="auj" ${filtre.jour==='auj'?'selected':''}>Aujourd’hui</option><option value="demain" ${filtre.jour==='demain'?'selected':''}>Demain</option><option value="tous" ${filtre.jour==='tous'?'selected':''}>Tous les matchs à venir</option></select></label>
      <label>De (%)<input data-bc="min" type="number" min="0" max="100" step="1" value="${e(filtre.min)}" inputmode="numeric"></label>
      <label>À (%)<input data-bc="max" type="number" min="0" max="100" step="1" value="${e(filtre.max)}" inputmode="numeric"></label>
      <button type="button" class="bc-chip on" data-bc-apply>Appliquer la plage</button>
      <label class="bc-check"><input data-bc="confirmes" type="checkbox" ${filtre.confirmes?'checked':''}>Titulaires confirmés seulement</label></div>
      <div class="bc-range">${plages.map(([label,min,max])=>`<button type="button" class="bc-chip ${Number(filtre.min)===min&&Number(filtre.max)===max?'on':''}" data-bc-range="${min},${max}" aria-pressed="${Number(filtre.min)===min&&Number(filtre.max)===max}">${label}</button>`).join('')}</div></div>
    <div class="bc-results" aria-live="polite"><b>${lignes.length} profil${lignes.length>1?'s':''} ${erreur?'':`entre ${e(filtre.min)} et ${e(filtre.max)} %`}</b><span>Probabilité décroissante ↓</span></div>
    ${cards?`<div class="bc-grid">${cards}</div>`:`<div class="bc-empty"><b>${erreur?'Plage à corriger':'Aucun profil dans cette sélection'}</b><p>${e(erreur||'Aucun joueur ne remplit tes filtres parmi les matchs encore à venir. Tu peux consulter une autre plage ou un autre jour ; le bot ne modifie pas ses estimations pour remplir la liste.')}</p>${erreur?'':'<button type="button" class="bc-chip" data-bc-reset>Voir tous les profils à venir</button>'}</div>`}
    ${lignes.length>limit?`<button type="button" class="bc-more" data-bc-more>Voir ${Math.min(12,lignes.length-limit)} profils de plus</button>`:''}
    <p class="bc-foot">* Estimation si le joueur est titulaire. Un pourcentage élevé ne garantit pas un but. ${data?'':'Données en cours de chargement.'} Les cotes affichées, quand elles existent, sont des prix bookmaker reçus.</p>
    <details class="bc-method"><summary>Comment le bot fait sa sélection</summary><p>Il retient les joueurs avec un historique suffisant et les classe par probabilité de marquer au moins une fois. Le filtre ne change pas les probabilités. ${h.matchs||0} matchs et ${h.joueurs||0} joueurs observés. ${t.n||0} prévisions évaluées sur ${t.matchs||0} matchs. ${ev.statut==='validation_initiale'?'Le modèle dispose d’une validation initiale ; sa rentabilité reste à établir.':'Le modèle est encore en cours d’évaluation ; sa rentabilité n’est pas établie.'} L’adversaire et le rôle sur penalties ne sont pas ajustés séparément dans cette version.</p></details></section>`;
}
function buteursConseilsBind(root,filtre,refresh){
  root.querySelectorAll('[data-bc]').forEach(el=>el.addEventListener('change',()=>{
    const k=el.dataset.bc;filtre[k]=el.type==='checkbox'?el.checked:el.value;filtre.limite=12;if(k!=='min'&&k!=='max')refresh();
  }));
  root.querySelectorAll('[data-bc-apply]').forEach(el=>el.addEventListener('click',()=>{filtre.limite=12;refresh();}));
  root.querySelectorAll('[data-bc-range]').forEach(el=>el.addEventListener('click',()=>{
    const [min,max]=el.dataset.bcRange.split(',').map(Number);Object.assign(filtre,{min,max,limite:12});refresh();
  }));
  root.querySelectorAll('[data-bc-more]').forEach(el=>el.addEventListener('click',()=>{filtre.limite=(filtre.limite||12)+12;refresh();}));
  root.querySelectorAll('[data-bc-reset]').forEach(el=>el.addEventListener('click',()=>{Object.assign(filtre,{min:0,max:100,jour:'tous',confirmes:false,limite:12});refresh();}));
}
