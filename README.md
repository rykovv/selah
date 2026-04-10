# vMix Church Service Manager

A web-based church service management tool that serves hymn slides, program data, and custom data feeds to [vMix](https://www.vmix.com/) via JSON API endpoints.

Built with FastAPI and HTMX for a responsive, single-page-like experience without a JavaScript framework.

## Features

- **Hymn Library** -- import, create, and edit hymns with dual slide types (vMix and PowerPoint)
- **Service Plan** -- arrange hymns for a worship service with drag-to-reorder
- **Service Programs** -- build named program rundowns (announcements, worship items, etc.) with mute/unmute support
- **Data Tables** -- create custom data feeds with user-defined columns and rows, each served at a fixed JSON endpoint (e.g. `/api/feed/bible-verses`)
- **Data Table Patterns** -- configure data tables to supply `{{name_N}}` substitution tags to PowerPoint templates
- **PowerPoint Generation** -- export hymn slides or full programs as `.pptx`, with template-based placeholder replacement and timestamped filenames
- **Presentation Templates** -- upload custom PowerPoint templates for program exports
- **API Monitoring** -- real-time request-rate charts for all JSON endpoints
- **Dark/Light Theme** -- toggle with automatic persistence
- **Configurable Storage** -- custom database and template directory paths via Settings, persisted in a local `config.json`
- **Versioned Migrations** -- automatic database schema upgrades on startup

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.9, FastAPI, SQLAlchemy (sync), Jinja2 |
| Frontend | HTMX, Bootstrap 5, Sortable.js, Chart.js |
| Database | SQLite |
| PowerPoint | python-pptx, Pillow |
| Distribution | PyInstaller (standalone `.exe`) |

## Getting Started

### Prerequisites

- Python 3.9+

### Installation

```bash
git clone <repo-url>
cd vmix-hymal-manager
pip install -r requirements.txt
```

### Running

```bash
cd src/vmix-church-service-manager
python app.py
```

The app starts at **http://localhost:10001**. On first run, a setup wizard will prompt you to configure database and template paths.

## Project Structure

```
src/vmix-church-service-manager/
    app.py                  # Entry point (uvicorn)
    factory.py              # Application factory, middleware
    config.py               # Settings (host, port, paths, version)
    config_file.py          # Persistent config.json reader/writer
    database.py             # SQLAlchemy engine, session, migrations
    models.py               # ORM models + Pydantic schemas
    utils.py                # Shared utilities
    routes/
        dashboard.py        # Dashboard page
        hymns.py            # Hymn CRUD, editor, service plan
        programs.py         # Program CRUD, items, PPT export
        data_tables.py      # Data table CRUD, row management, patterns
        templates_mgr.py    # Template upload/delete
        api.py              # JSON API endpoints
        monitoring.py       # Monitoring dashboard + stats API
        settings.py         # Storage path configuration
    services/
        pptx_service.py     # PowerPoint generation (3-phase)
        program_service.py  # Program JSON serialization
        monitoring.py       # Request rate tracking
    templates/              # Jinja2 HTML templates
scripts/                    # Database migration/patch scripts
```

## API Endpoints

These JSON endpoints are designed to be consumed by vMix as data sources:

| Endpoint | Description |
|----------|-------------|
| `GET /api/hymns/service` | All hymn slides (flattened rows: number, title, label, text) |
| `GET /api/program/current` | Currently active program items |
| `GET /api/program/{id}/json` | Specific program items by ID |
| `GET /api/feed/{slug}` | Custom data table rows (user-defined columns) |
| `GET /api/version` | App version |

### Monitoring

| Endpoint | Description |
|----------|-------------|
| `GET /api/monitoring/stats?window=1` | Request-per-second stats for all monitored feeds |

## PPT Pattern Substitution

When generating a PowerPoint from a service program, the system scans the template for `{{...}}` tags and resolves them in priority order:

| Pattern | Source |
|---------|--------|
| `{{tag}}` | Service program item — replaced by the Person/Description of the item whose PPT Tag matches |
| `{{name_N}}` | Data table pattern — replaced by row N of a data table with pattern "name" enabled |
| `{{hymn_N}}` | Service plan hymn — exploded into title + lyrics slides |

Configure data table patterns in the data table editor via the **Pattern** button.

## Configuration

Default settings (in `config.py`):

| Setting | Default |
|---------|---------|
| Host | `0.0.0.0` |
| Port | `10001` |
| Database | `hymns.db` (relative to CWD) |
| Templates dir | `templates/` |

Custom database and template directory paths can be configured through the **Settings** page. Paths are persisted in `config.json` (next to the executable) so they survive reinstalls and fresh runs.

## Database

SQLite with 10 tables, auto-created on first run. The schema is defined in `database.py` and mirrored by SQLAlchemy models in `models.py`.

Versioned migrations run automatically on startup. The current schema version is tracked in the `app_settings` table.

## Building

A PyInstaller spec file is included for building a standalone Windows executable:

```bash
pyinstaller vmix-church-service-manager.spec
```

Output: `dist/vmix-church-service-manager/vmix-church-service-manager.exe`

## Releases

Automated via GitHub Actions. Push a tag matching `v*` to trigger a build:

```bash
git tag -a v1.1.0 -m "v1.1.0"
git push origin v1.1.0
```

The workflow builds on Windows, creates a zip archive, and publishes a GitHub Release with auto-generated notes.
