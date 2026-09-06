-- ============================================================================
-- PARRAINAGE : vendeurs, codes promo, attribution des clients
-- ============================================================================
-- À coller dans Supabase → SQL Editor → Run (APRÈS rls_admin.sql).
--
-- Principe :
--   · l'opérateur ajoute un « vendeur » depuis l'onglet Admin du robot →
--     un code promo unique est généré (format PF-XXXXX) ;
--   · le filleul saisit le code à l'inscription / connexion / page
--     d'activation → il est enregistré UNE SEULE FOIS sur son compte
--     (premier code déclaré gagne, impossible de changer ensuite) ;
--   · la validation passe par une fonction sécurisée : personne ne peut
--     modifier son abonnement soi-même, seulement déclarer un code.
-- ============================================================================

-- 1) Table des vendeurs / partenaires
create table if not exists public.partenaires (
  id      bigint generated always as identity primary key,
  code    text not null unique,
  nom     text,
  actif   boolean not null default true,
  cree_le timestamptz not null default now()
);
alter table public.partenaires enable row level security;

-- L'opérateur seul voit et gère les vendeurs.
drop policy if exists "operateur_partenaires" on public.partenaires;
create policy "operateur_partenaires" on public.partenaires
  for all to authenticated
  using (auth.email() = 'operateur@pronos-foot.bj')
  with check (auth.email() = 'operateur@pronos-foot.bj');

-- 2) Vue PUBLIQUE des codes valides (validation à l'inscription sans compte
--    opérateur). N'expose que le code — ni les noms, ni les dates.
create or replace view public.codes_promo as
  select code from public.partenaires where actif;
grant select on public.codes_promo to anon, authenticated;

-- 3) Colonne d'attribution sur les comptes
alter table public.abonnements add column if not exists code_promo text;
create index if not exists idx_abonnements_code_promo
  on public.abonnements (code_promo);

-- 4) Fonction d'attribution : la seule façon d'écrire code_promo.
--    SECURITY DEFINER = elle s'exécute avec les droits du propriétaire,
--    donc AUCUNE politique d'update directe n'est nécessaire sur
--    abonnements (l'abonné ne peut pas toucher à sa propre échéance).
create or replace function public.declarer_code_promo(p_code text)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_code text := upper(btrim(coalesce(p_code, '')));
  n int;
begin
  if auth.uid() is null then
    return 'pas_connecte';
  end if;
  if v_code = '' then
    return 'invalide';
  end if;
  select count(*) into n from public.codes_promo where code = v_code;
  if n = 0 then
    return 'invalide';
  end if;
  update public.abonnements
     set code_promo = v_code
   where user_id = auth.uid() and code_promo is null;
  if found then
    return 'ok';
  end if;
  -- compte sans ligne d'abonnement (créé avant le trigger) : on la crée
  if not exists (select 1 from public.abonnements where user_id = auth.uid()) then
    insert into public.abonnements (user_id, email, plan, debut, fin, code_promo)
    select auth.uid(), u.email, 'attente', current_date, date '1970-01-01', v_code
    from auth.users u
    where u.id = auth.uid()
    on conflict (user_id) do nothing;
    return 'ok';
  end if;
  return 'deja';                 -- un code est déjà attribué à ce compte
end
$$;
revoke all on function public.declarer_code_promo(text) from public;
grant execute on function public.declarer_code_promo(text) to anon, authenticated;
