"""Modelos de equipos y sus políticas operativas de asignación."""

import uuid
from enum import Enum as PythonEnum

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class AssignmentStrategy(str, PythonEnum):
    """Criterios disponibles para elegir un responsable automáticamente."""

    # Prioriza al miembro con menos tickets activos.
    LEAST_ACTIVE = "LEAST_ACTIVE"
    # Prioriza al miembro que lleva más tiempo sin recibir una asignación.
    LONGEST_IDLE = "LONGEST_IDLE"


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("name", name="teams_name_key"),
        CheckConstraint(
            "auto_assignment_delay_minutes >= 0",
            name="ck_teams_auto_assignment_delay_non_negative",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)

    # Reclamo manual: un miembro elige voluntariamente un ticket de la cola.
    self_assignment_enabled = Column(Boolean, nullable=False, default=False, server_default=false())

    # Asignación automática: el sistema espera el plazo y aplica la estrategia.
    auto_assignment_enabled = Column(Boolean, nullable=False, default=False, server_default=false())
    auto_assignment_delay_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    assignment_strategy = Column(
        Enum(AssignmentStrategy, name="assignmentstrategy"),
        nullable=False,
        default=AssignmentStrategy.LEAST_ACTIVE,
        server_default=AssignmentStrategy.LEAST_ACTIVE.value,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    members = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    lead_assignments = relationship(
        "TeamLead",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    tickets = relationship("Ticket", back_populates="team")
    categories = relationship(
        "CategoryTeam",
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")


class TeamLead(Base):
    __tablename__ = "team_leads"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_leads_team_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    team = relationship("Team", back_populates="lead_assignments")
    user = relationship("User", back_populates="team_lead_assignments")
