"""What the vault keeps for editing but the site never publishes.

Used by obsidian_to_jsonld.py (concept pages) and generate_skos_for_index.py
(index JSON-LD), so both apply exactly the same rules.

Which SECTIONS are published:
  - only the SKOS headings in SKOS_SECTIONS; any other  # heading  is private
  - nothing after a  # Work in Progress  heading, not even a SKOS heading
    (a hard stop: put drafts, LLM conversations, research notes below it)

Which LINES are dropped inside a published section:

  - Obsidian comments  %% ... %%  (inline or spanning lines), e.g. the marker
    that sync_hierarchy.py writes at the top of each # Broader section
  - task lines  - [ ] ...  and  - [x] ...  (editing to-dos, e.g. #Cite, #Edit)
  - the placeholder sentences from Templates/skos-note.md, which stay in the
    notes as writing prompts until they are replaced with real content
  - markdown separator lines (---, ***, ___): the homemade converter would
    print them literally, and the headings already separate the sections
"""
import re

# The prompt text from Templates/skos-note.md. A line is dropped only if it is
# exactly one of these (after trimming), so real content is never touched.
PLACEHOLDERS = {
    "supplies a complete explanation of the intended meaning of a concept",
    "this concept has broader concept X",
    "this concept has narrower concept Y",
    "enables the representation of associative (non-hierarchical) links, which can also be used to represent part-whole links that are not meant as hierarchical relationships.",
    "synonyms and near synonyms",
    "describes significant changes to the meaning or the form of a concept",
    "documents fine-grained changes to a concept, for the purposes of administration and maintenance (e.g. versioning)",
    "supplies information that is an aid to administrative housekeeping, such as reminders of editorial work still to be done, or warnings in the event that future editorial changes might be made",
    "supplies some, possibly partial, information about the intended meaning of a concept, especially as an indication of how the use of a concept is limited in indexing practice.",
}

# Level-1 headings that are published, in the vault's spelling.
SKOS_SECTIONS = [
    "Definition", "Broader", "Narrower", "Related", "Alternative Label",
    "Example", "History Note", "Change Note", "Editorial Note", "Scope Note",
]
WIP_HEADING = "work in progress"
H1 = re.compile(r"^#\s+(.+?)\s*$")

TASK = re.compile(r"^\s*[-*+]\s+\[[ xX]\]")
RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
INLINE_COMMENT = re.compile(r"%%.*?%%")


def clean_lines(lines):
    """Return the publishable lines, in order. Blank lines are kept (callers
    already ignore them); everything listed in the module docstring is dropped."""
    out, in_comment = [], False
    for line in lines:
        if in_comment:
            if "%%" in line:
                in_comment = False
                line = line.split("%%", 1)[1]
            else:
                continue
        line = INLINE_COMMENT.sub("", line)
        if "%%" in line:                      # comment opens and continues on later lines
            line, in_comment = line.split("%%", 1)[0], True
        if TASK.match(line) or RULE.match(line) or line.strip() in PLACEHOLDERS:
            continue
        if not line.strip() and out and not out[-1].strip():
            continue                          # collapse runs of blank lines
        out.append(line.rstrip())
    return out


def placeholder_count(text):
    """How many template placeholder lines a note still contains."""
    return sum(1 for line in text.split("\n") if line.strip() in PLACEHOLDERS)


def before_wip(text):
    """The part of a note above its  # Work in Progress  heading (all of it if none)."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = H1.match(line)
        if m and m.group(1).strip().lower() == WIP_HEADING:
            return "\n".join(lines[:i])
    return text


def publishable_sections(text):
    """{SKOS heading: [cleaned non-blank lines]} for the published part of a note.
    Sections under any other heading, and everything after Work in Progress,
    are left out. A SKOS heading that occurs twice is merged, in order."""
    canon = {h.lower(): h for h in SKOS_SECTIONS}
    sections, current = {}, None
    for line in clean_lines(before_wip(text).split("\n")):
        m = H1.match(line)
        if m:
            current = canon.get(m.group(1).strip().lower())
            if current:
                sections.setdefault(current, [])
        elif current and line.strip():
            sections[current].append(line.strip())
    return sections


def review(text):
    """What a writer may want to tidy in a note, as (kind, detail) pairs."""
    canon = {h.lower() for h in SKOS_SECTIONS}
    pub = before_wip(text)
    has_wip = pub != text
    lines = pub.split("\n")
    issues, seen, current = [], set(), None
    for i, line in enumerate(lines):
        m = H1.match(line)
        if m:
            name = m.group(1).strip()
            current = name.lower()
            if current not in canon:
                issues.append(("private heading above Work in Progress", name))
            elif current in seen:
                issues.append(("SKOS heading appears twice", name))
            seen.add(current)
        elif RULE.match(line) and current in canon:
            nxt = next((l for l in lines[i + 1:] if l.strip()), "")
            if not H1.match(nxt):
                issues.append(("--- inside a published section; text below it IS published",
                               f"under # {current.title()}"))
    return issues, has_wip
