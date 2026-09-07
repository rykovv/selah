# Selah

**Selah** is a church service management system: plan services, manage hymn sets and lyrics, generate PowerPoint decks, and feed live data to [vMix](https://www.vmix.com/) via JSON API endpoints.

Built with FastAPI and HTMX for a responsive, single-page-like experience without a JavaScript framework. Ships as a Windows installer with in-app auto-update; runs fully offline.

> *Selah* — the word that appears throughout the Psalms, often understood as a pause to reflect during worship.

## Features

- **Hymn Library** -- import, create, and edit hymns with dual slide types (vMix and PowerPoint)
- **Hymn Sets** -- keep multiple named hymn sets (Sabbath School, Divine Service, …); the live set drives the vMix feed
- **Bible** -- verse sets with per-set translations (NKJV bundled; 200+ translations in ~40 languages downloadable), smart reference input with autocomplete, live verse preview, a vMix feed, and PPT export with automatic slide splitting for long passages
- **Service Programs** -- build named program rundowns (announcements, worship items, etc.) with mute/unmute support
- **Cell References** -- fill any program or data table cell by referencing another (`$row:Column`) with live resolution
- **Data Tables** -- create custom data feeds with user-defined columns and rows, each served at a fixed JSON endpoint (e.g. `/api/feed/bible-verses`)
- **Data Table Patterns** -- configure data tables to supply `{{name_N}}` / `{{name_column_N}}` substitution tags to PowerPoint templates
- **PowerPoint Generation** -- export hymn slides or full programs as `.pptx`, with template-based placeholder replacement, live preview, and font inheritance
- **Presentation Templates** -- upload custom PowerPoint templates for program exports
- **API Monitoring** -- real-time request-rate charts for all JSON endpoints
- **Auto-Update** -- installed apps check GitHub releases and update with one click
- **Dark/Light Theme** -- toggle with automatic persistence
- **Configurable Storage** -- custom database and template directory paths via Settings; point them at a synced folder to share across machines
- **Versioned Migrations** -- automatic database schema upgrades on startup

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.9, FastAPI, SQLAlchemy (sync), Jinja2 |
| Frontend | HTMX, Bootstrap 5, Sortable.js, Chart.js (all vendored, offline-capable) |
| Database | SQLite |
| PowerPoint | python-pptx, Pillow |
| Distribution | Inno Setup installer + PyInstaller (windowed `.exe`) |

## Getting Started

### Installing (Windows)

Download `selah-setup-<version>.exe` from the [latest release](https://github.com/rykovv/selah/releases) and run it. No admin rights needed; data lives in `%APPDATA%\Selah`.

### Running from source

```bash
git clone https://github.com/rykovv/selah.git
cd selah
pip install -r requirements.txt
cd src/selah
python -m uvicorn app:app --host 0.0.0.0 --port 10001
```

The app starts at **http://localhost:10001**. On first run, a setup wizard will prompt you to configure database and template paths.

## Project Structure

```
src/selah/
    app.py                  # Entry point (uvicorn, logging)
    factory.py              # Application factory, middleware
    config.py               # Settings (host, port, paths, version)
    config_file.py          # Persistent config.json reader/writer
    paths.py                # Windows-conventional data/log locations
    database.py             # SQLAlchemy engine, session, migrations
    models.py               # ORM models + Pydantic schemas
    utils.py                # Shared utilities (incl. cell reference resolver)
    routes/                 # dashboard, hymns, bible, programs, data_tables,
                            # templates_mgr, api, monitoring, settings
    services/               # pptx generation, program serialization,
                            # hymn sets, bible translations & verse sets,
                            # updater, autostart, app control,
                            # log buffer, monitoring
    templates/              # Jinja2 HTML templates
    static/                 # Vendored frontend assets + shared JS
    bibles/                 # Bundled Bible data (catalog + KJV + RU Synodal)
installer/setup.iss         # Inno Setup script
build.ps1                   # Local build (PyInstaller + ISCC)
```

## API Endpoints

These JSON endpoints are designed to be consumed by vMix as data sources:

| Endpoint | Description |
|----------|-------------|
| `GET /api/hymns/service` | Live hymn set slides (flattened rows: number, title, label, text) |
| `GET /api/bible/service` | Live Bible verse set (one row per entry: reference, verse text) |
| `GET /api/program/current` | Currently active program items |
| `GET /api/program/{id}/json` | Specific program items by ID |
| `GET /api/feed/{slug}` | Custom data table rows (user-defined columns) |
| `GET /api/version` | App version |
| `GET /api/monitoring/stats?window=1` | Request-per-second stats for all monitored feeds |

## PPT Pattern Substitution

When generating a PowerPoint from a service program, the system scans the template for `{{...}}` tags and resolves them in priority order:

| Pattern | Source |
|---------|--------|
| `{{tag}}` | Service program item — replaced by the Subtitle of the item whose Tag matches |
| `{{name_N}}` / `{{name_column_N}}` | Data table pattern — value column or any column of row N |
| `{{hymn_N}}` | Live hymn set — exploded into title + lyrics slides |

Configure data table patterns in the data table editor via the **Pattern** button.

## Building

```powershell
.\build.ps1              # PyInstaller bundle + Inno Setup installer
.\build.ps1 -SkipInstaller
```

Output: `dist\installer\selah-setup-<version>.exe` (requires [Inno Setup 6](https://jrsoftware.org/isdl.php)).

## Releases

Automated via GitHub Actions. Bump `APP_VERSION` in `config.py`, then push a matching tag:

```bash
git tag v1.5.0
git push origin v1.5.0
```

Every release ships the installer (which is also the silent auto-update payload) and a portable zip.
