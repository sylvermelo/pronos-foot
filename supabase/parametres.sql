-- ============================================================================
-- PARAMÈTRES DYNAMIQUES — prix, promotions, barème affiliés
-- ============================================================================
-- À coller dans : Dashboard Supabase → SQL Editor → New query → Run.
-- Script IDEMPOTENT. À passer APRÈS affilies.sql.
--
-- Demande utilisateur (10/09) : « rendre tout dynamique dans l'admin et non
-- fixé en dur. Les prix je dois pouvoir les changer, créer une période de
-- promotion : tel prix jusqu'à telle date avec l'ancien prix barré. »
--
-- Principe : une petite table `parametres` (clé → valeur JSON), lisible par
-- tout le monde (la vitrine et l'espace affilié l'affichent), modifiable
-- UNIQUEMENT par l'opérateur via la fonction sécurisée maj_parametres().
-- Le déclencheur des gains affiliés lit désormais les commissions ICI —
-- plus aucun montant codé en dur.
-- ============================================================================

-- ---------------------------------------------------------------- 1) table
create table if not exists public.parametres (
  cle    text primary key,
  valeur jsonb not null,
  maj_le timestamptz not null default now()
);
alter table public.parametres enable row level security;

-- Lecture publique (prix/promo affichés sur la vitrine = informations publiques).
drop policy if exists "parametres_lecture_publique" on public.parametres;
create policy "parametres_lecture_publique" on public.parametres
  for select to anon, authenticated using (true);
-- Aucune politique d'écriture : la modification passe par maj_parametres()
-- (security definer, réservée à l'opérateur).

-- ---------------------------------------------------------------- 2) valeurs par défaut (barème validé le 10/09)
insert into public.parametres (cle, valeur) values
  ('prix', '{"mensuel_fcfa": 2500, "duree_jours": 30, "devise": "FCFA"}'::jsonb),
  ('promo', '{"actif": false, "prix_fcfa": null, "jusquau": null}'::jsonb),
  ('affiliation', '{"reduction_fcfa": 500, "commission_premiere": 1000, "commission_renouvellement": 500, "seuil_paiement_fcfa": 2500}'::jsonb)
on conflict (cle) do nothing;

-- ---------------------------------------------------------------- 3) écriture réservée à l'opérateur
create or replace function public.maj_parametres(p_cle text, p_valeur jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.email() is distinct from 'operateur@pronos-foot.bj' then
    return jsonb_build_object('ok', false, 'erreur', 'interdit');
  end if;
  if p_cle not in ('prix', 'promo', 'affiliation') then
    return jsonb_build_object('ok', false, 'erreur', 'cle_inconnue');
  end if;
  if p_valeur is null then
    return jsonb_build_object('ok', false, 'erreur', 'valeur_vide');
  end if;
  -- garde-fous simples sur la promo : prix promo < prix normal, date valide
  if p_cle = 'promo' and coalesce((p_valeur->>'actif')::boolean, false) then
    if coalesce((p_valeur->>'prix_fcfa')::int, 0) <= 0 then
      return jsonb_build_object('ok', false, 'erreur', 'prix_promo_invalide');
    end if;
    if (p_valeur->>'jusquau') is null then
      return jsonb_build_object('ok', false, 'erreur', 'date_manquante');
    end if;
  end if;
  insert into public.parametres (cle, valeur, maj_le)
  values (p_cle, p_valeur, now())
  on conflict (cle) do update set valeur = excluded.valeur, maj_le = now();
  return jsonb_build_object('ok', true);
end
$$;
revoke all on function public.maj_parametres(text, jsonb) from public;
grant execute on function public.maj_parametres(text, jsonb) to authenticated;

-- ---------------------------------------------------------------- 4) gains affiliés : commissions dynamiques
-- Remplace la version d'affilies.sql : les montants 1000/500 sont maintenant
-- lus dans parametres → modifiables depuis l'admin sans retoucher la base.
create or replace function public.enregistrer_gain_activation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_type text;
  v_montant int;
  v_aff jsonb;
begin
  if tg_op = 'UPDATE' then
    if new.fin is not distinct from old.fin then return new; end if;
    if new.fin <= old.fin then return new; end if;
  end if;
  if new.code_promo is null then return new; end if;
  if new.fin < current_date then return new; end if;
  if coalesce(new.plan, '') = 'operateur' then return new; end if;
  -- anti-fraude : pas d'auto-commission (affilié = son propre filleul)
  if exists (select 1 from public.partenaires p
              where p.code = new.code_promo and p.user_id = new.user_id) then
    return new;
  end if;
  select coalesce((select valeur from public.parametres where cle = 'affiliation'),
                  '{}'::jsonb) into v_aff;
  if exists (select 1 from public.gains_affilies g
              where g.filleul_user_id = new.user_id and g.type = 'premiere') then
    v_type := 'renouvellement';
    v_montant := coalesce((v_aff->>'commission_renouvellement')::int, 500);
  else
    v_type := 'premiere';
    v_montant := coalesce((v_aff->>'commission_premiere')::int, 1000);
  end if;
  insert into public.gains_affilies (code, filleul_user_id, type, montant, fin_cible)
  values (new.code_promo, new.user_id, v_type, v_montant, new.fin)
  on conflict do nothing;
  return new;
end
$$;

-- ============================================================================
-- FIN — Vérification : SELECT * FROM parametres; → 3 lignes
-- (prix 2500 / promo inactive / affiliation 500-1000-500, seuil 2500).
-- ============================================================================
