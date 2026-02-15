import re

import sys
import os
import shutil

from datetime import datetime, timezone

import uvicorn

from fastapi import FastAPI, Depends
from fastapi import Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import UploadFile, File

from pydantic import BaseModel, ConfigDict
from typing import List

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from sqlalchemy import or_

from fastapi.responses import StreamingResponse # Add this to imports
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.dml.color import RGBColor
from io import BytesIO


DATABASE_URL = "sqlite:///./hymns.db"
UPLOAD_DIR = "templates"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

if getattr(sys, 'frozen', False):
    # Running as compiled .exe
    base_dir = os.path.dirname(sys.executable)
    
    # Check for PyInstaller v6+ structure (_internal folder)
    internal_templates = os.path.join(base_dir, "_internal", "templates")
    root_templates = os.path.join(base_dir, "templates")
    
    if os.path.exists(internal_templates):
        template_dir = internal_templates
    else:
        template_dir = root_templates
else:
    # Running as script (Dev mode)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, "templates")

# Initialize Jinja2 with the correct dynamic path
templates = Jinja2Templates(directory=template_dir)

def get_db():
    """Dependency injection for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class HymnModel(Base):
    __tablename__ = "hymns"
    
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String, unique=True, index=True)
    title = Column(String)
    
    # Relationship: One Hymn -> Many Slides
    slides = relationship("SlideModel", back_populates="hymn", cascade="all, delete-orphan")
    service_plans = relationship("ServicePlanHymnModel", back_populates="hymn")

class SlideModel(Base):
    __tablename__ = "slides"
    id = Column(Integer, primary_key=True, index=True)
    hymn_id = Column(Integer, ForeignKey("hymns.id"))
    
    label = Column(String)  # e.g., "Verse 1", "Chorus"
    content = Column(Text)
    order = Column(Integer)
    
    # 'VMIX' or 'PPT'
    # We default to 'VMIX' so existing data still works
    type = Column(String, default="VMIX") 

    hymn = relationship("HymnModel", back_populates="slides")


class ServicePlanHymnModel(Base):
    __tablename__ = "service_plan"
    
    id = Column(Integer, primary_key=True, index=True)
    sequence = Column(Integer, unique=True) # 1st hymn, 2nd hymn, etc.
    hymn_id = Column(Integer, ForeignKey("hymns.id"))
    
    # We fetch the hymn details when we load the plan
    hymn = relationship("HymnModel", back_populates="service_plans")


class ServiceProgramModel(Base):
    __tablename__ = "programs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String) 
    is_active = Column(Boolean, default=False)
    template_id = Column(Integer, ForeignKey("presentation_templates.id"), nullable=True)
    last_used = Column(DateTime, default=datetime.now(timezone.utc))

    template = relationship("PresentationTemplateModel")
    items = relationship("ServiceProgramItemModel", back_populates="program", cascade="all, delete-orphan")


class ServiceProgramItemModel(Base):
    __tablename__ = "program_items"

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(Integer, ForeignKey("programs.id"))
    sequence = Column(Integer)
    title = Column(String)     
    subtitle = Column(String)
    tag = Column(String) # PPT tag for dynamic replacement, e.g. {{offertory}}
    is_muted = Column(Boolean, default=False) # If True, hide from vMix JSON

    program = relationship("ServiceProgramModel", back_populates="items")


class PresentationTemplateModel(Base):
    __tablename__ = "presentation_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    filename = Column(String) # The actual file name on disk

# --- 3. The vMix Transformation Logic ---

class VmixRow(BaseModel):
    HymnNumber: str
    Title: str
    Label: str
    SlideText: str

    model_config = ConfigDict(from_attributes=True)


app = FastAPI()

# Create tables on startup
Base.metadata.create_all(bind=engine)


@app.get("/api/vmix", response_model=List[VmixRow])
def get_vmix_feed(db: Session = Depends(get_db)):
    """
    1. Query the ServicePlan to see what is scheduled.
    2. Join with Hymns and Slides.
    3. Flatten into the list format vMix needs.
    """
    # Get the plan, ordered by sequence (1st hymn, 2nd hymn...)
    service_items = db.query(ServicePlanHymnModel).order_by(ServicePlanHymnModel.sequence).all()
    
    vmix_output = []
    
    for item in service_items:
        hymn = item.hymn
        if not hymn: 
            continue
            
        # 1. Add the Hymn's Slides
        # Filter for PPT slides specifically
        vmix_slides_db = [s for s in hymn.slides if s.type == "VMIX"]
        
        # Fallback: If no VMIX slides exist, use PPT slides
        if not vmix_slides_db:
             vmix_slides_db = [s for s in hymn.slides if s.type == "PPT" or s.type is None]

        sorted_slides = sorted(vmix_slides_db, key=lambda x: x.order)
        
        for slide in sorted_slides:
            vmix_output.append(VmixRow(
                HymnNumber=hymn.number,
                Title=hymn.title,
                Label=slide.label,
                SlideText=slide.content
            ))
            
        # 2. Add 'Spacer' ONLY if this is not the last item
        vmix_output.append(VmixRow(
            HymnNumber="",         # Blank so it doesn't show garbage
            Title="",              # Visual cue for the vMix operator
            Label="",              # Shows 'CLEAR' in the vMix list column
            SlideText=""           # Empty text forces the Lower Third to clear
        ))
            
    return vmix_output


@app.get("/", response_class=HTMLResponse)
def read_dashboard(request: Request, db: Session = Depends(get_db)):
    """The new Main Dashboard: Active Program + Service Program"""
    
    # 1. Get Active Program
    active_prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.is_active == True).first()
    if active_prog:
        # Sort items
        active_prog.items.sort(key=lambda x: (x.sequence if x.sequence is not None else 9999, x.id))

    # 2. Get Hymn Service Plan
    plan = db.query(ServicePlanHymnModel).order_by(ServicePlanHymnModel.sequence).all()
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "program": active_prog,
        "service_plan": plan
    })

# --- HYMN MANAGER (Formerly Index) ---
@app.get("/hymns", response_class=HTMLResponse)
def page_hymns_manager(
    request: Request,
    db: Session = Depends(get_db)
):
    """The Hymn Selection Interface (Old Dashboard)"""
    # 1. Get the current plan
    plan = db.query(ServicePlanHymnModel).order_by(ServicePlanHymnModel.sequence).all()
    # 2. Get the full library (Simple version: fetch all)
    library = db.query(HymnModel).order_by(HymnModel.number).all()
    
    return templates.TemplateResponse("hymn_manager.html", {
        "request": request,
        "plan": plan,
        "library": library
    })


@app.post("/plan/add")
def add_to_plan(hymn_id: int = Form(...), db: Session = Depends(get_db)):
    """Add a hymn to the end of the service list."""
    # Find the current highest sequence number
    last_item = db.query(ServicePlanHymnModel).order_by(ServicePlanHymnModel.sequence.desc()).first()
    new_seq = (last_item.sequence + 1) if last_item else 1
    
    new_entry = ServicePlanHymnModel(sequence=new_seq, hymn_id=hymn_id)
    db.add(new_entry)
    db.commit()
    
    # Reload the page to show the change
    return RedirectResponse(url="/hymns", status_code=303)


@app.delete("/plan/{item_id}")
def remove_from_plan(item_id: int, db: Session = Depends(get_db)):
    """Remove an item. HTMX expects a 200 OK or empty response."""
    item = db.query(ServicePlanHymnModel).filter(ServicePlanHymnModel.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return HTMLResponse(content="") # Return empty string to remove element from DOM


@app.get("/editor", response_class=HTMLResponse)
def editor_dashboard(request: Request, db: Session = Depends(get_db)):
    """The main shell for the editor."""
    hymns = db.query(HymnModel).order_by(HymnModel.number).all()
    return templates.TemplateResponse("editor.html", {"request": request, "hymns": hymns})


@app.get("/hymns/form", response_class=HTMLResponse)
def get_empty_form(request: Request):
    """Returns an empty form for creating a new hymn."""
    return templates.TemplateResponse("partials/hymn_form.html", {"request": request, "hymn": None})


@app.get("/hymns/{hymn_id}/form", response_class=HTMLResponse)
def get_edit_form(hymn_id: int, request: Request, db: Session = Depends(get_db)):
    """Returns a pre-filled form for an existing hymn."""
    hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
    # Sort slides to ensure they appear in order
    if hymn:
        hymn.slides.sort(key=lambda x: x.order)
    
    return templates.TemplateResponse("partials/hymn_form.html", {"request": request, "hymn": hymn})


@app.post("/hymns/save")
def save_hymn(
    hymn_id: int = Form(None),
    number: str = Form(...),
    title: str = Form(...),
    # vMix Data
    vmix_labels: list[str] = Form(default=[]),
    vmix_contents: list[str] = Form(default=[]),
    # PPT Data
    ppt_labels: list[str] = Form(default=[]),
    ppt_contents: list[str] = Form(default=[]),
    db: Session = Depends(get_db)
):
    if hymn_id:
        hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
        hymn.number = number
        hymn.title = title
        # Clear old slides to replace with new ones
        db.query(SlideModel).filter(SlideModel.hymn_id == hymn_id).delete()
    else:
        hymn = HymnModel(number=number, title=title)
        db.add(hymn)
        db.commit() # Commit to get ID
        db.refresh(hymn)

    # 1. Save vMix Slides
    for i, (lbl, content) in enumerate(zip(vmix_labels, vmix_contents)):
        db.add(SlideModel(
            hymn_id=hymn.id, 
            label=lbl, 
            content=content, 
            order=i,
            type="VMIX"
        ))

    # 2. Save PPT Slides
    for i, (lbl, content) in enumerate(zip(ppt_labels, ppt_contents)):
        db.add(SlideModel(
            hymn_id=hymn.id, 
            label=lbl, 
            content=content, 
            order=i,
            type="PPT"
        ))

    db.commit()
    
    # Redirect back to editor to refresh the list
    return RedirectResponse(url="/editor", status_code=303)

@app.delete("/hymns/{hymn_id}")
def delete_hymn(hymn_id: int, db: Session = Depends(get_db)):
    # 1. Manual Cascade: Remove from service plans
    db.query(ServicePlanHymnModel).filter(ServicePlanHymnModel.hymn_id == hymn_id).delete()
    
    # 2. Delete the hymn
    hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
    if hymn:
        db.delete(hymn)
        db.commit()

    # 3. RETURN UI UPDATE
    # We return the "Empty State" HTML to clear the editor form immediately.
    # We ALSO send a custom header "HX-Trigger: refreshLibrary" which the sidebar listens for.
    empty_state = """
    <div class="d-flex h-100 justify-content-center align-items-center text-muted card-body">
        <div class="text-center">
            <h4>Hymn Deleted</h4>
            <p>Select another hymn or click "+ New Hymn"</p>
        </div>
    </div>
    """
    return HTMLResponse(content=empty_state, headers={"HX-Trigger": "refreshLibrary"})


@app.get("/library/search", response_class=HTMLResponse)
def search_library(request: Request, q: str = "", db: Session = Depends(get_db)):
    """
    Search hymns by Number, Title, or Slide Content.
    Returns a partial HTML list.
    """
    query = db.query(HymnModel).outerjoin(SlideModel)
    
    if q:
        search = f"%{q}%"
        # The core search logic:
        # 1. Match Number OR
        # 2. Match Title OR
        # 3. Match any Slide Content
        query = query.filter(
            or_(
                HymnModel.number.ilike(search),
                HymnModel.title.ilike(search),
                SlideModel.content.ilike(search)
            )
        )
    
    # .distinct() is crucial because joining on slides might return 
    # the same hymn multiple times if the keyword appears in multiple slides.
    hymns = query.distinct().order_by(HymnModel.number).all()
    
    return templates.TemplateResponse("partials/library_list.html", {
        "request": request, 
        "library": hymns
    })


@app.get("/editor/search", response_class=HTMLResponse)
def search_editor_library(request: Request, q: str = "", db: Session = Depends(get_db)):
    """
    Search endpoint specifically for the Editor sidebar.
    Returns clickable links instead of 'Add to Plan' buttons.
    """
    query = db.query(HymnModel).outerjoin(SlideModel)
    
    if q:
        search = f"%{q}%"
        query = query.filter(
            or_(
                HymnModel.number.ilike(search),
                HymnModel.title.ilike(search),
                SlideModel.content.ilike(search)
            )
        )
    
    hymns = query.distinct().order_by(HymnModel.number).all()
    
    return templates.TemplateResponse("partials/editor_list.html", {
        "request": request, 
        "hymns": hymns
    })


@app.get("/hymns/{hymn_id}/preview", response_class=HTMLResponse)
def preview_hymn(hymn_id: int, db: Session = Depends(get_db)):
    """Returns the hymn lyrics in a tabbed view (vMix & PPT)."""
    hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
    if not hymn:
        return "<div>Hymn not found</div>"
    
    # 1. Separate Slides by Type
    vmix_slides = sorted([s for s in hymn.slides if s.type == "VMIX"], key=lambda x: x.order)
    # Fallback for old data: if no type is set, treat as VMIX
    if not vmix_slides:
        vmix_slides = sorted([s for s in hymn.slides if s.type is None], key=lambda x: x.order)

    ppt_slides = sorted([s for s in hymn.slides if s.type == "PPT"], key=lambda x: x.order)

    # 2. Helper to generate slide HTML
    def render_slides(slides):
        if not slides:
            return '<div class="text-muted text-center p-4">No slides defined for this format.</div>'
        
        html_out = ""
        for i, slide in enumerate(slides):
            badge_class = "bg-secondary"
            lbl = slide.label.lower() if slide.label else ""
            if "v" in lbl: badge_class = "bg-primary"
            if "c" in lbl: badge_class = "bg-success"
            
            badge = f'<span class="badge {badge_class} me-2">{slide.label}</span>' if slide.label else ""
            
            html_out += f"""
            <div class="card mb-2 border-0 shadow-sm bg-light">
                <div class="card-body p-2 d-flex">
                    <div style="min-width: 80px;" class="text-muted small me-2">
                        Slide {i+1}<br>{badge}
                    </div>
                    <div class="text-dark flex-grow-1" style="white-space: pre-wrap; font-family: sans-serif; font-size: 1.1rem;">{slide.content}</div>
                </div>
            </div>
            """
        return html_out

    # 3. Construct the Tabbed Interface
    html = f"""
    <div class="p-0">
        <h4 class="text-primary px-2 mb-3">{hymn.number} - {hymn.title}</h4>

        <ul class="nav nav-tabs px-2" id="previewTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="prev-vmix-tab" data-bs-toggle="tab" data-bs-target="#prev-vmix" type="button" role="tab">
                    vMix (Live)
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="prev-ppt-tab" data-bs-toggle="tab" data-bs-target="#prev-ppt" type="button" role="tab">
                    PowerPoint
                </button>
            </li>
        </ul>

        <div class="tab-content p-2 mt-2" id="previewTabContent">
            <div class="tab-pane fade show active" id="prev-vmix" role="tabpanel">
                {render_slides(vmix_slides)}
            </div>
            
            <div class="tab-pane fade" id="prev-ppt" role="tabpanel">
                {render_slides(ppt_slides)}
            </div>
        </div>
    </div>
    """
    
    return html


@app.get("/download/ppt")
def download_ppt(
    aspect: str = "4:3",
    font_select: str = "Arial", # Renamed from 'font'
    font_manual: str = "",      # New parameter
    title_size: int = 80,
    lyrics_size: int = 60,
    db: Session = Depends(get_db)
):
    """Generates a Service PowerPoint with Manual Font Support."""
    
    plan = db.query(ServicePlanHymnModel).order_by(ServicePlanHymnModel.sequence).all()
    if not plan:
        return Response("Service program is empty", status_code=400)

    prs = Presentation()
    
    # 1. Geometry Setup
    if aspect == "4:3":
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)
        SLIDE_W = Inches(10)
        SLIDE_H = Inches(7.5)
    else:
        prs.slide_width = Inches(16)
        prs.slide_height = Inches(9)
        SLIDE_W = Inches(16)
        SLIDE_H = Inches(9)

    MARGIN = Inches(0.5)
    SAFE_WIDTH = SLIDE_W - (MARGIN * 2)
    SAFE_HEIGHT = SLIDE_H - (MARGIN * 2)

    # --- FONT LOGIC ---
    # Determine the actual font name to use
    if font_select == "Manual" and font_manual.strip():
        FONT_NAME = font_manual.strip()
    else:
        FONT_NAME = font_select

    BG_COLOR = RGBColor(0, 0, 0)
    TEXT_COLOR = RGBColor(255, 255, 255)
    
    TITLE_SIZE = Pt(title_size)      
    NUMBER_SIZE = Pt(int(title_size * 0.5)) 
    LYRICS_SIZE = Pt(lyrics_size) 

    # --- HELPERS ---
    def create_black_slide(prs):
        slide = prs.slides.add_slide(prs.slide_layouts[6]) 
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = BG_COLOR
        return slide

    def clean_text(text):
        if not text: return ""
        return text.replace('\r\n', '\n').replace('\r', '\n').replace('\x0b', '\n').strip()

    def get_text_frame(slide):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 
            MARGIN, MARGIN, SAFE_WIDTH, SAFE_HEIGHT
        )
        shape.fill.background() 
        shape.line.fill.background() 
        
        tf = shape.text_frame
        tf.word_wrap = True 
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE 
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE 
        return tf

    # --- GENERATION LOOP ---
    for index, item in enumerate(plan):
        hymn = item.hymn
        if not hymn: continue

        # A. TITLE SLIDE
        slide = create_black_slide(prs)
        tf = get_text_frame(slide)
        
        # Paragraph 1: Hymn Number
        p1 = tf.paragraphs[0]
        p1.text = f"Hymn #{hymn.number}"
        p1.font.name = FONT_NAME
        p1.font.size = NUMBER_SIZE
        p1.font.bold = False
        p1.font.color.rgb = TEXT_COLOR
        p1.alignment = PP_ALIGN.CENTER
        
        # Paragraph 2: Title
        p2 = tf.add_paragraph()
        p2.text = hymn.title
        p2.font.name = FONT_NAME
        p2.font.size = TITLE_SIZE
        p2.font.bold = True
        p2.font.color.rgb = TEXT_COLOR
        p2.alignment = PP_ALIGN.CENTER

        # B. LYRICS SLIDES
        slides_source = [s for s in hymn.slides if s.type == "PPT"]
        if not slides_source:
            slides_source = [s for s in hymn.slides if s.type == "VMIX" or s.type is None]
        
        grouped_slides = []
        current_group = None
        
        for s in sorted(slides_source, key=lambda x: x.order):
            content = clean_text(s.content)
            label = s.label
            
            if label or current_group is None:
                if current_group: grouped_slides.append(current_group)
                current_group = {'content': content} 
            else:
                current_group['content'] += "\n\n" + content
        if current_group: grouped_slides.append(current_group)

        for ppt_slide in grouped_slides:
            slide = create_black_slide(prs)
            tf = get_text_frame(slide)
            
            p = tf.paragraphs[0]
            p.text = ppt_slide['content']
            p.font.name = FONT_NAME
            p.font.size = LYRICS_SIZE
            p.font.bold = False
            p.font.color.rgb = TEXT_COLOR
            p.alignment = PP_ALIGN.CENTER
        
        # C. SPACER
        if index < len(plan) - 1:
            create_black_slide(prs)

    output = BytesIO()
    prs.save(output)
    output.seek(0)
    filename = f"Sabbath_Service_{aspect.replace(':','')}.pptx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return StreamingResponse(
        output, headers=headers, 
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


@app.get("/programs", response_class=HTMLResponse)
def page_programs(request: Request, db: Session = Depends(get_db)):
    programs = db.query(ServiceProgramModel).order_by(
        ServiceProgramModel.last_used.desc(), 
        ServiceProgramModel.id.desc()
    ).all()
    return templates.TemplateResponse("programs.html", {"request": request, "programs": programs})


@app.post("/programs/new")
def new_program(db: Session = Depends(get_db)):
    # Create blank program with default name
    # We removed the date logic here
    new_prog = ServiceProgramModel(name="New Service Program", is_active=False, last_used=datetime.now(timezone.utc))
    
    db.add(new_prog)
    db.commit()
    db.refresh(new_prog)
    
    return RedirectResponse(f"/programs/{new_prog.id}", status_code=303)


# 3. THE NEW EDITOR PAGE (Full Screen)
@app.get("/programs/{id}", response_class=HTMLResponse)
def program_editor_page(id: int, request: Request, db: Session = Depends(get_db)):
    prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).first()
    
    if not prog:
        return RedirectResponse("/programs")
    
    # CRITICAL: Sort items before sending to template
    # 1. Primary Sort: 'sequence' (Low numbers first)
    # 2. Secondary Sort: 'id' (Created earlier first, as tie-breaker)
    # We use 9999 as a fallback if sequence is None to put unsorted items at the end
    prog.items.sort(key=lambda x: (x.sequence if x.sequence is not None else 9999, x.id))
        
    all_templates = db.query(PresentationTemplateModel).all()
    
    return templates.TemplateResponse("program_editor.html", {
        "request": request, 
        "program": prog, 
        "templates": all_templates
    })


@app.delete("/programs/{id}")
def delete_program(id: int, db: Session = Depends(get_db)):
    """Deletes the entire program and redirects to the main list."""
    
    # 1. Delete the program (Cascades to items automatically if configured, 
    #    but standard SQLAlchemy delete usually handles it if relationships are set correctly)
    db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).delete()
    db.commit()
    
    # 2. Redirect back to the main list
    # HTMX will follow this 303 redirect and replace the body with the list page
    return RedirectResponse("/programs", status_code=303)


@app.get("/programs/{id}/edit", response_class=HTMLResponse)
def edit_program(id: int, request: Request, db: Session = Depends(get_db)):
    prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).first()
    return templates.TemplateResponse("partials/program_editor.html", {"request": request, "program": prog})


@app.post("/programs/{id}/update_meta")
def update_program_meta(
    id: int, 
    name: str = Form(...), 
    template_id: int = Form(None), # Accept template_id
    db: Session = Depends(get_db)
):
    prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).first()
    prog.name = name
    prog.template_id = template_id # Save
    db.commit()
    return Response(status_code=200)


@app.post("/programs/{id}/add_item")
def add_program_item(id: int, request: Request, db: Session = Depends(get_db)):
    # Add blank row
    new_item = ServiceProgramItemModel(program_id=id, title="", subtitle="", sequence=999)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return templates.TemplateResponse("partials/program_row.html", {"request": request, "item": new_item})


@app.post("/programs/item/{item_id}/update")
def update_item(item_id: int, title: str = Form(""), subtitle: str = Form(""), tag: str = Form(""), db: Session = Depends(get_db)):
    item = db.query(ServiceProgramItemModel).filter(ServiceProgramItemModel.id == item_id).first()
    item.title = title
    item.subtitle = subtitle
    item.tag = tag # Save Tag
    db.commit()
    return Response(status_code=200)


@app.delete("/programs/item/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    db.query(ServiceProgramItemModel).filter(ServiceProgramItemModel.id == item_id).delete()
    db.commit()
    return Response(status_code=200)


# --- PPT GENERATION LOGIC ---
def replace_text_preserving_formatting(pptx_path, output_path, replacements):
    if not os.path.exists(pptx_path): return

    prs = Presentation(pptx_path)
    # Prepare keys with double braces {{key}}
    search_replace_pairs = {("{{" + key + "}}"): str(value) for key, value in replacements.items()}

    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame: continue
            
            for paragraph in shape.text_frame.paragraphs:
                full_text = paragraph.text
                match_found = False
                
                # Check for matches
                for pattern, replacement in search_replace_pairs.items():
                    if pattern in full_text:
                        full_text = full_text.replace(pattern, replacement)
                        match_found = True
                
                if match_found:
                    # Capture style of first run
                    original_runs = paragraph.runs
                    saved_font_props = None
                    if len(original_runs) > 0:
                        first_run = original_runs[0]
                        saved_font_props = {
                            'bold': first_run.font.bold,
                            'italic': first_run.font.italic,
                            'underline': first_run.font.underline,
                            'size': first_run.font.size,
                            'name': first_run.font.name,
                            'color_obj': first_run.font.color if first_run.font.color else None
                        }

                    # Replace text
                    paragraph.clear() 
                    new_run = paragraph.add_run()
                    new_run.text = full_text

                    # Re-apply formatting
                    if saved_font_props:
                        new_run.font.bold = saved_font_props['bold']
                        new_run.font.italic = saved_font_props['italic']
                        new_run.font.underline = saved_font_props['underline']
                        new_run.font.size = saved_font_props['size']
                        new_run.font.name = saved_font_props['name']
                        if saved_font_props['color_obj']:
                            try:
                                if saved_font_props['color_obj'].type == 1: 
                                    new_run.font.color.rgb = saved_font_props['color_obj'].rgb
                                elif saved_font_props['color_obj'].type == 2:
                                    new_run.font.color.theme_color = saved_font_props['color_obj'].theme_color
                            except: pass

    prs.save(output_path)


def duplicate_slide(pres, index):
    """
    Safely duplicates the slide at 'index' to the end of the presentation.
    Handles Text Boxes, AutoShapes, and Pictures.
    """
    source = pres.slides[index]
    dest = pres.slides.add_slide(source.slide_layout)

    # 1. Copy Background
    try:
        if source.background.fill.type == 1: # Solid fill
            dest.background.fill.solid()
            dest.background.fill.fore_color.rgb = source.background.fill.fore_color.rgb
    except:
        pass # Background might be complex (gradient/picture), skip if fails

    # 2. Copy Shapes
    for shape in source.shapes:
        # --- CASE A: TEXT BOXES & SHAPES ---
        if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE or shape.shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
            try:
                # Determine geometry
                if shape.shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
                    geom = MSO_AUTO_SHAPE_TYPE.RECTANGLE
                else:
                    geom = shape.auto_shape_type
                
                # Create new shape
                new_shape = dest.shapes.add_shape(geom, shape.left, shape.top, shape.width, shape.height)
                
                # Copy Fill
                try:
                    if shape.fill.type == 1:
                        new_shape.fill.solid()
                        new_shape.fill.fore_color.rgb = shape.fill.fore_color.rgb
                except: pass

                # Copy Text & Formatting
                if shape.has_text_frame:
                    new_shape.text_frame.clear()
                    for paragraph in shape.text_frame.paragraphs:
                        new_p = new_shape.text_frame.add_paragraph()
                        new_p.text = paragraph.text
                        new_p.alignment = paragraph.alignment
                        
                        # Copy Font Styles from first run
                        if paragraph.runs:
                            r_source = paragraph.runs[0]
                            r_dest = new_p.font
                            r_dest.name = r_source.font.name
                            r_dest.size = r_source.font.size
                            r_dest.bold = r_source.font.bold
                            r_dest.italic = r_source.font.italic
                            r_dest.underline = r_source.font.underline
                            try:
                                if r_source.font.color.type == 1:
                                    r_dest.color.rgb = r_source.font.color.rgb
                            except: pass
            except Exception as e:
                print(f"Skipping shape due to error: {e}")

        # --- CASE B: PICTURES ---
        elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            try:
                blob = shape.image.blob
                from io import BytesIO
                dest.shapes.add_picture(BytesIO(blob), shape.left, shape.top, shape.width, shape.height)
            except: pass

    return dest


def move_slide(pres, old_index, new_index):
    """Moves a slide from old_index to new_index."""
    xml_slides = pres.slides._sldIdLst
    slides = list(xml_slides)
    xml_slides.remove(slides[old_index])
    xml_slides.insert(new_index, slides[old_index])


# --- DOWNLOAD ENDPOINT ---
@app.get("/programs/{id}/download_ppt")
def download_program_ppt(id: int, db: Session = Depends(get_db)):
    prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).first()
    
    if not prog or not prog.template_id:
        return Response("No template assigned.", status_code=400)
    
    template = db.query(PresentationTemplateModel).filter(PresentationTemplateModel.id == prog.template_id).first()
    if not template:
        return Response("Template file not found.", status_code=404)

    input_path = f"{UPLOAD_DIR}/{template.filename}"
    if not os.path.exists(input_path):
        return Response("Template file missing on disk.", status_code=404)

    prs = Presentation(input_path)
    
    # --- PHASE 1: STANDARD REPLACEMENTS ---
    replacements = {}
    for item in prog.items:
        if item.tag and item.subtitle:
            replacements[item.tag] = item.subtitle
    
    search_replace_pairs = {("{{" + key + "}}"): str(value) for key, value in replacements.items()}
    
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    full_text = paragraph.text
                    for pattern, replacement in search_replace_pairs.items():
                        if pattern in full_text:
                            full_text = full_text.replace(pattern, replacement)
                            paragraph.text = full_text
                            

    # --- PHASE 2: HYMN EXPLOSION (REUSE STRATEGY) ---
    # We iterate backwards to maintain valid indices for upcoming slides
    for i in range(len(prs.slides) - 1, -1, -1):
        slide = prs.slides[i]
        
        # 1. Check for Hymn Tag
        hymn_seq = None
        hymn_tag_pattern = ""
        
        for shape in slide.shapes:
            if not shape.has_text_frame: continue
            for paragraph in shape.text_frame.paragraphs:
                match = re.search(r"\{\{hymn_(\d+)\}\}", paragraph.text)
                if match:
                    hymn_seq = int(match.group(1))
                    hymn_tag_pattern = match.group(0)
                    break
            if hymn_seq: break
        
        if not hymn_seq: continue 
            
        # 2. Fetch Content
        plan_item = db.query(ServicePlanHymnModel).filter(ServicePlanHymnModel.sequence == hymn_seq).first()
        content_chunks = []

        # breakpoint()
        
        if not plan_item or not plan_item.hymn:
            content_chunks.append(f"(Hymn #{hymn_seq} not scheduled)")
        else:
            hymn = plan_item.hymn
            # Chunk 0: Title
            content_chunks.append(f"#{hymn.number}\n{hymn.title}")
            # Chunk 1+: Lyrics
            ppt_slides = [s for s in hymn.slides if s.type == "PPT"]
            if ppt_slides:
                for s in sorted(ppt_slides, key=lambda x: x.order):
                    content_chunks.append(s.content)
            else:
                raw_text = hymn.content_search or ""
                content_chunks.extend(raw_text.split('\n\n'))

        # 3. Apply Content
        # We have 'slide' at index 'i' which contains the Tag.
        # We have N chunks.
        # Chunk 0 will go into 'slide' (The Original).
        # Chunks 1..N will go into NEW slides inserted after 'i'.
        
        def clean_text(text):
            if not text: return ""
            return text.replace('\r\n', '\n').replace('\r', '\n').replace('\x0b', '\n').strip()
        
        # B. Handle First Chunk (Modify Original)
        # Now we finally replace the tag in the original slide.
        first_chunk = content_chunks[0]
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    if hymn_tag_pattern in paragraph.text:
                        paragraph.text = paragraph.text.replace(hymn_tag_pattern, clean_text(first_chunk))

        # breakpoint()

        # A. Handle Extra Chunks (Create Copies First)
        # We do this BEFORE modifying the original 'slide', so the copies inherit the Tag.
        

        insertion_index = i + 1
        
        for extra_chunk in content_chunks[1:]:
            # Duplicate the Original Template (which still has the {{hymn_x}} tag)
            new_slide = duplicate_slide(prs, i)
            
            # Move it to the correct position (immediately after the previous one)
            # new_slide is currently at len(prs.slides)-1
            move_slide(prs, len(prs.slides)-1, insertion_index)
            
            # Replace the tag in the NEW slide
            for s in new_slide.shapes:
                if s.has_text_frame:
                    for p in s.text_frame.paragraphs:
                        p.text = p.text.replace(p.text, clean_text(extra_chunk))
            
            insertion_index += 1


    # --- SAVE ---
    output = BytesIO()
    prs.save(output)
    output.seek(0)
    
    filename = f"{prog.name.replace(' ', '_')}.pptx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output, headers=headers, 
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )

# --- VMIX ENDPOINT ---

@app.post("/programs/{id}/activate")
def activate_program(id: int, request: Request, db: Session = Depends(get_db)):
    """Sets the given program as the 'Active' one."""
    # 1. Deactivate all
    db.query(ServiceProgramModel).update({ServiceProgramModel.is_active: False})
    
    # 2. Activate target
    prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).first()
    if prog:
        prog.is_active = True
        prog.last_used = datetime.now(timezone.utc)
        db.commit()
    
    # 3. Return ONLY the list partial (not the whole page)
    programs = db.query(ServiceProgramModel).order_by(ServiceProgramModel.id.desc()).all()
    return templates.TemplateResponse("partials/program_list.html", {"request": request, "programs": programs})


@app.post("/programs/{id}/reorder")
def reorder_program_items(
    id: int, 
    item_ids: List[int] = Form(...), # Receives list: item_ids=1&item_ids=5...
    db: Session = Depends(get_db)
):
    """Updates the sequence of items based on the received list order."""
    # Loop through the list of IDs. 
    # The index in the list becomes the new sequence number.
    for index, item_id in enumerate(item_ids):
        item = db.query(ServiceProgramItemModel).filter(ServiceProgramItemModel.id == item_id).first()
        if item:
            item.sequence = index
            
    db.commit()
    return Response(status_code=200)


@app.get("/templates_manager", response_class=HTMLResponse)
def page_templates(request: Request, db: Session = Depends(get_db)):
    tmpls = db.query(PresentationTemplateModel).all()
    return templates.TemplateResponse("templates_manager.html", {"request": request, "templates": tmpls})


@app.post("/templates/upload")
def upload_template(name: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Save file
    file_location = f"{UPLOAD_DIR}/{file.filename}"
    with open(file_location, "wb+") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Save DB entry
    new_tmpl = PresentationTemplateModel(name=name, filename=file.filename)
    db.add(new_tmpl)
    db.commit()
    
    return RedirectResponse("/templates_manager", status_code=303)


@app.delete("/templates/{id}")
def delete_template(id: int, db: Session = Depends(get_db)):
    tmpl = db.query(PresentationTemplateModel).filter(PresentationTemplateModel.id == id).first()
    if tmpl:
        # Try removing file
        try:
            os.remove(f"{UPLOAD_DIR}/{tmpl.filename}")
        except:
            pass
        db.delete(tmpl)
        db.commit()
    return Response(status_code=200)


@app.post("/programs/item/{item_id}/toggle_mute")
def toggle_item_mute(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(ServiceProgramItemModel).filter(ServiceProgramItemModel.id == item_id).first()
    if item:
        # Toggle boolean
        item.is_muted = not item.is_muted
        db.commit()
        
    # Return the updated row HTML
    return templates.TemplateResponse("partials/program_row.html", {"request": request, "item": item})


# --- API ENDPOINTS (JSON for vMix) ---

@app.get("/api/program/{id}/json")
def get_program_json(id: int, db: Session = Depends(get_db)):
    """Returns JSON for a specific program ID."""
    prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).first()
    
    if not prog:
        return []

    # Sort items by sequence (if available) or ID
    items = sorted(prog.items, key=lambda x: (x.sequence if x.sequence is not None else 9999, x.id))
    
    data = []
    for item in items:
        if item.is_muted:
            continue

        data.append({
            "title": item.title or "",
            "subtitle": item.subtitle or ""
        })
            
    return data


@app.get("/api/program/current")
def get_current_program_json(db: Session = Depends(get_db)):
    """Returns JSON for the currently ACTIVE program."""
    prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.is_active == True).first()
    # Use sequence first, then ID as fallback
    
    if not prog:
        return [{"title": "No Active Program", "subtitle": "Select one in Dashboard"}]

    items = sorted(prog.items, key=lambda x: (x.sequence if x.sequence is not None else 9999, x.id))
    
    data = []
    for item in items:
        if item.is_muted:
            continue

        data.append({
            "title": item.title or "",
            "subtitle": item.subtitle or ""
        })
            
    return data


if __name__ == "__main__":
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    uvicorn.run(app, host="0.0.0.0", port=10001)