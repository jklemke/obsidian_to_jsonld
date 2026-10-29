# obsidian_to_jsonld
Python code for transforming SKOS-annotated Obsidian markdown files to JSON-LD HTML pages for https://vernacular.cloud.

Only markdown files in the **root** of the vault are read, and only those with a `concept-key` in their front matter become pages. Subfolders (the book, research notes, templates) are ignored.

## Setup (once per machine)
Requires Python 3.11 or later. In PowerShell:
```powershell
cd C:\Users\joekl\devel\obsidian_to_jsonld
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Then check the paths in `config.toml`.

## Settings
All paths, the version, the domain and the root concept key live in `config.toml`. The scripts read them through `vc_config.py`. Nothing is hard-coded in the scripts.

## Workflow
```powershell
.\.venv\Scripts\Activate.ps1
python obsidian_to_jsonld.py            # build concept pages for the version named in config.toml
python obsidian_to_jsonld.py --rebuild  # regenerate an existing version from scratch
python generate_skos_for_index.py       # write <version>/index.html and the root redirect
python serve_localhost.py               # review at http://localhost:8899/
```
Each version is built into its own folder `<site_dir>/<version>/`. The build refuses to overwrite an existing version folder unless `--rebuild` is given, so earlier releases keep their permalinks.

To start a new release, change `version` in `config.toml` and run the build and the index script.

## The index page
The hand-crafted index lives in `templates/index.html` (Jinja2). Edit the section structure there, never in the site folder.
- Concept links in the template are relative (`href="<key>/"`), so they resolve inside whichever version folder the page is published to.
- `generate_skos_for_index.py` renders it to `<site_dir>/<version>/index.html`, adding JSON-LD built from the section structure and the vault's `# Definition` sections.
- It also writes `<site_dir>/index.html`, a small page that redirects `/` to `/<version>/`. It will not replace a root `index.html` that it did not generate, unless run with `--force`. Use `--no-root` to leave the root alone.

## Latest-version links
Pages link to `/latest/<key>/`. On the live site an AWS Amplify rule (app vernacular-cloud-003, eu-west-1) redirects `/latest/<*>` to `/<version>/<*>` (302); update its target at each release. `serve_localhost.py` imitates that rule locally.

Publish by committing and pushing the `vernacular-cloud-003` repository; AWS Amplify deploys from GitHub.
