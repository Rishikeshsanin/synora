-- Run with psql against ONLY the disposable database after applying the migration.
-- Transaction rolls back test grants and records.
begin;
do $$
begin
  if has_schema_privilege('anon','synora','USAGE') or has_schema_privilege('authenticated','synora','USAGE') then
    raise exception 'Unexpected direct client schema access';
  end if;
  if exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
            where n.nspname='synora' and c.relkind='r' and not c.relrowsecurity) then
    raise exception 'RLS disabled';
  end if;
end $$;
insert into synora.projects(id,user_id,name) values
 ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','11111111-1111-4111-8111-111111111111','owner A'),
 ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','22222222-2222-4222-8222-222222222222','owner B');
grant usage on schema synora to authenticated;
grant select on synora.projects to authenticated;
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$
begin
  if (select count(*) from synora.projects) <> 1 or
     exists(select 1 from synora.projects where name='owner B') then
    raise exception 'RLS owner isolation failed';
  end if;
  if has_table_privilege('authenticated','synora.projects','INSERT') then
    raise exception 'Unexpected write grant';
  end if;
end $$;
reset role;
rollback;
