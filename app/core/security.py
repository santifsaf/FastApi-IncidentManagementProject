from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.schemas.auth import TokenPayload

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def _validate_bcrypt_password_length(password: str) -> None:
    # bcrypt admite como máximo 72 bytes, no 72 caracteres.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes.")


def hash_password(password: str) -> str:
    """Valida y transforma una contraseña plana en un hash bcrypt."""

    _validate_bcrypt_password_length(password)
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara una contraseña plana con un hash almacenado."""

    # Si supera el límite de bcrypt, la tratamos como contraseña inválida.
    if len(plain_password.encode("utf-8")) > 72:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def normalize_email(email: str) -> str:
    """Normaliza el email usado para búsquedas y restricciones de unicidad."""

    return email.strip().lower()


def create_access_token(subject: str) -> str:
    """Genera un JWT de acceso para la identidad recibida en ``subject``."""

    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    # "sub" guarda la identidad principal autenticada. En este proyecto usamos user.id.
    payload = {"sub": subject, "exp": expire, "iat": now}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Valida firma y claims obligatorios, y devuelve un payload tipado."""

    decoded = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm],
        options={"require": ["exp", "iat", "sub"]},
    )
    return TokenPayload(**decoded)
