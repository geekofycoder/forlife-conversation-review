# ForLife: ideal conversation review

A one-page review of the "ideal conversation" draft for the Vera chat redesign, for the PM.
Pick an episode on the left (or from the menu on a phone) to read it; the other tabs hold the findings, rewrites, evidence and decisions.

**Live page:** https://geekofycoder.github.io/forlife-conversation-review/
Link straight to an episode with `#episode-A` … `#episode-K`, or to a tab with `#findings`, `#decisions`.

## Updating it

The page is generated from `ideal_conversation.md` (kept privately in the ForLife repo's `benchmark/episodes/`).

```bash
python3 build.py                      # reads ../ChatBot/benchmark/episodes/ideal_conversation.md
python3 build.py path/to/draft.md     # or any other copy
git add index.html && git commit -m "Update review" && git push
```

GitHub Pages republishes within a minute or two.

## Comments

Click **💬 Turn on comments** at the top, type your name and the shared passcode (once per browser).
- Point at any line, paragraph or table row and click 💬, or select a few words and click **Comment**.
- Replies sit under the comment. Lines with comments keep a 💬 count; the episode list and tabs show totals.
- If a commented line is reworded later, its comments move to "Comments on lines that have changed since" at the end of that section.
- No emails, no accounts, no status: just the discussion, on the page.

Comments are stored in a separate Supabase project (`supabase_setup.sql`), readable only with the passcode.
Change the passcode in that project's SQL Editor:
`update public.review_settings set passcode_hash = crypt('NEW-PASSCODE', gen_salt('bf'));`

## What goes in here

Only the draft: short quotes from test chats, with names written as `{name}`. The page is public, so never add the full chat export (`conversations.json`) or anything with a real name.
