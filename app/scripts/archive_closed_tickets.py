"""Archiva tickets cerrados antiguos.

Uso:
    python -m app.scripts.archive_closed_tickets

Este script es intencionalmente fino: abre una sesion, lee la configuracion y
delega la regla de negocio en ticket_lifecycle_service.
Mas adelante Celery puede reutilizar el mismo service.
"""

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.ticket_lifecycle_service import archive_old_closed_tickets


def main() -> int:
    db = SessionLocal()
    try:
        archived_count = archive_old_closed_tickets(
            db,
            days=settings.archive_closed_tickets_after_days,
        )
        print(f"Tickets archivados: {archived_count}")
        return archived_count
    finally:
        db.close()


if __name__ == "__main__":
    main()
