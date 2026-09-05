/**
 * Harnais de test v2 — interface « Quant Edge Terminal ».
 * Exécute réellement le script de static/index.html dans un DOM simulé,
 * avec de VRAIS appels HTTP vers le serveur local (port 8000).
 *
 * Objectif : attraper les erreurs d'exécution (TypeError, NaN, undefined…)
 * que `node --check` ne voit pas, onglet par onglet.
 *
 * Usage : node test_interface.js
 */
const fs = require('fs');
const vm = require('vm');

const BASE = 'http://127.0.0.1:8000';
const HTML = fs.readFileSync(__dirname + '/static/index.html', 'utf8');
const script = HTML.match(/<script>([\s\S]*?)<\/script>/)[1];

let erreurs = 0;
const ok = m => console.log('  \x1b[32mOK\x1b[0m   ' + m);
const ko = m => { erreurs++; console.log('  \x1b[31mECHEC\x1b[0m ' + m); };
const attendre = ms => new Promise(r => setTimeout(r, ms));

/* ------------------------------------------------- DOM simulé */
const elements = new Map();
function mkEl(sel) {
  return {
    _sel: sel, _h: '', textContent: '', value: '', checked: false,
    dataset: {}, style: {}, disabled: false, hidden: false,
    classList: { _s: new Set(),
      add(...c){c.forEach(x=>this._s.add(x))}, remove(...c){c.forEach(x=>this._s.delete(x))},
      toggle(c,f){f===undefined?(this._s.has(c)?this._s.delete(c):this._s.add(c)):(f?this._s.add(c):this._s.delete(c))},
      contains(c){return this._s.has(c)} },
    appendChild(){}, removeChild(){}, remove(){}, setAttribute(){}, getAttribute(){return null},
    set innerHTML(v){ this._h = v || ''; },
    get innerHTML(){ return this._h || ''; },
    addEventListener(){}, focus(){}, click(){}, scrollIntoView(){},
    querySelector(){ return mkEl(this._sel + ' >q'); },
    querySelectorAll(){ return []; },
  };
}
const document = {
  title: '', body: mkEl('body'),
  querySelector: s => { if (!elements.has(s)) elements.set(s, mkEl(s)); return elements.get(s); },
  querySelectorAll: () => [],
  createElement: t => mkEl('<' + t + '>'),
  addEventListener(){}, getElementById: i => document.querySelector('#' + i),
};

const sandbox = {
  document, console,
  fetch: (u, o) => fetch(u.startsWith('http') ? u : BASE + u, o),
  setTimeout, clearTimeout, setInterval, clearInterval,
  performance: { now: () => Date.now() },
  URL, URLSearchParams, TextEncoder, TextDecoder,
  window: {}, navigator: { language: 'fr-FR' },
  alert: () => {}, Math, JSON, Date, Number, String, Array, Object, Map, Set,
  isNaN, parseInt, parseFloat, Promise, Error, RegExp, Intl, encodeURIComponent, decodeURIComponent,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

const propre = t => !/NaN|undefined/.test(t || '');

(async () => {
  console.log('\n=== 1. Chargement & init() ===');
  let ctx;
  try {
    ctx = vm.createContext(sandbox);
    vm.runInContext(script, ctx, { timeout: 15000 });
    ok('script exécuté sans erreur au chargement');
  } catch (e) {
    ko('erreur au chargement : ' + e.message);
    console.log('     ' + (e.stack || '').split('\n').slice(1, 4).join('\n     '));
    process.exit(1);
  }
  await attendre(4000);   // laisse init() finir ses 3 appels réseau
  const etat = vm.runInContext('ETAT', ctx);
  if (etat.matchs.length >= 0 && etat.ligues.length > 0) ok(`init : ${etat.ligues.length} ligues, ${etat.matchs.length} matchs à venir`);
  else ko('init : données non chargées');
  const aucunPasse = etat.matchs.every(m => m.date >= new Date().toISOString().slice(0, 10));
  aucunPasse ? ok('aucun match passé dans la liste') : ko('DES MATCHS PASSÉS SUBSISTENT');
  const ouComplet = etat.matchs.every(m => !m.disponible || (m.over && m.over['1.5'] != null && m.under && m.under['1.5'] != null));
  ouComplet ? ok('over/under 1.5+ présents dans chaque match') : ko('over/under 1.5+ manquants');

  /* --- chaque onglet --- */
  console.log('\n=== 2. Rendu des 9 onglets ===');
  for (const id of ['matchs', 'conseils', 'suivi', 'coupon', 'sim', 'fleuves', 'sec', 'classement', 'bilan']) {
    try {
      elements.clear();
      vm.runInContext(`ETAT.onglet=${JSON.stringify(id)};rendu();`, ctx, { timeout: 30000 });
      await attendre(3000);
      // le DOM simulé n'a pas de parenté : on concatene les zones connues
      const html = (elements.get('#main') ? elements.get('#main').innerHTML : '')
        + (elements.get('#cWrap') ? elements.get('#cWrap').innerHTML : '')
        + (elements.get('#panel') ? elements.get('#panel').innerHTML : '')
        + (elements.get('#consWrap') ? elements.get('#consWrap').innerHTML : '')
        + (elements.get('#suiviWrap') ? elements.get('#suiviWrap').innerHTML : '');
      const nav = elements.get('#nav') ? elements.get('#nav').innerHTML : '';
      const lignes = (html.match(/<tr/g) || []).length;
      if (!propre(html))            ko(`onglet ${id} : contient NaN ou undefined`);
      else if (html.length < 400)   ko(`onglet ${id} : contenu trop court (${html.length})`);
      else ok(`onglet ${id} : ${html.length} caractères, ${lignes} lignes, nav ${nav.length > 0 ? 'ok' : 'vide'}`);
    } catch (e) {
      ko(`onglet ${id} a levé une exception : ${e.message}`);
      console.log('     ' + (e.stack || '').split('\n').slice(1, 3).join('\n     '));
    }
  }

  /* --- panneau détail (clic sur un match) --- */
  console.log('\n=== 3. Panneau « anatomie » d\'un match (toutes les options) ===');
  try {
    const m = etat.matchs.find(x => x.disponible) || { div: 'E0', home: 'Arsenal', away: 'Chelsea' };
    elements.clear();
    elements.set('#panel', mkEl('#panel'));
    sandbox.globalThis.__s = { id: m.div + '|' + m.home + '|' + m.away, div: m.div, home: m.home, away: m.away };
    await vm.runInContext('(async()=>{ await chargerPanneau(globalThis.__s); })()', ctx, { timeout: 30000 });
    const h = elements.get('#panel').innerHTML;
    [[ 'over/under de 0.5 à 5.5',   /0\.5 but/.test(h) && /5\.5 buts/.test(h)],
     [ 'double chance',             /Double chance/.test(h)],
     [ 'clean sheets',              /Clean sheet/.test(h)],
     [ 'scores exacts probables',   /Scores exacts les plus probables/.test(h)],
     [ 'fautes / corners / jaunes', /Fautes, corners, cartons/.test(h)],
     [ 'indice de confiance',       /Confiance/.test(h)],
     [ 'avertissement honnête',     /backtest|ROI/i.test(h)],
     [ 'boutons coupon',            /Ajouter Over 2\.5/.test(h)],
     [ 'aucun NaN',                 propre(h)],
    ].forEach(([l, v]) => v ? ok(l) : ko(l));
    console.log(`     taille du panneau : ${h.length} caractères`);
  } catch (e) {
    ko('chargerPanneau a levé une exception : ' + e.message);
  }

  /* --- graphique fat-tail --- */
  console.log('\n=== 4. Graphique fat-tail (DC τ vs Poisson naïf) ===');
  try {
    elements.set('#fatwrap', mkEl('#fatwrap'));
    const m = etat.matchs.find(x => x.disponible);
    if (m) {
      sandbox.globalThis.__m = m;
      await vm.runInContext('(async()=>{ await grapheFatTail(globalThis.__m); })()', ctx, { timeout: 30000 });
      const h = elements.get('#fatwrap').innerHTML;
      [[ 'svg rendu',            /<svg/.test(h)],
       [ 'zone fleuve marquée',  /ZONE FLEUVE/.test(h)],
       [ 'queue épaisse 5+',     /Queue épaisse/.test(h)],
       [ 'rappel du ROI réel',   /ROI/.test(h)],
       [ 'aucun NaN',            propre(h)],
      ].forEach(([l, v]) => v ? ok(l) : ko(l));
    } else ok('aucun match disponible : test sauté proprement');
  } catch (e) { ko('grapheFatTail a levé une exception : ' + e.message); }

  /* --- coupon --- */
  console.log('\n=== 5. Coupon ===');
  try {
    vm.runInContext('ETAT.coupon=[{label:"Over 2.5 — test",p:0.6},{label:"1 — test",p:0.5}];ETAT.onglet="coupon";rendu();', ctx, { timeout: 15000 });
    await attendre(500);
    const h = elements.get('#main').innerHTML;
    [[ 'probabilité combinée',  /Probabilité combinée/.test(h)],
     [ '30.0 % attendu (0.6×0.5)', /30\.0 %/.test(h)],
     [ 'avertissement indépendance', /indépendantes/.test(h)],
     [ 'aucun NaN',               propre(h)],
    ].forEach(([l, v]) => v ? ok(l) : ko(l));
    vm.runInContext('ETAT.coupon=[];', ctx);
  } catch (e) { ko('coupon a levé une exception : ' + e.message); }

  /* --- cas limites serveur --- */
  console.log('\n=== 6. Cas limites serveur ===');
  for (const [nom, url] of [
      ['division inconnue',    '/api/pronostic?div=ZZZ&home=A&away=B'],
      ['équipe inconnue',      '/api/pronostic?div=E0&home=InconnuFC&away=AutreFC'],
      ['secondaires inconnus', '/api/secondaires?div=ZZZ&home=A&away=B'],
      ['paramètres manquants', '/api/pronostic']]) {
    const rr = await fetch(BASE + url);
    rr.status >= 500 ? ko(`${nom} : ERREUR SERVEUR ${rr.status}`)
                     : ok(`${nom} : HTTP ${rr.status}`);
  }

  console.log(`\n${'='.repeat(60)}`);
  if (erreurs) { console.log(`\x1b[31m${erreurs} ÉCHEC(S)\x1b[0m\n`); process.exit(1); }
  console.log('\x1b[32mTOUS LES TESTS PASSENT\x1b[0m\n');
})();
