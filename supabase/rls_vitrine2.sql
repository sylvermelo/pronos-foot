-- ============================================================================
-- VITRINE v2 : conseils derrière abonnement, historique public, code opérateur
-- ============================================================================
-- À coller dans SQL Editor → Run (APRÈS avoir créé l'utilisateur opérateur
-- dans Authentication → Users, voir SUPABASE-GUIDE / message d'accompagnement).
-- ============================================================================

-- Table du plan (phase 3) : qui a accès, jusqu'à quand.
create table if not exists abonnements (
  id      bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  email   text,
  plan    text not null default 'mensuel',
  debut   date not null default current_date,
  fin     date not null,
  cree_le timestamptz not null default now()
);
alter table abonnements enable row level security;
drop policy if exists "abonne_lit_son_abonnement" on abonnements;
create policy "abonne_lit_son_abonnement" on abonnements
  for select to authenticated using (auth.uid() = user_id);

-- SÉLECTIONS / COMBINÉS : les verdicts PASSÉS restent publics (c'est ta
-- preuve de confiance) ; les conseils À VENIR (et le coupon corners, jamais
-- résolu automatiquement) exigent un abonnement ACTIF (fin >= aujourd'hui).
drop policy if exists "vitrine_lecture_selections" on selections;
create policy "vitrine_lecture_selections" on selections
  for select to anon, authenticated
  using (touche is not null
         or exists (select 1 from abonnements a
                    where a.user_id = auth.uid() and a.fin >= current_date));

drop policy if exists "vitrine_lecture_combines" on combines;
create policy "vitrine_lecture_combines" on combines
  for select to anon, authenticated
  using (touche is not null
         or exists (select 1 from abonnements a
                    where a.user_id = auth.uid() and a.fin >= current_date));

-- ACCÈS OPÉRATEUR permanent (sans paiement, sans inscription) : le compte
-- caché operateur@pronos-foot.bj dont le mot de passe est ton code secret.
insert into abonnements (user_id, email, plan, debut, fin)
select id, email, 'operateur', current_date, date '2099-12-31'
from auth.users
where email = 'operateur@pronos-foot.bj'
  and not exists (select 1 from abonnements a where a.user_id = auth.users.id);
