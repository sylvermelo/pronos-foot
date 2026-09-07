# Pack de prompts — site vitrine mobile avec Google Stitch

_Objectif : la vitrine mobile de PRONOS FOOT, dans le style « Quant Edge
Terminal » de l'application (fond sombre, accents cyan/vert, chiffres en
mono). Tout le texte de l'interface sera en FRANÇAIS — les prompts sont en
anglais parce que Stitch les comprend mieux, mais tu n'as rien à traduire :
tu copies-colles, c'est tout._

---

## Mode d'emploi (5 minutes)

1. Va sur **https://stitch.withgoogle.com** → connecte ton compte Google.
2. **« New Project »** → choisis **Mobile** (pas Desktop).
3. Colle le **Prompt 0** (style global) en premier — c'est lui qui donne la
   cohérence entre tous les écrans.
4. Ensuite, génère les écrans un par un avec les prompts 1 à 6.
5. Pas satisfait ? Sélectionne l'élément et demande une retouche **en
   français** dans le chat de Stitch (« rends les cartes plus compactes »,
   « le bouton en vert »…). Stitch itère très bien en français.
6. Quand le design te plaît : **« Export »** (code HTML/CSS ou Figma) et
   envoie-moi le tout — je branche les VRAIES données (sélections du jour,
   coupons corners, taux réels) et j'héberge la vitrine.

⚠️ Le quota gratuit de Stitch est limité par mois : une génération à la fois,
ne régénère pas dix fois le même écran — itère avec le chat plutôt.

**Règle d'or du contenu (non négociable, c'est aussi ta protection légale) :**
la vitrine ne promet AUCUN gain. Elle vend de l'analyse transparente :
les vrais taux, les vraies limites, le ROI négatif documenté. C'est ce qui
te distingue de tous les vendeurs de rêves Telegram.

---

## PROMPT 0 — Style global (à coller en premier)

```
Design system for a mobile-first French football analytics app called
"PRONOS FOOT". Style: "quant trading terminal" — very dark navy background
(#0A0E17), elevated cards (#121826) with 1px borders (#1E2A3F), accent
cyan #22D3EE for data and links, accent green #22C55E only for validated
wins, red #EF4444 only for losses. Typography: Inter or similar geometric
sans for text, monospace (JetBrains Mono) for ALL numbers, odds and
probabilities. Small uppercase labels with letter-spacing, pill badges,
thin progress bars, no gradients, no photos, no illustrations of players.
Dense but breathable data cards, 16px margins, bottom navigation bar with
5 icons. Tone: professional, cold, honest — a Bloomberg terminal for
football betting analysis, NOT a gambling casino site. All UI text must be
in French. Generate a home screen for this system.
```

---

## PROMPT 1 — Accueil / Héro

```
Mobile home screen for PRONOS FOOT (use the established dark quant terminal
design system). Structure top to bottom:
1. Header: small logo text "PRONOS FOOT" in monospace, a pill badge
   "MISE À JOUR AUTOMATIQUE · CHAQUE HEURE", and a live status dot.
2. Hero block: headline "L'analyse froide du football." subheadline
   "Pas de promesse de gains. Des probabilités mesurées sur 16 408 matchs
   réels, et les vrais résultats publiés chaque heure." Primary button
   "Voir les sélections du jour", secondary button "Le bilan honnête".
3. Three stat cards in a row (monospace numbers): "21 championnats
   couverts", "78 % de sélections touchées", "0 FCFA d'abonnement" — with
   a tiny caption under the 78%: "taux réel vérifié sur les résultats
   officiels ESPN".
4. A preview card "SÉLECTIONS DU JOUR" showing 3 example rows: match
   (teams + league), a market pill like "under 2.5", a monospace
   probability "82 %" and a fair odd "1.22". Footer of the card: link
   "Ouvrir le terminal complet →".
5. Bottom navigation: Accueil, Sélections, Corners, Bilan, Réglages.
All text in French. Honest, technical, dense.
```

---

## PROMPT 2 — Sélections du jour (l'écran produit principal)

```
Mobile screen "Sélections" for the PRONOS FOOT dark quant terminal design
system. Top: sticky day selector as horizontal scrollable chips
("Aujourd'hui", "Demain", dates), and a segmented control
"Tout / SAFE / Combinés". Content: a vertical list of selection cards.
Each card: kickoff time in monospace + league name (small, dim), the two
team names, a market pill (e.g. "over 2.5", "double chance 1X",
"under 3.5"), model probability in large monospace cyan ("84 %"), fair odd
("cote juste 1.19"), market odd when available with a small "PINNACLE"
badge, and a confidence dot (haute/moyenne/faible). Two cards show a green
"✓ TOUCHÉE" or red "✗ MANQUÉE" verdict state with final score "2-1" in
monospace, to show that results are public. Below the list, a section
"COMBINÉS DU ROBOT" with 3 compact cards: "SAFE DU JOUR · 2 matchs · cote
2.10", "COTE 2 · 5 matchs · cote 2.23", "FUN · 13 matchs · cote 24.71",
each with combined probability in monospace and a verdict state for past
days. Sticky footer bar: "Taux réel : 78 % · ROI backtest : −8,8 % —
parier comporte des risques". All text in French.
```

---

## PROMPT 3 — Coupon corners montante (ton écran exclusif)

```
Mobile screen "Corners" for the PRONOS FOOT dark quant terminal design
system. This screen presents a daily "coupon montante" built from corner
handicap markets. Structure:
1. Header card: title "COUPON MONTANTE — DIMANCHE 13", a big monospace
   total odd "1.85" in cyan with label "cote totale", a combined
   probability "54 %" and a caption "tous les bons matchs du jour, dans
   l'ordre des coups d'envoi — même jour uniquement, jamais de report".
2. Step list (the montante): 5 numbered rows, each with kickoff time,
   teams, the handicap pick as a pill "Barcelona +2 corners" (also variants
   "+1", "victoire", "−1"), a calibrated probability "86 %" in monospace
   with a tiny struck-through raw model probability "annonce 92 % → réel
   86 %" to show honesty, the fair odd "1.16", and the stake to place
   "mise 1.00 u → 1.16 u" growing at each step. The last row shows
   "si tout passe : 2.28 u récupérées".
3. A calibration note card: "Probabilités CALIBRÉES sur 16 408 matchs :
   le modèle brut surestimait la domination corners (victoire annoncée
   92 % → réalisée 79 %)."
4. Empty state variant: a centered card "AUCUN COUPON AUJOURD'HUI — aucun
   match n'atteint 85 % de fréquence réelle mesurée. Mieux vaut sauter un
   jour que forcer."
All text in French, dense monospace numbers, cyan/green accents.
```

---

## PROMPT 4 — Bilan honnête (l'écran qui te distingue)

```
Mobile screen "Bilan" for the PRONOS FOOT dark quant terminal design
system. Purpose: radical transparency about real results. Structure:
1. Big verdict header: "LE BILAN HONNÊTE" with subtext "publié chaque
   heure, résultats officiels ESPN, rien n'est effacé".
2. KPI grid (2×2 monospace cards): "78 % sélections touchées (43/55)",
   "ROI simulé +2.1 u sur 30 jours", "ROI backtest −8.8 % sur 213 665
   paris", "92 % annoncé → 92 % réalisé (calibration)".
3. A monthly bar chart card "taux de réussite par mois" in cyan bars, with
   one red bar to show losing months are displayed too.
4. A breakdown list by market with thin progress bars: "under 2.5 — 81 %",
   "over 2.5 — 74 %", "double chance — 88 %", "1X2 — 62 %" each bar green
   above 75%, amber below.
5. A limitations card, deliberately visible (not hidden in a footer):
   "CE QUE LE ROBOT NE FAIT PAS : pas de compositions d'équipe, pas de
   blessés, les marchés corners/cartons sans cotes officielles, et sur la
   durée le marché gagne. C'est un outil d'analyse, pas une machine à
   gains." with each item as a small crossed list row.
All text in French, cold and factual.
```

---

## PROMPT 5 — Comment ça marche (pédagogie)

```
Mobile screen "Méthode" for the PRONOS FOOT dark quant terminal design
system. A vertical timeline explaining the pipeline in 5 steps, each step
a card with a monospace number, a title and 2 lines of explanation:
1. "COLLECTE" — "Résultats et calendriers ESPN (chaque heure), historiques
   football-data.co.uk depuis 2018, cotes Pinnacle, xG réels Understat."
2. "MODÈLE" — "Puissance d'attaque et de défense de chaque équipe,
   correction Dixon-Coles, 21 championnats + coupes européennes."
3. "CALIBRATION" — "Chaque probabilité est confrontée à la fréquence
   RÉELLE mesurée en walk-forward : annoncé 93 % → réalisé 89 % sur les
   handicaps corners. Le modèle ne se note pas lui-même."
4. "ARCHIVAGE" — "Les sélections sont figées AVANT les coups d'envoi,
   puis résolues sur les scores officiels. Impossible de tricher après
   coup."
5. "PUBLICATION" — "Le site se régénère tout seul chaque heure via GitHub
   Actions. 0 FCFA d'infrastructure."
Below: a small "sources" grid with the logos-as-text: ESPN,
football-data.co.uk, Pinnacle via The Odds API, Understat, GitHub.
Bottom: a CTA card "Voir les sélections du jour →". All text in French.
```

---

## PROMPT 6 — Accès / tarif (prêt pour la Phase 4, sans prix)

```
Mobile screen "Accès" for the PRONOS FOOT dark quant terminal design
system. Two vertical plan cards, no prices shown yet (launch pending):
1. Card "GRATUIT — pour la confiance": included list with check icons:
   "Résultats et bilan honnête en direct", "Historiques et fréquences par
   ligue", "Calibration publique du modèle", badge "toujours gratuit".
2. Card "ABONNÉ — l'essentiel, chaque jour": "Sélections conseillées du
   jour", "Combinés SAFE / COTE 2 / COTE 5", "Coupon montante corners
   calibré", "Analyses cartons, fautes, corners par match", badge
   "bientôt · paiement Mobile Money (KKiaPay / FedaPay)".
3. A disclaimer block, small but clearly readable: "Aucune promesse de
   gains. Les vrais taux de réussite sont publics (onglet Bilan). Jeu
   réservé aux majeurs — parier comporte des risques d'endettement.
   Cadre légal béninois (LNB) en cours de vérification avant tout
   encaissement."
4. Sticky bottom button (disabled state): "Rejoindre la liste d'attente".
All text in French.
```

---

## Après Stitch — ce que tu m'envoies

- Le **code exporté** (bouton Export → HTML/CSS, ou le zip), ou à défaut des
  **captures d'écran** de chaque écran validé.
- Tes retouches finales décidées dans le chat de Stitch (je les verrai de
  toute façon dans l'export).

Ma partie ensuite : j'assemble les écrans en un vrai site mobile hébergé sur
GitHub Pages (0 FCFA), je branche les données réelles (les mêmes API que le
terminal : sélections du jour, coupon corners, bilan), et la vitrine pointe
vers l'application complète. Le tout testé localement avant mise en ligne,
comme d'habitude.
