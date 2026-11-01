"""One command for content editing: build the unpublished version and open it on localhost.

    python preview.py                     # build, then serve and open the version's index page
    python preview.py --concept "time"    # ... and open that concept's page instead
    python preview.py --verbose           # show the full output of every step

Steps:
  1. Refuse if the version in config.toml is already published (committed in the
     site repo). Published versions are frozen (D-007): bump the version first.
  2. obsidian_to_jsonld.py --rebuild   (includes the D-009 hierarchy check)
  3. generate_skos_for_index.py --no-root   (the root redirect and About page are
     left alone, so the site repo only changes inside the unpublished version folder)
  4. Serve on localhost and open the browser. If a server is already running on the
     port, it is reused: keep one terminal serving and re-run preview.py after each edit.

Never runs git commands that change anything; the release checklist is still done by hand.
The individual scripts work exactly as before for a detailed, step-by-step look.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser

import frontmatter

from vc_config import BASE_DIR, SITE_DIR, VAULT_DIR, OUTPUT_DIR, VERSION, PORT, check_paths

# In quiet mode only lines starting with one of these markers are shown.
SHOW = ("❌", "⚠️", "📝", "✅", "🌳", "Build Complete", "   ")


def is_published():
    """True if <site_dir>/<version>/ has files committed in the site repo."""
    try:
        out = subprocess.run(
            ["git", "-C", str(SITE_DIR), "ls-files", "--", VERSION],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"❌ Could not ask git whether {VERSION} is published: {e}")
    return bool(out.strip())


def run_step(label, script, args, verbose):
    """Run one build script with this Python. Returns True if it succeeded."""
    cmd = [sys.executable, str(BASE_DIR / script), *args]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    print(f"▶ {label}: {script} {' '.join(args)}".rstrip())
    if verbose:
        return subprocess.run(cmd, cwd=BASE_DIR, env=env).returncode == 0
    res = subprocess.run(cmd, cwd=BASE_DIR, env=env, capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    lines = (res.stdout + res.stderr).splitlines()
    if res.returncode != 0:
        print("\n".join("   " + l for l in lines))   # on failure show everything
        return False
    shown = [l for l in lines if l.startswith(SHOW) and not l.startswith("   Press")]
    print("\n".join("   " + l for l in shown))
    return True


def concept_key(name):
    """concept-key of the vault note called <name> (case-insensitive, .md optional)."""
    want = name.removesuffix(".md").casefold()
    for f in VAULT_DIR.glob("*.md"):
        if f.stem.casefold() == want:
            key = frontmatter.load(f).get("concept-key")
            if not key:
                sys.exit(f"❌ '{f.stem}' has no concept-key, so it has no page.")
            return str(key).strip()
    sys.exit(f"❌ No note called '{name}' at the top level of the vault.")


def server_running():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--concept", metavar="NAME", help="open this concept's page (note name)")
    ap.add_argument("--verbose", action="store_true", help="show the full output of every step")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    ap.add_argument("--no-serve", action="store_true", help="build only; don't start a server")
    args = ap.parse_args()

    problems = check_paths()
    if problems:
        sys.exit("\n".join(f"❌ {p}" for p in problems) + "\n   Fix the paths in config.toml.")

    print(f"🔖 Preview of version {VERSION}")
    if is_published():
        sys.exit(f"❌ {VERSION} is already published (committed in {SITE_DIR.name}); it is frozen (D-007).\n"
                 f"   Set the next version in config.toml, then run preview.py again.")

    key = concept_key(args.concept) if args.concept else None   # fail early on a typo

    t0 = time.time()
    if not run_step("Build", "obsidian_to_jsonld.py", ["--rebuild"], args.verbose):
        sys.exit("❌ Build stopped. Nothing was served.")
    if not run_step("Index", "generate_skos_for_index.py", ["--no-root"], args.verbose):
        sys.exit("❌ Index step failed.")
    print(f"✅ Built {VERSION} in {time.time() - t0:.1f}s -> {OUTPUT_DIR}")

    url = f"http://localhost:{PORT}/{VERSION}/" + (f"{key}/" if key else "")
    if args.no_serve:
        print(f"   {url}")
        return

    if server_running():
        print(f"🌐 Server already running on port {PORT}; reusing it.")
        if not args.no_open:
            webbrowser.open(url)
        print(f"   {url}")
        return

    server = subprocess.Popen([sys.executable, str(BASE_DIR / "serve_localhost.py")], cwd=BASE_DIR)
    try:
        for _ in range(50):              # wait up to ~5 s for the server to come up
            if server_running():
                break
            time.sleep(0.1)
        print(f"🌐 {url}\n   Edit in Obsidian, then run  python preview.py  again in another terminal.\n"
              f"   Ctrl+C here stops the server.")
        if not args.no_open:
            webbrowser.open(url)
        server.wait()
    except KeyboardInterrupt:
        server.terminate()
        print("\n--- Preview server stopped ---")


if __name__ == "__main__":
    main()
