"""Cálculo compartido de vencimientos para asignaciones automáticas."""

from datetime import datetime, timedelta, timezone


def calculate_assignment_due_at(
    enabled: bool,
    delay_minutes: int,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Devuelve el vencimiento o ``None`` cuando la automatización está apagada."""

    if not enabled:
        return None
    reference_time = now or datetime.now(timezone.utc)
    return reference_time + timedelta(minutes=delay_minutes)
