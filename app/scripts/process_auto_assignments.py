"""Procesa una tanda de autoasignaciones vencidas.

Uso:
    python -m app.scripts.process_auto_assignments

El script es un punto de entrada temporal y reutiliza el mismo service que más
adelante podrá invocar un worker periódico.
"""

from app.db.session import SessionLocal
from app.services.ticket_auto_assignment_service import process_due_auto_assignments


def main() -> None:
    db = SessionLocal()
    try:
        result = process_due_auto_assignments(db)
        print(f"Teams asignados: {result.teams_assigned}")
        print(f"Responsables asignados: {result.users_assigned}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
