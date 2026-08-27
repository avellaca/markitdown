import os
import io
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Form, Body, status
from fastapi.responses import PlainTextResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from markitdown import MarkItDown, StreamInfo, MarkItDownException

app = FastAPI(
    title="MarkItDown API",
    description="High-performance REST API wrapper for Microsoft MarkItDown document conversion to Markdown.",
    version="1.0.0",
)

# Enable CORS for cross-origin requests from frontend apps / webhooks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MarkItDown converter instance
def get_converter() -> MarkItDown:
    enable_plugins = os.getenv("MARKITDOWN_ENABLE_PLUGINS", "true").lower() in ("true", "1", "yes")
    converter = MarkItDown(
        enable_plugins=enable_plugins,
        exiftool_path=os.getenv("EXIFTOOL_PATH", "/usr/bin/exiftool"),
    )
    return converter

md = get_converter()


class ConvertUrlRequest(BaseModel):
    url: str

class ConvertPathRequest(BaseModel):
    path: str

class ConversionResponse(BaseModel):
    title: Optional[str] = None
    markdown: str
    filename: Optional[str] = None
    characters: int


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "markitdown-api"}


@app.post("/convert", response_model=ConversionResponse, tags=["Conversion"])
async def convert_file(
    file: UploadFile = File(..., description="Document file to convert to Markdown (PDF, DOCX, XLSX, PPTX, Image, Audio, etc.)")
):
    """
    Convert an uploaded file directly to Markdown and return structured JSON.
    """
    filename = file.filename or "uploaded_file"
    extension = Path(filename).suffix.lower() if filename else None
    
    stream_info = StreamInfo(
        filename=filename,
        extension=extension,
        mimetype=file.content_type,
    )

    try:
        file_bytes = await file.read()
        byte_stream = io.BytesIO(file_bytes)
        result = md.convert(byte_stream, stream_info=stream_info)
        return ConversionResponse(
            title=result.title,
            markdown=result.text_content or "",
            filename=filename,
            characters=len(result.text_content or ""),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to convert file '{filename}': {str(e)}",
        )


@app.post("/convert/raw", response_class=PlainTextResponse, tags=["Conversion"])
async def convert_file_raw(
    file: UploadFile = File(..., description="Document file to convert to Markdown")
):
    """
    Convert an uploaded file and return the raw Markdown string directly as text/plain.
    Ideal for n8n HTTP Request node, curl, or direct downstream processing.
    """
    filename = file.filename or "uploaded_file"
    extension = Path(filename).suffix.lower() if filename else None
    
    stream_info = StreamInfo(
        filename=filename,
        extension=extension,
        mimetype=file.content_type,
    )

    try:
        file_bytes = await file.read()
        byte_stream = io.BytesIO(file_bytes)
        result = md.convert(byte_stream, stream_info=stream_info)
        return PlainTextResponse(content=result.text_content or "", media_type="text/markdown; charset=utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to convert file '{filename}': {str(e)}",
        )


@app.post("/convert/url", response_model=ConversionResponse, tags=["Conversion"])
def convert_url(payload: ConvertUrlRequest):
    """
    Convert a webpage, remote document, or public URL to Markdown.
    """
    try:
        result = md.convert(payload.url)
        return ConversionResponse(
            title=result.title,
            markdown=result.text_content or "",
            filename=payload.url,
            characters=len(result.text_content or ""),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to convert URL '{payload.url}': {str(e)}",
        )


@app.post("/convert/path", response_model=ConversionResponse, tags=["Conversion"])
def convert_path(payload: ConvertPathRequest):
    """
    Convert a file from a shared volume / local container path (e.g., `/data/uploads/document.pdf`).
    """
    target_path = Path(payload.path)
    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found at path: {payload.path}",
        )

    try:
        result = md.convert(str(target_path))
        return ConversionResponse(
            title=result.title,
            markdown=result.text_content or "",
            filename=target_path.name,
            characters=len(result.text_content or ""),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to convert local file '{payload.path}': {str(e)}",
        )
