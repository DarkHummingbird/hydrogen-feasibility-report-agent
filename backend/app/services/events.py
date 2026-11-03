"""埋点（PRD 第四节 E1–E3）：存本地表，不上报第三方。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Event


def record(db: Session, code: str, report_id: str | None, **payload) -> Event:
    event = Event(code=code, report_id=report_id, payload=payload)
    db.add(event)
    db.commit()
    return event
