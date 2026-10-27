"""Build index.html, the PM review page, from the ideal-conversation draft.

Usage:  python3 build.py [path/to/ideal_conversation.md]
Default source: ../ChatBot/benchmark/episodes/ideal_conversation.md
Writes index.html next to this file. Plain Python 3, no packages.
"""
import hashlib
import html
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "ChatBot/benchmark/episodes/ideal_conversation.md"

# Comments live in a separate Supabase project (supabase_setup.sql). The anon key is meant to be public: it can only
# call the three passcode-checked functions, never read or write the tables directly.
SUPABASE_URL = "https://feasaiavkfgaorazjhfw.supabase.co"
SUPABASE_ANON_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlYXNhaWF2a2ZnYW9yYXpqaGZ3"
                     "Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMxMTAwNzQsImV4cCI6MjEwODY4NjA3NH0."
                     "RuZK9wvhp-O5H7uu7hdGIYY0arabQNR7Ujt1nkDyf7M")

NAME = '<span class="name" title="A real name, left out">name</span>'
EPISODE_IDS = {}  # "b9d47118-1" -> "D", filled once the episodes are read, so ids elsewhere link to them

# Every commentable block gets data-c="<section>:<hash of its text>", so a comment stays on its line when lines are added
# or moved. A reworded line gets a new hash; its old comments then show under "lines that changed".
CTX = {"section": "page", "seen": {}}


def anchor(inner_html):
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inner_html))).strip().lower()
    h = hashlib.sha1(f'{CTX["section"]}|{text}'.encode()).hexdigest()[:8]
    key = (CTX["section"], h)
    n = CTX["seen"].get(key, 0)
    CTX["seen"][key] = n + 1
    return f' data-c="{CTX["section"]}:{h}{":" + str(n) if n else ""}"'


# ---------- markdown, just the parts the draft uses ----------

def inline(text):
    t = html.escape(text, quote=False)
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", keep, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = t.replace("{name}", NAME)

    def back(m):
        c = codes[int(m.group(1))]
        if c == "{name}":
            return NAME
        if c in EPISODE_IDS:
            return f'<a class="ep" href="#episode-{EPISODE_IDS[c]}" title="Open episode {EPISODE_IDS[c]}">{c}</a>'
        return f"<code>{c}</code>"

    return re.sub(r"\x00(\d+)\x00", back, t)


def table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], [r for r in cells[1:] if not all(re.fullmatch(r":?-{3,}:?", c) for c in r)]
    out = ['<div class="table"><table><thead><tr>']
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for r in body:
        tds = "".join(f"<td>{inline(c)}</td>" for c in r)
        out.append(f"<tr{anchor(tds)}>{tds}</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


ITEM = re.compile(r"^(\s*)(\d+\.|[-*])\s+(.*)$")


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def a_list(lines, i):
    """A list starting at lines[i]; items may hold indented blocks (sub-lists, tables). Returns (html, next i)."""
    first = ITEM.match(lines[i])
    base, ordered = len(first.group(1)), first.group(2)[0].isdigit()
    items = []
    while i < len(lines):
        m = ITEM.match(lines[i])
        if not m or len(m.group(1)) != base or m.group(2)[0].isdigit() != ordered:
            break
        body, i = [m.group(3)], i + 1
        while i < len(lines):
            ln = lines[i]
            if ln.strip() and indent_of(ln) > base:
                body.append(ln)
                i += 1
            elif not ln.strip():
                nxt = next((x for x in lines[i + 1:] if x.strip()), "")
                if nxt and indent_of(nxt) > base:
                    body.append("")
                    i += 1
                else:
                    break
            else:
                break
        head, rest = body[0], body[1:]
        pad = min((indent_of(x) for x in rest if x.strip()), default=0)
        own = inline(head)
        attr = anchor(own)
        inner = blocks([x[pad:] for x in rest]) if rest else ""
        items.append(f"<li{attr}>{own}{inner}</li>")
    tag = "ol" if ordered else "ul"
    return f"<{tag}>{''.join(items)}</{tag}>", i


def blocks(lines):
    out, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if not s or s == "---":
            i += 1
        elif s.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            code = html.escape("\n".join(lines[i + 1:j]))
            out.append(f"<pre{anchor(code)}>{code}</pre>")
            i = j + 1
        elif re.match(r"#{3,4}\s", s):
            level = len(s.split()[0])
            h = inline(s[level:].strip())
            out.append(f"<h{level}{anchor(h)}>{h}</h{level}>")
            i += 1
        elif s.startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(table(lines[i:j]))
            i = j
        elif ITEM.match(lines[i]):
            h, i = a_list(lines, i)
            out.append(h)
        else:
            j = i
            while j < len(lines) and lines[j].strip() and not re.match(r"(\||```|#{3,4}\s|---$)", lines[j].strip()) \
                    and not (j > i and ITEM.match(lines[j])):
                j += 1
            p = inline(" ".join(x.strip() for x in lines[i:j]))
            out.append(f"<p{anchor(p)}>{p}</p>")
            i = j
    return "\n".join(out)


# ---------- the draft's structure ----------

def split_sections(text):
    """{'intro': [...lines], '1': (title, [...lines]), ...} split on '## n. Title'."""
    parts, key, title = {"intro": ("", [])}, "intro", ""
    for line in text.splitlines():
        m = re.match(r"^##\s+(\d+)\.\s+(.*)$", line)
        if m:
            key, title = m.group(1), m.group(2)
            parts[key] = (title, [])
        else:
            parts[key][1].append(line)
    return parts


TURN = re.compile(r"^\*\*(Patient|Vera)([^*]*?):\*\*\s*(.*)$")
NOTE_ONLY = re.compile(r"^\*\((.+)\)\*$")
TRAILING_NOTE = re.compile(r"^(.*?)\s*\*\((.+)\)\*$")


def parse_turns(quote_lines):
    turns = []
    for raw in quote_lines:
        s = raw.strip()
        if not s:
            continue
        m = TURN.match(s)
        if m:
            who, label, said = m.group(1), m.group(2).strip(), m.group(3).strip()
            note = None
            t = TRAILING_NOTE.match(said)
            if t:
                said, note = t.group(1).strip(), t.group(2).strip()
            turn = {"who": who, "said": said, "notes": [], "tag": "", "detail": "", "kind": who.lower()}
            inside = label.strip("(), ")
            if who == "Patient":
                bits = [b.strip() for b in inside.split(",", 1)]
                turn["tag"] = bits[0] if bits and bits[0] else ""
                turn["detail"] = bits[1] if len(bits) > 1 else ""
            elif "thinking" in label:
                turn["kind"] = "thinking"
            elif "emergency" in label:
                turn["kind"], turn["detail"] = "emergency", inside.replace("emergency", "", 1).strip(", ")
            if note == "assessment":
                if said:
                    turns.append(turn)
                turns.append({"kind": "assessment"})
                continue
            if note:
                turn["notes"].append(note)
            turns.append(turn)
            continue
        m = NOTE_ONLY.match(s)
        if m and turns and turns[-1]["kind"] != "assessment":
            turns[-1]["notes"].append(m.group(1))
        elif m:
            turns.append({"kind": "note", "said": m.group(1)})
    return turns


def render_turns(turns):
    out = ['<div class="script">']
    for t in turns:
        k = t["kind"]
        if k == "assessment":
            out.append('<div class="turn assessment"><div class="who"></div>'
                       '<div class="said">Vera gives the assessment</div></div>')
            continue
        if k == "note":
            out.append(f'<div class="turn note-row"><div class="who"></div><div class="said"><div class="note">{inline(t["said"])}</div></div></div>')
            continue
        if k == "patient":
            tag = t["tag"].lower()
            cls = "real" if tag.startswith("real") else "expected" if tag.startswith("expected") else "other"
            who = f'Patient <span class="tag {cls}">{html.escape(t["tag"])}</span>'
            if t["detail"]:
                who += f'<span class="detail">{inline(t["detail"])}</span>'
        elif k == "thinking":
            who = 'Vera <span class="tag thinking">what I\'m thinking</span>'
        elif k == "emergency":
            who = 'Vera <span class="tag emergency">emergency message</span>'
            if t["detail"]:
                who += f'<span class="detail">{inline(t["detail"])}</span>'
        else:
            who = "Vera"
        notes = "".join(f'<div class="note">{inline(n)}</div>' for n in t["notes"])
        said = inline(t["said"])
        out.append(f'<div class="turn {k}"{anchor(who + " " + said)}><div class="who">{who}</div>'
                   f'<div class="said"><p>{said}</p>{notes}</div></div>')
    out.append("</div>")
    return "\n".join(out)


def parse_episodes(lines):
    """Section 5: (intro lines, summary rows by letter, [episodes])."""
    intro, episodes, cur = [], [], None
    for line in lines:
        m = re.match(r"^###\s+([A-Z])\.\s+`([^`]+)`:\s*(.*)$", line)
        if m:
            cur = {"letter": m.group(1), "id": m.group(2), "title": m.group(3).strip(), "quote": [], "after": []}
            episodes.append(cur)
        elif cur is None:
            intro.append(line)
        elif line.startswith(">"):
            cur["quote"].append(line[1:].strip())
        elif line.strip() and line.strip() != "---":
            cur["after"].append(line.strip())
    rows = {}
    tbl = [x for x in intro if x.strip().startswith("|")]
    if tbl:
        head = [c.strip() for c in tbl[0].strip().strip("|").split("|")]
        for r in tbl[2:]:
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            rows[cells[0]] = dict(zip(head, cells))
    return [x for x in intro if not x.strip().startswith("|")], rows, episodes


def meta_value(row, *words):
    for k, v in row.items():
        if all(w in k.lower() for w in words):
            return v
    return ""


def build():
    text = SRC.read_text()
    secs = split_sections(text)
    intro_title = next((ln[2:].strip() for ln in secs["intro"][1] if ln.startswith("# ")), "The ideal conversation")
    intro_lines = [ln for ln in secs["intro"][1] if not ln.startswith("# ")]

    ep_title, ep_lines = secs["5"]
    ep_intro, summary, episodes = parse_episodes(ep_lines)
    for e in episodes:
        EPISODE_IDS[e["id"]] = e["letter"]

    # intro: the "what to look for" list goes on the Episodes tab; the rest goes in "About this draft"
    look_at = next((i for i, ln in enumerate(intro_lines) if "What to look for" in ln), None)
    about = intro_lines[:look_at] if look_at is not None else intro_lines
    look = intro_lines[look_at:] if look_at is not None else []

    picker, articles, options = [], [], []
    for n, e in enumerate(episodes):
        row = summary.get(e["letter"], {})
        case = re.sub(r"\s*\(`[^`]+`\)\s*$", "", meta_value(row, "case")) or e["title"]
        ptype = meta_value(row, "patient type")
        counts = meta_value(row, "original")
        expected = meta_value(row, "expected")
        shows = meta_value(row, "shows")
        title = e["title"][:1].upper() + e["title"][1:]
        options.append(f'<option value="{e["letter"]}">{e["letter"]} · {html.escape(re.sub(r"[`*]", "", case))}</option>')
        picker.append(
            f'<button class="pick" data-ep="{e["letter"]}"><span class="letter">{e["letter"]}</span>'
            f'<span class="pick-text"><span class="pick-title">{inline(case)}</span>'
            f'<span class="pick-sub">{inline(ptype)}{" · " + inline(counts) if counts else ""}</span></span></button>')
        prev_l = episodes[n - 1]["letter"] if n > 0 else None
        next_l = episodes[n + 1]["letter"] if n + 1 < len(episodes) else None
        nav = '<div class="ep-nav">' + (
            f'<a href="#episode-{prev_l}">← Episode {prev_l}</a>' if prev_l else "<span></span>") + (
            f'<a href="#episode-{next_l}">Episode {next_l} →</a>' if next_l else "<span></span>") + "</div>"
        facts = "".join(
            f'<div class="fact"><span class="fact-k">{k}</span><span class="fact-v">{inline(v)}</span></div>'
            for k, v in (("Patient type", ptype), ("Patient messages, real → ideal", counts),
                         ("Lines that are expected, not real", expected), ("What it shows", shows)) if v)
        CTX["section"] = f'ep-{e["letter"]}'
        h2 = inline(title)
        h2_attr = anchor("episode " + h2)
        script = render_turns(parse_turns(e["quote"]))
        after = ""
        for a in e["after"]:
            a_html = inline(a.strip("*") if a.startswith("*") and a.endswith("*") else a)
            after += f'<div class="after"{anchor(a_html)}>{a_html}</div>'
        articles.append(
            f'<article class="episode" id="ep-{e["letter"]}" data-ep="{e["letter"]}" data-section="ep-{e["letter"]}" hidden>'
            f'<header class="ep-head"><p class="eyebrow">Episode {e["letter"]} · <code>{e["id"]}</code></p>'
            f'<h2{h2_attr}>{h2}</h2><div class="facts">{facts}</div></header>'
            f'{script}{after}<div class="orphans" data-orphans="ep-{e["letter"]}"></div>{nav}</article>')

    select = "".join(options)

    def sec(key, panel):
        CTX["section"] = panel
        title, lines = secs[key]
        h2 = inline(title)
        return f'<section class="doc-sec"><h2{anchor(h2)}>{h2}</h2>{blocks(lines)}</section>'

    CTX["section"] = "about"
    about_html = blocks(about)
    CTX["section"] = "episodes"
    look_html = blocks(look)
    how_html = blocks(ep_intro)
    summary_html = table([x for x in ep_lines if x.strip().startswith("|")][:len(episodes) + 2])

    tabs = [
        ("episodes", f"Episodes ({len(episodes)})"),
        ("findings", "Findings"),
        ("shape", "Goal &amp; shape"),
        ("rewrites", "Rewrites"),
        ("evidence", "Evidence &amp; prompt"),
        ("decisions", "Decisions"),
    ]
    panels = {
        "findings": sec("1", "findings"),
        "shape": sec("2", "shape") + sec("3", "shape"),
        "rewrites": sec("4", "rewrites"),
        "evidence": sec("6", "evidence") + sec("7", "evidence"),
        "decisions": sec("8", "decisions"),
    }
    tab_html = "".join(f'<a class="tab" href="#{k}" data-tab="{k}">{v}</a>' for k, v in tabs)
    panel_html = "".join(f'<div class="panel" data-panel="{k}" hidden>{v}<div class="orphans" data-orphans="{k}"></div></div>'
                         for k, v in panels.items())
    updated = datetime.fromtimestamp(SRC.stat().st_mtime).strftime("%d %b %Y, %H:%M")

    page = TEMPLATE
    for k, v in {
        "{{TITLE}}": inline(intro_title),
        "{{TITLE_TEXT}}": html.escape(re.sub(r"[`*]", "", intro_title)),
        "{{ABOUT}}": about_html,
        "{{LOOK}}": look_html,
        "{{HOW_TO_READ}}": how_html,
        "{{SUMMARY}}": summary_html,
        "{{SB_URL}}": SUPABASE_URL,
        "{{SB_KEY}}": SUPABASE_ANON_KEY,
        "{{EP_TITLE}}": inline(ep_title),
        "{{PICKER}}": "".join(picker),
        "{{SELECT}}": select,
        "{{ARTICLES}}": "".join(articles),
        "{{TABS}}": tab_html,
        "{{PANELS}}": panel_html,
        "{{UPDATED}}": updated,
        "{{FIRST}}": episodes[0]["letter"] if episodes else "",
    }.items():
        page = page.replace(k, v)
    (HERE / "index.html").write_text(page)
    print(f"index.html: {len(episodes)} episodes ({', '.join(e['letter'] for e in episodes)}), "
          f"{sum(len(parse_turns(e['quote'])) for e in episodes)} lines, from {SRC}")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Ideal Conversation Review</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #f7f6f2; --surface: #ffffff; --ink: #1d1d1b; --muted: #6b6a64; --line: #e4e1d8;
  --accent: #2f5d50; --accent-soft: #e6efeb; --real: #2e6b3f; --real-bg: #e5f1e7;
  --expected: #8a5a00; --expected-bg: #fbefd6; --think: #36507a; --think-bg: #e8eef8;
  --danger: #9b2c2c; --danger-bg: #f9e5e3; --code: #f0eee8;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #151614; --surface: #1d1f1c; --ink: #ecebe6; --muted: #a3a29b; --line: #33352f;
    --accent: #8cc4b1; --accent-soft: #23302b; --real: #93d1a2; --real-bg: #1f3125;
    --expected: #e7bd6b; --expected-bg: #3a2f17; --think: #a9c1ea; --think-bg: #222c3d;
    --danger: #f0a29a; --danger-bg: #3d2221; --code: #2a2c27;
  }
}
:root[data-theme="dark"] {
  --bg: #151614; --surface: #1d1f1c; --ink: #ecebe6; --muted: #a3a29b; --line: #33352f;
  --accent: #8cc4b1; --accent-soft: #23302b; --real: #93d1a2; --real-bg: #1f3125;
  --expected: #e7bd6b; --expected-bg: #3a2f17; --think: #a9c1ea; --think-bg: #222c3d;
  --danger: #f0a29a; --danger-bg: #3d2221; --code: #2a2c27;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.6 Inter, system-ui, -apple-system, sans-serif; }
a { color: var(--accent); }
code, a.ep { font: 12.5px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--code); padding: 1px 5px; border-radius: 4px; }
a.ep { text-decoration: none; border: 1px solid var(--line); }
a.ep:hover { border-color: var(--accent); }
.name { font: 600 11px/1 Inter, sans-serif; letter-spacing: .04em; text-transform: uppercase; color: var(--muted);
  border: 1px dashed var(--muted); border-radius: 4px; padding: 2px 5px; vertical-align: 1px; }
.wrap { max-width: 1160px; margin: 0 auto; padding: 0 16px; }
.top { background: var(--surface); border-bottom: 1px solid var(--line); }
.top .wrap { padding-top: 28px; }
.kicker { margin: 0; color: var(--muted); font-size: 13px; letter-spacing: .02em; }
h1 { font: 600 clamp(24px, 3.4vw, 32px)/1.2 "Source Serif 4", Georgia, serif; margin: 6px 0 10px; }
.status { display: flex; flex-wrap: wrap; gap: 8px 16px; color: var(--muted); font-size: 13px; margin-bottom: 14px; }
.status b { color: var(--ink); font-weight: 600; }
details.about { margin: 0 0 18px; max-width: 820px; }
details.about summary { cursor: pointer; color: var(--accent); font-weight: 500; }
details.about p { color: var(--muted); }
nav.tabs { display: flex; gap: 4px; overflow-x: auto; scrollbar-width: none; margin-bottom: -1px; }
nav.tabs::-webkit-scrollbar { display: none; }
.tab { flex: none; padding: 10px 14px; text-decoration: none; color: var(--muted); font-weight: 500;
  border-bottom: 2px solid transparent; white-space: nowrap; }
.tab:hover { color: var(--ink); }
.tab.on { color: var(--ink); border-bottom-color: var(--accent); }
main.wrap { padding-top: 28px; padding-bottom: 64px; }
.callout { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px; margin-bottom: 18px; }
.callout p { margin: 0 0 6px; }
.callout ol { margin: 0; padding-left: 20px; }
.legend { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; color: var(--muted); font-size: 13px; margin: 0 0 18px; }
.layout { display: grid; grid-template-columns: 290px minmax(0, 1fr); gap: 28px; align-items: start; }
.picker { position: sticky; top: 16px; display: flex; flex-direction: column; gap: 6px; }
.picker h3 { margin: 0 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.pick { display: flex; gap: 10px; align-items: flex-start; text-align: left; width: 100%; padding: 10px 12px; border-radius: 9px;
  border: 1px solid var(--line); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.pick:hover { border-color: var(--accent); }
.pick.on { border-color: var(--accent); background: var(--accent-soft); }
.pick:focus-visible, .tab:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.letter { flex: none; width: 26px; height: 26px; border-radius: 6px; display: grid; place-items: center; font-weight: 600; font-size: 13px;
  background: var(--accent); color: var(--surface); }
.pick-text { display: flex; flex-direction: column; min-width: 0; }
.pick-title { font-weight: 500; font-size: 14px; line-height: 1.35; }
.pick-sub { color: var(--muted); font-size: 12.5px; }
.mobile-pick { display: none; margin-bottom: 16px; }
.mobile-pick label { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 4px; }
select { width: 100%; padding: 10px 12px; font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }
.episode { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 24px 28px 18px; }
.eyebrow { margin: 0; color: var(--muted); font-size: 13px; }
.ep-head h2 { font: 600 24px/1.25 "Source Serif 4", Georgia, serif; margin: 4px 0 14px; }
.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-bottom: 20px; }
.fact { background: var(--bg); border-radius: 8px; padding: 8px 12px; }
.fact-k { display: block; font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.fact-v { font-weight: 500; }
.script { border-top: 1px solid var(--line); }
.turn { display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.who { font-weight: 600; font-size: 13.5px; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; align-content: flex-start; }
.said p { margin: 0; font: 17px/1.55 "Source Serif 4", Georgia, serif; }
.turn.patient .said p { color: var(--ink); }
.turn.thinking { background: var(--think-bg); margin: 0 -14px; padding: 12px 14px; border-radius: 8px; border-bottom: 0; }
.turn.thinking + .turn { border-top: 1px solid var(--line); }
.turn.emergency .said { border-left: 3px solid var(--danger); padding-left: 12px; }
.turn.assessment .said { color: var(--muted); font-style: italic; }
.tag { font-weight: 600; font-size: 11px; letter-spacing: .03em; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; }
.tag.real { color: var(--real); background: var(--real-bg); }
.tag.expected { color: var(--expected); background: var(--expected-bg); }
.tag.thinking { color: var(--think); background: var(--surface); }
.tag.emergency { color: var(--danger); background: var(--danger-bg); }
.tag.other { color: var(--muted); background: var(--code); }
.detail { flex-basis: 100%; font-weight: 400; color: var(--muted); font-size: 12.5px; line-height: 1.35; }
.note { margin-top: 6px; color: var(--muted); font-size: 13.5px; padding-left: 10px; border-left: 2px solid var(--line); }
.after { margin-top: 18px; padding: 12px 14px; background: var(--accent-soft); border-radius: 8px; font-size: 14.5px; }
.ep-nav { display: flex; justify-content: space-between; margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--line); }
.ep-nav a { text-decoration: none; font-weight: 500; }
details.howto { margin-top: 18px; }
details.howto summary { cursor: pointer; color: var(--accent); font-weight: 500; }
.panel, .doc-sec { max-width: 900px; }
.panel[data-panel="episodes"] { max-width: none; }
.doc-sec + .doc-sec { margin-top: 40px; }
.doc-sec h2 { font: 600 26px/1.25 "Source Serif 4", Georgia, serif; margin: 0 0 14px; }
.doc-sec h3 { font-size: 17px; margin: 28px 0 10px; }
.doc-sec li { margin: 4px 0; }
.table { overflow-x: auto; margin: 12px 0 20px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; vertical-align: top; padding: 9px 12px; border-bottom: 1px solid var(--line); }
th { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); font-weight: 600; background: var(--bg); }
tr:last-child td { border-bottom: 0; }
pre { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; overflow-x: auto;
  font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }
footer { color: var(--muted); font-size: 12.5px; padding: 24px 0 40px; border-top: 1px solid var(--line); }
/* comments */
.cbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: 0 0 14px; font-size: 13.5px; }
.cbar-btn { font: 500 13.5px Inter, system-ui, sans-serif; padding: 7px 12px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink); cursor: pointer; }
.cbar-btn:hover { border-color: var(--accent); }
.cbar-btn.primary { background: var(--accent); border-color: var(--accent); color: var(--surface); }
.cbar-btn:disabled { opacity: .6; cursor: default; }
.cbar-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.cbar-form input { font: inherit; padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); width: 170px; }
.cbar-on { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; color: var(--muted); }
.cbar-on b { color: var(--ink); }
.linkish { background: none; border: 0; padding: 0; font: inherit; color: var(--accent); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.c-err { color: var(--danger); font-size: 13px; }
.commenting [data-c] { position: relative; padding-right: 52px; }
.commenting tr[data-c] { padding-right: 0; }
.commenting tr[data-c] > td:last-child { position: relative; padding-right: 58px; }
.c-btn { display: none; position: absolute; top: 2px; right: 0; align-items: center; font: 500 12px/1 Inter, system-ui, sans-serif;
  padding: 4px 7px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--muted); cursor: pointer; z-index: 2; }
.turn > .c-btn { top: 12px; }
td > .c-btn { top: 8px; right: 6px; }
.c-btn:hover { border-color: var(--accent); color: var(--accent); }
.c-btn.has { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
.commenting [data-c]:hover > .c-btn, .commenting tr[data-c]:hover > td > .c-btn, .commenting .tapped > .c-btn,
.commenting .tapped > td > .c-btn, .commenting .c-btn.has, .commenting .c-btn.open { display: inline-flex; }
::highlight(cquote) { background-color: rgba(255, 205, 0, .38); }
.sel-btn { position: absolute; z-index: 20; font: 600 12.5px Inter, system-ui, sans-serif; padding: 7px 11px; border-radius: 8px; border: 0;
  background: var(--ink); color: var(--surface); box-shadow: 0 4px 14px rgba(0, 0, 0, .2); cursor: pointer; }
.thread { margin: 6px 0 14px; padding: 12px 14px; border: 1px solid var(--line); border-left: 3px solid var(--accent); border-radius: 8px;
  background: var(--surface); font: 14px/1.5 Inter, system-ui, sans-serif; color: var(--ink); text-align: left; }
tr.thread-row > td { background: var(--bg); padding: 2px 12px 8px; }
.c-item { padding: 8px 0; border-bottom: 1px solid var(--line); }
.t-items > .c-item:last-child { border-bottom: 0; }
.c-replies { margin: 6px 0 0 6px; padding-left: 12px; border-left: 2px solid var(--line); }
.c-replies .c-item { border-bottom: 0; padding: 6px 0; }
.c-meta { font-size: 12.5px; color: var(--muted); }
.c-meta b { color: var(--ink); font-weight: 600; }
.c-q { margin: 4px 0; padding: 1px 8px; border-left: 3px solid #e2bf2c; color: var(--muted); font-style: italic; }
.c-body { white-space: pre-wrap; overflow-wrap: anywhere; }
.c-acts { display: flex; gap: 12px; align-items: center; font-size: 12.5px; margin-top: 3px; color: var(--muted); }
.t-empty { color: var(--muted); font-size: 13px; margin: 0 0 6px; }
.t-ctx { font-size: 12.5px; color: var(--muted); margin: 8px 0 6px; display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
.t-ctx q { font-style: italic; color: var(--ink); }
.thread textarea { display: block; width: 100%; min-height: 64px; resize: vertical; font: inherit; padding: 8px 10px; border: 1px solid var(--line);
  border-radius: 8px; background: var(--bg); color: var(--ink); }
.thread textarea:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.t-actions { display: flex; gap: 12px; align-items: center; margin-top: 8px; }
.orphans:empty { display: none; }
.orphans { margin-top: 22px; padding: 12px 14px; border: 1px dashed var(--muted); border-radius: 10px; }
.orphans h4 { margin: 0 0 4px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.orphan-line { font-size: 13.5px; color: var(--muted); margin: 12px 0 4px; }
.pick { position: relative; }
.pick-c, .tab-c { font: 600 11px/1 Inter, system-ui, sans-serif; color: var(--accent); background: var(--accent-soft); border-radius: 999px; padding: 3px 6px; }
.pick-c { position: absolute; top: 8px; right: 8px; }
.pick:has(.pick-c) { padding-right: 56px; }
.tab-c { margin-left: 6px; }
@media (max-width: 860px) {
  .layout { grid-template-columns: 1fr; }
  .picker { display: none; }
  .mobile-pick { display: block; }
  .episode { padding: 18px 16px 14px; }
  .turn { grid-template-columns: 1fr; gap: 4px; }
  .turn.thinking { margin: 0 -8px; padding: 12px 8px; }
}
</style>
</head>
<body>
<div class="top">
  <div class="wrap">
    <p class="kicker">ForLife · Vera chat redesign · PM review</p>
    <h1>{{TITLE}}</h1>
    <div class="status"><span><b>Draft</b> for discussion</span><span>Question order not yet reviewed by a doctor</span><span>Updated {{UPDATED}}</span></div>
    <div class="cbar">
      <button type="button" class="cbar-btn" id="c-on">💬 Turn on comments</button>
      <form class="cbar-form" id="c-form" hidden>
        <input id="c-name" placeholder="Your name" maxlength="40" autocomplete="name" aria-label="Your name" required>
        <input id="c-pass" type="password" placeholder="Passcode" autocomplete="current-password" aria-label="Passcode" required>
        <button type="submit" class="cbar-btn primary">Turn on</button>
        <span class="c-err" id="c-form-err" role="alert"></span>
      </form>
      <div class="cbar-on" id="c-status" hidden>
        <span>💬 Commenting as <b id="c-who"></b></span>
        <span id="c-total"></span>
        <span class="cbar-hint">Point at a line and click 💬, or select words and click <b>Comment</b>.</span>
        <button type="button" class="linkish" id="c-refresh">Refresh</button>
        <button type="button" class="linkish" id="c-off">Turn off</button>
      </div>
    </div>
    <details class="about"><summary>About this draft</summary>{{ABOUT}}<div class="orphans" data-orphans="about"></div></details>
    <nav class="tabs" aria-label="Sections">{{TABS}}</nav>
  </div>
</div>
<main class="wrap">
  <div class="panel" data-panel="episodes" hidden>
    <div class="callout">{{LOOK}}</div>
    <div class="legend">
      <span><span class="tag real">real</span> the patient's actual words</span>
      <span><span class="tag expected">expected</span> built from facts they gave later</span>
      <span><span class="tag thinking" style="background:var(--think-bg)">what I'm thinking</span> one extra message from Vera</span>
      <span><span class="name">name</span> a real name, left out</span>
    </div>
    <div class="layout">
      <aside class="picker" aria-label="Choose an episode"><h3>Choose an episode</h3>{{PICKER}}</aside>
      <div>
        <div class="mobile-pick"><label for="ep-select">Episode</label><select id="ep-select">{{SELECT}}</select></div>
        {{ARTICLES}}
        <details class="howto"><summary>How these were rebuilt, and all nine at a glance</summary>{{HOW_TO_READ}}{{SUMMARY}}</details>
        <div class="orphans" data-orphans="episodes"></div>
      </div>
    </div>
  </div>
  {{PANELS}}
</main>
<footer class="wrap">Built from <code>ideal_conversation.md</code>. Episode ids like <code>39ae9855-1</code> point to the real chat, kept privately. The app and its prompt are unchanged.</footer>
<script>
(function () {
  var panels = document.querySelectorAll('.panel');
  var tabs = document.querySelectorAll('.tab');
  var picks = document.querySelectorAll('.pick');
  var articles = document.querySelectorAll('.episode');
  var select = document.getElementById('ep-select');
  var first = '{{FIRST}}';
  function show(hash) {
    var h = (hash || '').replace(/^#/, '');
    var ep = null, tab = h || 'episodes';
    var m = h.match(/^episode-([A-Z])$/);
    if (m) { ep = m[1]; tab = 'episodes'; }
    if (!document.querySelector('.panel[data-panel="' + tab + '"]')) tab = 'episodes';
    panels.forEach(function (p) { p.hidden = p.dataset.panel !== tab; });
    tabs.forEach(function (t) { t.classList.toggle('on', t.dataset.tab === tab); if (t.dataset.tab === tab) t.setAttribute('aria-current', 'page'); else t.removeAttribute('aria-current'); });
    if (tab === 'episodes') {
      if (!ep || !document.getElementById('ep-' + ep)) ep = first;
      articles.forEach(function (a) { a.hidden = a.dataset.ep !== ep; });
      picks.forEach(function (b) { b.classList.toggle('on', b.dataset.ep === ep); b.setAttribute('aria-pressed', b.dataset.ep === ep); });
      if (select) select.value = ep;
    }
  }
  picks.forEach(function (b) { b.addEventListener('click', function () { location.hash = 'episode-' + b.dataset.ep; }); });
  if (select) select.addEventListener('change', function () { location.hash = 'episode-' + select.value; });
  window.addEventListener('hashchange', function () { show(location.hash); window.scrollTo({ top: 0 }); });
  show(location.hash);
})();
</script>
<script>
/* Comments: stored in Supabase, reached only through passcode-checked functions. All comment text is set with
   textContent, never as HTML. */
(function () {
  var CFG = { url: '{{SB_URL}}', key: '{{SB_KEY}}' };
  function get(k) { try { return localStorage.getItem('review_' + k); } catch (e) { return null; } }
  function put(k, v) { try { if (v == null) localStorage.removeItem('review_' + k); else localStorage.setItem('review_' + k, v); } catch (e) {} }
  var S = { pass: get('pass'), name: get('name'), list: [], on: false, open: null };
  var $ = function (id) { return document.getElementById(id); };
  var hoverless = window.matchMedia && window.matchMedia('(hover: none)').matches;

  function rpc(fn, args) {
    return fetch(CFG.url + '/rest/v1/rpc/' + fn, {
      method: 'POST',
      headers: { apikey: CFG.key, Authorization: 'Bearer ' + CFG.key, 'Content-Type': 'application/json' },
      body: JSON.stringify(args)
    }).then(function (r) {
      return r.text().then(function (t) {
        var d = null;
        try { d = t ? JSON.parse(t) : null; } catch (e) { /* not JSON */ }
        if (!r.ok) throw new Error((d && d.message) || ('error ' + r.status));
        return d;
      });
    });
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function button(cls, text, fn) { var b = el('button', cls, text); b.type = 'button'; b.addEventListener('click', fn); return b; }
  function when(iso) {
    var d = new Date(iso), s = (Date.now() - d.getTime()) / 1000;
    if (s < 60) return 'just now';
    if (s < 3600) return Math.floor(s / 60) + ' min ago';
    if (s < 86400) return Math.floor(s / 3600) + ' h ago';
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) + ', ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }
  function panelOf(section) { return (section.indexOf('ep-') === 0 || section === 'episodes') ? 'episodes' : section; }
  function blockFor(anchor) { return document.querySelector('[data-c="' + CSS.escape(anchor) + '"]'); }
  function btnHost(block) { return block.tagName === 'TR' ? block.lastElementChild : block; }
  function lineText(block) {
    var c = block.cloneNode(true);
    c.querySelectorAll('.c-btn, .thread-wrap').forEach(function (x) { x.remove(); });
    return c.textContent.replace(/\s+/g, ' ').trim().slice(0, 2000);
  }
  function byId(id) { for (var i = 0; i < S.list.length; i++) if (S.list[i].id === id) return S.list[i]; return null; }
  function tops(anchor) { return S.list.filter(function (c) { return c.anchor === anchor && !c.parent_id; }); }
  function replies(id) { return S.list.filter(function (c) { return c.parent_id === id; }); }

  // ---------- one thread: the comments on one line, with a box to add one ----------
  function buildThread(anchor, quote, keepOpen) {
    var st = { replyTo: null, quote: quote || null };
    var box = el('div', 'thread'); box.dataset.anchor = anchor;
    var items = el('div', 't-items');
    var ctx = el('div', 't-ctx');
    var ta = el('textarea'); ta.placeholder = 'Add a comment…'; ta.maxLength = 4000; ta.setAttribute('aria-label', 'Your comment');
    var err = el('span', 'c-err');
    var post = button('cbar-btn primary', 'Comment', send);
    var acts = el('div', 't-actions'); acts.append(post);
    if (!keepOpen) acts.append(button('linkish', 'Close', function () { closeThread(); decorate(); }));
    acts.append(err);
    box.append(items, ctx, ta, acts);

    function context() {
      ctx.textContent = '';
      var r = st.replyTo && byId(st.replyTo);
      if (r) ctx.append(el('span', null, 'Replying to ' + r.author));
      else if (st.quote) ctx.append(el('span', null, 'On the words'), el('q', null, st.quote));
      ctx.hidden = !(r || st.quote);
      if (!ctx.hidden) ctx.append(button('linkish', 'clear', function () { st.replyTo = null; st.quote = null; context(); }));
      post.textContent = r ? 'Reply' : 'Comment';
      ta.placeholder = r ? 'Write a reply…' : 'Add a comment…';
    }
    function fill() {
      items.textContent = '';
      var list = tops(anchor);
      if (!list.length) items.append(el('p', 't-empty', 'No comments yet.'));
      list.forEach(function (c) { items.append(item(c)); });
    }
    function item(c) {
      var d = el('div', 'c-item');
      var meta = el('div', 'c-meta'); meta.append(el('b', null, c.author), document.createTextNode(' · ' + when(c.created_at)));
      meta.title = new Date(c.created_at).toLocaleString();
      d.append(meta);
      if (c.quote) d.append(el('div', 'c-q', '“' + c.quote + '”'));
      d.append(el('div', 'c-body', c.body));
      var acts = el('div', 'c-acts');
      if (!c.parent_id) acts.append(button('linkish', 'Reply', function () { st.replyTo = c.id; st.quote = null; context(); ta.focus(); }));
      var del = button('linkish', 'Delete', function () {
        acts.textContent = '';
        acts.append(el('span', null, c.parent_id ? 'Delete this reply?' : 'Delete this comment and its replies?'),
          button('linkish', 'Yes, delete', function () { remove(c, acts); }),
          button('linkish', 'No', function () { fill(); }));
      });
      acts.append(del);
      d.append(acts);
      var rs = replies(c.id);
      if (rs.length) { var wrap = el('div', 'c-replies'); rs.forEach(function (x) { wrap.append(item(x)); }); d.append(wrap); }
      return d;
    }
    function send() {
      var body = ta.value.trim();
      if (!body) { ta.focus(); return; }
      var parent = st.replyTo ? byId(st.replyTo) : null;
      var block = blockFor(anchor);
      post.disabled = true; err.textContent = '';
      rpc('add_comment', {
        p_passcode: S.pass, p_anchor: anchor,
        p_section: parent ? parent.section : anchor.split(':')[0],
        p_line_text: block ? lineText(block) : (parent ? parent.line_text : ''),
        p_quote: parent ? null : st.quote, p_parent_id: parent ? parent.id : null,
        p_author: S.name, p_body: body
      }).then(function (row) {
        S.list.push(row); ta.value = ''; st.replyTo = null; st.quote = null;
        context(); fill(); decorate();
      }).catch(function (e) { err.textContent = 'Not saved: ' + e.message; })
        .then(function () { post.disabled = false; });
    }
    function remove(c, acts) {
      rpc('delete_comment', { p_passcode: S.pass, p_id: c.id }).then(function () {
        var gone = {}; gone[c.id] = true;
        S.list = S.list.filter(function (x) { return !gone[x.id] && !gone[x.parent_id]; });
        refill(); decorate();
      }).catch(function (e) { acts.textContent = ''; acts.append(el('span', 'c-err', 'Not deleted: ' + e.message)); });
    }
    box._fill = fill;
    context(); fill();
    return box;
  }
  function refill() { document.querySelectorAll('.thread').forEach(function (t) { if (t._fill) t._fill(); }); }

  function closeThread() {
    document.querySelectorAll('.thread-wrap.line').forEach(function (x) { x.remove(); });
    S.open = null;
  }
  function openThread(anchor, quote) {
    closeThread();
    var block = blockFor(anchor);
    if (!block) return;
    S.open = anchor;
    var box = buildThread(anchor, quote, false), wrap;
    if (block.tagName === 'TR') {
      wrap = el('tr', 'thread-wrap line thread-row');
      var td = el('td'); td.colSpan = block.children.length; td.append(box); wrap.append(td);
      block.after(wrap);
    } else {
      wrap = el('div', 'thread-wrap line'); wrap.append(box);
      if (block.tagName === 'LI') block.append(wrap); else block.after(wrap);
    }
    decorate();
    var ta = box.querySelector('textarea');
    if (ta) ta.focus();
  }

  // ---------- markers on the page ----------
  function setBadge(node, cls, n) {
    var b = node.querySelector('.' + cls);
    if (!n) { if (b) b.remove(); return; }
    if (!b) { b = el('span', cls); node.append(b); }
    b.textContent = '💬 ' + n;
  }
  function decorate() {
    var count = {};
    S.list.forEach(function (c) { count[c.anchor] = (count[c.anchor] || 0) + 1; });
    document.querySelectorAll('[data-c]').forEach(function (block) {
      var host = btnHost(block);
      if (!host) return;
      var b = host.querySelector(':scope > .c-btn');
      if (!b) {
        b = button('c-btn', '', function (ev) {
          ev.stopPropagation();
          if (S.open === block.dataset.c) { closeThread(); decorate(); } else openThread(block.dataset.c, null);
        });
        host.append(b);
      }
      var n = count[block.dataset.c] || 0;
      b.textContent = n ? '💬 ' + n : '💬';
      b.title = n ? n + (n > 1 ? ' comments' : ' comment') : 'Comment on this';
      b.setAttribute('aria-label', b.title);
      b.classList.toggle('has', n > 0);
      b.classList.toggle('open', S.open === block.dataset.c);
    });
    document.querySelectorAll('.pick').forEach(function (p) {
      setBadge(p, 'pick-c', S.list.filter(function (c) { return c.section === 'ep-' + p.dataset.ep; }).length);
    });
    document.querySelectorAll('.tab').forEach(function (t) {
      setBadge(t, 'tab-c', S.list.filter(function (c) { return panelOf(c.section) === t.dataset.tab; }).length);
    });
    $('c-total').textContent = S.list.length + (S.list.length === 1 ? ' comment' : ' comments');
    orphans();
    highlight();
  }

  // comments whose line was reworded or removed: keep them visible at the end of their section
  function orphans() {
    var groups = {};
    S.list.forEach(function (c) {
      if (c.parent_id || blockFor(c.anchor)) return;
      var box = document.querySelector('.orphans[data-orphans="' + CSS.escape(c.section) + '"]') || document.querySelector('.orphans[data-orphans="episodes"]');
      var key = box.dataset.orphans;
      (groups[key] = groups[key] || {})[c.anchor] = c.line_text;
    });
    document.querySelectorAll('.orphans').forEach(function (box) {
      var g = groups[box.dataset.orphans] || {};
      var sig = Object.keys(g).sort().join('|');
      if (box.dataset.sig === sig) return;
      box.dataset.sig = sig;
      box.textContent = '';
      if (!sig) return;
      box.append(el('h4', null, 'Comments on lines that have changed since'));
      Object.keys(g).forEach(function (a) {
        box.append(el('div', 'orphan-line', 'The line was: ' + (g[a] || '(unknown)')));
        var wrap = el('div', 'thread-wrap'); wrap.append(buildThread(a, null, true)); box.append(wrap);
      });
    });
  }

  // yellow highlight on the words a comment was made on
  function findRange(root, quote) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) { return n.parentElement && n.parentElement.closest('.c-btn, .thread-wrap') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; }
    });
    var nodes = [], text = '', n;
    while ((n = walker.nextNode())) { nodes.push([n, text.length]); text += n.data; }
    var i = text.toLowerCase().indexOf(quote.toLowerCase());
    if (i < 0) return null;
    var end = i + quote.length, r = document.createRange(), started = false;
    for (var k = 0; k < nodes.length; k++) {
      var node = nodes[k][0], off = nodes[k][1], len = node.data.length;
      if (!started && i < off + len) { r.setStart(node, i - off); started = true; }
      if (started && end <= off + len) { r.setEnd(node, end - off); return r; }
    }
    return null;
  }
  function highlight() {
    if (!window.CSS || !CSS.highlights || typeof Highlight === 'undefined') return;
    var ranges = [];
    S.list.forEach(function (c) {
      if (!c.quote) return;
      var b = blockFor(c.anchor);
      var r = b && findRange(b, c.quote);
      if (r) ranges.push(r);
    });
    CSS.highlights.set('cquote', new Highlight(...ranges));
  }

  // ---------- select words, then "Comment" ----------
  var selBtn = button('sel-btn', 'Comment', function () {
    if (!pending) return;
    var p = pending; pending = null; selBtn.hidden = true;
    var sel = window.getSelection(); if (sel) sel.removeAllRanges();
    openThread(p.anchor, p.quote);
  });
  selBtn.hidden = true;
  selBtn.addEventListener('mousedown', function (e) { e.preventDefault(); });
  document.body.append(selBtn);
  var pending = null;
  function blockOf(node) {
    var e = node && (node.nodeType === 1 ? node : node.parentElement);
    if (!e || e.closest('.thread-wrap, .c-btn, .cbar, .sel-btn')) return null;
    return e.closest('[data-c]');
  }
  function onSelect() {
    if (!S.on) return;
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) { selBtn.hidden = true; return; }
    var q = sel.toString().replace(/\s+/g, ' ').trim();
    var r = sel.getRangeAt(0), a = blockOf(r.startContainer), b = blockOf(r.endContainer);
    if (!q || !a || a !== b || q.length > 1000) { selBtn.hidden = true; return; }
    var rect = r.getBoundingClientRect();
    selBtn.style.top = Math.max(0, rect.top + window.scrollY - 42) + 'px';
    selBtn.style.left = Math.min(document.documentElement.clientWidth - 120, Math.max(8, rect.left + window.scrollX)) + 'px';
    selBtn.hidden = false;
    pending = { anchor: a.dataset.c, quote: q };
  }
  document.addEventListener('mouseup', function () { setTimeout(onSelect, 0); });
  document.addEventListener('keyup', function (e) { if (e.shiftKey) onSelect(); });
  document.addEventListener('selectionchange', function () { if (hoverless) setTimeout(onSelect, 300); });
  document.addEventListener('mousedown', function (e) { if (e.target !== selBtn) selBtn.hidden = true; });

  // phones have no hover: a tap on a line shows its 💬
  document.addEventListener('click', function (e) {
    if (!S.on || !hoverless || e.target.closest('a, button, input, textarea, select, .thread-wrap')) return;
    var b = e.target.closest('[data-c]');
    document.querySelectorAll('.tapped').forEach(function (x) { if (x !== b) x.classList.remove('tapped'); });
    if (b) b.classList.add('tapped');
  });

  // ---------- turning comments on and off ----------
  function turnOn(name, pass) {
    return rpc('list_comments', { p_passcode: pass }).then(function (rows) {
      S.name = name; S.pass = pass; put('name', name); put('pass', pass);
      S.list = rows || []; S.on = true;
      document.body.classList.add('commenting');
      $('c-on').hidden = true; $('c-form').hidden = true; $('c-status').hidden = false;
      $('c-who').textContent = name;
      decorate();
    });
  }
  function turnOff() {
    S.on = false; S.list = []; S.open = null; put('pass', null);
    document.body.classList.remove('commenting');
    document.querySelectorAll('.c-btn, .thread-wrap, .pick-c, .tab-c').forEach(function (x) { x.remove(); });
    document.querySelectorAll('.orphans').forEach(function (x) { x.textContent = ''; delete x.dataset.sig; });
    if (window.CSS && CSS.highlights) CSS.highlights.delete('cquote');
    $('c-status').hidden = true; $('c-on').hidden = false;
  }
  function refresh() {
    if (!S.on) return;
    rpc('list_comments', { p_passcode: S.pass }).then(function (rows) { S.list = rows || []; refill(); decorate(); }).catch(function () {});
  }
  $('c-on').addEventListener('click', function () {
    $('c-on').hidden = true; $('c-form').hidden = false;
    $('c-name').value = S.name || '';
    ($('c-name').value ? $('c-pass') : $('c-name')).focus();
  });
  $('c-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var n = $('c-name').value.trim(), p = $('c-pass').value;
    if (!n || !p) return;
    $('c-form-err').textContent = 'Checking…';
    turnOn(n, p).then(function () { $('c-form-err').textContent = ''; $('c-pass').value = ''; })
      .catch(function (err) { $('c-form-err').textContent = /passcode/.test(err.message) ? 'That passcode is not right.' : 'Could not connect: ' + err.message; });
  });
  $('c-off').addEventListener('click', turnOff);
  $('c-refresh').addEventListener('click', refresh);
  setInterval(function () { if (S.on && document.visibilityState === 'visible' && !document.querySelector('.thread textarea:focus')) refresh(); }, 45000);
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') refresh(); });
  if (S.pass && S.name) turnOn(S.name, S.pass).catch(function () { put('pass', null); });
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
