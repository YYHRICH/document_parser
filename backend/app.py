"""FastAPI delivery layer for document parsing.

The API is intentionally thin: routing, normalization and quality remain independently
callable libraries. This module only creates durable jobs and asks the composition root
to run them.
"""

from __future__ import annotations

import io
import json
from contextlib import asynccontextmanager
import mimetypes
import os
import sys
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..core.contracts import ParseRequest, QualityPackage
from ..composition.gateway import DocumentParserGateway
from ..orchestration import (
    InProcessTaskQueue,
    JobConflictError,
    ParseFailureKind,
    ParseJob,
    ParseJobOrchestrator,
    ParseJobStatus,
    collect_job_metrics,
)
from ..composition.reparse_recommendations import (
    recommend_reparse_for_job,
    reparse_signals_for_job,
)
from .schemas import (
    ParseJobCancelResponse,
    ParseJobComparisonResponse,
    ParseJobEventsResponse,
    ParseJobLineageResponse,
    ParseJobReparseRecommendationsResponse,
    ParseJobResponse,
    ParseJobStatusResponse,
    ParseRecordResponse,
    ParserListResponse,
    ParserSelectionPolicy,
    QualityPackageResponse,
    ReparseRequest,
    public_parse_job,
    public_parse_job_events,
)
from .lineage import (
    DifferentSourceIdentityError,
    build_lineage_snapshot,
    build_same_source_comparison,
    resolve_lineage,
    same_source_identity,
    summarize_document_structure,
)
from .reparse_recommendations import (
    cloud_denied_reparse_policy,
    public_reparse_recommendations,
)
from .delivery import QUALITY_DELIVERY_ARTIFACTS, delivery_eligibility
from .storage import ApiStorage, SourceIntegrityError
from .task_endpoints import build_task_router

try:
    from quality import run_quality
except ModuleNotFoundError:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from quality import run_quality


_DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_DEFAULT_MAX_ARCHIVE_BYTES = 250 * 1024 * 1024
_DEFAULT_MAX_TASK_FILES = 20
_FORBIDDEN_PUBLIC_OPTION_KEYS = {
    "native_output_dir",
    "mineru_api_base_url",
    "mineru_api_token",
    "mineru_server_url",
    "mineru_trusted_hosts",
    "trusted_hosts",
    "api_token",
    "authorization",
    "api_base_url",
    "server_url",
    "bearer_token",
}

_JOB_CREATION_CONFLICT_DETAIL = "The parse job request conflicts with an existing request."
_JOB_METADATA_INVALID_DETAIL = "Parse job metadata is invalid."
_PARSE_RESULT_VERIFICATION_DETAIL = "Parse result cannot be verified."
_QUALITY_PACKAGE_VERIFICATION_DETAIL = "Quality package cannot be verified."
_PUBLISHED_PACKAGE_VERIFICATION_DETAIL = "Published parse package cannot be verified."
_RETRY_SOURCE_VERIFICATION_DETAIL = "The stored source cannot be verified for retry."
_REPARSE_SOURCE_VERIFICATION_DETAIL = "The stored source cannot be verified for reparse."
_RETRY_REJECTION_DETAILS = {
    "Only failed jobs can be retried.": "Only failed jobs can be retried.",
    "Jobs that failed due to policy cannot be retried.": (
        "Jobs that failed due to policy cannot be retried."
    ),
    "Jobs that failed due to unsupported cannot be retried.": (
        "Jobs that failed due to unsupported cannot be retried."
    ),
    "Jobs that failed due to integrity cannot be retried.": (
        "Jobs that failed due to integrity cannot be retried."
    ),
    "This failed job is not retryable.": "This failed job is not retryable.",
}


def create_app(
    *,
    storage_root: Path | str = Path("outputs/api"),
    gateway: DocumentParserGateway | None = None,
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES,
    max_archive_uncompressed_bytes: int = _DEFAULT_MAX_ARCHIVE_BYTES,
    max_task_files: int = _DEFAULT_MAX_TASK_FILES,
    job_workers: int = 2,
    allow_quality_package_override: bool = False,
) -> FastAPI:
    """Create an API app with a durable filesystem job store and replaceable queue.

    ``/api/parses`` remains a synchronous compatibility endpoint. New clients should
    use ``/api/jobs`` and poll the job state; this prevents a long parser run from
    occupying an HTTP request worker.
    """
    if (
        max_upload_bytes <= 0
        or max_archive_uncompressed_bytes <= 0
        or max_task_files <= 0
        or job_workers <= 0
    ):
        raise ValueError("Upload, archive, task-file and worker limits must be positive.")

    parser_gateway = gateway or DocumentParserGateway.from_environment()
    storage = ApiStorage(storage_root)
    orchestrator = ParseJobOrchestrator(
        gateway=parser_gateway,
        repository=storage,
        quality_runner=run_quality,
    )
    task_queue = InProcessTaskQueue(orchestrator.run, max_workers=job_workers)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # A queued job was never claimed and can safely resume. A job observed
        # mid-stage belongs to a stopped process, so record an explicit retryable
        # interruption instead of replaying an unknown partial parser attempt.
        try:
            for job in storage.iter_recoverable_jobs():
                if job.status == ParseJobStatus.QUEUED:
                    task_queue.submit(job.parse_id)
                    continue
                if (
                    job.status == ParseJobStatus.QUALITY_CHECKING
                    and storage.package_root(job.parse_id).is_dir()
                ):
                    try:
                        document = storage.load_document(job.parse_id)
                        quality_package = storage.load_quality_package(job.parse_id)
                        quality_state = quality_package.quality_report.state
                        # A recovered, manifest-verified package is a completed
                        # result. Its quality state remains attached as downstream
                        # guidance and is not a workflow or delivery gate.
                        terminal = ParseJobStatus.SUCCEEDED
                        storage.save_job(
                            job.transition(
                                terminal,
                                document_id=document.document_id,
                                quality_run_id=job.quality_run_id,
                                quality_state=quality_state.value,
                                package_path=str(storage.package_root(job.parse_id).resolve()),
                                error=None,
                                error_reference=None,
                                failure_kind=None,
                                retryable=False,
                                message=(
                                    "Recovered a fully published document revision after restart."
                                ),
                            )
                        )
                        continue
                    except (FileNotFoundError, ValueError, JobConflictError):
                        pass
                try:
                    storage.save_job(
                        job.transition(
                            ParseJobStatus.FAILED,
                            error=(
                                "A previous worker stopped before this job completed; retry is safe."
                            ),
                            error_reference="worker-interrupted",
                            failure_kind=ParseFailureKind.TRANSIENT,
                            retryable=True,
                            message=(
                                "Interrupted in-progress job was marked retryable during recovery."
                            ),
                        )
                    )
                except JobConflictError:
                    continue
            yield
        finally:
            task_queue.shutdown(wait=False)

    app = FastAPI(title="Document Parser API", version="0.2.0", lifespan=lifespan)
    cors_origins = _configured_frontend_origins()
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )
    app.state.storage = storage
    app.state.orchestrator = orchestrator
    app.state.task_queue = task_queue
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/parsers", response_model=ParserListResponse)
    def list_parsers() -> ParserListResponse:
        return ParserListResponse(
            parsers=parser_gateway.list_parsers(),
            selection_policy=ParserSelectionPolicy(
                cloud_parsers_enabled=bool(
                    getattr(parser_gateway, "cloud_parsers_enabled", False)
                ),
            ),
        )

    async def create_job_from_upload(
        *,
        file: UploadFile,
        parser_id: str | None,
        options_json: str | None,
        idempotency_key: str | None,
        parent_parse_id: str | None = None,
    ):
        content = await _read_upload_limited(file, max_upload_bytes=max_upload_bytes)
        filename = file.filename or "upload.bin"
        file_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        _validate_upload_metadata(filename=filename, file_type=file_type)
        _validate_archive_budget(content, max_uncompressed_bytes=max_archive_uncompressed_bytes)
        options = _parse_options(options_json)
        try:
            return storage.create_job(
                parse_id=storage.new_parse_id(),
                source_filename=filename,
                source_file_type=file_type,
                source_content=content,
                requested_parser_id=parser_id or None,
                options=options,
                parent_parse_id=parent_parse_id,
                idempotency_key=_validate_idempotency_key(idempotency_key),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_JOB_CREATION_CONFLICT_DETAIL,
            ) from error

    app.include_router(
        build_task_router(
            storage=storage,
            task_queue=task_queue,
            create_job_from_upload=create_job_from_upload,
            validate_options=_validate_public_options,
            validate_idempotency_key=_validate_idempotency_key,
            max_task_files=max_task_files,
        )
    )

    def status_response(job) -> ParseJobStatusResponse:
        return ParseJobStatusResponse(
            parse_id=job.parse_id,
            status=job.status.value,
            job=public_parse_job(job),
            status_url=f"/api/jobs/{job.parse_id}",
        )

    @app.get("/api/metrics")
    def get_platform_metrics() -> dict[str, object]:
        """Read-only operational summary; authorization can be added at the delivery edge."""
        return collect_job_metrics(storage.iter_jobs())

    @app.post(
        "/api/jobs",
        response_model=ParseJobStatusResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_parse_job(
        file: Annotated[UploadFile, File()],
        parser_id: Annotated[str | None, Form()] = None,
        options_json: Annotated[str | None, Form()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ParseJobStatusResponse:
        job = await create_job_from_upload(
            file=file,
            parser_id=parser_id,
            options_json=options_json,
            idempotency_key=idempotency_key,
        )
        if not job.status.terminal:
            task_queue.submit(job.parse_id)
        return status_response(job)

    @app.post(
        "/api/jobs/{parse_id}/retry",
        response_model=ParseJobStatusResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def retry_parse_job(
        parse_id: str,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ParseJobStatusResponse:
        """Create one retry child for a retryable terminal failure."""

        try:
            result = storage.create_retry_job(
                parent_parse_id=parse_id,
                idempotency_key=_validate_idempotency_key(idempotency_key),
            )
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_public_retry_rejection_detail(error),
            ) from error
        except JobConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Retry creation conflicted; repeat the request with the same Idempotency-Key.",
            ) from error

        if result.created and not result.job.status.terminal:
            task_queue.submit(result.job.parse_id)
        return status_response(result.job)

    @app.get("/api/jobs/compare", response_model=ParseJobComparisonResponse)
    def compare_parse_jobs(
        left: str,
        right: str,
    ) -> ParseJobComparisonResponse:
        """Compare safe execution metadata for exactly one immutable input source."""

        try:
            left_job = storage.load_job(left)
            right_job = storage.load_job(right)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=_JOB_METADATA_INVALID_DETAIL) from error
        if not same_source_identity(left_job, right_job):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Jobs do not belong to the same immutable source identity.",
            )

        structural_counts = _safe_structural_counts_for_jobs(
            storage,
            (left_job, right_job),
        )
        try:
            payload = build_same_source_comparison(
                left_job,
                right_job,
                structural_counts_by_parse_id=structural_counts,
            )
        except DifferentSourceIdentityError as error:
            # The immutable fields above cannot normally change, but retain a safe
            # guard should a repository implementation race or violate its contract.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Jobs do not belong to the same immutable source identity.",
            ) from error
        return ParseJobComparisonResponse.model_validate(payload)

    @app.get("/api/jobs/{parse_id}/lineage", response_model=ParseJobLineageResponse)
    def get_parse_job_lineage(parse_id: str) -> ParseJobLineageResponse:
        """Return root-to-target ancestry as a content-free control-plane view."""

        try:
            target = storage.load_job(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=_JOB_METADATA_INVALID_DETAIL) from error

        resolution = resolve_lineage(target, storage.load_job)
        structural_counts = _safe_structural_counts_for_jobs(storage, resolution.jobs)
        payload = build_lineage_snapshot(
            target,
            resolution.jobs,
            structural_counts_by_parse_id=structural_counts,
            lineage_complete=resolution.complete,
            lineage_integrity=resolution.integrity,
        )
        return ParseJobLineageResponse.model_validate(payload)

    @app.get(
        "/api/jobs/{parse_id}/reparse-recommendations",
        response_model=ParseJobReparseRecommendationsResponse,
    )
    def get_parse_job_reparse_recommendations(
        parse_id: str,
    ) -> ParseJobReparseRecommendationsResponse:
        """Return deterministic, content-free reparse advice for one job."""

        try:
            job = storage.load_job(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="Parse job metadata is invalid.",
            ) from error

        # No signal means no capability lookup or policy decision is needed.  The
        # explicit null response keeps this distinct from an evaluated-but-blocked
        # candidate set.
        if not reparse_signals_for_job(job):
            return ParseJobReparseRecommendationsResponse(parse_id=job.parse_id)

        try:
            recommendations = recommend_reparse_for_job(
                job,
                parser_gateway.list_parsers(),
                # This endpoint receives neither Principal nor CloudExecutionGrant.
                # Do not read job.options.allow_cloud or deployment allow_cloud here:
                # absent an explicit identity grant, effective policy is cloud-deny.
                policy=cloud_denied_reparse_policy(),
            )
            public_recommendations = public_reparse_recommendations(recommendations)
        except Exception as error:
            # Capability snapshots, adapter validation, and response projection are
            # internal details; no raw implementation failure, option value, or
            # filesystem context may be sent to a client from this read-only route.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Reparse recommendations are temporarily unavailable.",
            ) from error

        return ParseJobReparseRecommendationsResponse(
            parse_id=job.parse_id,
            recommendations=public_recommendations,
        )

    @app.get("/api/jobs/{parse_id}", response_model=ParseJobStatusResponse)
    def get_parse_job(parse_id: str) -> ParseJobStatusResponse:
        try:
            return status_response(storage.load_job(parse_id))
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=_JOB_METADATA_INVALID_DETAIL) from error

    @app.get(
        "/api/jobs/{parse_id}/events",
        response_model=ParseJobEventsResponse,
    )
    def get_parse_job_events(parse_id: str) -> ParseJobEventsResponse:
        try:
            job = storage.load_job(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=_JOB_METADATA_INVALID_DETAIL) from error
        return public_parse_job_events(job)

    @app.delete("/api/jobs/{parse_id}", response_model=ParseJobCancelResponse)
    def cancel_parse_job(parse_id: str) -> ParseJobCancelResponse:
        try:
            job = storage.load_job(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=_JOB_METADATA_INVALID_DETAIL) from error
        if job.status.terminal:
            return ParseJobCancelResponse(
                parse_id=parse_id,
                status=job.status.value,
                job=public_parse_job(job),
            )
        if job.status not in {ParseJobStatus.QUEUED, ParseJobStatus.PREFLIGHT}:
            raise HTTPException(status_code=409, detail="Job is already executing and cannot be force-cancelled.")
        try:
            job = storage.save_job(
                job.transition(
                    ParseJobStatus.CANCELLED,
                    error="Cancelled by client before parsing started.",
                    error_reference="client-cancelled",
                    failure_kind=ParseFailureKind.CANCELLED,
                    retryable=False,
                    message="Client cancelled the job before parser execution.",
                )
            )
        except JobConflictError:
            latest = storage.load_job(parse_id)
            if latest.status.terminal:
                return ParseJobCancelResponse(
                    parse_id=parse_id,
                    status=latest.status.value,
                    job=public_parse_job(latest),
                )
            raise HTTPException(status_code=409, detail="Job state changed while cancellation was requested.")
        return ParseJobCancelResponse(
            parse_id=parse_id,
            status=job.status.value,
            job=public_parse_job(job),
        )

    @app.post("/api/parses", response_model=ParseJobResponse)
    async def create_parse_legacy(
        file: Annotated[UploadFile, File()],
        parser_id: Annotated[str | None, Form()] = None,
        options_json: Annotated[str | None, Form()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ParseJobResponse:
        """Compatibility endpoint. Prefer ``POST /api/jobs`` for non-blocking clients."""
        job = await create_job_from_upload(
            file=file,
            parser_id=parser_id,
            options_json=options_json,
            idempotency_key=idempotency_key,
        )
        completed = orchestrator.run(job.parse_id)
        if completed.status != ParseJobStatus.SUCCEEDED:
            _raise_for_failed_job(completed)
        document = storage.load_document(completed.parse_id)
        return ParseJobResponse(
            parse_id=completed.parse_id,
            document=document,
            native_artifact_count=len(document.native_artifacts),
        )

    @app.get("/api/parses/{parse_id}", response_model=ParseRecordResponse)
    def get_parse(parse_id: str) -> ParseRecordResponse:
        try:
            document = storage.load_document(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse result not found.") from error
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_PARSE_RESULT_VERIFICATION_DETAIL,
            ) from error
        return ParseRecordResponse(
            parse_id=parse_id,
            document=document,
        )

    @app.get("/api/parses/{parse_id}/quality-package", response_model=QualityPackageResponse)
    def get_quality_package(parse_id: str) -> QualityPackageResponse:
        try:
            quality_package = storage.load_quality_package(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Quality package not found.") from error
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_QUALITY_PACKAGE_VERIFICATION_DETAIL,
            ) from error
        return QualityPackageResponse(
            parse_id=parse_id,
            quality_package=quality_package,
        )

    @app.post("/api/parses/{parse_id}/quality-package", response_model=QualityPackageResponse)
    def set_quality_package(parse_id: str, body: QualityPackage) -> QualityPackageResponse:
        """Trusted migration hook; disabled by default to prevent client-forged quality. """
        if not allow_quality_package_override:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="External quality-package replacement is disabled. Run quality through a ParseJob.",
            )
        try:
            document = storage.load_document(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_PARSE_RESULT_VERIFICATION_DETAIL,
            ) from error
        if body.document_id != document.document_id:
            raise HTTPException(
                status_code=400,
                detail="Quality package document_id does not match the stored parse.",
            )
        storage.write_quality_package(parse_id, body)
        return QualityPackageResponse(
            parse_id=parse_id,
            quality_package=storage.load_quality_package(parse_id),
        )

    @app.get("/api/parses/{parse_id}/artifacts")
    def list_artifacts(parse_id: str) -> dict[str, object]:
        try:
            files = storage.list_package_files(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_PUBLISHED_PACKAGE_VERIFICATION_DETAIL,
            ) from error
        return {"parse_id": parse_id, "files": files}

    @app.get("/api/parses/{parse_id}/download")
    def download_package(parse_id: str) -> FileResponse:
        package_root = storage.package_root(parse_id)
        if not package_root.is_dir():
            raise HTTPException(status_code=404, detail="Parse job not found.")
        try:
            # Only the immutable manifest whitelist is eligible for download.
            # The manifest itself is included as package metadata after it has
            # already been verified against every registered artifact.
            registered_files = storage.registered_package_files(parse_id)
            manifest_path = package_root / "artifact_manifest.json"
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_PUBLISHED_PACKAGE_VERIFICATION_DETAIL,
            ) from error
        archive_fd, archive_name = tempfile.mkstemp(
            prefix=f"document-package-{parse_id}-", suffix=".zip"
        )
        os.close(archive_fd)
        archive_path = Path(archive_name)
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_path in registered_files:
                    archive.write(file_path, file_path.relative_to(package_root).as_posix())
                if manifest_path.is_file():
                    archive.write(manifest_path, "artifact_manifest.json")
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=f"document-package-{parse_id}.zip",
            background=BackgroundTask(_remove_temp_file, archive_path),
        )

    @app.get("/api/parses/{parse_id}/delivery")
    def download_business_delivery(parse_id: str) -> FileResponse:
        """Return the quality-approved business package without diagnostic artifacts."""
        try:
            quality_package, delivery_files = storage.read_quality_delivery_snapshot(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Quality package not found.") from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Business delivery cannot be verified.",
            ) from error

        eligibility = delivery_eligibility(quality_package.quality_report.state)
        if not eligibility.allowed:
            raise HTTPException(
                status_code=eligibility.status_code or status.HTTP_409_CONFLICT,
                detail=eligibility.detail or "Business delivery is unavailable.",
            )

        archive_fd, archive_name = tempfile.mkstemp(
            prefix=f"quality-delivery-{parse_id}-", suffix=".zip"
        )
        os.close(archive_fd)
        archive_path = Path(archive_name)
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for relative_path in QUALITY_DELIVERY_ARTIFACTS:
                    archive.writestr(relative_path, delivery_files[relative_path])
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=f"quality-delivery-{parse_id}.zip",
            background=BackgroundTask(_remove_temp_file, archive_path),
        )

    @app.get("/api/parses/{parse_id}/artifacts/{artifact_path:path}")
    def get_artifact(parse_id: str, artifact_path: str) -> FileResponse:
        try:
            path = storage.resolve_package_file(parse_id, artifact_path)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Artifact not found.") from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_PUBLISHED_PACKAGE_VERIFICATION_DETAIL,
            ) from error
        return FileResponse(path, media_type=storage.content_type_for(path))

    @app.post(
        "/api/parses/{parse_id}/reparse",
        response_model=ParseJobStatusResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def reparse(
        parse_id: str,
        body: ReparseRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ParseJobStatusResponse:
        """Create an idempotent asynchronous child job from the durable source."""

        options = _validate_public_options(dict(body.options))
        try:
            result = storage.create_reparse_job(
                parent_parse_id=parse_id,
                requested_parser_id=body.parser_id,
                options=options,
                idempotency_key=_validate_idempotency_key(idempotency_key),
            )
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Original source file not found.") from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_public_reparse_rejection_detail(error),
            ) from error
        except JobConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reparse creation conflicted; repeat the request with the same Idempotency-Key.",
            ) from error

        if result.created and not result.job.status.terminal:
            task_queue.submit(result.job.parse_id)
        return status_response(result.job)

    return app


def _safe_structural_counts_for_jobs(
    storage: ApiStorage,
    jobs: Iterable[ParseJob],
) -> dict[str, dict[str, object]]:
    """Best-effort structure reads for a read-only view.

    Packages are verified by ``ApiStorage.load_document`` before their counts are
    projected.  A missing or tampered package simply has no counts; this endpoint
    must not reveal filesystem paths or partial parser content in an error.
    """

    summaries: dict[str, dict[str, object]] = {}
    for job in jobs:
        if job.document_id is None:
            continue
        try:
            document = storage.load_document(job.parse_id)
            summaries[job.parse_id] = summarize_document_structure(document)
        except Exception:
            # This is intentionally best effort: validation/integrity failures stay
            # hidden here and are available through their existing diagnostic paths.
            continue
    return summaries


async def _read_upload_limited(file: UploadFile, *, max_upload_bytes: int) -> bytes:
    content = await file.read(max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Uploaded file exceeds the configured size limit.")
    return content


def _validate_upload_metadata(*, filename: str, file_type: str) -> None:
    extension = Path(filename).suffix.lower()
    if not extension:
        return
    allowed = {
        ".pdf": {"application/pdf"},
        ".md": {"text/markdown", "text/plain", "application/octet-stream"},
        ".txt": {"text/plain", "application/octet-stream"},
        ".png": {"image/png", "application/octet-stream"},
        ".jpg": {"image/jpeg", "application/octet-stream"},
        ".jpeg": {"image/jpeg", "application/octet-stream"},
    }
    expected = allowed.get(extension)
    if expected is not None and file_type not in expected:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_type!r} does not match extension {extension!r}.",
        )


def _validate_archive_budget(content: bytes, *, max_uncompressed_bytes: int) -> None:
    """Reject obvious zip bombs before handing Office/adapter inputs to external tools."""
    if not content.startswith(b"PK\x03\x04"):
        return
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            total = sum(item.file_size for item in infos)
            if len(infos) > 10_000 or total > max_uncompressed_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="Archive exceeds configured uncompressed-size budget.",
                )
    except zipfile.BadZipFile as error:
        raise HTTPException(status_code=400, detail="Uploaded archive is invalid.") from error


def _remove_temp_file(path: Path) -> None:
    path.unlink(missing_ok=True)


def _parse_options(options_json: str | None) -> dict[str, object]:
    if not options_json:
        return {}
    try:
        value = json.loads(options_json)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="options_json must be valid JSON.") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="options_json must be a JSON object.")
    return _validate_public_options(value)


def _validate_public_options(value: dict[str, Any]) -> dict[str, object]:
    def visit(item: Any, *, path: str = "options") -> Any:
        if isinstance(item, dict):
            result: dict[str, Any] = {}
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise HTTPException(status_code=400, detail=f"{path} keys must be strings.")
                normalized = key.strip().lower()
                if normalized in _FORBIDDEN_PUBLIC_OPTION_KEYS or normalized.startswith("mineru_api_"):
                    raise HTTPException(status_code=400, detail=f"{path}.{key} is server-controlled and cannot be supplied by clients.")
                result[key] = visit(nested, path=f"{path}.{key}")
            return result
        if isinstance(item, list):
            return [visit(part, path=path) for part in item]
        return item

    return visit(value)


def _validate_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 200 or any(character.isspace() for character in normalized):
        raise HTTPException(status_code=400, detail="Idempotency-Key must be a short non-whitespace token.")
    return normalized


def _public_retry_rejection_detail(error: ValueError) -> str:
    if isinstance(error, SourceIntegrityError):
        return _RETRY_SOURCE_VERIFICATION_DETAIL
    return _RETRY_REJECTION_DETAILS.get(
        str(error),
        "The retry request cannot be accepted.",
    )


def _public_reparse_rejection_detail(error: ValueError) -> str:
    if isinstance(error, SourceIntegrityError):
        return _REPARSE_SOURCE_VERIFICATION_DETAIL
    return "The reparse request conflicts with an existing request."


def _raise_for_failed_job(job) -> None:
    code = 422
    if job.failure_kind is not None and job.failure_kind.value == "policy":
        code = 403
    if job.failure_kind is not None and job.failure_kind.value in {"unsupported", "unavailable"}:
        code = 400
    safe_error = public_parse_job(job).error
    raise HTTPException(
        status_code=code,
        detail=safe_error or "The parse job did not complete.",
    )


def _configured_frontend_origins() -> list[str]:
    """Read an explicit CORS allowlist for separately hosted frontends."""

    raw = os.getenv("DOCUMENT_PARSER_FRONTEND_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


app = create_app()
