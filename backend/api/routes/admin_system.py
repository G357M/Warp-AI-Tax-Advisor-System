"""Admin System page: latest status of host cron jobs and manual runs. Requires the admin role."""
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.admin_ops_requests import request_job
from core.admin_system import system_status
from core.database import get_db
from core.security import require_admin
from core.time_utils import utc_now
from models import User

router = APIRouter(prefix="/admin/system", tags=["Admin"], dependencies=[Depends(require_admin)])

ManualJob = Literal["scraper_ingest", "scraper_full", "canary", "backup"]


def _dirs() -> tuple:
    return (Path(os.environ.get("ADMIN_OPS_STATUS_DIR", "/app/ops-status")),
            Path(os.environ.get("ADMIN_OPS_REQUEST_DIR", "/app/ops-requests")))


@router.get("")
def get_system():
    status_dir, request_dir = _dirs()
    return system_status(status_dir, utc_now(), request_dir)


@router.post("/jobs/{job}", status_code=202, responses={
    409: {"description": "already_pending, scraper_busy, backup_too_recent or canary_too_recent"},
    500: {"description": "ops_queue_unavailable: the request folder is not writable"},
})
def post_job(job: ManualJob, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    status_dir, request_dir = _dirs()
    return request_job(db, actor=admin, job=job, status_dir=status_dir, request_dir=request_dir, now=utc_now())
