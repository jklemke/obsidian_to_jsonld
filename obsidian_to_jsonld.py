import os
import re
import json
import frontmatter
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from html.parser import HTMLParser

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
            # OLD: return f'<a href="{target_uuid}.html" ...            
            # NEW: Absolute path to the directory (matches the JSON-LD ID)
            # Note: We ensure there is NO .html extension.
            return f'<a href="/{VERSION}/{target_uuid}" class="internal-link">{label_text}</a>'            
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

class SmartHTMLFormatter(HTMLParser):
    def __init__(self, indent_width=2):
        super().__init__()
        self.indent_width = indent_width
        self.level = 0
        self.formatted = []
        
        # Tags that define the SKELETON (Always break lines around them)
        self.structural_tags = {
            'html', 'head', 'body', 'header', 'footer', 'main', 'aside', 
            'section', 'div', 'ul', 'ol', 'script', 'style', 'meta', 'link'
        }
        
        # Tags that define CONTENT (Start on new line, but keep text inline)
        self.content_tags = {
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'title', 'blockquote', 'small'
        }
        
        self.void_tags = {'meta', 'link', 'img', 'br', 'hr', 'input'}
        
        # State tracking
        self.just_opened_block = False

    def _add_newline_if_needed(self):
        if self.formatted and not self.formatted[-1].endswith('\n'):
            self.formatted.append('\n')

    def _indent(self):
        self.formatted.append(' ' * (self.level * self.indent_width))

    def handle_starttag(self, tag, attrs):
        # 1. Logic for Structural Tags (ul, div, main)
        if tag in self.structural_tags:
            self._add_newline_if_needed()
            self._indent()
            
            # Reconstruct tag
            attr_str = ''.join(f' {k}="{v}"' if v else f' {k}' for k, v in attrs)
            self.formatted.append(f"<{tag}{attr_str}>")
            
            if tag not in self.void_tags:
                self.level += 1
                self.just_opened_block = True

        # 2. Logic for Content Tags (p, h1, li)
        elif tag in self.content_tags:
            self._add_newline_if_needed()
            self._indent()
            
            attr_str = ''.join(f' {k}="{v}"' if v else f' {k}' for k, v in attrs)
            self.formatted.append(f"<{tag}{attr_str}>")
            
            # We do NOT add a newline here. We wait for text.
            self.just_opened_block = True
            
        # 3. Inline Tags (a, span, strong)
        else:
            # Just append inline
            attr_str = ''.join(f' {k}="{v}"' if v else f' {k}' for k, v in attrs)
            self.formatted.append(f"<{tag}{attr_str}>")
            self.just_opened_block = False

    def handle_endtag(self, tag):
        # 1. Structural Tags
        if tag in self.structural_tags:
            if tag not in self.void_tags:
                self.level -= 1
                self._add_newline_if_needed()
                self._indent()
            self.formatted.append(f"</{tag}>")
            self.just_opened_block = False

        # 2. Content Tags
        elif tag in self.content_tags:
            # If we are closing a content tag, we check:
            # Did we just finish a nested block (like a <ul> inside a <li>)?
            # If yes, we are on a new line, so we need to indent.
            # If no (we just had text), we close on the same line.
            if self.formatted and self.formatted[-1].endswith('\n'):
                 self._indent()
            
            self.formatted.append(f"</{tag}>")
            self.just_opened_block = False

        # 3. Inline Tags
        else:
            self.formatted.append(f"</{tag}>")

    def handle_data(self, data):
        stripped = data.strip()
        if not stripped: return

        # If we just opened a STRUCTURAL block (like <ul>), we need a newline before text
        # (Though valid HTML rarely has raw text directly inside <ul>)
        if self.just_opened_block and self.formatted[-1].endswith('>'):
             # Check if the last tag was structural
             last_tag_line = self.formatted[-1]
             # If strictly structural, maybe force newline? 
             # For now, let's keep it simple: Text always appends.
             pass

        self.formatted.append(data)
        # We consumed the "just opened" state
        self.just_opened_block = False
    
    def handle_decl(self, decl):
        self.formatted.append(f"<!{decl}>\n")

    def handle_comment(self, data):
        self._add_newline_if_needed()
        self._indent()
        self.formatted.append(f"")
        
def prettify_html(html_content):
    formatter = SmartHTMLFormatter(indent_width=2)
    formatter.feed(html_content)
    # Join and clean up multiple newlines
    output = "".join(formatter.formatted)
    # Simple regex to remove excessive blank lines (optional)
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

def pass_two_build_site():
    print("--- Generating Site ---")
    
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("skos_concept.html")
    
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
        
        # Render the raw HTML from Jinja
        raw_html = template.render(
            title=title,
            html_main_content=html_main,
            html_aside_content=html_aside,
            json_ld=json.dumps(skos_data, indent=8),
            uuid=uuid,
            version=VERSION
        )
        
        # --- NEW FORMATTING LOGIC ---
        # 1. Use the custom Smart Formatter
        final_html = prettify_html(raw_html)
        
        # 2. Write to file       
        # OLD:
        # filename = f"{uuid}.html"
        # target_file = OUTPUT_DIR / filename

        # NEW: Directory Index Pattern
        # Creates: vernacular-cloud-003/0.0.1/{uuid}/index.html
        concept_dir = OUTPUT_DIR / uuid
        concept_dir.mkdir(parents=True, exist_ok=True)
        
        target_file = concept_dir / "index.html"
        
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(final_html)        
            
    print(f"Build Complete. Files written to {OUTPUT_DIR}")
    
if __name__ == "__main__":
    pass_one_index_uuids()
    pass_two_build_site()
