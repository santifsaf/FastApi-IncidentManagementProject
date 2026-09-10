"""Casos de uso relacionados con la creación de usuarios."""

from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password, normalize_email
from app.models.user import User
from app.schemas.user import UserCreate


class UserServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def create_user_service(db, user_in: UserCreate) -> User:
    """Normaliza el email, protege la contraseña y persiste un usuario único."""

    email = normalize_email(user_in.email)
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise UserServiceError("Email already registered", 409)

    try:
        new_user = User(
            email=email,
            password_hash=hash_password(user_in.password),
            full_name=user_in.full_name,
        )
    except ValueError as exc:
        raise UserServiceError(str(exc), 400) from exc

    db.add(new_user)

    try:
        db.commit()
        db.refresh(new_user)
        return new_user
    except IntegrityError as exc:
        db.rollback()
        raise UserServiceError("Email already registered", 409) from exc
    except Exception:
        db.rollback()
        raise
