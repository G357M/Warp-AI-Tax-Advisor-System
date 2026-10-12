"""Admin Corpus page: document base contents and growth. Requires the admin role."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.admin_corpus import corpus
from core.database import get_db
from core.security import require_admin
from core.time_utils import utc_now

router = APIRouter(prefix="/admin/corpus", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("")
def get_corpus(db: Session = Depends(get_db)):
    return corpus(db, utc_now())
