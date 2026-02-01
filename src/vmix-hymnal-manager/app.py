import uvicorn

from fastapi import FastAPI, Depends
from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel, ConfigDict
from typing import List

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base


DATABASE_URL = "sqlite:///./hymns.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

templates = Jinja2Templates(directory="src/vmix-hymnal-manager/templates")

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
            
        # Sort slides by their internal order (v1, then v2, then c...)
        # We manually sort here or enforce it in the query.
        sorted_slides = sorted(hymn.slides, key=lambda x: x.order)
        
        for slide in sorted_slides:
            vmix_output.append(VmixRow(
                HymnNumber=hymn.number,
                Title=hymn.title,
                Label=slide.label,
                SlideText=slide.content
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10001)