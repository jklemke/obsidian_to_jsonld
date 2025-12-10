import os
import re
import json
import frontmatter
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from html.parser import HTMLParser

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
# Adjusted relative path based on your setup
SOURCE_DIR = BASE_DIR / "../../../Dropbox/docs/Knowledge Mgt/Obsidian markdown/VernacularCloud"
OUTPUT_DIR = BASE_DIR / "../../html/vernacular-cloud-003/0.0.1"
TEMPLATE_DIR = BASE_DIR / "templates"

VERSION = "0.0.1"
DOMAIN = "https://vernacular.cloud"

# Mapping Markdown Headers to SKOS properties
HEADER_TO_SKOS = {
    "Definition": "skos:definition",
    "Broader": "skos:broader",
    "Narrower": "skos:narrower",
    "Related": "skos:related",
    "Alternative Label": "skos:altLabel",
    "Editorial Note": "skos:editorialNote",
    "History Note": "skos:historyNote",
    "Scope Note": "skos:scopeNote",
    "Example": "skos:example"
}

# --- GLOBAL INDEX ---
# Stores { "concept title": "uuid" } for link resolution
concept_index = {}

def get_files():
    """Yields all markdown files in the source directory."""
    return Path(SOURCE_DIR).glob("*.md")

def clean_link_text(text):
    """Extracts text from [[Link]] or returns raw text."""
    match = re.search(r'\[\[(.*?)\]\]', text)
    return match.group(1) if match else text.strip()

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
    text = re.sub(r'(?<!\!)\[([^\]]+)\]\(([^)]+)\)', md_link_sub, text)

    return text 

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
    """Splits markdown content by H1 headers."""
    sections = {}
    current_header = None
    lines = content.split('\n')
    
    for line in lines:
        header_match = re.match(r'^#\s+(.*)', line)
        if header_match:
            current_header = header_match.group(1).strip()
            sections[current_header] = []
        elif current_header:
            if line.strip(): 
                sections[current_header].append(line.strip())
                
    return sections

def generate_skos_json(uuid, title, sections):
    scheme_uri = f"{DOMAIN}/{VERSION}/concept-scheme/"    

    json_ld = {
        "@context": {
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "dct": "http://purl.org/dc/terms/"
        },
        "@id": f"{DOMAIN}/{VERSION}/{uuid}/", 
        "@type": "skos:Concept",
        "skos:prefLabel": title,
        "skos:inScheme": scheme_uri
    }

    for header, lines in sections.items():
        skos_prop = HEADER_TO_SKOS.get(header)
        if not skos_prop or not lines: continue

        if header in ["Broader", "Narrower", "Related"]:
            uris = []
            for line in lines:
                link_text = clean_link_text(line).lower()
                target_uuid = concept_index.get(link_text)
                if target_uuid:
                    uris.append(f"{DOMAIN}/{VERSION}/{target_uuid}/")
            if uris:
                json_ld[skos_prop] = uris if len(uris) > 1 else uris[0]

        elif header == "Alternative Label":
            clean_items = [line.lstrip('- ').strip() for line in lines]
            json_ld[skos_prop] = clean_items

        else:
            text_block = " ".join(lines)
            json_ld[skos_prop] = text_block

    return json_ld

def render_section_to_html(lines):
    html_parts = []
    in_list = False
    bullet_pattern = re.compile(r'^[-*+]\s+(.*)')

    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        
        bullet_match = bullet_pattern.match(stripped)
        
        if bullet_match:
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            raw_content = bullet_match.group(1)
            content = process_text_links(raw_content)
            html_parts.append(f"<li>{content}</li>")

        elif stripped.startswith('##'):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            content = stripped.lstrip('#').strip()
            content = process_text_links(content)
            html_parts.append(f"<h3>{content}</h3>")

        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            content = process_text_links(stripped)
            html_parts.append(f"<p>{content}</p>")
            
    if in_list:
        html_parts.append("</ul>")
        
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

def generate_concept_scheme(all_concepts, output_dir, version="0.0.1"):
    """Generates the root index.html containing the SKOS ConceptScheme."""
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
                concept_uri = f"https://vernacular.cloud/{version}/{uuid}/"
                
                # Append to JSON-LD list (Standard SKOS)
                jsonld_links.append({"@id": concept_uri})
                
                # Append to HTML list (Rich Data)
                html_render_list.append({
                    "url": concept_uri,
                    "name": label,
                    "uuid": uuid
                })
            else:
                filename = concept.get('filename', 'unknown file')
                print(f"⚠️ Warning: Found 'top-concept' but missing 'concept-key' in {filename}")

    # 2. Build the JSON-LD Structure
    scheme_data = {
        "@context": {
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "dc": "http://purl.org/dc/elements/1.1/"
        },
        "@graph": [
            {
                # UPDATED: Added trailing slash to match directory structure
                "@id": f"https://vernacular.cloud/{version}/concept-scheme/",
                "@type": "skos:ConceptScheme",
                "dc:title": "Vernacular Cloud",
                "dc:creator": "Victor Badinage",
                "skos:prefLabel": "Vernacular Cloud",
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
            version=version
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
                version=VERSION
            )
            
            final_html = prettify_html(raw_html)
            
            concept_dir = OUTPUT_DIR / uuid
            concept_dir.mkdir(parents=True, exist_ok=True)
            target_file = concept_dir / "index.html"
            
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(final_html) 
                
        except Exception as e:
            print(f"Error processing {file_path.name}: {e}")
            
    print(f"Build Complete. Files written to {OUTPUT_DIR}")
    return all_concepts_data

def main():
    print(f"📂 Scanning files in {SOURCE_DIR}...")
    
    # 1. Build the Global Index (Required for linking)
    pass_one_index_uuids()
    
    # 2. Generate Pages and Collect Data (Single Pass)
    all_concepts = pass_two_build_site_and_collect()
    
    # 3. Generate the Scheme Index (Using collected data)
    if all_concepts:
        generate_concept_scheme(all_concepts, OUTPUT_DIR, version=VERSION)
    else:
        print("❌ No concepts found. Check SOURCE_DIR path.")

if __name__ == "__main__":
    main()
