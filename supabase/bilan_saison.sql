create or replace function public.bilan_saison(debut date)
returns jsonb language sql stable security invoker set search_path = ''
as $$
select jsonb_build_object(
'sel',coalesce((select jsonb_agg(to_jsonb(s) order by jour) from (
select jour,count(*)::integer n,count(*) filter(where touche)::integer t
from public.selections where jour>=debut and touche is not null group by jour) s),'[]'::jsonb),
'comb',coalesce((select jsonb_agg(to_jsonb(c) order by jour,nom) from (
select jour,nom,count(*)::integer n,count(*) filter(where touche)::integer t
from public.combines where jour>=debut and touche is not null group by jour,nom) c),'[]'::jsonb));
$$;
revoke all on function public.bilan_saison(date) from public;
grant execute on function public.bilan_saison(date) to anon,authenticated;
