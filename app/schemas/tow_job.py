# ===============================
# FILE: app/schemas/tow_job.py
# (FULL FILE - includes new photo fields
#  + submit-evidence response schema)
# ===============================
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.tow_job import TowStatus


class TowJobCreate(BaseModel):
    plate_number: str = Field(min_length=2, max_length=32)
    location_lat: float
    location_lng: float
    location_accuracy_m: Optional[float] = None
    violation_type: Optional[str] = None
    notes: Optional[str] = None


class TowJobAssign(BaseModel):
    driver_id: str


class TowJobStatusUpdate(BaseModel):
    status: TowStatus
    notes: Optional[str] = None


class TowJobOut(BaseModel):
    id: str
    plate_number: str
    officer_id: str
    status: str
    assigned_driver_id: Optional[str]
    violation_type: Optional[str]
    notes: Optional[str]
    location_lat: float
    location_lng: float
    location_accuracy_m: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class TowJobPhotoOut(BaseModel):
    id: str
    tow_job_id: str
    uploaded_by_user_id: str
    photo_type: str
    file_path: str
    content_type: str
    size_bytes: int

    # NEW
    lat: Optional[float] = None
    lng: Optional[float] = None
    accuracy_m: Optional[float] = None
    captured_at: Optional[datetime] = None

    created_at: datetime

    class Config:
        from_attributes = True


class SubmitEvidenceResponse(BaseModel):
    job: TowJobOut
    photo: TowJobPhotoOut

# from datetime import datetime
# from typing import Optional

# from pydantic import BaseModel, Field

# from app.models.tow_job import TowStatus


# class TowJobCreate(BaseModel):
#     plate_number: str = Field(min_length=2, max_length=32)
#     location_lat: float
#     location_lng: float
#     location_accuracy_m: Optional[float] = None
#     violation_type: Optional[str] = None
#     notes: Optional[str] = None


# class TowJobAssign(BaseModel):
#     driver_id: str


# class TowJobStatusUpdate(BaseModel):
#     status: TowStatus
#     notes: Optional[str] = None


# class TowJobOut(BaseModel):
#     id: str
#     plate_number: str
#     officer_id: str
#     status: str
#     assigned_driver_id: Optional[str]
#     violation_type: Optional[str]
#     notes: Optional[str]
#     location_lat: float
#     location_lng: float
#     location_accuracy_m: Optional[float]
#     created_at: datetime

#     class Config:
#         from_attributes = True


# class TowJobPhotoOut(BaseModel):
#     id: str
#     tow_job_id: str
#     uploaded_by_user_id: str
#     photo_type: str
#     file_path: str
#     content_type: str
#     size_bytes: int
#     created_at: datetime

#     class Config:
#         from_attributes = True
