import http.server
import socketserver
import functools

# --- CONFIGURATION (all values come from config.toml via vc_config.py) ---
# We serve the site root (the PARENT of the version folders) so that
# /<version>/<uuid>/ and /css/ paths resolve exactly as they do on the live site.
from vc_config import SITE_DIR, VERSION, PORT


class SiteHandler(http.server.SimpleHTTPRequestHandler):
    """Static file server that also imitates the live site's /latest/ alias.

    On vernacular.cloud an Amplify rule redirects /latest/<*> to /<version>/<*>.
    Here we do the same, using the version currently set in config.toml.
    """

    def do_GET(self):
        if self.path == "/latest" or self.path.startswith("/latest/"):
            rest = self.path[len("/latest"):].lstrip("/")
            self.send_response(302)
            self.send_header("Location", f"/{VERSION}/{rest}")
            self.end_headers()
            return
        super().do_GET()


def serve():
    if not SITE_DIR.exists():
        print(f"Error: Site root not found at {SITE_DIR}")
        print("Check site_dir in config.toml.")
        return
    if not (SITE_DIR / VERSION).exists():
        print(f"Warning: no build for version {VERSION} yet. Run obsidian_to_jsonld.py first.")

    Handler = functools.partial(SiteHandler, directory=str(SITE_DIR))
    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"\n--- Vernacular Cloud Dev Server ---")
        print(f"    Home:     http://localhost:{PORT}/   (redirects to /{VERSION}/)")
        print(f"    Version:  http://localhost:{PORT}/{VERSION}/")
        print(f"    Scheme:   http://localhost:{PORT}/{VERSION}/concept-scheme/")
        print(f"    Root:     {SITE_DIR}")
        print("\n    Press Ctrl+C to stop...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n--- Server Stopped by User ---")


if __name__ == "__main__":
    serve()
