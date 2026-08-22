from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    profile_id: str
    operating_system: str
    operating_system_version: str
    cpu_model: str
    physical_cores: int | None
    logical_cores: int | None
    ram_total_gb: float | None
    ram_available_gb: float | None
    gpu_vendor: str | None
    gpu_model: str | None
    gpu_vram_total_gb: float | None
    gpu_vram_available_gb: float | None
    disk_type: str | None
    disk_free_gb: float | None
    ollama_version: str | None
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_hardware_profile(*, now: datetime | None = None) -> HardwareProfile:
    """Collect safe, best-effort host information without probing external services."""

    try:
        disk_free_gb = shutil.disk_usage(".").free / (1024**3)
    except OSError:
        disk_free_gb = None
    logical_cores = os.cpu_count()
    ram_total_gb, ram_available_gb = _memory_gb()
    timestamp = (now or datetime.now(UTC)).isoformat(timespec="seconds").replace("+00:00", "Z")
    return HardwareProfile(
        profile_id=f"hardware_{uuid4().hex}",
        operating_system=platform.system() or "unknown",
        operating_system_version=platform.version() or "unknown",
        cpu_model=platform.processor() or "unknown",
        physical_cores=None,
        logical_cores=logical_cores if logical_cores is None or logical_cores > 0 else None,
        ram_total_gb=ram_total_gb,
        ram_available_gb=ram_available_gb,
        gpu_vendor=None,
        gpu_model=None,
        gpu_vram_total_gb=0.0,
        gpu_vram_available_gb=0.0,
        disk_type=None,
        disk_free_gb=disk_free_gb if disk_free_gb is None or disk_free_gb >= 0 else None,
        ollama_version=None,
        created_at=timestamp,
    )


def _memory_gb() -> tuple[float | None, float | None]:
    if sys.platform == "win32":
        try:
            import ctypes

            class _MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = _MemoryStatus()
            status.length = ctypes.sizeof(_MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return _bytes_to_gb(status.total_physical), _bytes_to_gb(status.available_physical)
        except (AttributeError, OSError, TypeError):
            return None, None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            values: dict[str, int] = {}
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                key, separator, raw_value = line.partition(":")
                if separator and raw_value.strip().endswith(" kB"):
                    values[key] = int(raw_value.strip()[:-3]) * 1024
            if "MemTotal" in values and "MemAvailable" in values:
                return _bytes_to_gb(values["MemTotal"]), _bytes_to_gb(values["MemAvailable"])
        except (OSError, ValueError):
            return None, None
    return None, None


def _bytes_to_gb(value: int) -> float:
    return round(value / (1024**3), 2)


__all__ = ["HardwareProfile", "detect_hardware_profile"]
