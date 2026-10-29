"""Keep the broader/narrower hierarchy in the vault consistent (D-009).

The parent's  # Narrower  list is the master. Each note's  # Broader  section is
a generated copy, kept so both directions stay navigable in Obsidian.

    python sync_hierarchy.py              check only (default): report, change nothing
    python sync_hierarchy.py --fix        rewrite # Broader sections to match the parents
    python sync_hierarchy.py --promote    first add Broader-only links to the parent's # Narrower
    python sync_hierarchy.py --promote --fix   (both; the one-time migration)
    --skip-parent NAME   never promote into NAME (repeatable), e.g. a concept being rethought

--promote never adds a link that would create a loop; those are reported instead.

Only notes in the vault ROOT are considered (same rule as obsidian_to_jsonld.py).
--fix touches nothing but the # Broader section; --promote touches nothing but the
end of a parent's # Narrower list. Exit code 1 if the check finds problems.
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

GENERATED = "%% generated from parents' # Narrower by sync_hierarchy.py; edit the parent %%"
LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
H1 = re.compile(r"^#\s+(.+?)\s*$")


class Note:
    def __init__(self, path):
        self.path = path
        self.stem = path.stem
        self.text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", self.text, re.S)
        k = re.search(r"^concept-key:\s*(\S+)", m.group(1), re.M) if m else None
        self.key = k.group(1) if k else None

    def section_span(self, name):
        """(start, end) line indexes of a level-1 section's BODY, or None."""
        lines = self.text.split("\n")
        start = None
        for i, line in enumerate(lines):
            m = H1.match(line)
            if not m:
                continue
            if start is not None:
                return start, i
            if m.group(1).strip().lower() == name:
                start = i + 1
        return (start, len(lines)) if start is not None else None

    def links(self, name):
        span = self.section_span(name)
        if not span:
            return []
        body = self.text.split("\n")[span[0]:span[1]]
        return [x.strip() for line in body for x in LINK.findall(line)]


def load(vault):
    notes = {p.stem: Note(p) for p in sorted(Path(vault).glob("*.md"))}
    lower = {k.lower(): k for k in notes}
    resolve = lambda name: notes.get(name) or notes.get(lower.get(name.lower(), ""))
    return notes, resolve


def analyse(notes, resolve):
    parents = defaultdict(list)          # child stem -> [parent stems], in note order
    report = defaultdict(list)
    for p in notes.values():
        for name in p.links("narrower"):
            c = resolve(name)
            if not c:
                report["Narrower links to a missing note"].append(f"{p.stem} → [[{name}]]")
            elif c.stem == p.stem:
                report["Self-references (ignored)"].append(f"{p.stem} lists itself in # Narrower")
            elif p.stem not in parents[c.stem]:
                parents[c.stem].append(p.stem)

    # cycles in the master (Narrower) graph
    graph = defaultdict(list)
    for c, ps in parents.items():
        for p in ps:
            graph[p].append(c)
    seen_cycles = set()

    def dfs(node, path):
        for nxt in graph[node]:
            if nxt in path:
                cyc = path[path.index(nxt):]
                i = cyc.index(min(cyc))
                seen_cycles.add(" ⊃ ".join(cyc[i:] + cyc[:i] + [cyc[i]]))
            elif len(path) < 50:
                dfs(nxt, path + [nxt])
    for start in list(graph):
        dfs(start, [start])
    report["Loops in the # Narrower hierarchy (must be broken by hand)"] = sorted(seen_cycles)

    promote = defaultdict(list)          # parent stem -> [child stems] to append
    out_of_sync = []
    for n in notes.values():
        current = [resolve(x).stem if resolve(x) else x for x in n.links("broader")]
        expected = parents.get(n.stem, [])
        for b in current:
            if b == n.stem:
                report["Self-references (ignored)"].append(f"{n.stem} lists itself in # Broader")
            elif b not in expected and resolve(b):
                promote[b].append(n.stem)
        if sorted(set(current)) != sorted(expected):
            out_of_sync.append(n)
    for p, kids in sorted(promote.items()):
        report["Broader-only links (--promote adds them to the parent's # Narrower)"].append(
            f"{p} ← " + ", ".join(kids))
    report["# Broader out of sync (--fix rewrites)"] = [n.stem for n in out_of_sync]
    return parents, promote, report


def reaches(parents, start, target):
    """True if target is a descendant of start, i.e. start is an ancestor of target."""
    stack, seen = [target], set()
    while stack:
        n = stack.pop()
        if n == start:
            return True
        if n not in seen:
            seen.add(n)
            stack.extend(parents.get(n, []))
    return False


def rewrite_broader(note, parents):
    lines = note.text.split("\n")
    body = [GENERATED] + [f"- [[{p}]]" for p in parents]
    span = note.section_span("broader")
    if span:
        lines[span[0]:span[1]] = body
    else:
        nar = note.section_span("narrower")
        at = nar[0] - 1 if nar else len(lines)
        lines[at:at] = ["# Broader"] + body
    note.text = "\n".join(lines)


def append_narrower(note, children):
    lines = note.text.split("\n")
    span = note.section_span("narrower")
    new = [f"- [[{c}]]" for c in children]
    if span:
        end = span[1]
        while end > span[0] and not lines[end - 1].strip():   # keep blank lines after the list
            end -= 1
        lines[end:end] = new
    else:
        lines += ["# Narrower"] + new
    note.text = "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fix", action="store_true", help="rewrite # Broader sections")
    ap.add_argument("--promote", action="store_true", help="append Broader-only links to parents' # Narrower")
    ap.add_argument("--skip-parent", action="append", default=[], metavar="NAME",
                    help="do not promote into this parent (repeatable)")
    ap.add_argument("--vault", help="vault folder (default: vault_dir from config.toml)")
    args = ap.parse_args()

    if args.vault:
        vault = Path(args.vault)
    else:
        from vc_config import VAULT_DIR
        vault = VAULT_DIR
    notes, resolve = load(vault)
    parents, promote, report = analyse(notes, resolve)

    changed = set()
    refused = []
    if args.promote and promote:
        skip = {s.lower() for s in args.skip_parent}
        for p, kids in promote.items():
            if p.lower() in skip:
                refused += [f"{p} ← {k} (--skip-parent)" for k in kids]
                continue
            ok = []
            for k in kids:
                if p == k or reaches(parents, k, p):
                    refused.append(f"{p} ← {k} (would create a loop)")
                else:
                    ok.append(k)
                    parents[k].append(p)          # later checks see this link
            if ok:
                append_narrower(notes[p], ok)
                changed.add(p)
        parents, promote, report = analyse(notes, resolve)   # re-read the new master
    if args.fix:
        for n in notes.values():
            want = parents.get(n.stem, [])
            have = [resolve(x).stem if resolve(x) else x for x in n.links("broader")]
            if sorted(set(have)) != sorted(want) or (n.section_span("broader") and GENERATED not in n.text and want):
                rewrite_broader(n, want)
                changed.add(n.stem)
    for stem in sorted(changed):
        notes[stem].path.write_text(notes[stem].text, encoding="utf-8", newline="\n")
    if changed:
        parents, promote, report = analyse(notes, resolve)   # report the state after writing
    if refused:
        report["Not promoted (--fix drops them from # Broader)"] = refused

    problems = 0
    for title, items in report.items():
        if not items:
            continue
        problems += len(items)
        print(f"\n## {title} ({len(items)})")
        for i in items:
            print(f"- {i}")
    if changed:
        print(f"\n✏️  Wrote {len(changed)} notes: " + ", ".join(sorted(changed)))
    print("\n✅ Hierarchy in sync." if not problems else f"\n⚠️  {problems} items to look at.")
    sys.exit(1 if problems and not args.fix else 0)


if __name__ == "__main__":
    main()
