/**
 * Vérification de PARITÉ : le moteur JavaScript embarqué dans le fichier
 * autonome doit produire exactement les mêmes chiffres que le serveur Python.
 *
 * Sans ce test, l'application hors-ligne pourrait afficher des résultats
 * différents de la version serveur sans que personne ne s'en aperçoive.
 *
 * Usage : node test_app_autonome.js   (le serveur doit tourner sur le port 8000)
 */
const fs = require('fs');
const vm = require('vm');

const BASE = 'http://127.0.0.1:8000';
const FICHIER = __dirname + '/pronos-foot-autonome.html';

let erreurs = 0, avertissements = 0;
const ok  = (m) => console.log('  \x1b[32mOK\x1b[0m   ' + m);
const ko  = (m) => { erreurs++; console.log('  \x1b[31mECHEC\x1b[0m ' + m); };
const warn= (m) => { avertissements++; console.log('  \x1b[33m!!\x1b[0m     ' + m); };

if (!fs.existsSync(FICHIER)) {
  console.log('\x1b[31mFichier autonome introuvable. Lance d\'abord : python3 genere_app.py\x1b[0m');
  process.exit(1);
}
const html = fs.readFileSync(FICHIER, 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

/* ---------------------------------------------------- DOM simulé */
function mkEl(sel) {
  return { _sel: sel, _h: '', textContent: '', value: '', checked: false, dataset: {},
    style: {}, disabled: false,
    classList: { _s:new Set(), add(...c){c.forEach(x=>this._s.add(x))},
      remove(...c){c.forEach(x=>this._s.delete(x))},
      toggle(c,f){f===undefined?(this._s.has(c)?this._s.delete(c):this._s.add(c)):(f?this._s.add(c):this._s.delete(c))},
      contains(c){return this._s.has(c)} },
    appendChild(){}, remove(){}, setAttribute(){}, getAttribute(){return null},
    addEventListener(){}, focus(){}, click(){},
    set innerHTML(v){ this._h=v; const m=/<option[^>]*value="([^"]*)"/.exec(v||'');
      if(m && /<select|<option/.test(v)) this.value=m[1]; },
    get innerHTML(){ return this._h||'' },
    querySelector(){ return mkEl(sel+'>q'); }, querySelectorAll(){ return []; } };
}
const elements = new Map();
const document = { title:'', body: mkEl('body'),
  querySelector:(s)=>{ if(!elements.has(s)) elements.set(s, mkEl(s)); return elements.get(s); },
  querySelectorAll:()=>[], createElement:(t)=>mkEl('<'+t+'>'),
  addEventListener(){}, getElementById:(i)=>document.querySelector('#'+i) };

const sandbox = { document, console,
  localStorage:{_d:{},getItem(k){return this._d[k]??null},setItem(k,v){this._d[k]=String(v)},removeItem(k){delete this._d[k]}},
  fetch:(u,o)=>fetch(u.startsWith('http')?u:BASE+u,o),
  setTimeout, clearTimeout, setInterval, clearInterval, URL, URLSearchParams,
  performance:{now:()=>Date.now()}, encodeURIComponent, decodeURIComponent, TextEncoder, TextDecoder,
  Math, JSON, Date, Number, String, Array, Object, Map, Set, isNaN, parseInt,
  parseFloat, Promise, Error, RegExp, Intl, window:{}, navigator:{language:'fr-FR'}, alert:()=>{} };
sandbox.window = sandbox; sandbox.globalThis = sandbox;

console.log('\n=== 1. Le fichier autonome se charge-t-il sans serveur ? ===');
let ctx;
try {
  ctx = vm.createContext(sandbox);
  vm.runInContext(script, ctx, { timeout: 15000 });
  ok(`script exécuté (${(script.length/1024).toFixed(0)} Ko de code embarqué)`);
} catch (e) {
  ko('erreur au chargement : ' + e.message);
  console.log('     ' + (e.stack||'').split('\n').slice(1,4).join('\n     '));
  process.exit(1);
}

/* aucune dépendance réseau ne doit subsister */
const resteFetch = (script.match(/\bfetch\s*\(/g) || []).length;
resteFetch === 0 ? ok('aucun appel réseau dans le code embarqué (fetch absent)')
                 : warn(`${resteFetch} appel(s) fetch subsistent — vérifier`);

const evalJS = (code) => vm.runInContext(code, ctx, { timeout: 30000 });

(async () => {
  /* ---------------- 2. parité du moteur sur des matchs réels ---------------- */
  console.log('\n=== 2. Parité moteur JS ⟷ serveur Python ===');
  const matchs = await (await fetch(BASE + '/api/matchs')).json();
  const echantillon = matchs.filter(m => m.disponible).slice(0, 25);
  console.log(`    ${echantillon.length} matchs comparés champ par champ`);

  let nChamps = 0, nEcart = 0, pire = 0, pireCas = '';
  const CHAMPS_NUM = ['lambda_home','lambda_away','buts_attendus','victoire_1','nul','victoire_2',
    'double_chance_1X','double_chance_12','double_chance_X2','btts_oui','btts_non',
    'score_fleuve_5plus','score_fleuve_6plus','eclat_3plus','eclat_4plus',
    'clean_sheet_home','clean_sheet_away'];

  for (const m of echantillon) {
    const url = `/api/pronostic?div=${m.div}&home=${encodeURIComponent(m.home)}&away=${encodeURIComponent(m.away)}`;
    const py = await (await fetch(BASE + url)).json();
    sandbox.globalThis.__d = m.div; sandbox.globalThis.__h = m.home; sandbox.globalThis.__a = m.away;
    const js = evalJS('pronosticJS(globalThis.__d, globalThis.__h, globalThis.__a)');
    if (!js) { ko(`JS n'a pas su calculer ${m.home} vs ${m.away}`); continue; }

    for (const c of CHAMPS_NUM) {
      if (py[c] == null || js[c] == null) continue;
      nChamps++;
      const e = Math.abs(py[c] - js[c]);
      if (e > pire) { pire = e; pireCas = `${m.home}-${m.away}.${c} (py ${py[c]} / js ${js[c]})`; }
      if (e > 0.0011) { nEcart++; if (nEcart <= 3) warn(`écart ${c} : ${m.home} vs ${m.away} → py ${py[c]} / js ${js[c]}`); }
    }
    /* marchés Over/Under */
    for (const s of Object.keys(py.over || {})) {
      nChamps++;
      const e = Math.abs((py.over[s]||0) - (js.over[s]||0));
      if (e > pire) { pire = e; pireCas = `over${s} ${m.home}-${m.away}`; }
      if (e > 0.0011) nEcart++;
    }
    /* matrice des scores */
    for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) {
      nChamps++;
      const e = Math.abs(py.matrice[i][j] - js.matrice[i][j]);
      if (e > pire) { pire = e; pireCas = `matrice[${i}][${j}] ${m.home}-${m.away}`; }
      if (e > 0.0011) nEcart++;
    }
    /* scores les plus probables */
    const topPy = (py.scores_top||[]).map(x=>x.score).join(',');
    const topJs = (js.scores_top||[]).map(x=>x.score).join(',');
    nChamps++;
    if (topPy !== topJs) { nEcart++; warn(`scores probables différents : ${m.home} vs ${m.away}\n         py ${topPy}\n         js ${topJs}`); }
  }
  if (nEcart === 0) ok(`${nChamps} valeurs comparées, aucune divergence`);
  else ko(`${nEcart} divergence(s) sur ${nChamps} valeurs — pire écart ${pire.toExponential(2)} (${pireCas})`);
  if (nEcart === 0) console.log(`    plus grand écart observé : ${pire.toExponential(2)} (arrondi d'affichage)`);

  /* ---------------- 3. parité des marchés secondaires ---------------- */
  console.log('\n=== 3. Parité fautes / corners / cartons ===');
  let nSec = 0, nSecEcart = 0, pireSec = 0;
  for (const m of echantillon.slice(0, 15)) {
    if (!m.sec) continue;
    sandbox.globalThis.__d = m.div; sandbox.globalThis.__h = m.home; sandbox.globalThis.__a = m.away;
    const js = evalJS('secondairesJS(globalThis.__d, globalThis.__h, globalThis.__a, null)');
    if (!js) { warn(`secondaires JS indisponibles pour ${m.home} vs ${m.away}`); continue; }
    for (const mk of ['fautes','corners','jaunes']) {
      const py = m.sec[mk], jsv = js.marches[mk] ? js.marches[mk].total_attendu : null;
      if (py == null || jsv == null) continue;
      nSec++;
      const e = Math.abs(py - jsv);
      if (e > pireSec) pireSec = e;
      if (e > 0.011) { nSecEcart++; warn(`${mk} ${m.home} vs ${m.away} : py ${py} / js ${jsv}`); }
    }
  }
  if (nSec && nSecEcart === 0) ok(`${nSec} totaux secondaires comparés, écart max ${pireSec.toFixed(4)}`);
  else if (nSec) ko(`${nSecEcart} divergence(s) sur ${nSec} totaux secondaires`);
  else warn('aucun marché secondaire à comparer dans l\'échantillon');

  /* ---------------- 4. les 7 onglets s'affichent-ils hors-ligne ? ---------------- */
  console.log('\n=== 4. Rendu des 10 onglets en mode autonome ===');
  await new Promise(r => setTimeout(r, 3500));   // laisse init() terminer ses chargements
  for (const id of ['matchs','conseils','suivi','coupon','sim','fleuves','sec','corners','classement','bilan']) {
    try {
      elements.clear();
      evalJS(`ETAT.onglet=${JSON.stringify(id)};rendu();`);
      await new Promise(r => setTimeout(r, 1500));
      // le DOM simule n'a pas de parente : on concatene les zones connues
      const c = (elements.get('#main')?.innerHTML||'')
              + (elements.get('#cWrap')?.innerHTML||'')
              + (elements.get('#panel')?.innerHTML||'')
              + (elements.get('#fatwrap')?.innerHTML||'')
              + (elements.get('#consWrap')?.innerHTML||'')
              + (elements.get('#suiviWrap')?.innerHTML||'');
      const nan = /NaN|undefined/.test(c);
      if (nan) ko(`onglet ${id} : contient NaN ou undefined`);
      else if (c.length > 400) ok(`onglet ${id} : ${c.length.toLocaleString('fr-FR')} caracteres`);
      else ko(`onglet ${id} : contenu trop court (${c.length})`);
    } catch (e) { ko(`onglet ${id} : ${e.message}`); }
  }

  /* ---------------- 5. le simulateur accepte-t-il une confrontation libre ? ---------------- */
  console.log('\n=== 5. Simulateur : confrontation libre (jamais pré-calculée) ===');
  try {
    const div = evalJS('Object.keys(DATA.moteur)[0]');
    const eq = evalJS(`DATA.moteur[${JSON.stringify(div)}].equipes_actuelles`);
    if (eq && eq.length >= 2) {
      const [h, a] = [eq[0], eq[eq.length - 1]];
      sandbox.globalThis.__d = div; sandbox.globalThis.__h = h; sandbox.globalThis.__a = a;
      const r = evalJS('pronosticJS(globalThis.__d, globalThis.__h, globalThis.__a)');
      if (r && r.victoire_1 > 0) {
        const s = r.victoire_1 + r.nul + r.victoire_2;
        if (Math.abs(s - 1) < 0.01) ok(`${div} : ${h} vs ${a} → 1:${(r.victoire_1*100).toFixed(1)}% X:${(r.nul*100).toFixed(1)}% 2:${(r.victoire_2*100).toFixed(1)}% (somme ${(s*100).toFixed(1)} %)`);
        else ko(`les probabilités ne somment pas à 1 : ${s}`);
      } else ko('pronosticJS a échoué sur une confrontation libre');
    } else warn('aucune liste d\'équipes disponible pour tester');
  } catch (e) { ko('test simulateur : ' + e.message); }

  /* ---------------- 6. corners : parité confrontation + coupon montante ---------------- */
  console.log('\n=== 6. Onglet Corners : parité confrontation ⟷ serveur + coupon ===');
  try {
    let nCorn = 0, nCornEcart = 0, pireCorn = 0;
    for (const m of echantillon.slice(0, 12)) {
      if (!m.sec || !m.sec.confrontation) continue;
      sandbox.globalThis.__d = m.div; sandbox.globalThis.__h = m.home; sandbox.globalThis.__a = m.away;
      const js = evalJS('secondairesJS(globalThis.__d, globalThis.__h, globalThis.__a, null)');
      if (!js || !js.confrontation) { warn('confrontation JS absente pour ' + m.home + ' vs ' + m.away); continue; }
      const py = m.sec.confrontation;
      const paires = [['lambda_home', py.lambda_home, js.confrontation.lambda_home],
        ['lambda_away', py.lambda_away, js.confrontation.lambda_away],
        ['partage_dom', py.partage_dom, js.confrontation.partage_dom],
        ['p_vict_dom', py.p_vict_dom, js.confrontation.p_vict_dom]];
      for (const f of ['+2','+1','victoire','-1','-2','-3','-4']) {
        paires.push(['echelle' + f, (py.echelle||{})[f], (js.confrontation.echelle||{})[f]]);
        paires.push(['echelle_cal' + f, (py.echelle_cal||{})[f], (js.confrontation.echelle_cal||{})[f]]);
      }
      for (const [nom, a, b] of paires) {
        if (a == null || b == null) { if (a != null || b != null) { nCornEcart++; warn(nom + ' ' + m.home + ' : py ' + a + ' / js ' + b); } continue; }
        nCorn++;
        const e = Math.abs(a - b);
        if (e > pireCorn) pireCorn = e;
        if (e > 0.011) { nCornEcart++; if (nCornEcart <= 3) warn(nom + ' ' + m.home + ' vs ' + m.away + ' : py ' + a + ' / js ' + b); }
      }
    }
    if (nCorn && nCornEcart === 0) ok(nCorn + ' valeurs corners comparées, écart max ' + pireCorn.toFixed(4));
    else if (nCorn) ko(nCornEcart + ' divergence(s) sur ' + nCorn + ' valeurs corners');
    else warn('aucune confrontation à comparer dans l\'échantillon');

    /* cohérence du coupon montante : plancher, tri horaire, produit des cotes */
    const cp = evalJS(`(function(){
      const nowC=new Date(Date.now()+3600000).toISOString().slice(0,16);
      const ms=ETAT.matchs.filter(m=>m.disponible&&!m.coupe&&m.sec&&m.sec.confrontation&&m.date&&m.date>=nowC.slice(0,10)&&!(m.heure&&(m.date+"T"+m.heure)<nowC));
      const parJour={}; for(const m of ms)(parJour[m.date]=parJour[m.date]||[]).push(m);
      const jours=Object.keys(parJour).sort();
      let tous={etapes:[],coteTot:1,pTot:1,miseFin:1};
      for(const d of jours){ const c=cornCoupon(parJour[d],CORN_PLANCHER); if(c.etapes.length>tous.etapes.length||d===jours[0]) tous=c; tous.jour=tous.jour||d; }
      const d0=jours[0]; return {jours:jours.length,cp:cornCoupon(parJour[d0]||[],CORN_PLANCHER),d0:d0};
    })()`);
    if (cp && cp.jours >= 0) {
      const e = cp.cp.etapes;
      let probs = 0;
      for (const L of e) if (L.c.pc < CORN_PLANCHER - 1e-9) probs++;
      let triOk = true;
      for (let i = 1; i < e.length; i++) {
        const k = x => (x.m.date + 'T' + (x.m.heure || '99:99'));
        if (k(e[i-1]) > k(e[i])) triOk = false;
      }
      const prod = e.reduce((a, L) => a * L.c.pc, 1);
      const prodOk = e.length === 0 || Math.abs(prod - cp.cp.pTot) < 1e-9;
      const cotOk = e.length === 0 || Math.abs(e.reduce((a, L) => a * L.c.cote, 1) - cp.cp.coteTot) < 1e-9;
      if (probs === 0 && triOk && prodOk && cotOk)
        ok('coupon ' + (cp.d0 || '?') + ' : ' + e.length + ' maillon(s), plancher respecté, tri horaire, cote totale ' + cp.cp.coteTot.toFixed(2));
      else ko('coupon incohérent : plancher=' + probs + ' tri=' + triOk + ' produit=' + prodOk + ' cote=' + cotOk);
    } else warn('coupon non évaluable (fenêtre calendrier vide)');
  } catch (err) { ko('test corners : ' + err.message); }

  console.log(`\n${'='.repeat(62)}`);
  if (erreurs === 0)
    console.log(`\x1b[32mFICHIER AUTONOME VALIDÉ\x1b[0m — identique au serveur (${avertissements} avertissement(s))`);
  else
    console.log(`\x1b[31m${erreurs} PROBLÈME(S)\x1b[0m — le fichier autonome diverge du serveur`);
  console.log('='.repeat(62) + '\n');
  process.exit(erreurs ? 1 : 0);
})();
