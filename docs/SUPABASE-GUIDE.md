# Supabase — ta partie en 6 étapes (10 minutes, 0 FCFA)

Le code est déjà prêt et en place : le robot écrit désormais dans la base
**en plus** des fichiers JSON actuels (double écriture = aucun risque pour le
site). Il ne manque que TON projet Supabase. Sans lui, tout continue de
tourner exactement comme avant.

---

## Étape 1 — Créer le compte

1. Va sur **https://supabase.com** et clique sur **« Start your project »**.
2. Le plus simple : **« Continue with GitHub »** (ton compte GitHub existe
   déjà). Sinon e-mail + mot de passe.

## Étape 2 — Créer le projet

1. **« New project »**.
2. Name : `pronos-foot` · Database password : clique **« Generate a password »**
   et copie-le dans un coin (on n'en aura pas besoin, mais garde-le).
3. Region : **West Europe (France)** — le plus proche du Bénin.
4. Plan : **Free** (0 FCFA — 500 Mo, largement assez pour plusieurs années).
5. **« Create new project »** et attends ~2 minutes.

## Étape 3 — Créer les tables

1. Menu de gauche : **« SQL Editor »**.
2. Ouvre le fichier `supabase/schema.sql` de ce dépôt, copie TOUT son contenu.
3. Colle dans le SQL Editor → **« Run »** (ou Ctrl+Entrée).
4. Vérifie : menu **« Table Editor »** → tu dois voir 7 tables
   (`journal_pipeline`, `selections`, `combines`, `matchs`, `predictions`,
   `cotes`, `stats_equipes`).

## Étape 4 — Récupérer les deux informations

Menu de gauche : **« Settings »** (l'engrenage) → **« API »** (ou « Data API ») :

1. **Project URL** : quelque chose comme `https://abcdefgh.supabase.co`
   → ce n'est pas secret, tu peux me le coller ici.
2. **Clés API** : il y en a deux.
   - `anon` `public` → publique, ne donne accès à RIEN (la sécurité RLS bloque
     tout). Tu peux me la coller ici sans risque.
   - `service_role` `secret` → ⚠️ **c'est la clé maîtresse d'écriture**.
     Ne la colle NULLE PART ailleurs que dans GitHub (étape 5).

## Étape 5 — Mettre les secrets dans GitHub

1. Va sur `https://github.com/sylvermelo/pronos-foot/settings/secrets/actions`
2. **« New repository secret »** — deux fois :

   | Name | Secret |
   |---|---|
   | `SUPABASE_URL` | ton Project URL (étape 4.1) |
   | `SUPABASE_SERVICE_KEY` | la clé `service_role` (étape 4.2) |

## Étape 6 — Reviens me le dire

Écris-moi simplement **« c'est fait »** (avec le Project URL si tu veux que je
vérifie). Je lance une synchronisation de test, on regarde ensemble les
premières lignes dans le Table Editor, et l'heure suivante le robot écrira
tout seul dans la base à chaque exécution.

---

## Ce qui est déjà codé de mon côté

- `db.py` : écrit sélections + combinés + verdicts dans la base (upsert —
  rejouer une exécution ne duplique jamais rien) et laisse une ligne de
  journal à chaque passage. Sans secrets configurés : il ne fait rien,
  proprement.
- `supabase/schema.sql` : les 7 tables du plan, sécurité RLS activée partout
  sans aucune politique publique (la clé publique anon ne voit RIEN — la
  lecture abonnés s'ouvrira en Phase 3).
- Le workflow horaire a une nouvelle étape « Double écriture Supabase » qui ne
  peut jamais casser le pipeline.
- Les JSON dans git restent la source principale : le site actuel ne change
  pas d'un poil.
