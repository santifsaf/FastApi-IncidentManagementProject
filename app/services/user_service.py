from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate


class UserServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def create_user_service(db, user_in: UserCreate) -> User:
    try:
        new_user = User(
            email=user_in.email,
            password_hash=hash_password(user_in.password),
            full_name=user_in.full_name,
        )
    except ValueError as exc:
        raise UserServiceError(str(exc), 400) from exc

    db.add(new_user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise UserServiceError("Email already registered", 409) from exc

    db.refresh(new_user)
    return new_user
