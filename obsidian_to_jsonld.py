import argparse
import re
import json
import shutil
import sys
import frontmatter
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from html.parser import HTMLParser
from html import escape as html_escape
from vault_clean import publishable_sections, placeholder_count, review, skos_text

# --- CONFIGURATION (all values come from config.toml via vc_config.py) ---
from vc_config import (
    VERSION, DOMAIN, VAULT_DIR, CONCEPT_DIR, EMBED_SEARCH, SITE_DIR, OUTPUT_DIR, TEMPLATE_DIR,
    SCHEME_IRI, SCHEME_PAGE_URL, SCHEME_LABEL, JSONLD_CONTEXT, concept_iri, page_url, check_paths,
)
DEFAULT_DESCRIPTION = "vernacular cloud taxonomy with json-ld"


SOURCE_DIR = CONCEPT_DIR

# Mapping Markdown Headers to SKOS properties
HEADER_TO_SKOS = {
    "Definition": "skos:definition",
    "Broader": "skos:broader",
    "Narrower": "skos:narrower",
    "Related": "skos:related",
    "Alternative Label": "skos:altLabel",
    "Editorial Note": "skos:editorialNote",
    "Change Note": "skos:changeNote",
    "History Note": "skos:historyNote",
    "Scope Note": "skos:scopeNote",
    "Example": "skos:example"
}

# --- GLOBAL INDEX ---
# Stores { "concept title": "uuid" } for link resolution
concept_index = {}

def get_files():
    """Markdown files at the top level of the concept folder only. Subfolders
    are deliberately ignored: glob("*.md") does not recurse."""
    return sorted(Path(SOURCE_DIR).glob("*.md"))

def clean_link_text(text):
    """Extracts text from [[Link]] or returns raw text."""
    match = re.search(r'\[\[(.*?)\]\]', text)
    return match.group(1) if match else text.strip()

# --- HELPER: Inline Markdown (2026-11-15) ---
def format_inline(text):
    """Escape stray & and <, then render `code`, **bold** and *italic*.
    _italic_ is rendered only at word boundaries (URLs and file names use underscores).
    Intentional inline HTML tags (<br>, <sup>) and entities pass through."""
    text = re.sub(r'&(?![A-Za-z#][A-Za-z0-9]*;)', '&amp;', text)
    text = re.sub(r'<(?![A-Za-z/!])', '&lt;', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*(?=\S)(.+?)(?<=\S)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])', r'<em>\1</em>', text)
    # _italic_ only at word boundaries, so file_name_here and URLs are untouched (2026-11-15)
    text = re.sub(r'(?<![\w/\\])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w/])', r'<em>\1</em>', text)
    return text

# --- HELPER: Embeds ![[Note#^blockid]] (2026-11-15) ---
EMBED_RE = re.compile(r'!\[\[([^\]|#]+)(#\^?[^\]|]*)?(?:\|[^\]]*)?\]\]')
_note_paths = {}
embed_warnings = []
credit_warnings = []   # a quote followed by a short paragraph: a credit outside the quote?
# Embeds from these notes are attributed under the quotation; all others are unmarked (JWK 2026-11-15)
QUOTE_SOURCES = {"Victor Badinage Quotes by Theme": "Victor Badinage"}

def find_vault_note(name):
    """Path of the note called <name>.md, or None. Searched in EMBED_SEARCH order
    (concept folder, products folder, whole vault); shallowest first within each."""
    key = name.strip()
    if key not in _note_paths:
        _note_paths[key] = None
        for folder in EMBED_SEARCH:
            hits = [p for p in Path(folder).rglob(f"{key}.md") if ".obsidian" not in p.parts and ".trash" not in p.parts]
            if hits:
                hits.sort(key=lambda p: (len(p.parts), str(p)))
                _note_paths[key] = hits[0]
                break
    return _note_paths[key]

def resolve_embed(note, ref):
    """Text of the block ^id in <note>, without its id and list marker; None if not found."""
    if not ref or not ref.startswith("#^"):
        return None  # heading and whole-note embeds are not inlined
    block = ref[2:].strip()
    path = find_vault_note(note)
    if not path:
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f"^{block}":
            # id on its own line labels the block just above it (Obsidian)
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            para = []
            while j >= 0 and lines[j].strip():
                para.insert(0, lines[j].strip())
                if re.match(r"^[-*+]\s+", lines[j].strip()):
                    break  # a list item stands alone
                j -= 1
            text = " ".join(para)
        elif re.search(rf"\s\^{re.escape(block)}\s*$", line):
            text = re.sub(rf"\s\^{re.escape(block)}\s*$", "", line).strip()
        else:
            continue
        text = re.sub(r"^(?:[-*+]\s+|>\s*)", "", text).strip()
        return text or None
    return None

# --- HELPER: Centralized Link Processing ---
def process_text_links(text):
    """
    1. Replaces [[Target]] with <a class="internal-link"> (Same Tab)
    2. Replaces [Label](URL) with <a class="external-link" target="_blank"> (New Tab)
    """
    
    # --- 1. Internal Wiki Links (Same Tab) ---
    def wiki_link_sub(match):
        inner = match.group(1)
        if '|' in inner:
            target_text, label_text = inner.split('|', 1)
        else:
            target_text = inner
            label_text = inner
            
        target_clean = target_text.strip().lower()
        target_uuid = concept_index.get(target_clean)
        
        if target_uuid:
            # Absolute path to the directory (matches the JSON-LD ID)
            return f'<a href="/{VERSION}/{target_uuid}/" class="internal-link">{label_text}</a>'                    
        else:
            return label_text

    text = re.sub(r'\[\[(.*?)\]\]', wiki_link_sub, text)

    # --- 2. External Markdown Links (New Tab) ---
    def md_link_sub(match):
        label = match.group(1)
        url = match.group(2)
        return f'<a href="{url}" class="external-link" target="_blank" rel="noopener noreferrer">{label}</a>'

    # Regex excludes images starting with !
    text = re.sub(r'(?<!\!)\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)', md_link_sub, text)

    return text 

def attr_string(attrs):
    """Attributes for a start tag. HTMLParser hands back unescaped values, so
    escape them again; otherwise a quote in a meta description ends the attribute."""
    return ''.join(f' {k}="{html_escape(v, quote=True)}"' if v else f' {k}' for k, v in attrs)


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
            attr_str = attr_string(attrs)
            self.formatted.append(f"<{tag}{attr_str}>")
            if tag not in self.void_tags:
                self.level += 1
                self.just_opened_block = True

        elif tag in self.content_tags:
            self._add_newline_if_needed()
            self._indent()
            attr_str = attr_string(attrs)
            self.formatted.append(f"<{tag}{attr_str}>")
            self.just_opened_block = True
            
        else:
            attr_str = attr_string(attrs)
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

        # Safety check: Ensure formatted list is not empty before checking last element
        if self.just_opened_block and self.formatted and self.formatted[-1].endswith('>'):
             pass

        self.formatted.append(data)
        self.just_opened_block = False
    
    def handle_decl(self, decl):
        self.formatted.append(f"<!{decl}>\n")

    def handle_comment(self, data):
        self._add_newline_if_needed()
        self._indent()
        self.formatted.append(f"") # Added comment markers for valid HTML
        
def prettify_html(html_content):
    formatter = SmartHTMLFormatter(indent_width=2)
    formatter.feed(html_content)
    output = "".join(formatter.formatted)
    return re.sub(r'\n\s*\n', '\n', output)
    
def parse_sections(content):
    """The published SKOS sections of a note (vault_clean.publishable_sections):
    only SKOS headings, nothing after # Work in Progress, and no comments,
    tasks or template placeholders. A section left empty is skipped."""
    return publishable_sections(content)

def plain_text(lines, limit=300):
    """One line of plain text from a section, for <meta description> and og:description."""
    text = " ".join(l.strip().lstrip("-*+ ").strip() for l in lines or [] if l.strip())
    text = re.sub(r'!\[\[[^\]]*\]\]', '', text)                    # embeds
    text = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', text)  # [[x|y]] -> y
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)            # [label](url) -> label
    text = re.sub(r'[*_`]', '', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(' ', 1)[0] + " …"
    return text


def jsonld_embed(note, ref):
    """An embedded block as plain text for JSON-LD, with the same credit the page
    shows for quotations from QUOTE_SOURCES (2026-11-16)."""
    text = resolve_embed(note, ref)
    if not text:
        return None
    text = skos_text([text]) or ""
    source = QUOTE_SOURCES.get(note.strip())
    return f"{text} — {source}" if source and text else (text or None)


def generate_skos_json(uuid, title, sections):
    """Two nodes (D-006): the concept, under its permanent IRI, and this version's
    page, which states that it is a version of that concept."""
    concept = {
        "@id": concept_iri(uuid),
        "@type": "skos:Concept",
        "skos:prefLabel": title,
        "skos:inScheme": SCHEME_IRI
    }
    page = {
        "@id": page_url(uuid),
        "dct:isVersionOf": concept_iri(uuid),
        "owl:versionInfo": VERSION
    }
    json_ld = {"@context": JSONLD_CONTEXT, "@graph": [concept, page]}

    for header, lines in sections.items():
        skos_prop = HEADER_TO_SKOS.get(header)
        if not skos_prop or not lines: continue

        if header in ["Broader", "Narrower", "Related"]:
            uris = []
            for line in lines:
                link_text = clean_link_text(line).lower()
                target_uuid = concept_index.get(link_text)
                if target_uuid:
                    uris.append(concept_iri(target_uuid))
            if uris:
                concept[skos_prop] = uris if len(uris) > 1 else uris[0]

        elif header == "Alternative Label":
            clean_items = [t for t in (skos_text([line]) for line in lines) if t]
            if clean_items:
                concept[skos_prop] = clean_items

        else:
            # plain text, not Markdown: quotes resolved and credited, markers and links stripped (2026-11-16)
            text_block = skos_text(lines, embed=jsonld_embed)
            if text_block:
                concept[skos_prop] = text_block

    return json_ld

def render_section_to_html(lines):
    html_parts = []
    in_list = False
    in_quote = False
    bullet_pattern = re.compile(r'^[-*+]\s+(.*)')

    def inline(s):
        return process_text_links(format_inline(s))

    def close_open():
        nonlocal in_list, in_quote
        if in_list:
            html_parts.append("</ul>")
            in_list = False
        if in_quote:
            html_parts.append("</blockquote>")
            in_quote = False

    for line in lines:
        stripped = line.strip()
        if not stripped: continue

        if '![[' in stripped:
            quotes = []
            for m in EMBED_RE.finditer(stripped):
                q = resolve_embed(m.group(1), m.group(2))
                if q:
                    quotes.append((q, QUOTE_SOURCES.get(m.group(1).strip())))
                else:
                    embed_warnings.append(m.group(0))
            rest = EMBED_RE.sub('', stripped).strip()
            if rest:
                close_open()
                html_parts.append(render_section_to_html([rest]))
            for q, author in quotes:
                close_open()
                credit = f"\n<footer><cite>{author}</cite></footer>" if author else ""
                html_parts.append(f"<blockquote>\n<p>{inline(q)}</p>{credit}\n</blockquote>")
            continue

        bullet_match = bullet_pattern.match(stripped)

        if stripped.startswith('>'):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            body = stripped.lstrip('>').strip()
            if not body:
                continue  # a bare '>' separates lines inside the quote
            if not in_quote:
                html_parts.append("<blockquote>")
                in_quote = True
            credit = re.match(r'^(?:\u2014|--)\s*(.+)$', body)
            if credit:
                # "> — Author, *Work* locator": the dash is supplied by CSS (2026-11-15)
                html_parts.append(f"<footer><cite>{inline(credit.group(1))}</cite></footer>")
                html_parts.append("</blockquote>")
                in_quote = False
            else:
                html_parts.append(f"<p>{inline(body)}</p>")

        elif bullet_match:
            if in_quote:
                html_parts.append("</blockquote>")
                in_quote = False
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{inline(bullet_match.group(1))}</li>")

        elif stripped.startswith('##'):
            close_open()
            html_parts.append(f"<h3>{inline(stripped.lstrip('#').strip())}</h3>")

        else:
            if (in_quote or (html_parts and html_parts[-1] == "</blockquote>")) and len(stripped) < 120:
                credit_warnings.append(stripped)
            close_open()
            html_parts.append(f"<p>{inline(stripped)}</p>")

    close_open()
    return "\n".join(html_parts)    
    
def render_html_main(sections):
    html_parts = []
    main_keys = ["Definition", "Broader", "Narrower", "Related"]
    
    for header in main_keys:
        lines = sections.get(header)
        if not lines: continue
        html_parts.append(f"<h2>{header}</h2>")
        section_html = render_section_to_html(lines)
        html_parts.append(section_html)
            
    return "\n".join(html_parts)    
    
def render_html_aside(sections):
    html_parts = []
    main_keys = ["Definition", "Broader", "Narrower", "Related"]
    
    for header, lines in sections.items():
        if not lines: continue
        if header in main_keys: continue 
        html_parts.append(f"<h2>{header}</h2>")
        section_html = render_section_to_html(lines)
        html_parts.append(section_html)
        
    return "\n".join(html_parts)

def generate_concept_scheme(all_concepts, output_dir, version=VERSION):
    """Generates <version>/concept-scheme/index.html containing the SKOS ConceptScheme."""
    print("--- Generating Concept Scheme ---")
    
    # 1. Prepare Data Containers
    jsonld_links = []
    html_render_list = []
    
    for concept in all_concepts:
        fm = concept.get('frontmatter', {})
        
        # This catches both the Boolean True and the String "true"
        if str(fm.get('top-concept')).lower() == 'true':    
            uuid = fm.get('concept-key')
            
            # DRY Rule: Use filename as the label source of truth
            # We assume filename is "TITLE.md"
            label = Path(concept['filename']).stem
            
            if uuid:
                # JSON-LD names the concept (permanent IRI, D-006) ...
                jsonld_links.append(concept_iri(uuid))

                # ... the HTML links to its page in this version.
                html_render_list.append({
                    "url": page_url(uuid),
                    "iri": concept_iri(uuid),
                    "name": label,
                    "uuid": uuid
                })
            else:
                filename = concept.get('filename', 'unknown file')
                print(f"⚠️ Warning: Found 'top-concept' but missing 'concept-key' in {filename}")

    # 2. Build the JSON-LD Structure
    scheme_data = {
        "@context": JSONLD_CONTEXT,
        "@graph": [
            {
                "@id": SCHEME_IRI,
                "@type": "skos:ConceptScheme",
                "owl:versionIRI": SCHEME_PAGE_URL,
                "owl:versionInfo": version,
                "dc:title": SCHEME_LABEL,
                "dc:creator": "Victor Badinage",
                "skos:prefLabel": SCHEME_LABEL,
                "skos:definition": "A systematic philosophy combining grammar, dialectic, and rhetoric with the semantic technology of taxonomies, ontologies, knowledge graphs, social media, and so-called AI.",
                "skos:hasTopConcept": jsonld_links
            }
        ]
    }

    # 3. Render Template
    json_ld_script = json.dumps(scheme_data, indent=2)
    template_path = Path(TEMPLATE_DIR) 
    env = Environment(loader=FileSystemLoader(str(template_path)))
    
    try:
        template = env.get_template('skos_scheme.html')
        
        output_html = template.render(
            json_ld_script=json_ld_script,
            top_concepts=html_render_list,
            version=version,
            scheme_iri=SCHEME_IRI,
            scheme_page_url=SCHEME_PAGE_URL
        )
        
        # UPDATED: Create 'concept-scheme' directory
        scheme_dir = output_dir / "concept-scheme"
        scheme_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = scheme_dir / "index.html"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output_html)
            
        print(f"✅ Generated ConceptScheme at {output_file} with {len(jsonld_links)} top concepts.")
        
    except Exception as e:
        print(f"❌ Error generating index.html: {e}")

def pass_one_index_uuids():
    """Scans all files to build a map of 'Title -> UUID'."""
    print("--- Building Index ---")
    if not SOURCE_DIR.exists():
        print(f"ERROR: Source directory not found at {SOURCE_DIR}")
        return

    for file_path in get_files():
        try:
            post = frontmatter.load(file_path)
            uuid = post.metadata.get('concept-key')
            if uuid:
                title = file_path.stem.lower() 
                concept_index[title] = uuid
        except Exception as e:
            print(f"Error indexing {file_path}: {e}")

def pass_two_build_site_and_collect():
    """
    Generates HTML pages AND collects data for the Concept Scheme.
    Returns: list of dicts {filename, frontmatter, content}
    """
    print("--- Generating Site & Collecting Data ---")
    
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    try:
        template = env.get_template("skos_concept.html")
    except Exception as e:
        print(f"CRITICAL: Could not load 'skos_concept.html' template: {e}")
        return []

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_concepts_data = []
    pages_written = 0
    skipped_no_key = []

    for file_path in get_files():
        try:
            post = frontmatter.load(file_path)
            uuid = post.metadata.get('concept-key')
            
            # Save data for Scheme generation later
            note_data = {
                'filename': file_path.name,
                'frontmatter': post.metadata,
                'content': post.content
            }
            all_concepts_data.append(note_data)

            if not uuid:
                skipped_no_key.append(file_path.name)
                continue # Skip HTML generation if no UUID
            
            # --- HTML GENERATION LOGIC ---
            title = file_path.stem 
            sections = parse_sections(post.content)
            
            skos_data = generate_skos_json(uuid, title, sections)
            html_main = render_html_main(sections)
            html_aside = render_html_aside(sections)
            
            raw_html = template.render(
                title=title,
                html_main_content=html_main,
                html_aside_content=html_aside,
                json_ld=json.dumps(skos_data, indent=2),
                uuid=uuid,
                version=VERSION,
                domain=DOMAIN,
                concept_iri=concept_iri(uuid),
                page_url=page_url(uuid),
                description=plain_text(sections.get("Definition")) or DEFAULT_DESCRIPTION
            )
            
            final_html = prettify_html(raw_html)
            
            concept_dir = OUTPUT_DIR / uuid
            concept_dir.mkdir(parents=True, exist_ok=True)
            target_file = concept_dir / "index.html"
            
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(final_html)
            pages_written += 1

        except Exception as e:
            print(f"Error processing {file_path.name}: {e}")

    print(f"Build Complete. {pages_written} concept pages written to {OUTPUT_DIR}")
    print(f"   {len(skipped_no_key)} root notes skipped (no concept-key).")
    return all_concepts_data

def prepare_output_dir(rebuild):
    """Each version is built into its own, freshly emptied folder, so pages
    for renamed or deleted concepts never linger. An existing version folder
    is only replaced when --rebuild is given, which protects published
    permalinks of earlier releases."""
    if OUTPUT_DIR.exists():
        if not rebuild:
            print(f"❌ {OUTPUT_DIR} already exists.")
            print("   To make a new release, change 'version' in config.toml.")
            print(f"   To regenerate {VERSION} from scratch, run again with --rebuild.")
            return False
        # Safety: only ever delete <site_dir>/<x.y.z>
        if OUTPUT_DIR.parent.resolve() != SITE_DIR.resolve() or OUTPUT_DIR.name != VERSION:
            print(f"❌ Refusing to delete unexpected folder {OUTPUT_DIR}")
            return False
        print(f"🧹 Removing previous build of {VERSION} at {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    return True

def hierarchy_ok():
    """D-009: the parents' # Narrower lists are the master and # Broader is a
    generated copy. Stop the build if the vault is out of sync or has loops,
    so skos:broader and skos:narrower are always consistent when published."""
    import sync_hierarchy
    notes, resolve = sync_hierarchy.load(CONCEPT_DIR)
    _, _, report = sync_hierarchy.analyse(notes, resolve)
    blocking = {k: v for k, v in report.items()
                if v and (k.startswith("Loops") or k.startswith("# Broader out of sync"))}
    if not blocking:
        print("🌳 Hierarchy check: in sync")
        return True
    print("❌ Hierarchy check failed (D-009):")
    for title, items in blocking.items():
        print(f"   {title}: {len(items)}  e.g. {', '.join(items[:5])}")
    print("   Run  python sync_hierarchy.py  for details, then  --fix  (or --promote --fix).")
    print("   To build anyway, add --no-check.")
    return False


def main():
    parser = argparse.ArgumentParser(description="Build the vernacular.cloud site from the Obsidian vault.")
    parser.add_argument("--rebuild", action="store_true",
                        help="delete and regenerate the folder for the configured version")
    parser.add_argument("--no-check", action="store_true",
                        help="skip the broader/narrower hierarchy check (sync_hierarchy.py)")
    args = parser.parse_args()

    problems = check_paths()
    if problems:
        for p in problems:
            print(f"❌ {p}")
        print("   Fix the paths in config.toml.")
        sys.exit(1)

    print(f"🔖 Version {VERSION}")
    if not args.no_check and not hierarchy_ok():
        sys.exit(1)
    print(f"📂 Scanning files in {SOURCE_DIR}...")

    if not prepare_output_dir(args.rebuild):
        sys.exit(1)

    # 1. Build the Global Index (Required for linking)
    pass_one_index_uuids()
    
    # 2. Generate Pages and Collect Data (Single Pass)
    all_concepts = pass_two_build_site_and_collect()
    
    # 3. Generate the Scheme Index (Using collected data)
    if all_concepts:
        generate_concept_scheme(all_concepts, OUTPUT_DIR, version=VERSION)
    else:
        print("❌ No concepts found. Check SOURCE_DIR path.")

    # 4. To-do count for the content walkthrough (placeholders are never published)
    stubs = [f.stem for f in get_files()
             if placeholder_count(f.read_text(encoding="utf-8", errors="replace"))]
    if stubs:
        print(f"📝 {len(stubs)} notes still contain template placeholders (not published).")
    ruled = [f.stem for f in get_files()
             if any(k.startswith("---") for k, _ in review(f.read_text(encoding="utf-8", errors="replace"))[0])]
    if ruled:
        print(f"⚠️ {len(ruled)} notes have text after a --- inside a published section (it IS published): "
              + ", ".join(ruled[:8]) + (" …" if len(ruled) > 8 else ""))
        print("   Replace the --- with  # Work in Progress  if that text is private.")
    if credit_warnings:
        print(f"ℹ️ {len(credit_warnings)} quotes are followed by a short line that may be a credit outside the quote "
              "(write it inside as  > — Author, *Work* locator): " + " | ".join(credit_warnings[:6]))
    if embed_warnings:
        print(f"⚠️ {len(embed_warnings)} embeds could not be inlined and were left out: "
              + ", ".join(sorted(set(embed_warnings))[:8]))

if __name__ == "__main__":
    main()
