# backend/auth/security.py
from passlib.context import CryptContext

# bcrypt is simple and solid. If you already use argon2, say so and we’ll switch.
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    if plain is None:
        raise ValueError("plain password is None")
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return pwd_ctx.verify(plain, hashed)
