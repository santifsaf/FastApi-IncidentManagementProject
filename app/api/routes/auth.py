"""Endpoint de autenticación y emisión de tokens de acceso."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.security import create_access_token, normalize_email, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Valida email y contraseña, y emite un bearer token para usuarios activos.

    OAuth2 llama ``username`` al identificador del formulario; en esta API ese
    valor representa el email normalizado del usuario.
    """

    email = normalize_email(form_data.username)
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    access_token = create_access_token(subject=str(user.id))
    return Token(access_token=access_token)
