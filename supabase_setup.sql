-- Comments for the ideal-conversation review page.
-- Run once in a NEW Supabase project: SQL Editor > New query > paste > change the passcode on the last line > Run.
-- The tables can't be read or written directly with the public (anon) key; the page only uses the three
-- functions below, and each one checks the shared passcode first.

create extension if not exists pgcrypto with schema extensions;

create table public.review_comments (
  id          bigint generated always as identity primary key,
  anchor      text not null,                      -- which line or paragraph (e.g. "ep-D:3f9a2c")
  section     text not null,                      -- tab or episode (e.g. "ep-D", "findings")
  line_text   text not null default '',           -- the line as it was, so a comment survives edits
  quote       text,                               -- the words selected, if any
  parent_id   bigint references public.review_comments (id) on delete cascade,  -- a reply
  author      text not null check (char_length(btrim(author)) between 1 and 40),
  body        text not null check (char_length(btrim(body)) between 1 and 4000),
  created_at  timestamptz not null default now()
);
create index on public.review_comments (anchor);

create table public.review_settings (
  passcode_hash text not null
);

alter table public.review_comments enable row level security;
alter table public.review_settings enable row level security;
revoke all on public.review_comments, public.review_settings from anon, authenticated;

create or replace function public.review_passcode_ok(p_passcode text)
returns boolean
language sql stable security definer set search_path = public, extensions
as $$
  select exists (select 1 from review_settings where passcode_hash = crypt(p_passcode, passcode_hash));
$$;

create or replace function public.list_comments(p_passcode text)
returns setof public.review_comments
language plpgsql stable security definer set search_path = public, extensions
as $$
begin
  if not review_passcode_ok(p_passcode) then
    raise exception 'wrong passcode';
  end if;
  return query select * from review_comments order by created_at;
end;
$$;

create or replace function public.add_comment(
  p_passcode text, p_anchor text, p_section text, p_line_text text,
  p_quote text, p_parent_id bigint, p_author text, p_body text)
returns public.review_comments
language plpgsql security definer set search_path = public, extensions
as $$
declare
  saved public.review_comments;
begin
  if not review_passcode_ok(p_passcode) then
    raise exception 'wrong passcode';
  end if;
  insert into review_comments (anchor, section, line_text, quote, parent_id, author, body)
  values (p_anchor, p_section, coalesce(left(p_line_text, 2000), ''), nullif(left(p_quote, 1000), ''),
          p_parent_id, btrim(p_author), btrim(p_body))
  returning * into saved;
  return saved;
end;
$$;

create or replace function public.delete_comment(p_passcode text, p_id bigint)
returns void
language plpgsql security definer set search_path = public, extensions
as $$
begin
  if not review_passcode_ok(p_passcode) then
    raise exception 'wrong passcode';
  end if;
  delete from review_comments where id = p_id;   -- its replies go with it
end;
$$;

revoke all on function public.review_passcode_ok(text) from public, anon, authenticated;
revoke all on function public.list_comments(text) from public;
revoke all on function public.add_comment(text, text, text, text, text, bigint, text, text) from public;
revoke all on function public.delete_comment(text, bigint) from public;
grant execute on function public.list_comments(text) to anon;
grant execute on function public.add_comment(text, text, text, text, text, bigint, text, text) to anon;
grant execute on function public.delete_comment(text, bigint) to anon;

-- The shared passcode: change CHANGE-ME to your own before running.
insert into public.review_settings (passcode_hash) values (crypt('CHANGE-ME', gen_salt('bf')));

-- To change the passcode later, run only this line:
-- update public.review_settings set passcode_hash = crypt('NEW-PASSCODE', gen_salt('bf'));
