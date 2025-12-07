import os
import re
import json
import frontmatter
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent

SOURCE_DIR = BASE_DIR / "../../../Dropbox/docs/Knowledge Mgt/Obsidian markdown/VernacularCloud"
OUTPUT_DIR = BASE_DIR / "../../html/vernacular-cloud-003/0.0.1"
TEMPLATE_DIR = BASE_DIR / "./templates"

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
            # Class: internal-link | Target: (default/self)
            return f'<a href="{target_uuid}.html" class="internal-link">{label_text}</a>'
        else:
            return label_text

    text = re.sub(r'\[\[(.*?)\]\]', wiki_link_sub, text)

    # --- 2. External Markdown Links (New Tab) ---
    def md_link_sub(match):
        label = match.group(1)
        url = match.group(2)
        # Class: external-link | Target: _blank
        return f'<a href="{url}" class="external-link" target="_blank" rel="noopener noreferrer">{label}</a>'

    # Regex excludes images starting with !
    text = re.sub(r'(?<!\!)\[([^\]]+)\]\(([^)]+)\)', md_link_sub, text)

    return text 

    
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
    json_ld = {
        "@context": "https://www.w3.org/2004/02/skos/core#",
        # CLEAN URL: No .html here
        "@id": f"{DOMAIN}/{VERSION}/{uuid}", 
        "@type": "skos:Concept",
        "skos:prefLabel": title
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
                    # CLEAN URL: No .html here
                    uris.append(f"{DOMAIN}/{VERSION}/{target_uuid}")
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
    """
    Parses a list of lines into HTML, handling Mixed Content.
    - Standard text -> <p>
    - '##' -> <h3>
    - '- ', '* ', '+ ' -> <ul><li>
    """
    html_parts = []
    in_list = False
    
    # Regex for lines starting with -, *, or + followed by a space
    bullet_pattern = re.compile(r'^[-*+]\s+(.*)')

    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        
        # 1. Check for Bullet Points
        bullet_match = bullet_pattern.match(stripped)
        
        if bullet_match:
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            
            # Extract content after the bullet
            raw_content = bullet_match.group(1)
            content = process_text_links(raw_content)
            html_parts.append(f"<li>{content}</li>")

        # 2. Check for Sub-Headers (##)
        elif stripped.startswith('##'):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            
            content = stripped.lstrip('#').strip()
            content = process_text_links(content)
            html_parts.append(f"<h3>{content}</h3>")

        # 3. Standard Paragraphs
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            
            content = process_text_links(stripped)
            html_parts.append(f"<p>{content}</p>")
            
    # Close any open list at the end of the section
    if in_list:
        html_parts.append("</ul>")
        
    return "\n".join(html_parts)   
   
def render_html_main(sections):
    """HTML renderer for the <main> element."""
    html_parts = []
    
    # Sections strictly for the Main area
    main_keys = ["Definition", "Broader", "Narrower", "Related"]
    
    for header in main_keys:
        lines = sections.get(header)
        if not lines: continue
        
        # 1. Add the Section Title
        html_parts.append(f"<h2>{header}</h2>")
        
        # 2. CALL THE HELPER FUNCTION
        # This handles the mix of paragraphs, headers, and bullet lists
        section_html = render_section_to_html(lines)
        html_parts.append(section_html)
            
    return "\n".join(html_parts)    
    
def render_html_aside(sections):
    """HTML renderer for the <aside> element."""
    html_parts = []
    main_keys = ["Definition", "Broader", "Narrower", "Related"]
    
    for header, lines in sections.items():
        if not lines: continue
        if header in main_keys: continue # Skip main stuff
        
        html_parts.append(f"<h2>{header}</h2>")
        
        # CALL THE HELPER FUNCTION
        section_html = render_section_to_html(lines)
        html_parts.append(section_html)
        
    return "\n".join(html_parts)
    
def double_indent(html):
    # Replace leading spaces on each line
    return re.sub(
        r'(?m)^( +)',               # match 1+ spaces at start of line
        lambda m: '  ' * len(m.group(1)),    # double the indent
        html
    )

def pass_two_build_site():
    print("--- Generating Site ---")
    
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("skos_concept.html")
    
    # Ensure the 0.0.1 folder exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    for file_path in get_files():
        post = frontmatter.load(file_path)
        uuid = post.metadata.get('concept-key')
        if not uuid: continue
        
        title = file_path.stem 
        sections = parse_sections(post.content)
        
        skos_data = generate_skos_json(uuid, title, sections)
        html_main = render_html_main(sections)
        html_aside = render_html_aside(sections)
        
        output_html = template.render(
            title=title,
            html_main_content=html_main,
            html_aside_content=html_aside,
            json_ld=json.dumps(skos_data, indent=2),
            uuid=uuid,
            version=VERSION
        )
        
        pretty_html = BeautifulSoup(output_html, "html.parser").prettify()
        pretty_indent2 = double_indent(pretty_html)
        
        # CHANGED: Write directly to {UUID}.html in the output dir
        filename = f"{uuid}.html"
        target_file = OUTPUT_DIR / filename
        
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(pretty_indent2)
            
    print(f"Build Complete. Files written to {OUTPUT_DIR}")

if __name__ == "__main__":
    pass_one_index_uuids()
    pass_two_build_site()