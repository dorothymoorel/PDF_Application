from ipaddress import ip_address
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

_LOCALHOST_BIND_ERROR = (
    "STARTUP_BLOCKED_NON_LOCAL_BIND: API host must be localhost or a loopback IP."
)
_WEB_ORIGINS_ERROR = "Origin configuration must contain only local HTTP origins."
DEFAULT_WEB_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
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


def _normalize_web_origin(value: str) -> str:
    if not value.isprintable():
        raise ValueError(_WEB_ORIGINS_ERROR)

    candidate = value.strip()
    if not candidate or "*" in candidate or "?" in candidate or "#" in candidate:
        raise ValueError(_WEB_ORIGINS_ERROR)

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError(_WEB_ORIGINS_ERROR) from None

    if (
        parsed.scheme.casefold() != "http"
        or not parsed.netloc
        or hostname is None
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(_WEB_ORIGINS_ERROR)

    try:
        normalized_host = validate_api_host(hostname)
    except ValueError:
        raise ValueError(_WEB_ORIGINS_ERROR) from None

    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    return f"http://{normalized_host}:{port}"


def parse_web_origins(value: str) -> tuple[str, ...]:
    origins: list[str] = []
    seen: set[str] = set()
    for entry in value.split(","):
        normalized = _normalize_web_origin(entry)
        if normalized not in seen:
            origins.append(normalized)
            seen.add(normalized)
    return tuple(origins)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRANSLOKA_API_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    web_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=DEFAULT_WEB_ORIGINS,
        validation_alias="TRANSLOKA_WEB_ORIGINS",
    )

    @property
    def data_directories(self) -> LocalDataDirectories:
        return resolve_local_data_directories()

    @field_validator("host", mode="before")
    @classmethod
    def validate_host(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError(_LOCALHOST_BIND_ERROR)
        return validate_api_host(value)

    @field_validator("web_origins", mode="before")
    @classmethod
    def validate_web_origins(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return parse_web_origins(value)
        if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
            return parse_web_origins(",".join(value))
        raise ValueError(_WEB_ORIGINS_ERROR)
