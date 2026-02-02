# ======================================
# FILE: app/routers/tow_jobs.py
# (FULL FILE - adds:
#  - per-photo lat/lng/accuracy/captured_at via Form(...)
#  - POST /tow-jobs/submit-evidence (create job + upload photo + store GPS)
# ======================================
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_roles
from app.core.db import get_db
from app.models.event import TowJobEvent
from app.models.photo import TowJobPhoto
from app.models.tow_job import TowJob, TowStatus
from app.models.user import User, UserRole
from app.schemas.tow_job import TowJobAssign, TowJobCreate, TowJobOut, TowJobStatusUpdate
from app.services.storage import save_upload_streaming

router = APIRouter(prefix="/tow-jobs", tags=["tow-jobs"])


def _log_event(db: Session, tow_job_id: str, actor_user_id: str, event_type: str, message: str | None = None):
    ev = TowJobEvent(
        id=str(uuid.uuid4()),
        tow_job_id=tow_job_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        message=message,
    )
    db.add(ev)


def _assert_job_access(user: User, job: TowJob):
    if user.role in (UserRole.DISPATCHER, UserRole.ADMIN):
        return
    if user.role == UserRole.OFFICER and job.officer_id == user.id:
        return
    if user.role == UserRole.DRIVER and job.assigned_driver_id == user.id:
        return
    raise HTTPException(status_code=403, detail="Not your job")


def _parse_iso_datetime(dt: str | None) -> Optional[datetime]:
    """
    Accepts ISO8601 strings like:
      2026-01-19T12:34:56Z
      2026-01-19T12:34:56+00:00
      2026-01-19T12:34:56
    Returns datetime or None.
    """
    if not dt:
        return None
    s = dt.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        raise HTTPException(status_code=400, detail="captured_at must be ISO8601 datetime (e.g. 2026-01-19T12:34:56Z)")


@router.post("", response_model=TowJobOut)
def create_tow_job(
    payload: TowJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OFFICER, UserRole.ADMIN)),
):
    job = TowJob(
        id=str(uuid.uuid4()),
        plate_number=payload.plate_number.strip().upper(),
        officer_id=user.id,
        status=TowStatus.NEW,
        violation_type=payload.violation_type,
        notes=payload.notes,
        location_lat=payload.location_lat,
        location_lng=payload.location_lng,
        location_accuracy_m=payload.location_accuracy_m,
    )
    db.add(job)
    _log_event(db, job.id, user.id, "CREATED", f"Job created for plate {job.plate_number}")
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[TowJobOut])
def list_tow_jobs(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(TowJob)

    if user.role == UserRole.OFFICER:
        q = q.filter(TowJob.officer_id == user.id)
    elif user.role == UserRole.DRIVER:
        q = q.filter(TowJob.assigned_driver_id == user.id)

    if status_filter:
        try:
            q = q.filter(TowJob.status == TowStatus(status_filter))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid status_filter")

    return q.order_by(TowJob.created_at.desc()).all()


@router.post("/{job_id}/assign", response_model=TowJobOut)
def assign_driver(
    job_id: str,
    payload: TowJobAssign,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DISPATCHER, UserRole.ADMIN)),
):
    job = db.query(TowJob).filter(TowJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tow job not found")

    driver = (
        db.query(User)
        .filter(User.id == payload.driver_id, User.role == UserRole.DRIVER, User.is_active == True)  # noqa: E712
        .first()
    )
    if not driver:
        raise HTTPException(status_code=400, detail="Driver not found")

    job.assigned_driver_id = driver.id
    job.status = TowStatus.ASSIGNED
    _log_event(db, job.id, user.id, "ASSIGNED", f"Assigned to driver {driver.id}")
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/status", response_model=TowJobOut)
def update_status(
    job_id: str,
    payload: TowJobStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(TowJob).filter(TowJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tow job not found")

    _assert_job_access(user, job)

    old = job.status.value
    job.status = payload.status

    if payload.notes:
        existing = (job.notes or "").strip()
        line = f"[{user.role.value}] {payload.notes.strip()}"
        job.notes = f"{existing}\n{line}".strip() if existing else line

    _log_event(
        db,
        job.id,
        user.id,
        "STATUS_CHANGED",
        f"Status {old} -> {job.status.value}" + (f" | {payload.notes.strip()}" if payload.notes else ""),
    )

    db.commit()
    db.refresh(job)
    return job


# -----------------------------------------
# UPDATED: upload photo now accepts geo + captured_at
# -----------------------------------------
@router.post("/{job_id}/photos")
def upload_job_photo(
    job_id: str,
    photo: UploadFile = File(...),
    photo_type: str = Form(...),  # BEFORE, AFTER, PLATE_CLOSEUP, OTHER

    # NEW per-photo capture fields (from device)
    lat: Optional[float] = Form(None),
    lng: Optional[float] = Form(None),
    accuracy_m: Optional[float] = Form(None),
    captured_at: Optional[str] = Form(None),

    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(TowJob).filter(TowJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tow job not found")

    _assert_job_access(user, job)

    allowed_types = {"BEFORE", "AFTER", "PLATE_CLOSEUP", "OTHER"}
    if photo_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"photo_type must be one of {sorted(allowed_types)}")

    allowed_ct = {"image/jpeg", "image/png", "image/webp"}
    if photo.content_type not in allowed_ct:
        raise HTTPException(status_code=400, detail="Only jpeg/png/webp images are allowed")

    # Basic geo sanity if provided
    if (lat is None) != (lng is None):
        raise HTTPException(status_code=400, detail="Provide both lat and lng, or neither")
    if lat is not None and not (-90.0 <= lat <= 90.0):
        raise HTTPException(status_code=400, detail="lat must be between -90 and 90")
    if lng is not None and not (-180.0 <= lng <= 180.0):
        raise HTTPException(status_code=400, detail="lng must be between -180 and 180")

    captured_dt = _parse_iso_datetime(captured_at)

    stored_path, size_bytes = save_upload_streaming(photo)

    rec = TowJobPhoto(
        id=str(uuid.uuid4()),
        tow_job_id=job.id,
        uploaded_by_user_id=user.id,
        photo_type=photo_type,
        file_path=stored_path,
        content_type=photo.content_type,
        size_bytes=size_bytes,
        lat=lat,
        lng=lng,
        accuracy_m=accuracy_m,
        captured_at=captured_dt,
    )
    db.add(rec)

    _log_event(
        db,
        job.id,
        user.id,
        "PHOTO_UPLOADED",
        f"{photo_type} uploaded ({size_bytes} bytes)"
        + (f" | photo_geo={lat},{lng} acc={accuracy_m}" if lat is not None else ""),
    )

    db.commit()
    db.refresh(rec)

    return {
        "id": rec.id,
        "tow_job_id": rec.tow_job_id,
        "uploaded_by_user_id": rec.uploaded_by_user_id,
        "photo_type": rec.photo_type,
        "file_path": rec.file_path,
        "content_type": rec.content_type,
        "size_bytes": rec.size_bytes,
        "lat": rec.lat,
        "lng": rec.lng,
        "accuracy_m": rec.accuracy_m,
        "captured_at": rec.captured_at,
        "created_at": rec.created_at,
        "download_url": f"/tow-jobs/{job.id}/photos/{rec.id}/download",
    }


# -----------------------------------------
# NEW: one-shot endpoint for Officer
# Creates job + uploads photo + stores GPS + manual plate
# -----------------------------------------
@router.post("/submit-evidence")
def submit_evidence(
    # Manual plate
    plate_number: str = Form(...),

    # Authoritative device GPS for the vehicle (store on JOB)
    job_lat: float = Form(...),
    job_lng: float = Form(...),
    job_accuracy_m: Optional[float] = Form(None),

    # Optional extra metadata
    violation_type: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),

    # Photo + per-photo GPS (can be same as job GPS, but kept separately for proof)
    photo: UploadFile = File(...),
    photo_type: str = Form("PLATE_CLOSEUP"),
    photo_lat: Optional[float] = Form(None),
    photo_lng: Optional[float] = Form(None),
    photo_accuracy_m: Optional[float] = Form(None),
    captured_at: Optional[str] = Form(None),

    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.OFFICER, UserRole.ADMIN)),
):
    plate = plate_number.strip().upper()
    if not plate:
        raise HTTPException(status_code=400, detail="plate_number is required")

    # Validate job GPS
    if not (-90.0 <= job_lat <= 90.0):
        raise HTTPException(status_code=400, detail="job_lat must be between -90 and 90")
    if not (-180.0 <= job_lng <= 180.0):
        raise HTTPException(status_code=400, detail="job_lng must be between -180 and 180")

    # Validate photo GPS (if provided)
    if (photo_lat is None) != (photo_lng is None):
        raise HTTPException(status_code=400, detail="Provide both photo_lat and photo_lng, or neither")
    if photo_lat is not None and not (-90.0 <= photo_lat <= 90.0):
        raise HTTPException(status_code=400, detail="photo_lat must be between -90 and 90")
    if photo_lng is not None and not (-180.0 <= photo_lng <= 180.0):
        raise HTTPException(status_code=400, detail="photo_lng must be between -180 and 180")

    allowed_ct = {"image/jpeg", "image/png", "image/webp"}
    if photo.content_type not in allowed_ct:
        raise HTTPException(status_code=400, detail="Only jpeg/png/webp images are allowed")

    allowed_types = {"BEFORE", "AFTER", "PLATE_CLOSEUP", "OTHER"}
    if photo_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"photo_type must be one of {sorted(allowed_types)}")

    captured_dt = _parse_iso_datetime(captured_at)

    # Create job
    job = TowJob(
        id=str(uuid.uuid4()),
        plate_number=plate,
        officer_id=user.id,
        status=TowStatus.NEW,
        violation_type=violation_type,
        notes=notes,
        location_lat=job_lat,
        location_lng=job_lng,
        location_accuracy_m=job_accuracy_m,
    )
    db.add(job)
    _log_event(db, job.id, user.id, "CREATED", f"Job created via submit-evidence for plate {plate}")

    # Save photo
    stored_path, size_bytes = save_upload_streaming(photo)
    rec = TowJobPhoto(
        id=str(uuid.uuid4()),
        tow_job_id=job.id,
        uploaded_by_user_id=user.id,
        photo_type=photo_type,
        file_path=stored_path,
        content_type=photo.content_type,
        size_bytes=size_bytes,
        lat=photo_lat,
        lng=photo_lng,
        accuracy_m=photo_accuracy_m,
        captured_at=captured_dt,
    )
    db.add(rec)
    _log_event(
        db,
        job.id,
        user.id,
        "PHOTO_UPLOADED",
        f"{photo_type} uploaded via submit-evidence ({size_bytes} bytes)"
        + (f" | photo_geo={photo_lat},{photo_lng} acc={photo_accuracy_m}" if photo_lat is not None else ""),
    )

    db.commit()
    db.refresh(job)
    db.refresh(rec)

    return {
        "job": {
            "id": job.id,
            "plate_number": job.plate_number,
            "officer_id": job.officer_id,
            "status": job.status.value,
            "assigned_driver_id": job.assigned_driver_id,
            "violation_type": job.violation_type,
            "notes": job.notes,
            "location_lat": job.location_lat,
            "location_lng": job.location_lng,
            "location_accuracy_m": job.location_accuracy_m,
            "created_at": job.created_at,
        },
        "photo": {
            "id": rec.id,
            "tow_job_id": rec.tow_job_id,
            "uploaded_by_user_id": rec.uploaded_by_user_id,
            "photo_type": rec.photo_type,
            "content_type": rec.content_type,
            "size_bytes": rec.size_bytes,
            "lat": rec.lat,
            "lng": rec.lng,
            "accuracy_m": rec.accuracy_m,
            "captured_at": rec.captured_at,
            "created_at": rec.created_at,
            "download_url": f"/tow-jobs/{job.id}/photos/{rec.id}/download",
        },
    }


@router.get("/{job_id}/photos/{photo_id}/download")
def download_job_photo(
    job_id: str,
    photo_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(TowJob).filter(TowJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tow job not found")

    _assert_job_access(user, job)

    rec = db.query(TowJobPhoto).filter(TowJobPhoto.id == photo_id, TowJobPhoto.tow_job_id == job.id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Photo not found")

    abs_path = os.path.abspath(rec.file_path)
    uploads_abs = os.path.abspath("uploads")
    if not abs_path.startswith(uploads_abs + os.sep):
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File missing on server")

    return FileResponse(path=abs_path, media_type=rec.content_type, filename=os.path.basename(abs_path))


@router.get("/{job_id}/evidence")
def get_job_evidence(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(TowJob).filter(TowJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tow job not found")

    _assert_job_access(user, job)

    photos = db.query(TowJobPhoto).filter(TowJobPhoto.tow_job_id == job.id).all()

    return {
        "job": {
            "id": job.id,
            "plate_number": job.plate_number,
            "status": job.status.value,
            "officer_id": job.officer_id,
            "assigned_driver_id": job.assigned_driver_id,
            "violation_type": job.violation_type,
            "notes": job.notes,
            "location_lat": job.location_lat,
            "location_lng": job.location_lng,
            "location_accuracy_m": job.location_accuracy_m,
            "created_at": job.created_at,
        },
        "photos": [
            {
                "id": p.id,
                "photo_type": p.photo_type,
                "uploaded_by_user_id": p.uploaded_by_user_id,
                "created_at": p.created_at,
                "content_type": p.content_type,
                "size_bytes": p.size_bytes,
                "lat": p.lat,
                "lng": p.lng,
                "accuracy_m": p.accuracy_m,
                "captured_at": p.captured_at,
                "download_url": f"/tow-jobs/{job.id}/photos/{p.id}/download",
            }
            for p in photos
        ],
    }


@router.get("/{job_id}/events")
def get_job_events(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(TowJob).filter(TowJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tow job not found")

    _assert_job_access(user, job)

    events = (
        db.query(TowJobEvent)
        .filter(TowJobEvent.tow_job_id == job.id)
        .order_by(TowJobEvent.created_at.asc())
        .all()
    )

    return [
        {
            "id": e.id,
            "tow_job_id": e.tow_job_id,
            "actor_user_id": e.actor_user_id,
            "event_type": e.event_type,
            "message": e.message,
            "created_at": e.created_at,
        }
        for e in events
    ]

# from __future__ import annotations

# import os
# import uuid
# from typing import Optional

# from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
# from fastapi.responses import FileResponse
# from sqlalchemy.orm import Session

# from app.core.auth import get_current_user, require_roles
# from app.core.db import get_db
# from app.models.event import TowJobEvent
# from app.models.photo import TowJobPhoto
# from app.models.tow_job import TowJob, TowStatus
# from app.models.user import User, UserRole
# from app.schemas.tow_job import TowJobAssign, TowJobCreate, TowJobOut, TowJobStatusUpdate
# from app.services.storage import save_upload_streaming

# router = APIRouter(prefix="/tow-jobs", tags=["tow-jobs"])


# def _log_event(db: Session, tow_job_id: str, actor_user_id: str, event_type: str, message: str | None = None):
#     ev = TowJobEvent(
#         id=str(uuid.uuid4()),
#         tow_job_id=tow_job_id,
#         actor_user_id=actor_user_id,
#         event_type=event_type,
#         message=message,
#     )
#     db.add(ev)


# def _assert_job_access(user: User, job: TowJob):
#     """
#     Shared access check for evidence/photos/events endpoints.
#     Dispatchers/Admin can access all.
#     Officers only their jobs.
#     Drivers only assigned jobs.
#     """
#     if user.role in (UserRole.DISPATCHER, UserRole.ADMIN):
#         return
#     if user.role == UserRole.OFFICER and job.officer_id == user.id:
#         return
#     if user.role == UserRole.DRIVER and job.assigned_driver_id == user.id:
#         return
#     raise HTTPException(status_code=403, detail="Not your job")


# @router.post("", response_model=TowJobOut)
# def create_tow_job(
#     payload: TowJobCreate,
#     db: Session = Depends(get_db),
#     user: User = Depends(require_roles(UserRole.OFFICER, UserRole.ADMIN)),
# ):
#     job = TowJob(
#         id=str(uuid.uuid4()),
#         plate_number=payload.plate_number.strip().upper(),
#         officer_id=user.id,
#         status=TowStatus.NEW,
#         violation_type=payload.violation_type,
#         notes=payload.notes,
#         location_lat=payload.location_lat,
#         location_lng=payload.location_lng,
#         location_accuracy_m=payload.location_accuracy_m,
#     )
#     db.add(job)
#     _log_event(db, job.id, user.id, "CREATED", f"Job created for plate {job.plate_number}")
#     db.commit()
#     db.refresh(job)
#     return job


# @router.get("", response_model=list[TowJobOut])
# def list_tow_jobs(
#     status_filter: Optional[str] = None,
#     db: Session = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     q = db.query(TowJob)

#     if user.role == UserRole.OFFICER:
#         q = q.filter(TowJob.officer_id == user.id)
#     elif user.role == UserRole.DRIVER:
#         q = q.filter(TowJob.assigned_driver_id == user.id)

#     if status_filter:
#         try:
#             q = q.filter(TowJob.status == TowStatus(status_filter))
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid status_filter")

#     return q.order_by(TowJob.created_at.desc()).all()


# @router.post("/{job_id}/assign", response_model=TowJobOut)
# def assign_driver(
#     job_id: str,
#     payload: TowJobAssign,
#     db: Session = Depends(get_db),
#     user: User = Depends(require_roles(UserRole.DISPATCHER, UserRole.ADMIN)),
# ):
#     job = db.query(TowJob).filter(TowJob.id == job_id).first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Tow job not found")

#     driver = (
#         db.query(User)
#         .filter(User.id == payload.driver_id, User.role == UserRole.DRIVER, User.is_active == True)  # noqa: E712
#         .first()
#     )
#     if not driver:
#         raise HTTPException(status_code=400, detail="Driver not found")

#     job.assigned_driver_id = driver.id
#     job.status = TowStatus.ASSIGNED
#     _log_event(db, job.id, user.id, "ASSIGNED", f"Assigned to driver {driver.id}")
#     db.commit()
#     db.refresh(job)
#     return job


# @router.post("/{job_id}/status", response_model=TowJobOut)
# def update_status(
#     job_id: str,
#     payload: TowJobStatusUpdate,
#     db: Session = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     job = db.query(TowJob).filter(TowJob.id == job_id).first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Tow job not found")

#     _assert_job_access(user, job)

#     old = job.status.value
#     job.status = payload.status

#     if payload.notes:
#         existing = (job.notes or "").strip()
#         line = f"[{user.role.value}] {payload.notes.strip()}"
#         job.notes = f"{existing}\n{line}".strip() if existing else line

#     _log_event(
#         db,
#         job.id,
#         user.id,
#         "STATUS_CHANGED",
#         f"Status {old} -> {job.status.value}" + (f" | {payload.notes.strip()}" if payload.notes else ""),
#     )

#     db.commit()
#     db.refresh(job)
#     return job


# @router.post("/{job_id}/photos")
# def upload_job_photo(
#     job_id: str,
#     photo: UploadFile = File(...),
#     photo_type: str = Form(...),  # BEFORE, AFTER, PLATE_CLOSEUP, OTHER
#     db: Session = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     job = db.query(TowJob).filter(TowJob.id == job_id).first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Tow job not found")

#     _assert_job_access(user, job)

#     allowed_types = {"BEFORE", "AFTER", "PLATE_CLOSEUP", "OTHER"}
#     if photo_type not in allowed_types:
#         raise HTTPException(status_code=400, detail=f"photo_type must be one of {sorted(allowed_types)}")

#     allowed_ct = {"image/jpeg", "image/png", "image/webp"}
#     if photo.content_type not in allowed_ct:
#         raise HTTPException(status_code=400, detail="Only jpeg/png/webp images are allowed")

#     stored_path, size_bytes = save_upload_streaming(photo)

#     rec = TowJobPhoto(
#         id=str(uuid.uuid4()),
#         tow_job_id=job.id,
#         uploaded_by_user_id=user.id,
#         photo_type=photo_type,
#         file_path=stored_path,
#         content_type=photo.content_type,
#         size_bytes=size_bytes,
#     )
#     db.add(rec)

#     _log_event(db, job.id, user.id, "PHOTO_UPLOADED", f"{photo_type} photo uploaded ({size_bytes} bytes)")
#     db.commit()
#     db.refresh(rec)

#     return {
#         "id": rec.id,
#         "tow_job_id": rec.tow_job_id,
#         "uploaded_by_user_id": rec.uploaded_by_user_id,
#         "photo_type": rec.photo_type,
#         "file_path": rec.file_path,
#         "content_type": rec.content_type,
#         "size_bytes": rec.size_bytes,
#         "created_at": rec.created_at,
#         "download_url": f"/tow-jobs/{job.id}/photos/{rec.id}/download",
#     }


# @router.get("/{job_id}/photos/{photo_id}/download")
# def download_job_photo(
#     job_id: str,
#     photo_id: str,
#     db: Session = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     job = db.query(TowJob).filter(TowJob.id == job_id).first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Tow job not found")

#     _assert_job_access(user, job)

#     rec = db.query(TowJobPhoto).filter(TowJobPhoto.id == photo_id, TowJobPhoto.tow_job_id == job.id).first()
#     if not rec:
#         raise HTTPException(status_code=404, detail="Photo not found")

#     # Prevent path tricks: only allow files inside uploads/
#     abs_path = os.path.abspath(rec.file_path)
#     uploads_abs = os.path.abspath("uploads")
#     if not abs_path.startswith(uploads_abs + os.sep):
#         raise HTTPException(status_code=400, detail="Invalid file path")

#     if not os.path.exists(abs_path):
#         raise HTTPException(status_code=404, detail="File missing on server")

#     return FileResponse(path=abs_path, media_type=rec.content_type, filename=os.path.basename(abs_path))


# @router.get("/{job_id}/evidence")
# def get_job_evidence(
#     job_id: str,
#     db: Session = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     job = db.query(TowJob).filter(TowJob.id == job_id).first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Tow job not found")

#     _assert_job_access(user, job)

#     photos = db.query(TowJobPhoto).filter(TowJobPhoto.tow_job_id == job.id).all()

#     return {
#         "job": {
#             "id": job.id,
#             "plate_number": job.plate_number,
#             "status": job.status.value,
#             "officer_id": job.officer_id,
#             "assigned_driver_id": job.assigned_driver_id,
#             "violation_type": job.violation_type,
#             "notes": job.notes,
#             "location_lat": job.location_lat,
#             "location_lng": job.location_lng,
#             "location_accuracy_m": job.location_accuracy_m,
#             "created_at": job.created_at,
#         },
#         "photos": [
#             {
#                 "id": p.id,
#                 "photo_type": p.photo_type,
#                 "uploaded_by_user_id": p.uploaded_by_user_id,
#                 "created_at": p.created_at,
#                 "content_type": p.content_type,
#                 "size_bytes": p.size_bytes,
#                 "download_url": f"/tow-jobs/{job.id}/photos/{p.id}/download",
#             }
#             for p in photos
#         ],
#     }


# @router.get("/{job_id}/events")
# def get_job_events(
#     job_id: str,
#     db: Session = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     job = db.query(TowJob).filter(TowJob.id == job_id).first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Tow job not found")

#     _assert_job_access(user, job)

#     events = (
#         db.query(TowJobEvent)
#         .filter(TowJobEvent.tow_job_id == job.id)
#         .order_by(TowJobEvent.created_at.asc())
#         .all()
#     )

#     return [
#         {
#             "id": e.id,
#             "tow_job_id": e.tow_job_id,
#             "actor_user_id": e.actor_user_id,
#             "event_type": e.event_type,
#             "message": e.message,
#             "created_at": e.created_at,
#         }
#         for e in events
#     ]
