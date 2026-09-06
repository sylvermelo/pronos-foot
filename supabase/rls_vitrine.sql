-- ============================================================================
-- VITRINE : lecture publique des données affichées (Phase vitrine)
-- ============================================================================
-- À coller dans Dashboard Supabase → SQL Editor → Run.
-- Ouvre en LECTURE SEULEMENT les deux tables que la vitrine affiche
-- (sélections + combinés, y compris le coupon corners montante).
-- Le robot continue d'écrire avec la clé service_role (elle contourne RLS).
-- journal_pipeline, matchs, predictions, cotes, stats_equipes RESTENT fermés.
-- ============================================================================
drop policy if exists "vitrine_lecture_selections" on selections;
create policy "vitrine_lecture_selections" on selections
  for select to anon, authenticated using (true);

drop policy if exists "vitrine_lecture_combines" on combines;
create policy "vitrine_lecture_combines" on combines
  for select to anon, authenticated using (true);
