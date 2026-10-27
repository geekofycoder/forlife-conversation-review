"""Build index.html, the PM review page, from the ideal-conversation draft.

Usage:  python3 build.py [path/to/ideal_conversation.md]
Default source: ../ChatBot/benchmark/episodes/ideal_conversation.md
Writes index.html next to this file. Plain Python 3, no packages.
"""
import html
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "ChatBot/benchmark/episodes/ideal_conversation.md"

NAME = '<span class="name" title="A real name, left out">name</span>'
EPISODE_IDS = {}  # "b9d47118-1" -> "D", filled once the episodes are read, so ids elsewhere link to them


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
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
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
        inner = blocks([x[pad:] for x in rest]) if rest else ""
        items.append(f"<li>{inline(head)}{inner}</li>")
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
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
        elif re.match(r"#{3,4}\s", s):
            level = len(s.split()[0])
            out.append(f"<h{level}>{inline(s[level:].strip())}</h{level}>")
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
            out.append("<p>" + inline(" ".join(x.strip() for x in lines[i:j])) + "</p>")
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
        out.append(f'<div class="turn {k}"><div class="who">{who}</div><div class="said"><p>{inline(t["said"])}</p>{notes}</div></div>')
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
        after = "".join(f'<div class="after">{inline(a.strip("*") if a.startswith("*") and a.endswith("*") else a)}</div>'
                        for a in e["after"])
        articles.append(
            f'<article class="episode" id="ep-{e["letter"]}" data-ep="{e["letter"]}" hidden>'
            f'<header class="ep-head"><p class="eyebrow">Episode {e["letter"]} · <code>{e["id"]}</code></p>'
            f'<h2>{inline(title)}</h2><div class="facts">{facts}</div></header>'
            f'{render_turns(parse_turns(e["quote"]))}{after}{nav}</article>')

    select = "".join(options)

    def sec(key):
        title, lines = secs[key]
        return f'<section class="doc-sec"><h2>{inline(title)}</h2>{blocks(lines)}</section>'

    tabs = [
        ("episodes", f"Episodes ({len(episodes)})"),
        ("findings", "Findings"),
        ("shape", "Goal &amp; shape"),
        ("rewrites", "Rewrites"),
        ("evidence", "Evidence &amp; prompt"),
        ("decisions", "Decisions"),
    ]
    panels = {
        "findings": sec("1"),
        "shape": sec("2") + sec("3"),
        "rewrites": sec("4"),
        "evidence": sec("6") + sec("7"),
        "decisions": sec("8"),
    }
    tab_html = "".join(f'<a class="tab" href="#{k}" data-tab="{k}">{v}</a>' for k, v in tabs)
    panel_html = "".join(f'<div class="panel" data-panel="{k}" hidden>{v}</div>' for k, v in panels.items())
    updated = datetime.fromtimestamp(SRC.stat().st_mtime).strftime("%d %b %Y, %H:%M")

    page = TEMPLATE
    for k, v in {
        "{{TITLE}}": inline(intro_title),
        "{{TITLE_TEXT}}": html.escape(re.sub(r"[`*]", "", intro_title)),
        "{{ABOUT}}": blocks(about),
        "{{LOOK}}": blocks(look),
        "{{HOW_TO_READ}}": blocks(ep_intro),
        "{{SUMMARY}}": table([x for x in ep_lines if x.strip().startswith("|")][:len(episodes) + 2]),
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


TEMPLATE = """<!doctype html>
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
    <details class="about"><summary>About this draft</summary>{{ABOUT}}</details>
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
</body>
</html>
"""

if __name__ == "__main__":
    build()
