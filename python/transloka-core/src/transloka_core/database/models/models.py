from enum import StrEnum

from sqlalchemy import CheckConstraint, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base


class ModelLicenseStatus(StrEnum):
    APPROVED = "APPROVED"
    APPROVED_FOR_PERSONAL_USE = "APPROVED_FOR_PERSONAL_USE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class ModelRole(StrEnum):
    TRANSLATION = "TRANSLATION"
    VALIDATION = "VALIDATION"


_LICENSE_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in ModelLicenseStatus)


class LocalModelRecord(Base):
    __tablename__ = "local_models"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'mdl_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_local_models_prefixed_uuid",
        ),
        CheckConstraint(
            "trim(ollama_model_name) <> ''",
            name="ck_local_models_name",
        ),
        CheckConstraint(
            "disk_size_bytes IS NULL OR disk_size_bytes >= 0",
            name="ck_local_models_disk_size",
        ),
        CheckConstraint(
            f"license_status IN ({_LICENSE_STATUS_VALUES})",
            name="ck_local_models_license_status",
        ),
        CheckConstraint("is_installed IN (0, 1)", name="ck_local_models_installed"),
        CheckConstraint(
            "is_selected_translation IN (0, 1)",
            name="ck_local_models_selected_translation",
        ),
        CheckConstraint(
            "is_selected_validation IN (0, 1)",
            name="ck_local_models_selected_validation",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_local_models_metadata_json_valid",
        ),
        CheckConstraint(
            "trim(last_detected_at) <> ''",
            name="ck_local_models_last_detected",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    ollama_model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameter_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantization: Mapped[str | None] = mapped_column(Text, nullable=True)
    disk_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    license_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_status: Mapped[str] = mapped_column(Text, nullable=False)
    is_installed: Mapped[int] = mapped_column(Integer, nullable=False)
    is_selected_translation: Mapped[int] = mapped_column(Integer, nullable=False)
    is_selected_validation: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_detected_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_local_models_ollama_name",
    LocalModelRecord.ollama_model_name,
    unique=True,
)
Index(
    "uq_local_models_selected_translation",
    LocalModelRecord.is_selected_translation,
    unique=True,
    sqlite_where=text("is_selected_translation = 1"),
)
Index(
    "uq_local_models_selected_validation",
    LocalModelRecord.is_selected_validation,
    unique=True,
    sqlite_where=text("is_selected_validation = 1"),
)
