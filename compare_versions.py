"""Compare two built versions of the site, ignoring the version numbers themselves.

Use after a refactoring that should not change any content (for example the
vault move in 0.0.8): every page should come out the same as in the previous
version apart from its version number.

    python compare_versions.py 0.0.7 0.0.8

Prints the files found in only one version, then each file whose text differs
once both version strings are replaced by "<version>", with the first
differing line. Exit code 0 if nothing differs.
"""
import sys
from pathlib import Path

from vc_config import SITE_DIR

TEXT = {".html", ".json", ".jsonld", ".css", ".js", ".txt", ".xml"}


def files(root):
    return {p.relative_to(root) for p in root.rglob("*") if p.is_file()}


def normalised(path, old, new):
    text = path.read_text(encoding="utf-8", errors="replace")
    return text.replace(old, "<version>").replace(new, "<version>").splitlines()


def main(old, new):
    a, b = SITE_DIR / old, SITE_DIR / new
    for d in (a, b):
        if not d.is_dir():
            sys.exit(f"❌ {d} not found")
    fa, fb = files(a), files(b)
    only_a, only_b = sorted(fa - fb), sorted(fb - fa)
    print(f"{len(fa)} files in {old}, {len(fb)} in {new}, {len(fa & fb)} in both")
    for label, lst in ((f"only in {old}", only_a), (f"only in {new}", only_b)):
        if lst:
            print(f"⚠️ {len(lst)} {label}:")
            for p in lst:
                print(f"   {p}")
    differ = 0
    for rel in sorted(fa & fb):
        pa, pb = a / rel, b / rel
        if pa.suffix.lower() in TEXT:
            la, lb = normalised(pa, old, new), normalised(pb, old, new)
            if la == lb:
                continue
            differ += 1
            for i, (x, y) in enumerate(zip(la + [""] * len(lb), lb + [""] * len(la))):
                if x != y:
                    print(f"⚠️ {rel} line {i + 1}:\n   {old}: {x.strip()[:160]}\n   {new}: {y.strip()[:160]}")
                    break
        elif pa.read_bytes() != pb.read_bytes():
            differ += 1
            print(f"⚠️ {rel} (binary) differs")
    if differ or only_a or only_b:
        print(f"❌ {differ} files differ")
        return 1
    print("✅ identical apart from the version number")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python compare_versions.py <old version> <new version>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
