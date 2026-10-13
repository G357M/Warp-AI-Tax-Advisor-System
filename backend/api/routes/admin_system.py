"""Admin System page: latest status of host cron jobs. Requires the admin role."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from core.admin_system import system_status
from core.security import require_admin
from core.time_utils import utc_now

router = APIRouter(prefix="/admin/system", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("")
def get_system():
    return system_status(Path(os.environ.get("ADMIN_OPS_STATUS_DIR", "/app/ops-status")), utc_now())
