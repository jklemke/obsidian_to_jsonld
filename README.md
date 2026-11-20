# obsidian_to_jsonld
Python code for transforming SKOS-annotated Obsidian markdown files to JSON-LD HTML pages for the Badinagean Nomenclature at https://graszp.info.

Until release 0.0.8 the nomenclature lived at https://vernacular.cloud; since 0.1.0 (2026-11-19) it lives at https://graszp.info, the reference case of the [graszp](https://graszp.com) method. Every old vernacular.cloud address redirects there.

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
All paths, the version, the domain, the site name, the previous domain (for `owl:sameAs`) and the root concept key live in `config.toml`. The scripts read them through `vc_config.py`. Nothing is hard-coded in the scripts.

## Workflow
```powershell
.\.venv\Scripts\Activate.ps1
python obsidian_to_jsonld.py            # build concept pages for the version named in config.toml
python obsidian_to_jsonld.py --rebuild  # regenerate an existing version from scratch
python generate_skos_for_index.py       # write <version>/index.html, the site-level pages and the permanent IRI pages
python generate_skos_for_index.py --site-only   # only the site-level pages (after editing their templates)
python preview.py                       # build the unpublished version and review it on localhost
python serve_localhost.py               # review at http://localhost:8899/
```
Each version is built into its own folder `<site_dir>/<version>/`. The build refuses to overwrite an existing version folder unless `--rebuild` is given, so earlier releases keep their permalinks.

To start a new release, change `version` in `config.toml` and run the build and the index script.

## The index page
The hand-crafted index lives in `templates/index.html` (Jinja2). Edit the section structure there, never in the site folder.
- Concept links in the template are relative (`href="<key>/"`), so they resolve inside whichever version folder the page is published to.
- `generate_skos_for_index.py` renders it to `<site_dir>/<version>/index.html`, adding JSON-LD built from the section structure and the vault's `# Definition` sections.
- It also writes the site-level pages (D-012), unversioned and rewritten at each release:
	- `/` and `/nomenclature/` redirect to `/<version>/`; `/nomenclature/about/` is the About page; the old `/about/` redirects there
	- the list is `SITE_PAGES` in `generate_skos_for_index.py`
- The Vernacular Cloud LLC pages (`/`, `/consulting/`, `/method/`, the `/nomenclature/` pointer) are no longer generated: they are maintained by hand in the `vernacular-cloud-003` repository.
- It will not replace a site-level page that it did not generate, unless run with `--force`. Use `--no-root` to leave them alone.

## Permanent IRIs (D-006)
`https://graszp.info/<key>/` is the concept itself; `/<version>/<key>/` is one frozen version of it. A full `generate_skos_for_index.py` run writes a small page at each `/<key>/` and at `/concept-scheme/` with `dct:hasVersion` links and a redirect to the latest version. Concepts first published at vernacular.cloud (up to `previous_last_version`) also carry `owl:sameAs` their old `https://vernacular.cloud/<key>/` IRI.

## Latest-version links
Pages link to `/latest/<key>/`. On the live site an AWS Amplify rule (app for graszp.info, eu-west-1) redirects `/latest/<*>` to `/<version>/<*>` (302); update its target at each release. `serve_localhost.py` imitates that rule locally.

Publish by committing and pushing the `graszp.info` repository (github.com/graszp/graszp.info); AWS Amplify deploys from GitHub. The `vernacular-cloud-003` app redirects every nomenclature path to graszp.info (301).
