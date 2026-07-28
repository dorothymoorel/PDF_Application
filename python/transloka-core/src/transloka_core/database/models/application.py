from enum import StrEnum

from sqlalchemy import CheckConstraint, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SettingCategory(StrEnum):
    GENERAL = "GENERAL"
    STORAGE = "STORAGE"
    TRANSLATION = "TRANSLATION"
    OCR = "OCR"
    RECONSTRUCTION = "RECONSTRUCTION"
    BACKUP = "BACKUP"
    ADVANCED = "ADVANCED"


_CATEGORY_VALUES = ", ".join(f"'{category.value}'" for category in SettingCategory)


class ApplicationMetadata(Base):
    __tablename__ = "app_metadata"
    __table_args__ = {"sqlite_strict": True}

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class ApplicationSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint(
            "json_valid(value_json)",
            name="ck_app_settings_value_json_valid",
        ),
        CheckConstraint(
            f"category IN ({_CATEGORY_VALUES})",
            name="ck_app_settings_category",
        ),
        CheckConstraint(
            "(key = 'translation_batch_size' AND category = 'TRANSLATION') OR "
            "(key = 'ocr_concurrency' AND category = 'OCR')",
            name="ck_app_settings_key_category",
        ),
        {"sqlite_strict": True},
    )

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
