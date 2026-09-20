import os
import shutil
import tempfile
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_api_key
from src.services.book_worker import get_book_worker

logger = logging.getLogger("BooksRoute")
router = APIRouter(prefix="/api/v1/books", tags=["Books"])

STORAGE_DIR = os.getenv("BOOKS_STORAGE_PATH", os.path.join(tempfile.gettempdir(), "maeve_books"))
os.makedirs(STORAGE_DIR, exist_ok=True)

class IngestLocalRequest(BaseModel):
    file_path: str
    mode: Optional[str] = None
    extract_images: bool = True

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_and_ingest_book(
    file: UploadFile = File(...),
    mode: Optional[str] = Form(None),
    extract_images: bool = Form(True),
    api_key: str = Depends(get_api_key)
):
    """
    Endpoint de streaming multipart para upload de livros e processamento assíncrono em nuvem.
    Obedece estritamente ao invariante Zero-Token.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo inválido.")

    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in [".pdf", ".epub", ".mobi"]:
        raise HTTPException(
            status_code=400,
            detail=f"Extensão '{ext}' não suportada. Envie arquivos .pdf ou .epub."
        )

    # Gravação por streaming direto no storage em disco (Zero-Token Ingestion)
    dest_path = os.path.join(STORAGE_DIR, file.filename)
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Erro ao salvar upload do livro: {e}")
        raise HTTPException(status_code=500, detail="Falha ao gravar arquivo em disco.")

    worker = get_book_worker()
    job_id = worker.submit_job(
        file_path=dest_path,
        filename=file.filename,
        mode=mode,
        extract_images=extract_images
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "filename": file.filename,
        "message": f"Livro '{file.filename}' enfileirado para processamento assíncrono."
    }

@router.post("/ingest_local", status_code=status.HTTP_202_ACCEPTED)
async def ingest_local_book(
    req: IngestLocalRequest,
    api_key: str = Depends(get_api_key)
):
    """Dispara a ingestão de um livro já existente no sistema de arquivos."""
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {req.file_path}")

    filename = os.path.basename(req.file_path)
    worker = get_book_worker()
    job_id = worker.submit_job(
        file_path=req.file_path,
        filename=filename,
        mode=req.mode,
        extract_images=req.extract_images
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "filename": filename,
        "message": f"Livro '{filename}' enfileirado para ingestão."
    }

@router.get("/status/{job_id}")
async def get_book_status(
    job_id: str,
    api_key: str = Depends(get_api_key)
):
    """Consulta o status atual e resultado da ingestão de um livro."""
    worker = get_book_worker()
    job_info = worker.get_job_status(job_id)
    if not job_info:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' não encontrado.")
    return job_info
