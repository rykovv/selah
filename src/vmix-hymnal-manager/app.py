import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# --- 1. Domain Models ( The "Specification") ---

class Slide(BaseModel):
    """
    Represents one visual 'screen' in vMix.
    'content' stores the full text with \n for line breaks.
    """
    label: str   # e.g., "v1", "chorus"
    content: str # e.g., "Amazing grace\nHow sweet the sound"

class Hymn(BaseModel):
    id: int
    number: str
    title: str
    slides: List[Slide]

# --- 2. Data Store (Simulated) ---

hymn_library = [
    Hymn(
        id=1, number="101", title="Amazing Grace",
        slides=[
            # Flexibility: This slide has 2 lines
            Slide(label="v1", content="Amazing grace! How sweet the sound\nThat saved a wretch like me!"),
            # Flexibility: This slide has 3 lines (example of variation)
            Slide(label="v1", content="I once was lost,\nBut now am found;\nWas blind, but now I see."),
            Slide(label="c",  content="My chains are gone\nI've been set free")
        ]
    )
]

current_service_ids = [1]


# --- 3. The vMix Transformation Logic ---

class VmixRow(BaseModel):
    """The flat structure vMix expects."""
    HymnNumber: str
    Title: str
    Label: str
    SlideText: str  # Matches the 'Text Block' in vMix

def flatten_hymn_for_vmix(hymn: Hymn) -> List[VmixRow]:
    rows = []
    for slide in hymn.slides:
        rows.append(VmixRow(
            HymnNumber=hymn.number,
            Title=hymn.title,
            Label=slide.label,
            SlideText=slide.content 
        ))
    return rows

# --- 4. API Endpoint ---

@app.get("/api/vmix", response_model=List[VmixRow])
async def get_vmix_feed():
    vmix_output = []
    for hymn_id in current_service_ids:
        hymn = next((h for h in hymn_library if h.id == hymn_id), None)
        if hymn:
            vmix_output.extend(flatten_hymn_for_vmix(hymn))
    return vmix_output

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10001)