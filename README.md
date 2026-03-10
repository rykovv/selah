# vMix Hymnal Manager

A web-based church service management tool that serves hymn slides, program data, and custom data feeds to [vMix](https://www.vmix.com/) via JSON API endpoints.

Built with FastAPI and HTMX for a responsive, single-page-like experience without a JavaScript framework.

## Features

- **Hymn Library** -- import, create, and edit hymns with dual slide types (vMix and PowerPoint)
- **Service Plan** -- arrange hymns for a worship service with drag-to-reorder
- **Service Programs** -- build named program rundowns (announcements, worship items, etc.) with mute/unmute support
- **Data Tables** -- create custom data feeds with user-defined columns and rows, each served at a fixed JSON endpoint (e.g. `/api/feed/bible-verses`)
- **PowerPoint Generation** -- export hymn slides or full programs as `.pptx`, with template-based placeholder replacement
- **Presentation Templates** -- upload custom PowerPoint templates for program exports
- **API Monitoring** -- real-time request-rate charts for all JSON endpoints
- **Dark/Light Theme** -- toggle with automatic persistence
- **Configurable Storage** -- custom database and template directory paths via Settings

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
cd src/vmix-hymnal-manager
python app.py
```

The app starts at **http://localhost:10001**. On first run, a setup wizard will prompt you to configure database and template paths.

## Project Structure

```
src/vmix-hymnal-manager/
    app.py                  # Entry point (uvicorn)
    factory.py              # Application factory, middleware
    config.py               # Settings (host, port, paths)
    database.py             # SQLAlchemy engine, session, schema SQL
    models.py               # ORM models + Pydantic schemas
    utils.py                # Shared utilities
    routes/
        dashboard.py        # Dashboard page
        hymns.py            # Hymn CRUD, editor, service plan
        programs.py         # Program CRUD, items, PPT export
        data_tables.py      # Data table CRUD, row management
        templates_mgr.py    # Template upload/delete
        api.py              # JSON API endpoints (vMix feeds)
        monitoring.py       # Monitoring dashboard + stats API
        settings.py         # Storage path configuration
    services/
        pptx_service.py     # PowerPoint generation
        program_service.py  # Program JSON serialization
        monitoring.py       # Request rate tracking
    templates/              # Jinja2 HTML templates
scripts/                    # Database migration/patch scripts
```

## API Endpoints

These JSON endpoints are designed to be consumed by vMix as data sources:

| Endpoint | Description |
|----------|-------------|
| `GET /api/vmix` | All hymn slides (flattened rows: number, title, label, text) |
| `GET /api/program/current` | Currently active program items |
| `GET /api/program/{id}/json` | Specific program items by ID |
| `GET /api/feed/{slug}` | Custom data table rows (user-defined columns) |

### Monitoring

| Endpoint | Description |
|----------|-------------|
| `GET /api/monitoring/stats?window=1` | Request-per-second stats for all monitored feeds |

## Configuration

Default settings (in `config.py`):

| Setting | Default |
|---------|---------|
| Host | `0.0.0.0` |
| Port | `10001` |
| Database | `hymns.db` (relative to CWD) |
| Templates dir | `templates/` |

Custom database and template directory paths can be configured through the **Settings** page in the app. These are stored in a bootstrap `app_settings` table within the default database.

## Database

SQLite with 9 tables, auto-created on first run. The schema is defined in `database.py` and mirrored by SQLAlchemy models in `models.py`.

For existing installations, migration scripts are available in `scripts/`:

```bash
cd src/vmix-hymnal-manager
python ../../scripts/patch_db_data_tables.py
```

Patch scripts auto-detect custom database paths from `app_settings`.

## Building

A PyInstaller spec file is included for building a standalone Windows executable:

```bash
pyinstaller vmix-church-service-manager.spec
```

Output: `dist/vmix-hymnal-manager/vmix-hymnal-manager.exe`
