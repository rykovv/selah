"""Data Tables — custom vMix data feeds with user-defined columns and rows."""

import json
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from database import get_db
from models import DataTableModel, DataTableRowModel
from utils import generate_slug, sort_data_table_rows

router = APIRouter()


def _touch(table):
    """Update the table's updated_at timestamp."""
    table.updated_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Table CRUD
# ---------------------------------------------------------------------------

@router.get("/data-tables", response_class=HTMLResponse)
def page_data_tables(request: Request, db: Session = Depends(get_db)):
    tables = (
        db.query(DataTableModel)
        .order_by(DataTableModel.updated_at.desc(), DataTableModel.id.desc())
        .all()
    )
    for t in tables:
        t._columns = json.loads(t.columns_json)
        t._row_count = len(t.rows)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "data_tables.html", {"request": request, "tables": tables}
    )


@router.post("/data-tables/new")
def new_data_table(
    request: Request,
    name: str = Form(...),
    columns: List[str] = Form(...),
    db: Session = Depends(get_db),
):
    col_names = [c.strip() for c in columns if c.strip()]
    if not col_names:
        return Response("At least one column is required.", status_code=400)

    slug = generate_slug(name)
    base_slug = slug
    counter = 1
    while db.query(DataTableModel).filter(DataTableModel.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    table = DataTableModel(
        name=name.strip(),
        slug=slug,
        columns_json=json.dumps(col_names),
    )
    db.add(table)
    db.commit()
    db.refresh(table)
    return RedirectResponse(f"/data-tables/{table.id}", status_code=303)


@router.get("/data-tables/{table_id}", response_class=HTMLResponse)
def page_data_table_editor(
    table_id: int, request: Request, db: Session = Depends(get_db)
):
    table = db.query(DataTableModel).filter(DataTableModel.id == table_id).first()
    if not table:
        return RedirectResponse("/data-tables", status_code=303)

    columns = json.loads(table.columns_json)
    rows = sort_data_table_rows(table.rows)
    row_data = []
    for r in rows:
        data = json.loads(r.data_json)
        row_data.append({"row": r, "data": data})

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "data_table_editor.html",
        {
            "request": request,
            "table": table,
            "columns": columns,
            "row_data": row_data,
        },
    )


@router.delete("/data-tables/{table_id}")
def delete_data_table(table_id: int, db: Session = Depends(get_db)):
    db.query(DataTableModel).filter(DataTableModel.id == table_id).delete()
    db.commit()
    return Response(
        headers={"HX-Redirect": "/data-tables"}, status_code=200
    )


@router.post("/data-tables/{table_id}/update_meta")
def update_data_table_meta(
    table_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    table = db.query(DataTableModel).filter(DataTableModel.id == table_id).first()
    if not table:
        return Response("Table not found", status_code=404)

    table.name = name.strip()
    _touch(table)
    db.commit()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Column management
# ---------------------------------------------------------------------------

@router.post("/data-tables/{table_id}/update_columns")
def update_columns(
    table_id: int,
    columns: List[str] = Form(...),
    db: Session = Depends(get_db),
):
    table = db.query(DataTableModel).filter(DataTableModel.id == table_id).first()
    if not table:
        return Response("Table not found", status_code=404)

    new_cols = [c.strip() for c in columns if c.strip()]
    if not new_cols:
        return Response("At least one column is required.", status_code=400)

    table.columns_json = json.dumps(new_cols)
    _touch(table)

    # Migrate existing row data to match new columns
    for row in table.rows:
        old_data = json.loads(row.data_json)
        new_data = {col: old_data.get(col, "") for col in new_cols}
        row.data_json = json.dumps(new_data)

    db.commit()
    return RedirectResponse(f"/data-tables/{table_id}", status_code=303)


# ---------------------------------------------------------------------------
# Row CRUD
# ---------------------------------------------------------------------------

@router.post("/data-tables/{table_id}/add_row")
def add_data_table_row(
    table_id: int, request: Request, db: Session = Depends(get_db)
):
    table = db.query(DataTableModel).filter(DataTableModel.id == table_id).first()
    if not table:
        return Response("Table not found", status_code=404)

    columns = json.loads(table.columns_json)
    empty_data = {col: "" for col in columns}
    new_row = DataTableRowModel(
        table_id=table_id, data_json=json.dumps(empty_data), sequence=999
    )
    db.add(new_row)
    _touch(table)
    db.commit()
    db.refresh(new_row)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/data_table_row.html",
        {"request": request, "row": new_row, "columns": columns, "data": empty_data},
    )


@router.post("/data-tables/row/{row_id}/update")
async def update_data_table_row(
    row_id: int, request: Request, db: Session = Depends(get_db)
):
    row = db.query(DataTableRowModel).filter(DataTableRowModel.id == row_id).first()
    if not row:
        return Response("Row not found", status_code=404)

    columns = json.loads(row.table.columns_json)
    form = await request.form()
    data = {}
    for col in columns:
        data[col] = form.get(f"col__{col}", "")
    row.data_json = json.dumps(data)
    _touch(row.table)
    db.commit()
    return Response(status_code=200)


@router.delete("/data-tables/row/{row_id}")
def delete_data_table_row(row_id: int, db: Session = Depends(get_db)):
    row = db.query(DataTableRowModel).filter(DataTableRowModel.id == row_id).first()
    if row:
        _touch(row.table)
        db.delete(row)
        db.commit()
    return Response(status_code=200)


@router.post("/data-tables/{table_id}/reorder")
def reorder_data_table_rows(
    table_id: int,
    item_ids: List[int] = Form(...),
    db: Session = Depends(get_db),
):
    table = db.query(DataTableModel).filter(DataTableModel.id == table_id).first()
    if table:
        _touch(table)
    for index, row_id in enumerate(item_ids):
        row = (
            db.query(DataTableRowModel)
            .filter(DataTableRowModel.id == row_id)
            .first()
        )
        if row:
            row.sequence = index
    db.commit()
    return Response(status_code=200)
