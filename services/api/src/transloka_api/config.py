from ipaddress import ip_address

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCALHOST_BIND_ERROR = (
    "STARTUP_BLOCKED_NON_LOCAL_BIND: API host must be localhost or a loopback IP."
)


def validate_api_host(value: str) -> str:
    if not value.isprintable():
        raise ValueError(_LOCALHOST_BIND_ERROR)

    candidate = value.strip()
    if not candidate or "%" in candidate:
        raise ValueError(_LOCALHOST_BIND_ERROR)
    if candidate.casefold() == "localhost":
        return "localhost"

    try:
        address = ip_address(candidate)
    except ValueError:
        raise ValueError(_LOCALHOST_BIND_ERROR) from None
    if not address.is_loopback:
        raise ValueError(_LOCALHOST_BIND_ERROR)
    return str(address)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRANSLOKA_API_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("host", mode="before")
    @classmethod
    def validate_host(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError(_LOCALHOST_BIND_ERROR)
        return validate_api_host(value)
