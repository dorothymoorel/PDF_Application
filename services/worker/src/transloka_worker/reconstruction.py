from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Self, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pypdf import PdfReader, PdfWriter
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import DocumentBlock, DocumentSegment
from transloka_core.database.models.documents import Document
from transloka_core.database.models.exports import Export, ExportStatus, ExportType
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project, ProjectStatus
from transloka_core.database.models.reconstruction import (
    ReconstructionBlock,
    ReconstructionBlockStatus,
    ReconstructionJob,
    ReconstructionPage,
    ReconstructionStatus,
    TargetPageMapping,
    TargetPageMappingType,
)
from transloka_core.database.models.warnings import Warning, WarningSeverity, WarningStatus
from transloka_core.jobs.cancellation import JobCancellationService
from transloka_core.jobs.progress import JobProgressService
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.storage.local import LocalFileStorage, LocalFileStorageError
from transloka_quality.pdf import FinalPdfValidationReport, validate_final_pdf
from transloka_reconstruction.fonts.reportlab import ReportLabFontCatalog
from transloka_reconstruction.hybrid import (
    BlockDescriptor,
    BlockStrategy,
    HybridStrategyClassifier,
    PageDescriptor,
)
from transloka_reconstruction.overlay import (
    CoverRegion,
    OverlayPageGenerator,
    OverlayText,
    TextAlignment,
)
from transloka_reconstruction.reflow.generator import ReflowPageSettings, ReflowPDFGenerator
from transloka_reconstruction.reflow.types import ReflowBlock, ReflowBlockKind, ReflowDocument
from transloka_reconstruction.settings import ReconstructionMode, ReconstructionSettings

RECONSTRUCTION_COMMAND_SCHEMA = "transloka.reconstruction.command.v1"
_COMMAND_FIELDS = frozenset({"schema", "project_id", "document_id", "mode", "page_ids", "settings"})


class ReconstructionWorkerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReconstructionBlockInput:
    block_id: str
    block_type: str
    source_text: str
    translated_text: str | None
    source_geometry: Mapping[str, object]
    source_style: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ReconstructionPageInput:
    page_id: str
    source_page_number: int
    width_points: float
    height_points: float
    page_type: str
    column_count: int
    blocks: tuple[ReconstructionBlockInput, ...]


@dataclass(frozen=True, slots=True)
class LoadedReconstructionJob:
    job_id: str
    reconstruction_job_id: str
    project_id: str
    document_id: str
    source_pdf: bytes
    pages: tuple[ReconstructionPageInput, ...]
    selected_page_ids: tuple[str, ...]
    command: ReconstructionCommand
    critical_warnings: tuple[Warning, ...]


@dataclass(frozen=True, slots=True)
class RenderedPage:
    source_page_id: str
    source_page_number: int
    target_page_start: int
    target_page_end: int
    strategy: str
    block_strategies: tuple[tuple[str, str], ...]
    page_hash: str
    font_mappings: tuple[tuple[str, dict[str, object]], ...] = ()


@dataclass(frozen=True, slots=True)
class ReconstructionRenderResult:
    pdf_bytes: bytes
    pages: tuple[RenderedPage, ...]
    required_segments: tuple[str, ...]
    source_residue: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconstructionRunResult:
    job_id: str
    reconstruction_job_id: str
    status: JobStatus
    export_id: str | None
    file_id: str | None
    checksum_sha256: str | None
    page_count: int


@dataclass(frozen=True, slots=True)
class ReconstructionCommand:
    project_id: str
    document_id: str
    mode: ReconstructionMode | str
    page_ids: tuple[str, ...]
    settings: ReconstructionSettings | Mapping[str, object]

    def __post_init__(self) -> None:
        _validate_identifier(self.project_id, "prj_")
        _validate_identifier(self.document_id, "doc_")
        _validate_page_ids(self.page_ids)
        try:
            mode = (
                self.mode
                if isinstance(self.mode, ReconstructionMode)
                else ReconstructionMode(self.mode)
            )
        except (TypeError, ValueError):
            raise ReconstructionWorkerError("The reconstruction command mode is invalid.") from None
        try:
            settings = (
                self.settings
                if isinstance(self.settings, ReconstructionSettings)
                else ReconstructionSettings.from_dict(self.settings)
            )
        except (TypeError, ValueError) as exc:
            raise ReconstructionWorkerError(
                "The reconstruction command settings are invalid."
            ) from exc
        if settings.mode is not mode:
            raise ReconstructionWorkerError(
                "The reconstruction command mode does not match its settings."
            )
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "settings", settings)

    def to_payload(self) -> dict[str, object]:
        settings = cast(ReconstructionSettings, self.settings)
        return {
            "schema": RECONSTRUCTION_COMMAND_SCHEMA,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "mode": cast(ReconstructionMode, self.mode).value,
            "page_ids": list(self.page_ids),
            "settings": settings.to_dict(),
        }

    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        payload = _decode_command(value)
        if frozenset(payload) != _COMMAND_FIELDS:
            raise ReconstructionWorkerError("The reconstruction command fields are invalid.")
        if payload["schema"] != RECONSTRUCTION_COMMAND_SCHEMA:
            raise ReconstructionWorkerError("The reconstruction command schema is unsupported.")
        settings = payload.get("settings")
        if not isinstance(settings, Mapping):
            raise ReconstructionWorkerError("The reconstruction command settings are invalid.")
        try:
            return cls(
                project_id=_string_value(payload, "project_id"),
                document_id=_string_value(payload, "document_id"),
                mode=_string_value(payload, "mode"),
                page_ids=_page_id_tuple(payload["page_ids"]),
                settings=cast(Mapping[str, object], settings),
            )
        except (KeyError, TypeError):
            raise ReconstructionWorkerError(
                "The reconstruction command values are invalid."
            ) from None


class DatabaseReconstructionRequestLoader:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalFileStorage,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    def load(self, job_id: str) -> LoadedReconstructionJob:
        _validate_identifier(job_id, "job_")
        with self._session_factory() as session:
            job = session.get(ApplicationJob, job_id)
            if job is None or job.job_type != JobType.RECONSTRUCT_DOCUMENT.value:
                raise ReconstructionWorkerError("The reconstruction job is unavailable.")
            if job.status not in {
                JobStatus.QUEUED.value,
                JobStatus.RETRYING.value,
                JobStatus.RUNNING.value,
                JobStatus.CANCELLATION_REQUESTED.value,
                JobStatus.CANCELLED.value,
                JobStatus.COMPLETED.value,
                JobStatus.COMPLETED_WITH_WARNINGS.value,
            }:
                raise ReconstructionWorkerError("The reconstruction job is not executable.")
            command = ReconstructionCommand.from_payload_json(job.payload_json)
            project = session.get(Project, command.project_id)
            document = session.get(Document, command.document_id)
            reconstruction = session.scalar(
                select(ReconstructionJob).where(ReconstructionJob.application_job_id == job.id)
            )
            settings_json = json.dumps(
                cast(ReconstructionSettings, command.settings).to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            )
            if (
                project is None
                or document is None
                or reconstruction is None
                or project.active_document_id != command.document_id
                or document.project_id != command.project_id
                or job.project_id != command.project_id
                or job.document_id != command.document_id
                or reconstruction.project_id != command.project_id
                or reconstruction.document_id != command.document_id
                or reconstruction.mode != cast(ReconstructionMode, command.mode).value
                or reconstruction.settings_json != settings_json
            ):
                raise ReconstructionWorkerError("The reconstruction command state is inconsistent.")

            original = session.get(StoredFile, document.original_file_id)
            if (
                original is None
                or original.project_id != command.project_id
                or original.file_role != FileRole.ORIGINAL.value
                or original.status != FileStatus.VALIDATED.value
                or not original.is_immutable
                or original.mime_type != "application/pdf"
            ):
                raise ReconstructionWorkerError("The reconstruction source PDF is unavailable.")
            try:
                if self._storage.checksum(original.storage_key) != original.checksum_sha256:
                    raise ReconstructionWorkerError(
                        "The reconstruction source PDF checksum is invalid."
                    )
                with self._storage.open_read(original.storage_key) as source:
                    source_pdf = source.read()
            except LocalFileStorageError as exc:
                raise ReconstructionWorkerError(
                    "The reconstruction source PDF is unavailable."
                ) from exc

            page_rows = tuple(
                session.scalars(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == command.document_id)
                    .order_by(DocumentPage.source_page_number, DocumentPage.id)
                )
            )
            selected_ids = command.page_ids or tuple(page.id for page in page_rows)
            if not selected_ids:
                raise ReconstructionWorkerError("The reconstruction document has no pages.")
            selected_set = set(selected_ids)
            if selected_set - {page.id for page in page_rows}:
                raise ReconstructionWorkerError("A reconstruction page is unavailable.")
            pages = tuple(
                _load_page(session, page) for page in page_rows if page.id in selected_set
            )
            critical_warnings = tuple(
                session.scalars(
                    select(Warning).where(
                        Warning.project_id == command.project_id,
                        Warning.status == WarningStatus.OPEN.value,
                        Warning.severity == WarningSeverity.CRITICAL.value,
                    )
                )
            )
            return LoadedReconstructionJob(
                job_id=job.id,
                reconstruction_job_id=reconstruction.id,
                project_id=command.project_id,
                document_id=command.document_id,
                source_pdf=source_pdf,
                pages=pages,
                selected_page_ids=selected_ids,
                command=command,
                critical_warnings=critical_warnings,
            )


class ReconstructionRenderer:
    def __init__(self, *, font_catalog: ReportLabFontCatalog | None = None) -> None:
        self._font_catalog = font_catalog or ReportLabFontCatalog()

    def render(self, loaded: LoadedReconstructionJob) -> ReconstructionRenderResult:
        source_reader = PdfReader(BytesIO(loaded.source_pdf), strict=False)
        if len(source_reader.pages) < 1:
            raise ReconstructionWorkerError("The reconstruction source PDF has no pages.")
        selected = {page.source_page_number: page for page in loaded.pages}
        valid_page_numbers = set(range(1, len(source_reader.pages) + 1))
        if set(selected) - valid_page_numbers:
            raise ReconstructionWorkerError("A reconstruction page number is outside the PDF.")
        if not loaded.command.page_ids and set(selected) != valid_page_numbers:
            raise ReconstructionWorkerError(
                "The reconstruction database page set does not match the source PDF."
            )
        validate_source_residue = set(selected) == valid_page_numbers
        writer = PdfWriter()
        rendered_pages: list[RenderedPage] = []
        required_segments: list[str] = []
        source_residue: list[str] = []
        target_page_number = 1
        for source_page_number in range(1, len(source_reader.pages) + 1):
            page = selected.get(source_page_number)
            if page is None:
                sanitized = OverlayPageGenerator().generate(
                    loaded.source_pdf, page_index=source_page_number - 1
                )
                _append_pdf(writer, sanitized)
                target_page_number += 1
                continue
            page_pdf, strategy, block_strategies, font_mappings = self._render_page(loaded, page)
            page_count = _append_pdf(writer, page_pdf)
            page_required = tuple(
                block.translated_text for block in page.blocks if block.translated_text is not None
            )
            required_segments.extend(page_required)
            if validate_source_residue:
                source_residue.extend(
                    block.source_text
                    for block in page.blocks
                    if block.translated_text is not None
                    and block.source_text.strip()
                    and block.source_text.strip() != block.translated_text.strip()
                )
            rendered_pages.append(
                RenderedPage(
                    source_page_id=page.page_id,
                    source_page_number=source_page_number,
                    target_page_start=target_page_number,
                    target_page_end=target_page_number + page_count - 1,
                    strategy=strategy,
                    block_strategies=block_strategies,
                    page_hash=_sha256(page_pdf),
                    font_mappings=font_mappings,
                )
            )
            target_page_number += page_count
        output = BytesIO()
        writer.write(output)
        return ReconstructionRenderResult(
            pdf_bytes=output.getvalue(),
            pages=tuple(rendered_pages),
            required_segments=tuple(required_segments),
            source_residue=tuple(source_residue),
        )

    def _render_page(
        self,
        loaded: LoadedReconstructionJob,
        page: ReconstructionPageInput,
    ) -> tuple[bytes, str, tuple[tuple[str, str], ...], tuple[tuple[str, dict[str, object]], ...]]:
        mode = cast(ReconstructionMode, loaded.command.mode)
        if mode is ReconstructionMode.OVERLAY:
            return self._overlay(loaded.source_pdf, page)
        if mode is ReconstructionMode.REFLOW:
            return (*self._reflow(page), ())
        decision = HybridStrategyClassifier().classify_page(
            PageDescriptor(
                page_id=page.page_id,
                page_type=page.page_type,
                column_count=max(1, page.column_count),
                blocks=tuple(
                    BlockDescriptor(
                        block_id=block.block_id,
                        block_type=block.block_type,
                        text=block.translated_text or block.source_text,
                    )
                    for block in page.blocks
                ),
            ),
            settings=cast(ReconstructionSettings, loaded.command.settings),
        )
        reflow_blocks = {
            block.block_id
            for block in decision.block_decisions
            if block.strategy is BlockStrategy.REFLOW
        }
        # Reflow translated paragraphs inside their source boxes. Escalating one
        # block to whole-page reflow discards artwork and fixed source geometry.
        # The overlay renderer measures with the output font and rejects overflow.
        pdf, _, rendered_strategies, font_mappings = self._overlay(loaded.source_pdf, page)
        block_strategies = tuple(
            (
                block_id,
                "REFLOW" if strategy == "OVERLAY" and block_id in reflow_blocks else strategy,
            )
            for block_id, strategy in rendered_strategies
        )
        return pdf, "OVERLAY", block_strategies, font_mappings

    def _overlay(
        self,
        source_pdf: bytes,
        page: ReconstructionPageInput,
    ) -> tuple[bytes, str, tuple[tuple[str, str], ...], tuple[tuple[str, dict[str, object]], ...]]:
        texts: list[OverlayText] = []
        covers: list[CoverRegion] = []
        strategies: list[tuple[str, str]] = []
        font_mappings: list[tuple[str, dict[str, object]]] = []
        for block in page.blocks:
            if block.translated_text is None:
                strategies.append((block.block_id, "PRESERVE"))
                continue
            x, y, width, height = _pdf_geometry(block.source_geometry, page)
            font_size = _font_size(block.source_style, block.source_geometry, height)
            text_x, text_width, alignment = _text_box(block, page, x, width)
            style = block.source_style or {}
            source_font = style.get(
                "font_name", style.get("font_postscript_name", style.get("font_family"))
            )
            fallback = _font_name(block.source_style)
            font = self._font_catalog.resolve(
                source_font if isinstance(source_font, str) and source_font.strip() else fallback,
                block.translated_text,
                fallback=fallback,
            )
            font_mappings.append((block.block_id, font.metadata()))
            texts.append(
                OverlayText(
                    block.translated_text,
                    x=text_x,
                    y=y,
                    width=text_width,
                    height=height,
                    font_name=font.name,
                    font_size_pt=font_size,
                    leading_pt=_leading(block, font_size, height),
                    alignment=alignment,
                    text_id=block.block_id,
                )
            )
            covers.append(
                CoverRegion(
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    source_text=block.source_text or None,
                    region_id=block.block_id,
                )
            )
            strategies.append((block.block_id, "OVERLAY"))
        return (
            OverlayPageGenerator().generate(
                source_pdf,
                page_index=page.source_page_number - 1,
                texts=texts,
                covers=covers,
            ),
            "OVERLAY",
            tuple(strategies),
            tuple(font_mappings),
        )

    @staticmethod
    def _reflow(
        page: ReconstructionPageInput,
    ) -> tuple[bytes, str, tuple[tuple[str, str], ...]]:
        blocks: list[ReflowBlock] = []
        strategies: list[tuple[str, str]] = []
        for block in page.blocks:
            if block.translated_text is None:
                continue
            blocks.append(
                ReflowBlock(
                    block_id=block.block_id,
                    kind=_reflow_kind(block.block_type),
                    text=block.translated_text,
                    level=_heading_level(block.block_type),
                )
            )
            strategies.append((block.block_id, "REFLOW"))
        if not blocks:
            raise ReconstructionWorkerError("A reflow page has no translated text.")
        settings = ReflowPageSettings(width_pt=page.width_points, height_pt=page.height_points)
        pdf = ReflowPDFGenerator(page_settings=settings).generate(
            ReflowDocument(pages=(), blocks=tuple(blocks), document_id=None)
        )
        return pdf, "REFLOW", tuple(strategies)


class ProductionReconstructionJobRunner:
    def __init__(
        self,
        loader: DatabaseReconstructionRequestLoader,
        session_factory: sessionmaker[Session],
        storage: LocalFileStorage,
        temporary_root: Path,
        *,
        renderer: ReconstructionRenderer | None = None,
        worker_identifier: str | None = None,
    ) -> None:
        if not temporary_root.is_absolute():
            raise ValueError("The worker temporary root must be absolute.")
        self._loader = loader
        self._session_factory = session_factory
        self._storage = storage
        self._temporary_root = temporary_root.resolve(strict=False)
        self._renderer = renderer or ReconstructionRenderer()
        self._worker_identifier = _worker_identifier(worker_identifier)

    def run(self, job_id: str) -> ReconstructionRunResult:
        existing = _completed_result(self._session_factory, job_id)
        if existing is not None:
            return existing
        loaded = self._loader.load(job_id)
        cancellation = JobCancellationService(self._session_factory, self._temporary_root)
        if cancellation.checkpoint(job_id):
            return _finish_cancelled(self._session_factory, loaded, self._worker_identifier)
        try:
            _start_attempt(self._session_factory, job_id, self._worker_identifier)
            progress = JobProgressService(self._session_factory)
            progress.update(job_id, progress=0.05, current_stage="RECONSTRUCTION_PREPARING")
            _set_reconstruction_stage(
                self._session_factory,
                loaded.reconstruction_job_id,
                ReconstructionStatus.RENDERING,
                0.1,
            )
            rendered = self._renderer.render(loaded)
            if cancellation.checkpoint(job_id):
                return _finish_cancelled(self._session_factory, loaded, self._worker_identifier)
            progress.update(job_id, progress=0.75, current_stage="RECONSTRUCTION_VALIDATING")
            _set_reconstruction_stage(
                self._session_factory,
                loaded.reconstruction_job_id,
                ReconstructionStatus.VALIDATING,
                0.75,
            )
            settings = cast(ReconstructionSettings, loaded.command.settings)
            report = validate_final_pdf(
                rendered.pdf_bytes,
                required_segments=rendered.required_segments,
                source_residue=rendered.source_residue,
                critical_warnings=(
                    loaded.critical_warnings if settings.block_export_on_critical_errors else ()
                ),
            )
            report.raise_for_completion()
            if cancellation.checkpoint(job_id):
                return _finish_cancelled(self._session_factory, loaded, self._worker_identifier)
            result = self._publish(loaded, rendered, report)
            return result
        except Exception as exc:
            _fail_job(self._session_factory, job_id, exc, self._worker_identifier)
            raise

    def _publish(
        self,
        loaded: LoadedReconstructionJob,
        rendered: ReconstructionRenderResult,
        report: FinalPdfValidationReport,
    ) -> ReconstructionRunResult:
        export_id = f"exp_{uuid4()}"
        file_id = f"fil_{uuid4()}"
        filename = f"transloka-{loaded.document_id[4:12]}-{export_id[4:12]}.pdf"
        storage_key = f"projects/{loaded.project_id}/exports/{export_id}.pdf"
        temporary = self._storage.write_temporary(BytesIO(rendered.pdf_bytes))
        committed = self._storage.commit(temporary, storage_key, immutable=True)
        page_count = report.page_count
        checksum_sha256 = report.checksum_sha256
        size_bytes = report.size_bytes
        now = _utc_now()
        settings = cast(ReconstructionSettings, loaded.command.settings)
        settings_json = json.dumps(settings.to_dict(), sort_keys=True, separators=(",", ":"))
        with transaction_scope(self._session_factory) as session:
            job = session.get(ApplicationJob, loaded.job_id)
            reconstruction = session.get(ReconstructionJob, loaded.reconstruction_job_id)
            project = session.get(Project, loaded.project_id)
            document = session.get(Document, loaded.document_id)
            if job is None or reconstruction is None or project is None or document is None:
                raise ReconstructionWorkerError(
                    "The reconstruction state disappeared before publication."
                )
            existing = session.scalar(
                select(Export).where(Export.reconstruction_job_id == reconstruction.id)
            )
            if existing is not None and existing.status in {
                ExportStatus.COMPLETED.value,
                ExportStatus.COMPLETED_WITH_WARNINGS.value,
            }:
                return _result_from_export(job, reconstruction, existing)
            session.execute(
                delete(TargetPageMapping).where(
                    TargetPageMapping.reconstruction_job_id == reconstruction.id
                )
            )
            session.execute(
                delete(ReconstructionPage).where(
                    ReconstructionPage.reconstruction_job_id == reconstruction.id
                )
            )
            StoredFilesRepository(session).create(
                file_id=file_id,
                project_id=loaded.project_id,
                document_id=loaded.document_id,
                file_role=FileRole.EXPORT,
                storage_key=committed.storage_key,
                original_filename=filename,
                safe_filename=filename,
                mime_type="application/pdf",
                size_bytes=committed.size_bytes,
                checksum_sha256=committed.checksum_sha256,
                is_immutable=True,
                status=FileStatus.VALIDATED,
                metadata={
                    "reconstruction_job_id": reconstruction.id,
                    "validation_status": "COMPLETED",
                },
                created_at=now,
            )
            version = (
                int(
                    session.scalar(
                        select(func.coalesce(func.max(Export.version_number), 0)).where(
                            Export.project_id == loaded.project_id,
                            Export.export_type == ExportType.TRANSLATED_PDF.value,
                        )
                    )
                    or 0
                )
                + 1
            )
            export = Export(
                id=export_id,
                project_id=loaded.project_id,
                document_id=loaded.document_id,
                reconstruction_job_id=reconstruction.id,
                file_id=file_id,
                export_type=(
                    ExportType.BILINGUAL_PDF.value
                    if settings.output_profile.value == "BILINGUAL"
                    else ExportType.TRANSLATED_PDF.value
                ),
                output_profile=settings.output_profile.value,
                version_number=version,
                status=ExportStatus.COMPLETED.value,
                page_count=page_count,
                size_bytes=size_bytes,
                checksum_sha256=checksum_sha256,
                validation_report_id=f"val_{uuid4()}",
                settings_json=settings_json,
                created_at=now,
                completed_at=now,
                error_code=None,
            )
            session.add(export)
            _persist_rendered_pages(session, reconstruction, loaded, rendered, now)
            reconstruction.status = ReconstructionStatus.COMPLETED.value
            reconstruction.progress = 1.0
            reconstruction.started_at = reconstruction.started_at or now
            reconstruction.completed_at = now
            reconstruction.error_code = None
            document.status = "RECONSTRUCTED"
            document.updated_at = now
            project.status = ProjectStatus.READY_FOR_EXPORT.value
            project.updated_at = now
            job.status = JobStatus.COMPLETED.value
            job.progress = 1.0
            job.current_stage = JobStatus.COMPLETED.value
            job.result_json = json.dumps(
                {
                    "schema": "transloka.reconstruction.job.v1",
                    "reconstruction_job_id": reconstruction.id,
                    "export_id": export_id,
                    "file_id": file_id,
                    "checksum_sha256": checksum_sha256,
                    "page_count": page_count,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            job.completed_at = now
            job.heartbeat_at = now
            job.error_code = None
            job.error_message = None
            _finish_attempt(
                session,
                job.id,
                JobAttemptStatus.COMPLETED,
                now,
                self._worker_identifier,
                None,
                None,
            )
            session.flush()
            return ReconstructionRunResult(
                job_id=job.id,
                reconstruction_job_id=reconstruction.id,
                status=JobStatus.COMPLETED,
                export_id=export_id,
                file_id=file_id,
                checksum_sha256=checksum_sha256,
                page_count=page_count,
            )


def _load_page(session: Session, page: DocumentPage) -> ReconstructionPageInput:
    blocks = tuple(
        session.scalars(
            select(DocumentBlock)
            .where(DocumentBlock.page_id == page.id)
            .order_by(DocumentBlock.page_reading_order, DocumentBlock.id)
        )
    )
    segments_by_block: dict[str, list[DocumentSegment]] = defaultdict(list)
    if blocks:
        for segment in session.scalars(
            select(DocumentSegment)
            .where(DocumentSegment.block_id.in_(tuple(block.id for block in blocks)))
            .order_by(DocumentSegment.segment_order, DocumentSegment.id)
        ):
            segments_by_block[segment.block_id].append(segment)
    values: list[ReconstructionBlockInput] = []
    for block in blocks:
        segments = segments_by_block.get(block.id, [])
        if any(
            segment.final_text is None or not segment.final_text.strip() for segment in segments
        ):
            raise ReconstructionWorkerError("A reconstruction segment has no final translation.")
        translated = "\n".join(cast(str, segment.final_text) for segment in segments) or None
        values.append(
            ReconstructionBlockInput(
                block_id=block.id,
                block_type=block.block_type,
                source_text="\n".join(segment.resolved_source_text for segment in segments)
                or block.source_text
                or "",
                translated_text=translated,
                source_geometry=_geometry_json(block.source_geometry_json),
                source_style=_style_json(block.style_json),
            )
        )
    return ReconstructionPageInput(
        page_id=page.id,
        source_page_number=page.source_page_number,
        width_points=page.width_points,
        height_points=page.height_points,
        page_type=page.page_type,
        column_count=page.column_count,
        blocks=tuple(values),
    )


def _geometry_json(value: str) -> Mapping[str, object]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        raise ReconstructionWorkerError("A reconstruction block geometry is invalid.") from None
    if not isinstance(parsed, dict):
        raise ReconstructionWorkerError("A reconstruction block geometry is invalid.")
    return cast(dict[str, object], parsed)


def _style_json(value: str | None) -> Mapping[str, object]:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        raise ReconstructionWorkerError("A reconstruction block style is invalid.") from None
    if not isinstance(parsed, dict):
        raise ReconstructionWorkerError("A reconstruction block style is invalid.")
    return cast(dict[str, object], parsed)


def _pdf_geometry(
    geometry: Mapping[str, object], page: ReconstructionPageInput
) -> tuple[float, float, float, float]:
    try:
        x = _finite_geometry(geometry["x"])
        y = _finite_geometry(geometry["y"])
        width = _finite_geometry(geometry["width"], positive=True)
        height = _finite_geometry(geometry["height"], positive=True)
    except KeyError:
        raise ReconstructionWorkerError("A reconstruction block geometry is incomplete.") from None
    system = geometry.get("coordinate_system", "PDF_POINT_TOP_LEFT")
    if system == "NORMALIZED_TOP_LEFT":
        x *= page.width_points
        width *= page.width_points
        y *= page.height_points
        height *= page.height_points
    elif system == "PIXEL_TOP_LEFT":
        pixel_width = _finite_geometry(geometry.get("page_width"), positive=True)
        pixel_height = _finite_geometry(geometry.get("page_height"), positive=True)
        x *= page.width_points / pixel_width
        width *= page.width_points / pixel_width
        y *= page.height_points / pixel_height
        height *= page.height_points / pixel_height
    elif system not in {"PDF_POINT_TOP_LEFT", "PDF_POINT_BOTTOM_LEFT"}:
        raise ReconstructionWorkerError("A reconstruction coordinate system is unsupported.")
    if system != "PDF_POINT_BOTTOM_LEFT":
        y = page.height_points - y - height
    if (
        x < 0
        or y < 0
        or x + width > page.width_points + 0.1
        or y + height > page.height_points + 0.1
    ):
        raise ReconstructionWorkerError("A reconstruction block geometry is outside its page.")
    return x, y, width, height


def _finite_geometry(value: object, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReconstructionWorkerError("A reconstruction block geometry is invalid.")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ReconstructionWorkerError("A reconstruction block geometry is invalid.")
    return result


def _font_size(
    style: Mapping[str, object] | None,
    geometry: Mapping[str, object],
    height: float,
) -> float:
    value = (style or {}).get(
        "font_size",
        geometry.get("font_size_pt", min(12.0, max(6.0, height * 0.65))),
    )
    size = _finite_geometry(value, positive=True)
    return min(size, max(6.0, height))


def _font_name(style: Mapping[str, object] | None) -> str:
    values = style or {}
    value = values.get("font_name", values.get("font_postscript_name", values.get("font_family")))
    if not isinstance(value, str) or not value.strip():
        return "Helvetica"
    name = value.strip().removeprefix("/").split("+", 1)[-1]
    standard_fonts = {
        "Courier",
        "Courier-Bold",
        "Courier-Oblique",
        "Courier-BoldOblique",
        "Helvetica",
        "Helvetica-Bold",
        "Helvetica-Oblique",
        "Helvetica-BoldOblique",
        "Times-Roman",
        "Times-Bold",
        "Times-Italic",
        "Times-BoldItalic",
        "Symbol",
        "ZapfDingbats",
    }
    if name in standard_fonts:
        return name

    lowered = name.casefold()
    bold = (
        values.get("bold") is True
        or values.get("font_weight") in (600, 700, 800, 900)
        or any(marker in lowered for marker in ("bold", "semibold", "demi"))
    )
    italic = values.get("italic") is True or any(
        marker in lowered for marker in ("italic", "oblique")
    )
    if any(marker in lowered for marker in ("courier", "mono", "consol")):
        return (
            "Courier-BoldOblique"
            if bold and italic
            else ("Courier-Bold" if bold else "Courier-Oblique" if italic else "Courier")
        )
    if any(marker in lowered for marker in ("times", "serif", "georgia", "garamond")):
        return (
            "Times-BoldItalic"
            if bold and italic
            else ("Times-Bold" if bold else "Times-Italic" if italic else "Times-Roman")
        )
    return (
        "Helvetica-BoldOblique"
        if bold and italic
        else ("Helvetica-Bold" if bold else "Helvetica-Oblique" if italic else "Helvetica")
    )


def _text_box(
    block: ReconstructionBlockInput,
    page: ReconstructionPageInput,
    x: float,
    width: float,
) -> tuple[float, float, TextAlignment]:
    if page.column_count == 1 and block.block_type in {
        "DOCUMENT_TITLE",
        "SUBTITLE",
        "HEADING_1",
        "HEADING_2",
        "HEADING_3",
    }:
        width = max(width, page.width_points - (2 * x))
    if block.block_type == "PAGE_NUMBER" and x > page.width_points / 2:
        right = x + width
        x = page.width_points / 2
        width = right - x
        return x, width, TextAlignment.RIGHT
    return x, width, TextAlignment.LEFT


def _leading(block: ReconstructionBlockInput, font_size: float, height: float) -> float:
    source_lines = tuple(line for line in block.source_text.splitlines() if line.strip())
    if len(source_lines) > 1:
        leading = (height - font_size) / (len(source_lines) - 1)
        if math.isfinite(leading) and leading > 0:
            return leading
    return min(font_size * 1.2, height)


def _reflow_kind(block_type: str) -> ReflowBlockKind:
    if block_type == "DOCUMENT_TITLE":
        return ReflowBlockKind.TITLE
    if block_type == "SUBTITLE":
        return ReflowBlockKind.SUBTITLE
    if block_type.startswith("HEADING_"):
        return ReflowBlockKind.HEADING
    if block_type == "BLOCKQUOTE":
        return ReflowBlockKind.BLOCKQUOTE
    if block_type == "CODE_BLOCK":
        return ReflowBlockKind.CODE
    if block_type == "CAPTION":
        return ReflowBlockKind.CAPTION
    return ReflowBlockKind.PARAGRAPH


def _heading_level(block_type: str) -> int:
    if block_type.startswith("HEADING_") and block_type[-1:].isdigit():
        return int(block_type[-1])
    return 1


def _append_pdf(writer: PdfWriter, pdf: bytes) -> int:
    reader = PdfReader(BytesIO(pdf), strict=False)
    if not reader.pages:
        raise ReconstructionWorkerError("A reconstructed page PDF is empty.")
    for page in reader.pages:
        writer.add_page(page)
    return len(reader.pages)


def _sha256(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _persist_rendered_pages(
    session: Session,
    reconstruction: ReconstructionJob,
    loaded: LoadedReconstructionJob,
    rendered: ReconstructionRenderResult,
    now: str,
) -> None:
    inputs = {page.page_id: page for page in loaded.pages}
    for page in rendered.pages:
        source = inputs[page.source_page_id]
        reconstruction_page_id = f"rcp_{uuid4()}"
        session.add(
            ReconstructionPage(
                id=reconstruction_page_id,
                reconstruction_job_id=reconstruction.id,
                source_page_id=page.source_page_id,
                target_page_start=page.target_page_start,
                target_page_end=page.target_page_end,
                strategy=page.strategy,
                status=ReconstructionStatus.COMPLETED.value,
                output_file_id=None,
                page_hash=page.page_hash,
                warning_count=0,
                metadata_json=json.dumps(
                    {"source_page_number": page.source_page_number},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        strategies = dict(page.block_strategies)
        font_mappings = dict(page.font_mappings)
        for block in source.blocks:
            strategy = strategies.get(block.block_id, "PRESERVE")
            session.add(
                ReconstructionBlock(
                    id=f"rcb_{uuid4()}",
                    reconstruction_page_id=reconstruction_page_id,
                    block_id=block.block_id,
                    strategy=strategy,
                    fit_strategy=None,
                    source_geometry_json=json.dumps(
                        block.source_geometry, sort_keys=True, separators=(",", ":")
                    ),
                    target_geometry_json=None,
                    status=(
                        ReconstructionBlockStatus.PRESERVED.value
                        if strategy == "PRESERVE"
                        else ReconstructionBlockStatus.REFLOWED.value
                        if strategy == "REFLOW"
                        else ReconstructionBlockStatus.PLACED.value
                    ),
                    font_mapping_json=(
                        json.dumps(
                            font_mappings[block.block_id], sort_keys=True, separators=(",", ":")
                        )
                        if block.block_id in font_mappings
                        else None
                    ),
                    overflow_json=None,
                    collision_json=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        page_count = page.target_page_end - page.target_page_start + 1
        mapping_type = (
            TargetPageMappingType.ONE_TO_ONE
            if page_count == 1
            else TargetPageMappingType.ONE_TO_MANY
        )
        for mapping_order, target_page_number in enumerate(
            range(page.target_page_start, page.target_page_end + 1)
        ):
            session.add(
                TargetPageMapping(
                    id=f"tpm_{uuid4()}",
                    reconstruction_job_id=reconstruction.id,
                    source_page_id=page.source_page_id,
                    target_page_number=target_page_number,
                    mapping_type=mapping_type.value,
                    mapping_order=mapping_order,
                    created_at=now,
                )
            )


def _completed_result(
    session_factory: sessionmaker[Session], job_id: str
) -> ReconstructionRunResult | None:
    with session_factory() as session:
        job = session.get(ApplicationJob, job_id)
        if job is None or job.status not in {
            JobStatus.COMPLETED.value,
            JobStatus.COMPLETED_WITH_WARNINGS.value,
        }:
            return None
        reconstruction = session.scalar(
            select(ReconstructionJob).where(ReconstructionJob.application_job_id == job.id)
        )
        if reconstruction is None:
            raise ReconstructionWorkerError("The completed reconstruction state is unavailable.")
        export = session.scalar(
            select(Export).where(Export.reconstruction_job_id == reconstruction.id)
        )
        if export is None or export.status not in {
            ExportStatus.COMPLETED.value,
            ExportStatus.COMPLETED_WITH_WARNINGS.value,
        }:
            raise ReconstructionWorkerError("The completed reconstruction export is unavailable.")
        return _result_from_export(job, reconstruction, export)


def _result_from_export(
    job: ApplicationJob, reconstruction: ReconstructionJob, export: Export
) -> ReconstructionRunResult:
    return ReconstructionRunResult(
        job_id=job.id,
        reconstruction_job_id=reconstruction.id,
        status=JobStatus(job.status),
        export_id=export.id,
        file_id=export.file_id,
        checksum_sha256=export.checksum_sha256,
        page_count=export.page_count or 0,
    )


def _set_reconstruction_stage(
    session_factory: sessionmaker[Session],
    reconstruction_job_id: str,
    status: ReconstructionStatus,
    progress: float,
) -> None:
    now = _utc_now()
    with transaction_scope(session_factory) as session:
        row = session.get(ReconstructionJob, reconstruction_job_id)
        if row is None:
            raise ReconstructionWorkerError("The reconstruction job disappeared.")
        row.status = status.value
        row.progress = progress
        row.started_at = row.started_at or now


def _start_attempt(
    session_factory: sessionmaker[Session], job_id: str, worker_identifier: str
) -> None:
    now = _utc_now()
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, job_id)
        if job is None or job.status not in {
            JobStatus.QUEUED.value,
            JobStatus.RETRYING.value,
            JobStatus.RUNNING.value,
        }:
            raise ReconstructionWorkerError("The reconstruction job is not executable.")
        attempts = list(
            session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id == job.id)
                .order_by(JobAttempt.attempt_number)
            )
        )
        if attempts and attempts[-1].status == JobAttemptStatus.RUNNING.value:
            attempts[-1].worker_identifier = worker_identifier
            return
        session.add(
            JobAttempt(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"transloka:reconstruction-attempt:{job.id}:{len(attempts) + 1}",
                    )
                ),
                job_id=job.id,
                attempt_number=len(attempts) + 1,
                status=JobAttemptStatus.RUNNING.value,
                worker_identifier=worker_identifier,
                started_at=now,
                completed_at=None,
                duration_ms=None,
                error_code=None,
                error_message=None,
                details_json=None,
            )
        )


def _finish_attempt(
    session: Session,
    job_id: str,
    status: JobAttemptStatus,
    now: str,
    worker_identifier: str,
    error_code: str | None,
    error_message: str | None,
) -> None:
    attempt = session.scalar(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is None:
        return
    attempt.status = status.value
    attempt.worker_identifier = worker_identifier
    attempt.completed_at = now
    attempt.error_code = error_code
    attempt.error_message = error_message


def _finish_cancelled(
    session_factory: sessionmaker[Session],
    loaded: LoadedReconstructionJob,
    worker_identifier: str,
) -> ReconstructionRunResult:
    now = _utc_now()
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, loaded.job_id)
        reconstruction = session.get(ReconstructionJob, loaded.reconstruction_job_id)
        if job is None or reconstruction is None:
            raise ReconstructionWorkerError("The cancelled reconstruction state is unavailable.")
        job.status = JobStatus.CANCELLED.value
        job.current_stage = JobStatus.CANCELLED.value
        job.completed_at = job.completed_at or now
        job.cancelled_at = job.cancelled_at or now
        reconstruction.status = ReconstructionStatus.CANCELLED.value
        reconstruction.completed_at = now
        _finish_attempt(
            session,
            job.id,
            JobAttemptStatus.CANCELLED,
            now,
            worker_identifier,
            None,
            None,
        )
        return ReconstructionRunResult(
            job_id=job.id,
            reconstruction_job_id=reconstruction.id,
            status=JobStatus.CANCELLED,
            export_id=None,
            file_id=None,
            checksum_sha256=None,
            page_count=0,
        )


def _fail_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    error: Exception,
    worker_identifier: str,
) -> None:
    now = _utc_now()
    error_code = type(error).__name__.upper()[:100]
    error_message = str(error).strip()
    if not error_message or not error_message.isprintable() or len(error_message) > 500:
        error_message = "Reconstruction job failed."
    try:
        with transaction_scope(session_factory) as session:
            job = session.get(ApplicationJob, job_id)
            if job is None or job.status not in {
                JobStatus.QUEUED.value,
                JobStatus.RETRYING.value,
                JobStatus.RUNNING.value,
                JobStatus.CANCELLATION_REQUESTED.value,
            }:
                return
            reconstruction = session.scalar(
                select(ReconstructionJob).where(ReconstructionJob.application_job_id == job.id)
            )
            job.status = JobStatus.FAILED.value
            job.current_stage = JobStatus.FAILED.value
            job.error_code = error_code
            job.error_message = error_message
            job.completed_at = now
            job.heartbeat_at = now
            if reconstruction is not None:
                reconstruction.status = ReconstructionStatus.FAILED.value
                reconstruction.error_code = error_code
                reconstruction.completed_at = now
            _finish_attempt(
                session,
                job.id,
                JobAttemptStatus.FAILED,
                now,
                worker_identifier,
                error_code,
                error_message,
            )
    except Exception:
        return


def _worker_identifier(value: str | None) -> str:
    if value is None:
        return "transloka-reconstruction-worker"
    if not value or value != value.strip() or not value.isprintable() or len(value) > 200:
        raise ValueError("The worker identifier is invalid.")
    return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _decode_command(value: str) -> dict[str, object]:
    if not isinstance(value, str):
        raise ReconstructionWorkerError("The reconstruction command payload is invalid.")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ReconstructionWorkerError(
                    "The reconstruction command contains a duplicated field."
                )
            result[key] = item
        return result

    try:
        payload = json.loads(value, object_pairs_hook=object_pairs)
    except ReconstructionWorkerError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError):
        raise ReconstructionWorkerError("The reconstruction command payload is invalid.") from None
    if not isinstance(payload, dict):
        raise ReconstructionWorkerError("The reconstruction command payload is invalid.")
    return cast(dict[str, object], payload)


def _string_value(payload: Mapping[str, object], key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise TypeError
    return value


def _page_id_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError
    if any(type(item) is not str for item in value):
        raise TypeError
    return tuple(cast(Sequence[str], value))


def _validate_page_ids(values: tuple[str, ...]) -> None:
    if type(values) is not tuple:
        raise ReconstructionWorkerError("The reconstruction page identifiers are invalid.")
    for value in values:
        _validate_identifier(value, "pag_")
    if len(set(values)) != len(values):
        raise ReconstructionWorkerError(
            "The reconstruction command contains duplicate page identifiers."
        )


def _validate_identifier(value: str, prefix: str) -> None:
    if type(value) is not str or not value.startswith(prefix):
        raise ReconstructionWorkerError("A reconstruction command identifier is invalid.")
    try:
        parsed = UUID(value[len(prefix) :])
    except (ValueError, AttributeError):
        raise ReconstructionWorkerError("A reconstruction command identifier is invalid.") from None
    if str(parsed) != value[len(prefix) :]:
        raise ReconstructionWorkerError("A reconstruction command identifier is invalid.")


__all__ = [
    "RECONSTRUCTION_COMMAND_SCHEMA",
    "ReconstructionCommand",
    "ReconstructionWorkerError",
]
