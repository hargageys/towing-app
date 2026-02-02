from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_password, create_access_token
from app.models.user import User, UserRole
from app.models.tow_job import TowJob, TowStatus

from app.web.auth_web import COOKIE_NAME, get_current_user_from_cookie, require_roles_cookie

templates = Jinja2Templates(directory="app/web/templates")

router = APIRouter(prefix="/web", tags=["web"])


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_action(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.phone == phone).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"}, status_code=401)

    token = create_access_token(subject=user.id, role=user.role.value)

    # Redirect by role
    if user.role == UserRole.OFFICER:
        target = "/web/officer"
    elif user.role == UserRole.DRIVER:
        target = "/web/driver"
    elif user.role == UserRole.DISPATCHER:
        target = "/web/dispatcher"
    else:
        target = "/web/admin"

    resp = RedirectResponse(url=target, status_code=303)

    # Cookie settings:
    # - For MVP we keep it readable by JS if needed (not HttpOnly).
    #   Later we can switch to HttpOnly + server-side proxy for extra security.
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=60 * 60 * 12,
        samesite="lax",
        secure=False,   # set True when you move to HTTPS
        httponly=False,
    )
    return resp


@router.post("/logout")
def logout_action():
    resp = RedirectResponse(url="/web/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/", response_class=HTMLResponse)
def web_home(user: User = Depends(get_current_user_from_cookie)):
    # Bounce user to their dashboard
    if user.role == UserRole.OFFICER:
        return RedirectResponse("/web/officer", status_code=303)
    if user.role == UserRole.DRIVER:
        return RedirectResponse("/web/driver", status_code=303)
    if user.role == UserRole.DISPATCHER:
        return RedirectResponse("/web/dispatcher", status_code=303)
    return RedirectResponse("/web/admin", status_code=303)


# -------------------
# OFFICER DASHBOARD
# -------------------
@router.get("/officer", response_class=HTMLResponse)
def officer_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles_cookie(UserRole.OFFICER, UserRole.ADMIN)),
):
    # Show officer's recent jobs (admin can see all if you want; here we'll keep role-aware)
    q = db.query(TowJob)
    if user.role == UserRole.OFFICER:
        q = q.filter(TowJob.officer_id == user.id)

    jobs = q.order_by(TowJob.created_at.desc()).limit(25).all()

    return templates.TemplateResponse(
        "officer.html",
        {"request": request, "user": user, "jobs": jobs, "statuses": [s.value for s in TowStatus]},
    )


# -------------------
# DRIVER / DISPATCHER / ADMIN placeholders (we’ll build next)
# -------------------
@router.get("/driver", response_class=HTMLResponse)
def driver_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles_cookie(UserRole.DRIVER, UserRole.ADMIN)),
):
    q = db.query(TowJob)
    if user.role == UserRole.DRIVER:
        q = q.filter(TowJob.assigned_driver_id == user.id)

    jobs = q.order_by(TowJob.created_at.desc()).limit(50).all()
    return templates.TemplateResponse("driver.html", {"request": request, "user": user, "jobs": jobs})

@router.get("/dispatcher", response_class=HTMLResponse)
def dispatcher_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles_cookie(UserRole.DISPATCHER, UserRole.ADMIN)),
):
    jobs = db.query(TowJob).order_by(TowJob.created_at.desc()).limit(100).all()

    # Drivers list for assignment
    drivers = (
        db.query(User)
        .filter(User.role == UserRole.DRIVER, User.is_active == True)
        .order_by(User.name.asc())
        .all()
    )

    return templates.TemplateResponse(
        "dispatcher.html",
        {"request": request, "user": user, "jobs": jobs, "drivers": drivers},
    )

# @router.get("/dispatcher", response_class=HTMLResponse)
# def dispatcher_dashboard(
#     request: Request,
#     db: Session = Depends(get_db),
#     user: User = Depends(require_roles_cookie(UserRole.DISPATCHER, UserRole.ADMIN)),
# ):
#     jobs = db.query(TowJob).order_by(TowJob.created_at.desc()).limit(100).all()
#     return templates.TemplateResponse("dispatcher.html", {"request": request, "user": user, "jobs": jobs})


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles_cookie(UserRole.ADMIN)),
):
    jobs = db.query(TowJob).order_by(TowJob.created_at.desc()).limit(100).all()
    return templates.TemplateResponse("admin.html", {"request": request, "user": user, "jobs": jobs})
