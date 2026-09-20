import os
import asyncio
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, Callable, Awaitable

from src.services.registry import get_book_domain_service
from src.domain.books import BookDomainService

logger = logging.getLogger("BookIngestionWorker")

@dataclass
class BookJob:
    job_id: str
    file_path: str
    filename: str
    mode: Optional[str] = None
    status: str = "PENDING"  # PENDING, PROCESSING, SUCCESS, FAILED
    sync_git: bool = True
    sync_vector_db: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    on_complete: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    on_error: Optional[Callable[[str], Awaitable[None]]] = None

class BookIngestionWorker:
    """
    Worker assíncrono em background para ingestão de livros.
    Desacopla tarefas pesadas de parsing e vetorização do event loop do FastAPI e do Telegram.
    """

    def __init__(self, book_domain: Optional[BookDomainService] = None):
        self._book_domain = book_domain
        self.jobs: Dict[str, BookJob] = {}

    @property
    def book_domain(self) -> BookDomainService:
        if self._book_domain is None:
            self._book_domain = get_book_domain_service()
        return self._book_domain

    def submit_job(
        self,
        file_path: str,
        filename: str,
        mode: Optional[str] = None,
        extract_images: bool = True,
        sync_git: bool = True,
        sync_vector_db: bool = True,
        on_complete: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> str:
        """Registra e despacha a tarefa em background via asyncio.create_task."""
        job_id = str(uuid.uuid4())[:8]
        job = BookJob(
            job_id=job_id,
            file_path=file_path,
            filename=filename,
            mode=mode,
            sync_git=sync_git,
            sync_vector_db=sync_vector_db,
            on_complete=on_complete,
            on_error=on_error
        )
        self.jobs[job_id] = job

        # Dispara background task sem bloquear o caller
        asyncio.create_task(self._process_job(job, extract_images))
        logger.info(f"Job de ingestão {job_id} submetido para '{filename}'.")
        return job_id

    async def _process_job(self, job: BookJob, extract_images: bool):
        """Executa o pipeline no worker e aciona os callbacks."""
        job.status = "PROCESSING"
        try:
            result = await self.book_domain.ingest_book(
                file_path=job.file_path,
                filename=job.filename,
                mode=job.mode,
                extract_images=extract_images,
                sync_git=job.sync_git,
                sync_vector_db=job.sync_vector_db
            )
            job.status = "SUCCESS"
            job.completed_at = datetime.now()
            job.result = result

            if job.on_complete:
                try:
                    await job.on_complete(result)
                except Exception as cb_err:
                    logger.error(f"Erro no callback on_complete do job {job.job_id}: {cb_err}")

        except Exception as e:
            logger.error(f"Falha no processamento do job {job.job_id} ('{job.filename}'): {e}", exc_info=True)
            job.status = "FAILED"
            job.completed_at = datetime.now()
            job.error = str(e)

            if job.on_error:
                try:
                    await job.on_error(str(e))
                except Exception as cb_err:
                    logger.error(f"Erro no callback on_error do job {job.job_id}: {cb_err}")

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retorna o status atual de um job registrado."""
        job = self.jobs.get(job_id)
        if not job:
            return None
        return {
            "job_id": job.job_id,
            "filename": job.filename,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "result": job.result,
            "error": job.error
        }

# Instância singleton global do worker
_book_worker_instance: Optional[BookIngestionWorker] = None

def get_book_worker() -> BookIngestionWorker:
    global _book_worker_instance
    if _book_worker_instance is None:
        _book_worker_instance = BookIngestionWorker()
    return _book_worker_instance
