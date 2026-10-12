"""Admin trends: read-only time series. All endpoints require the admin role."""
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.admin_trends import trends
from core.database import get_db
from core.security import require_admin
from core.time_utils import utc_now

router = APIRouter(prefix="/admin/trends", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("")
def get_trends(period: Literal["30d", "90d", "12m"] = "30d", db: Session = Depends(get_db)):
    return trends(db, period, utc_now())
