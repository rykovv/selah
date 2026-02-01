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


class SlideModel(Base):
    __tablename__ = "slides"
    
    id = Column(Integer, primary_key=True, index=True)
    hymn_id = Column(Integer, ForeignKey("hymns.id"))
    label = Column(String)  # v1, c, etc.
    content = Column(Text)  # The multiline text
    order = Column(Integer) # To keep slides in correct sequence (1, 2, 3...)

    hymn = relationship("HymnModel", back_populates="slides")


class ServicePlanModel(Base):
    __tablename__ = "service_plan"
    
    id = Column(Integer, primary_key=True, index=True)
    sequence = Column(Integer, unique=True) # 1st hymn, 2nd hymn, etc.
    hymn_id = Column(Integer, ForeignKey("hymns.id"))
    
    # We fetch the hymn details when we load the plan
    hymn = relationship("HymnModel")

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
        sorted_slides = sorted(hymn.slides, key=lambda x: x.order)
        
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
    request: Request,
    hymn_id: Optional[int] = Form(None), # If None, it's a create action
    number: str = Form(...),
    title: str = Form(...),
    # FastAPI automatically collects multiple fields with same name into a list
    slide_labels: List[str] = Form(...), 
    slide_contents: List[str] = Form(...),
    db: Session = Depends(get_db)
):
    """Handles both CREATE and UPDATE."""
    
    if hymn_id:
        # UPDATE existing
        hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()

        hymn.number = number
        hymn.title = title
        # Clear old slides and re-add (Simplest strategy for updates)
        for slide in hymn.slides:
            db.delete(slide)
    else:
        # CREATE new
        hymn = HymnModel(number=number, title=title)
        db.add(hymn)
        db.flush() # Flush to get the new ID

    # Add Slides
    for index, (label, content) in enumerate(zip(slide_labels, slide_contents)):
        # Skip empty slides
        if not content.strip(): 
            continue
            
        new_slide = SlideModel(
            hymn_id=hymn.id, 
            label=label, 
            content=content, 
            order=index + 1
        )
        db.add(new_slide)
        
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10001)