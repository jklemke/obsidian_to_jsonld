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
python obsidian_to_jsonld.py            # build the version named in config.toml
python obsidian_to_jsonld.py --rebuild  # regenerate an existing version from scratch
python generate_skos_for_index.py       # refresh JSON-LD in the root index.html (keeps index.html.bak)
python serve_localhost.py               # review at http://localhost:8899/
```
Each version is built into its own folder `<site_dir>/<version>/`. The build refuses to overwrite an existing version folder unless `--rebuild` is given, so earlier releases keep their permalinks.

To start a new release, change `version` in `config.toml` and build.

Publish by committing and pushing the `vernacular-cloud-003` repository; AWS Amplify deploys from GitHub.
