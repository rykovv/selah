import sys
import os

import uvicorn

from fastapi import FastAPI, Depends
from fastapi import Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel, ConfigDict
from typing import List, Optional

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from sqlalchemy import or_

from fastapi.responses import StreamingResponse # Add this to imports
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor
from io import BytesIO


DATABASE_URL = "sqlite:///./hymns.db"

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
    service_plans = relationship("ServicePlanModel", back_populates="hymn")

class SlideModel(Base):
    __tablename__ = "slides"
    id = Column(Integer, primary_key=True, index=True)
    hymn_id = Column(Integer, ForeignKey("hymns.id"))
    
    label = Column(String)  # e.g., "Verse 1", "Chorus"
    content = Column(Text)
    order = Column(Integer)
    
    # NEW COLUMN: 'VMIX' or 'PPT'
    # We default to 'VMIX' so existing data still works
    type = Column(String, default="VMIX") 

    hymn = relationship("HymnModel", back_populates="slides")


class ServicePlanModel(Base):
    __tablename__ = "service_plan"
    
    id = Column(Integer, primary_key=True, index=True)
    sequence = Column(Integer, unique=True) # 1st hymn, 2nd hymn, etc.
    hymn_id = Column(Integer, ForeignKey("hymns.id"))
    
    # We fetch the hymn details when we load the plan
    hymn = relationship("HymnModel", back_populates="service_plans")

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
    service_items = db.query(ServicePlanModel).order_by(ServicePlanModel.sequence).all()
    
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

# --- 5. SEED DATA (For testing only) ---

@app.get("/debug/seed")
def seed_database(db: Session = Depends(get_db)):
    """A helper to populate the DB so you don't start empty."""
    
    # Clear existing
    db.query(ServicePlanModel).delete()
    db.query(SlideModel).delete()
    db.query(HymnModel).delete()
    
    # Create Hymn 1
    h1 = HymnModel(number="101", title="Amazing Grace")
    db.add(h1)
    db.commit() # Commit to get the ID
    
    # Add Slides for Hymn 1
    db.add(SlideModel(hymn_id=h1.id, order=1, label="v1", content="Amazing grace! How sweet the sound\nThat saved a wretch like me!"))
    db.add(SlideModel(hymn_id=h1.id, order=2, label="v2", content="'Twas grace that taught my heart to fear,\nAnd grace my fears relieved;"))
    
    # Create Hymn 2
    h2 = HymnModel(number="402", title="It is Well")
    db.add(h2)
    db.commit()
    
    db.add(SlideModel(hymn_id=h2.id, order=1, label="v1", content="When peace like a river\nAttendeth my way"))
    
    # Add to Service Plan (Playlist)
    db.add(ServicePlanModel(sequence=1, hymn_id=h1.id)) # Amazing Grace first
    db.add(ServicePlanModel(sequence=2, hymn_id=h2.id)) # It is Well second
    
    db.commit()
    return {"status": "Database seeded with 2 hymns and a service plan."}


@app.get("/", response_class=HTMLResponse)
def read_dashboard(request: Request, db: Session = Depends(get_db)):
    """Render the main dashboard."""
    # 1. Get the current plan
    plan = db.query(ServicePlanModel).order_by(ServicePlanModel.sequence).all()
    # 2. Get the full library (Simple version: fetch all)
    library = db.query(HymnModel).order_by(HymnModel.number).all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "plan": plan,
        "library": library
    })


@app.post("/plan/add")
def add_to_plan(hymn_id: int = Form(...), db: Session = Depends(get_db)):
    """Add a hymn to the end of the service list."""
    # Find the current highest sequence number
    last_item = db.query(ServicePlanModel).order_by(ServicePlanModel.sequence.desc()).first()
    new_seq = (last_item.sequence + 1) if last_item else 1
    
    new_entry = ServicePlanModel(sequence=new_seq, hymn_id=hymn_id)
    db.add(new_entry)
    db.commit()
    
    # Reload the page to show the change
    return RedirectResponse(url="/", status_code=303)


@app.delete("/plan/{item_id}")
def remove_from_plan(item_id: int, db: Session = Depends(get_db)):
    """Remove an item. HTMX expects a 200 OK or empty response."""
    item = db.query(ServicePlanModel).filter(ServicePlanModel.id == item_id).first()
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
    db.query(ServicePlanModel).filter(ServicePlanModel.hymn_id == hymn_id).delete()
    
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


# @app.delete("/hymns/{hymn_id}")
# def delete_hymn(hymn_id: int, db: Session = Depends(get_db)):
#     # 1. Manual Cascade: Remove this hymn from any Service Plans first
#     # This prevents the "Foreign Key Constraint" error
#     db.query(ServicePlanModel).filter(ServicePlanModel.hymn_id == hymn_id).delete()
    
#     # 2. Find and delete the hymn
#     hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
#     if hymn:
#         db.delete(hymn)
#         db.commit()
        
#     # 3. HTMX Redirect
#     # Instead of returning HTML, we send a header that tells the browser 
#     # to load the /editor page. This prevents the "Race Condition".
#     return Response(status_code=200, headers={"HX-Redirect": "/editor"})


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
    """Returns the hymn lyrics for the modal preview."""
    hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
    if not hymn:
        return "<div>Hymn not found</div>"
    
    hymn.slides.sort(key=lambda x: x.order)
    
    # We construct the HTML directly here to avoid creating another file
    html = f"""
    <div class="p-2">
        <h4 class="text-primary mb-3">{hymn.number} - {hymn.title}</h4>
    """
    
    for slide in hymn.slides:
        # Determine badge color
        badge_class = "bg-secondary"
        if "v" in slide.label.lower(): badge_class = "bg-primary"
        if "c" in slide.label.lower(): badge_class = "bg-success"
        
        badge = f'<span class="badge {badge_class} me-2">{slide.label}</span>' if slide.label else ""
        
        html += f"""
        <div class="d-flex mb-3 border-bottom pb-2">
            <div class="mt-1">{badge}</div>
            <div class="ms-2 text-dark" style="white-space: pre-wrap; font-size: 1.1rem;">{slide.content}</div>
        </div>
        """
    
    html += "</div>"
    return html


@app.get("/download/ppt")
def download_ppt(db: Session = Depends(get_db)):
    """Generates a Service PowerPoint."""
    
    # 1. Fetch the Plan
    plan = db.query(ServicePlanModel).order_by(ServicePlanModel.sequence).all()
    if not plan:
        return Response("Service plan is empty", status_code=400)

    # 2. Initialize Presentation (16:9 Widescreen)
    prs = Presentation()
    prs.slide_width = Inches(16)
    prs.slide_height = Inches(9)

    # --- STYLE CONSTANTS ---
    BG_COLOR = RGBColor(0, 0, 0)       # Black
    TEXT_COLOR = RGBColor(255, 255, 255) # White
    ACCENT_COLOR = RGBColor(100, 100, 100) # Grey for labels (v1, c)
    FONT_NAME = "Arial"                # Clean, universal sans-serif
    TITLE_SIZE = Pt(80)
    NUMBER_SIZE = Pt(54)
    LYRICS_SIZE = Pt(60)               # Large, readable from back of room
    LABEL_SIZE = Pt(40)                # Small label in corner

    def create_black_slide(prs):
        """Helper to create a blank slide with black background."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = BG_COLOR
        return slide

    def add_text_box(slide, text, size, top_inch, height_inch, is_bold=False, color=TEXT_COLOR):
        """
        Helper to center text on the slide.
        Now accepts 'top_inch' and 'height_inch' to control vertical placement.
        """
        # CLEANING
        if text:
            text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\x0b', '\n')
        
        # Left margin 1 inch, Width 14 inches (Centered horizontally)
        left = Inches(1)
        width = Inches(14)
        
        txBox = slide.shapes.add_textbox(left, top_inch, width, height_inch)
        tf = txBox.text_frame
        tf.word_wrap = True
        
        p = tf.paragraphs[0]
        p.text = text
        p.font.name = FONT_NAME
        p.font.size = size
        p.font.bold = is_bold
        p.font.color.rgb = color
        p.alignment = PP_ALIGN.CENTER

    # --- GENERATION LOOP ---
    for index, item in enumerate(plan):
        hymn = item.hymn
        if not hymn: continue

        # A. HYMN TITLE SLIDE
        slide = create_black_slide(prs)
        
        # 1. Hymn Number (Top Half)
        # Position: 2.5 inches from top
        add_text_box(slide, f"Hymn №{hymn.number}", NUMBER_SIZE, Inches(2.5), Inches(1.5), is_bold=False)

        # 2. Hymn Title (Bottom Half)
        # Position: 4.0 inches from top (Right below number)
        add_text_box(slide, hymn.title, TITLE_SIZE, Inches(4.0), Inches(4.0), is_bold=True)

        # B. LYRICS SLIDES
        # Filter for PPT slides specifically
        ppt_slides_db = [s for s in hymn.slides if s.type == "PPT"]
        
        # Fallback: If no PPT slides exist (legacy data), use vMix slides
        if not ppt_slides_db:
             ppt_slides_db = [s for s in hymn.slides if s.type == "VMIX" or s.type is None]

        sorted_slides = sorted(ppt_slides_db, key=lambda x: x.order)

        for lyric_slide in sorted_slides:
            slide = create_black_slide(prs)
            
            # Main Lyrics (Vertically Centered in a full-height box)
            # We use Top=1, Height=7 for maximum space
            txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(14), Inches(7))
            tf = txBox.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE # Center vertically
            
            p = tf.paragraphs[0]
            # Clean text here too
            clean_text = lyric_slide.content
            if clean_text:
                clean_text = clean_text.replace('\r\n', '\n').replace('\r', '\n').replace('\x0b', '\n')

            p.text = clean_text
            p.font.name = FONT_NAME
            p.font.size = LYRICS_SIZE
            p.font.color.rgb = TEXT_COLOR
            p.alignment = PP_ALIGN.CENTER

            # Corner Label (Bottom Right)
            if lyric_slide.label:
                # Top: 0.5 inch, Height: 1 inch
                txLabel = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(14), Inches(2))
                pLabel = txLabel.text_frame.paragraphs[0]
                pLabel.text = lyric_slide.label.upper() # UPPERCASE looks better for headers
                pLabel.font.name = FONT_NAME
                pLabel.font.size = LABEL_SIZE
                pLabel.font.color.rgb = ACCENT_COLOR 
                pLabel.font.bold = True
                pLabel.alignment = PP_ALIGN.CENTER
        
        # C. SPACER SLIDE
        if index < len(plan) - 1:
            create_black_slide(prs)

    # 3. Save to Memory Buffer
    output = BytesIO()
    prs.save(output)
    output.seek(0)

    # 4. Return as Download
    filename = "Sabbath_Service_Hymns.pptx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output, 
        headers=headers, 
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10001)