from pydantic import BaseModel, EmailStr, field_validator


def _validate_password_strength(v: str) -> str:
    if len(v) < 8 or not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        raise ValueError("Password must be at least 8 characters and include a letter and a number.")
    return v


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

    _password_strength = field_validator("password")(_validate_password_strength)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_admin: bool = False
    is_developer: bool = False
    is_email_verified: bool = True
    onboarding_completed: bool = True
    monitoring_consent: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    _password_strength = field_validator("new_password")(_validate_password_strength)
