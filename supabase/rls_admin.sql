-- ============================================================================
-- ADMIN : suivi automatique des comptes + activation en un clic
-- ============================================================================
-- À coller dans Supabase → SQL Editor → Run.
-- Ne modifie AUCUNE donnée existante : l'opérateur et les abonnés déjà actifs
-- gardent leur ligne telle quelle.
-- ============================================================================

-- 1) Une seule ligne d'abonnement par compte (le déclencheur s'appuie dessus).
--    Si cette étape échoue à cause de doublons existants : s'arrêter là et
--    le signaler — on nettoie d'abord.
create unique index if not exists abonnements_un_par_compte
  on public.abonnements (user_id);

-- 2) Déclencheur : chaque nouveau compte (inscription vitrine, Google,
--    téléphone) est inscrit automatiquement dans abonnements, état INACTIF
--    (fin = 1970-01-01). L'activation se fait ensuite depuis l'onglet Admin.
create or replace function public.nouveau_compte_abonnement()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.abonnements (user_id, email, plan, debut, fin, cree_le)
  values (new.id, new.email, 'attente', current_date, date '1970-01-01',
          coalesce(new.created_at, now()))
  on conflict (user_id) do nothing;
  return new;
end
$$;

drop trigger if exists nouveau_compte_abonnement on auth.users;
create trigger nouveau_compte_abonnement
  after insert on auth.users
  for each row execute function public.nouveau_compte_abonnement();

-- 3) Rattrapage : comptes créés AVANT l'installation du déclencheur.
insert into public.abonnements (user_id, email, plan, debut, fin, cree_le)
select u.id, u.email, 'attente', current_date, date '1970-01-01',
       coalesce(u.created_at, now())
from auth.users u
where not exists (select 1 from public.abonnements a where a.user_id = u.id);

-- 4) Droits ADMIN : le compte opérateur voit TOUTES les lignes et peut
--    modifier les échéances. Les comptes ordinaires continuent de ne voir
--    que leur propre ligne (politique « abonne_lit_son_abonnement »).
drop policy if exists "operateur_voit_tous_abonnements" on public.abonnements;
create policy "operateur_voit_tous_abonnements" on public.abonnements
  for select to authenticated
  using (auth.email() = 'operateur@pronos-foot.bj');

drop policy if exists "operateur_modifie_abonnements" on public.abonnements;
create policy "operateur_modifie_abonnements" on public.abonnements
  for update to authenticated
  using (auth.email() = 'operateur@pronos-foot.bj')
  with check (auth.email() = 'operateur@pronos-foot.bj');

drop policy if exists "operateur_insere_abonnements" on public.abonnements;
create policy "operateur_insere_abonnements" on public.abonnements
  for insert to authenticated
  with check (auth.email() = 'operateur@pronos-foot.bj');
