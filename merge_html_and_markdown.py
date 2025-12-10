import json
import os
import re
import frontmatter
from pathlib import Path
from bs4 import BeautifulSoup
from html.parser import HTMLParser

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "../../html/vernacular-cloud-003/index.html"
# HTML_FILE = Path("index.html") # (Fallback for testing)
MARKDOWN_DIR = BASE_DIR / "../../../Dropbox/docs/Knowledge Mgt/Obsidian markdown/VernacularCloud" 

DOMAIN = "https://vernacular.cloud"
VERSION = "0.0.1"
SCHEME_URI = f"{DOMAIN}/{VERSION}/concept-scheme/"
ROOT_UUID = "https://vernacular.cloud/0.0.1/nU2JNEcOO9ZHxSlpZMwbCgOG/"

# --- FORMATTER CLASS (From your snippet) ---
class SmartHTMLFormatter(HTMLParser):
    def __init__(self, indent_width=2):
        super().__init__()
        self.indent_width = indent_width
        self.level = 0
        self.formatted = []
        
        self.structural_tags = {
            'html', 'head', 'body', 'header', 'footer', 'main', 'aside', 
            'section', 'div', 'ul', 'ol', 'script', 'style', 'meta', 'link'
        }
        
        self.content_tags = {
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'title', 'blockquote', 'small'
        }
        
        self.void_tags = {'meta', 'link', 'img', 'br', 'hr', 'input'}
        self.just_opened_block = False

    def _add_newline_if_needed(self):
        if self.formatted and not self.formatted[-1].endswith('\n'):
            self.formatted.append('\n')

    def _indent(self):
        self.formatted.append(' ' * (self.level * self.indent_width))

    def handle_starttag(self, tag, attrs):
        if tag in self.structural_tags:
            self._add_newline_if_needed()
            self._indent()
            attr_str = ''.join(f' {k}="{v}"' if v else f' {k}' for k, v in attrs)
            self.formatted.append(f"<{tag}{attr_str}>")
            if tag not in self.void_tags:
                self.level += 1
                self.just_opened_block = True

        elif tag in self.content_tags:
            self._add_newline_if_needed()
            self._indent()
            attr_str = ''.join(f' {k}="{v}"' if v else f' {k}' for k, v in attrs)
            self.formatted.append(f"<{tag}{attr_str}>")
            self.just_opened_block = True
            
        else:
            attr_str = ''.join(f' {k}="{v}"' if v else f' {k}' for k, v in attrs)
            self.formatted.append(f"<{tag}{attr_str}>")
            self.just_opened_block = False

    def handle_endtag(self, tag):
        if tag in self.structural_tags:
            if tag not in self.void_tags:
                self.level -= 1
                self._add_newline_if_needed()
                self._indent()
            self.formatted.append(f"</{tag}>")
            self.just_opened_block = False

        elif tag in self.content_tags:
            if self.formatted and self.formatted[-1].endswith('\n'):
                 self._indent()
            self.formatted.append(f"</{tag}>")
            self.just_opened_block = False

        else:
            self.formatted.append(f"</{tag}>")

    def handle_data(self, data):
        stripped = data.strip()
        if not stripped: return

        if self.just_opened_block and self.formatted and self.formatted[-1].endswith('>'):
             pass

        self.formatted.append(data)
        self.just_opened_block = False
    
    def handle_decl(self, decl):
        self.formatted.append(f"<!{decl}>\n")

    def handle_comment(self, data):
        self._add_newline_if_needed()
        self._indent()
        self.formatted.append(f"") # Restored comment syntax
        
def prettify_html(html_content):
    formatter = SmartHTMLFormatter(indent_width=2)
    formatter.feed(html_content)
    output = "".join(formatter.formatted)
    return re.sub(r'\n\s*\n', '\n', output)

# --- LOGIC ---

def normalize_text(text_lines):
    if not text_lines: return None
    text = " ".join(line.strip() for line in text_lines if line.strip())
    text = re.sub(r'\[\[(.*?)\]\]', r'\1', text) 
    return text

def parse_definition_from_md(content):
    lines = content.split('\n')
    capturing = False
    definition_lines = []
    for line in lines:
        header_match = re.match(r'^#+\s+(.*)', line)
        if header_match:
            if header_match.group(1).strip().lower() == "definition":
                capturing = True
                continue
            elif capturing:
                break
        if capturing:
            definition_lines.append(line)
    return normalize_text(definition_lines)

def build_definition_map(source_dir):
    print(f"📂 Scanning Markdown files in {source_dir}...")
    def_map = {}
    source_path = Path(source_dir)
    if not source_path.exists():
        return {}
    for file_path in source_path.glob("*.md"):
        try:
            post = frontmatter.load(file_path)
            uuid = post.metadata.get('concept-key')
            if uuid:
                definition = parse_definition_from_md(post.content)
                if definition:
                    def_map[uuid] = definition
        except Exception: pass
    print(f"✅ Indexed {len(def_map)} definitions.")
    return def_map

def extract_uuid_from_url(url):
    parts = url.strip('/').split('/')
    return parts[-1] if parts else None

def make_absolute(url):
    if url.startswith("http"): return url
    if url.startswith("/"): return f"{DOMAIN}{url}"
    return f"{DOMAIN}/{url}"

def inject_into_html(json_data, html_path):
    """Finds the script tag, replaces content, and formats HTML."""
    print(f"💉 Injecting JSON-LD into {html_path}...")
    
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Find the JSON-LD script tag
    script_tag = soup.find("script", {"type": "application/ld+json"})
    
    if script_tag:
        # 1. Generate standard JSON
        raw_json = json.dumps(json_data, indent=2)
        
        # 2. Add 6-space indentation to EVERY line
        # We split the JSON by newlines, add the spaces, and rejoin them
        indentation = " " * 6
        indented_json = "\n".join(indentation + line for line in raw_json.split("\n"))
        
        # 3. Set the content: Newline + Indented Block + Newline + (Optional alignment for closing tag)
        script_tag.string = f"\n{indented_json}\n"
        
        # 4. Get raw HTML string from BeautifulSoup
        raw_html = str(soup)
        
        # 5. Run it through SmartHTMLFormatter
        final_html = prettify_html(raw_html)
        
        # 6. Write back to file
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        print(f"✅ Injection and formatting successful.")
    else:
        print("❌ Error: <script type='application/ld+json'> tag not found in HTML.")

def generate_full_jsonld():
    definition_map = build_definition_map(MARKDOWN_DIR)

    if not HTML_FILE.exists():
        print(f"❌ HTML file not found: {HTML_FILE}")
        return

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    graph_map = {} 
    main_area = soup.find("main")
    if not main_area: return

    sections = main_area.find_all("section", recursive=True)

    for section in sections:
        header = section.find("header")
        if not header: continue
        h1 = header.find("h1")
        if not h1: continue
        parent_link = h1.find("a")
        if not parent_link: continue

        parent_uri = make_absolute(parent_link['href'])
        parent_uuid = extract_uuid_from_url(parent_link['href'])
        
        # Handle Visible Label vs Data Attribute (PrefLabel)
        visible_text = parent_link.get_text(strip=True)
        hidden_pref = parent_link.get('data-pref-label')
        
        if hidden_pref:
            final_pref_label = hidden_pref
            final_alt_label = visible_text
        else:
            final_pref_label = visible_text
            final_alt_label = None
        
        narrower_uris = []
        paragraphs = section.find_all("p", recursive=False)
        for p in paragraphs:
            child_link = p.find("a")
            if child_link and child_link.get("href"):
                child_uri = make_absolute(child_link['href'])
                narrower_uris.append(child_uri)

        if parent_uri in graph_map:
            if narrower_uris:
                existing = graph_map[parent_uri].get("skos:narrower", [])
                combined = list(set(existing + narrower_uris))
                graph_map[parent_uri]["skos:narrower"] = combined
        else:
            concept_obj = {
                "@id": parent_uri,
                "@type": "skos:Concept",
                "skos:prefLabel": final_pref_label,
                "skos:inScheme": SCHEME_URI,
                "skos:broader": ROOT_UUID, 
            }
            if final_alt_label:
                concept_obj["skos:altLabel"] = final_alt_label

            if parent_uuid and parent_uuid in definition_map:
                concept_obj["skos:definition"] = definition_map[parent_uuid]
            if narrower_uris:
                concept_obj["skos:narrower"] = narrower_uris
            
            graph_map[parent_uri] = concept_obj

    full_json_ld = {
        "@context": {
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "dct": "http://purl.org/dc/terms/"
        },
        "@graph": list(graph_map.values())
    }

    # TRIGGER INJECTION AND FORMATTING
    inject_into_html(full_json_ld, HTML_FILE)

if __name__ == "__main__":
    generate_full_jsonld()