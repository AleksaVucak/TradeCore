from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    email_verified: bool = False
    totp_enabled: bool = False

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerifyEmailRequest(BaseModel):
    token: str


class VerifyEmailResponse(BaseModel):
    message: str
    email_verified: bool


class ResendVerificationResponse(BaseModel):
    message: str


class RegisterResponse(BaseModel):
    """Returned from POST /register — includes user info + a message about verification."""
    id: int
    email: str
    email_verified: bool = False
    message: str = "Verification email sent. Please check your inbox."

    class Config:
        from_attributes = True
