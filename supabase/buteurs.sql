-- Mémoire privée, jamais consultée par les navigateurs.
create table if not exists public.joueurs_matchs (
 event_id text primary key,
 division text not null,
 date_match date not null,
 brut jsonb not null,
 modifie_le timestamptz not null default now()
);
create index if not exists joueurs_matchs_modifie_idx on public.joueurs_matchs(modifie_le,event_id);
alter table public.joueurs_matchs enable row level security;
revoke all on public.joueurs_matchs from public, anon, authenticated;
grant select, insert, update on public.joueurs_matchs to service_role;
create table if not exists public.buteurs_previsions (
 event_id text primary key,
 debut_utc timestamptz not null,
 brut jsonb not null,
 modifie_le timestamptz not null default now()
);
alter table public.buteurs_previsions enable row level security;
revoke all on public.buteurs_previsions from public, anon, authenticated;
grant select, insert, update on public.buteurs_previsions to service_role;
notify pgrst, 'reload schema';
