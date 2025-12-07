import os
import http.server
import socketserver
import functools
from pathlib import Path

# --- CONFIGURATION ---
# Assumes this script is in the same folder as obsidian_to_jsonld.py
# We want to serve the PARENT of "0.0.1" so that /0.0.1/uuid and /css/ paths work.
BASE_DIR = Path(__file__).resolve().parent
SITE_ROOT = BASE_DIR / "../../html/vernacular-cloud-003"
PORT = 8899

def serve():
    if not SITE_ROOT.exists():
        print(f"Error: Site root not found at {SITE_ROOT}")
        print("Did you run the builder script first?")
        return

    # Change to the site root so "http://localhost:8899/" points here
    os.chdir(SITE_ROOT)
    
    Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=".")
    socketserver.TCPServer.allow_reuse_address = True

    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print(f"\n--- Vernacular Cloud Dev Server ---")
            print(f"    URL:  http://localhost:{PORT}/0.0.1/")
            print(f"    Root: {SITE_ROOT}")
            print(f"    Mode: Directory Index (Clean URLs)")
            print("\n    Press Ctrl+C to stop...")
            
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n--- Server Stopped by User ---")
        httpd.server_close()

if __name__ == "__main__":
    serve()
    