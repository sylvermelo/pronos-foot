-- ============================================================================
-- PRONOS FOOT — Phase 1 : la mémoire dans Supabase (Postgres)
-- ============================================================================
-- À coller dans : Dashboard Supabase → SQL Editor → New query → Run.
-- Script IDEMPOTENT : on peut le relancer sans rien casser.
--
-- Principe (PLAN-PLATEFORME.md) :
--   · le robot (GitHub Actions) ÉCRIT avec la clé « service_role » (secrète),
--     qui contourne RLS ;
--   · RLS est ACTIVÉE sur toutes les tables et AUCUNE politique publique
--     n'existe en Phase 1 → la clé « anon » (publique) ne voit RIEN.
--     La lecture par les abonnés s'ouvrira en Phase 3 (comptes + RLS fine).
--   · les JSON dans git restent la source principale (double écriture =
--     zéro risque pour le site actuel).
-- ============================================================================

-- ---------------------------------------------------------------- journal
-- Chaque exécution du robot y écrit son statut : un coup d'œil suffit pour
-- savoir si tout tourne.
create table if not exists journal_pipeline (
  id          bigint generated always as identity primary key,
  run_id      text,
  debut       timestamptz not null default now(),
  statut      text not null,              -- ok / warning / echec / ignore
  details     jsonb not null default '{}'::jsonb
);
create index if not exists idx_journal_debut on journal_pipeline (debut desc);

-- ---------------------------------------------------------------- sélections
-- La sélection conseillée archivée AVANT le match (miroir de data/suivi.json),
-- puis son verdict résolu sur les scores FINAUX ESPN.
create table if not exists selections (
  id           bigint generated always as identity primary key,
  jour         date not null,             -- jour d'archivage
  div          text not null,             -- code division (E0, SP1…)
  ligue        text,
  heure        text,
  home         text not null,
  away         text not null,
  option       text not null,             -- « over 2.5 », « 1 », « double chance 1X »…
  p            double precision,          -- probabilité du moteur à l'archivage
  cote_juste   double precision,
  cote_marche  double precision,
  confiance    text,
  touche       boolean,                   -- null = pas encore résolue
  buts_home    smallint,
  buts_away    smallint,
  resolue_le   date,
  brut         jsonb not null default '{}'::jsonb,   -- l'entrée JSON exacte (traçabilité)
  archivee_le  timestamptz not null default now(),
  unique (jour, div, home, away, option)
);
create index if not exists idx_selections_jour on selections (jour desc);

-- ---------------------------------------------------------------- combinés
-- SAFE / SAFE week-end / RISQUE / COTE 2 / COTE 5 / FUN du jour.
create table if not exists combines (
  id           bigint generated always as identity primary key,
  jour         date not null,
  nom          text not null,             -- safe / safe_weekend / risque / cote2 / cote5 / fun
  p_combine    double precision,
  cote         double precision,
  touche       boolean,                   -- null = pas encore résolu
  resolu_le    date,
  jambes       jsonb not null default '[]'::jsonb,
  brut         jsonb not null default '{}'::jsonb,
  archive_le   timestamptz not null default now(),
  unique (jour, nom)
);
create index if not exists idx_combines_jour on combines (jour desc);

-- ---------------------------------------------------------------- matchs
-- Calendrier + résultats (alimenté en Phase 2 ; créé dès maintenant pour
-- que les clés étrangères existent).
create table if not exists matchs (
  id            bigint generated always as identity primary key,
  division      text not null,
  saison        text,
  date_match    date not null,
  heure         text,
  home          text not null,
  away          text not null,
  arbitre       text,
  statut        text not null default 'a_venir',   -- a_venir / fini
  buts_home     smallint,
  buts_away     smallint,
  corners_home  smallint,                 -- rempli si la source hebdo co.uk les donne
  corners_away  smallint,
  maj           timestamptz not null default now(),
  unique (division, saison, date_match, home, away)
);
create index if not exists idx_matchs_date on matchs (date_match desc);

-- ---------------------------------------------------------------- prédictions
-- TOUTES les générations du modèle sont conservées → traçabilité honnête
-- (impossible de « tricher » après coup). Alimenté en Phase 2.
create table if not exists predictions (
  id            bigint generated always as identity primary key,
  match_id      bigint references matchs (id) on delete cascade,
  generee_le    timestamptz not null default now(),
  modele        text,                     -- ex. « dixon_coles_v3 »
  probabilites  jsonb not null default '{}'::jsonb,
  secondaires   jsonb not null default '{}'::jsonb
);
create index if not exists idx_predictions_match on predictions (match_id);

-- ---------------------------------------------------------------- cotes
-- Historique des cotes par match et bookmaker (Pinnacle, moyennes co.uk).
-- Alimenté en Phase 2 ; permettra de mesurer le closing line value.
create table if not exists cotes (
  id           bigint generated always as identity primary key,
  releve_le    timestamptz not null default now(),
  division     text,
  date_match   date,
  home         text,
  away         text,
  bookmaker    text,
  marche       text,
  cotes        jsonb not null default '{}'::jsonb
);
create index if not exists idx_cotes_releve on cotes (releve_le desc);

-- ---------------------------------------------------------------- stats équipes
-- Formes, xG pour/contre, cartons, corners — ce qui alimente les analyses
-- secondaires. Alimenté en Phase 2.
create table if not exists stats_equipes (
  division  text not null,
  saison    text not null,
  equipe    text not null,
  stats     jsonb not null default '{}'::jsonb,
  maj       timestamptz not null default now(),
  primary key (division, saison, equipe)
);

-- ---------------------------------------------------------------- RLS
-- Activée PARTOUT, aucune politique publique en Phase 1 :
-- la clé anon ne lit rien ; le robot écrit avec la clé service_role.
alter table journal_pipeline enable row level security;
alter table selections       enable row level security;
alter table combines         enable row level security;
alter table matchs           enable row level security;
alter table predictions      enable row level security;
alter table cotes            enable row level security;
alter table stats_equipes    enable row level security;

-- ============================================================================
-- FIN — vérification : Table Editor doit montrer 7 tables vides.
-- ============================================================================
