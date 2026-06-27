"""Azure Blob Storage helper.

Images are uploaded to a private container; we store only the **blob name** in the
database. Because anonymous public access is disabled on the account, accessible
URLs are produced on demand as time-limited SAS (signed) URLs via `resolve_url`.
This means rotating the account key never leaves stale URLs in the DB — fresh
SAS URLs are generated from the current key on every read.
"""

import os
import uuid
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)

load_dotenv()
logger = logging.getLogger(__name__)

# The Azure SDK logs every HTTP request/response at INFO — keep it quiet.
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)

CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "catalogue-images")
# How long generated SAS read URLs stay valid.
SAS_EXPIRY_DAYS = int(os.getenv("AZURE_SAS_EXPIRY_DAYS", "365"))

# Allowed image content types for uploads.
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_service: BlobServiceClient | None = None


def _client() -> BlobServiceClient:
    global _service
    if _service is None:
        if not CONNECTION_STRING:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not configured")
        _service = BlobServiceClient.from_connection_string(CONNECTION_STRING)
    return _service


def is_configured() -> bool:
    return bool(CONNECTION_STRING)


def upload_image(data: bytes, content_type: str, prefix: str = "") -> str:
    """Upload image bytes and return the stored blob name (to save in the DB).

    Raises ValueError for unsupported content types.
    """
    ext = ALLOWED_IMAGE_TYPES.get((content_type or "").lower())
    if not ext:
        raise ValueError(
            f"Unsupported image type '{content_type}'. Allowed: "
            f"{', '.join(sorted(ALLOWED_IMAGE_TYPES))}"
        )

    blob_name = f"{prefix}{uuid.uuid4().hex}{ext}"
    container = _client().get_container_client(CONTAINER)
    container.upload_blob(
        name=blob_name,
        data=data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )
    return blob_name


def delete_blob(blob_name: str) -> None:
    """Delete a blob by name. Silently ignores missing blobs / full URLs."""
    if not blob_name or blob_name.startswith("http"):
        return
    try:
        _client().get_container_client(CONTAINER).delete_blob(blob_name)
    except Exception as e:
        logger.warning(f"Failed to delete blob '{blob_name}': {e}")


def sas_url(blob_name: str) -> str:
    """Build a time-limited SAS read URL for a blob name."""
    svc = _client()
    token = generate_blob_sas(
        account_name=svc.account_name,
        container_name=CONTAINER,
        blob_name=blob_name,
        account_key=svc.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(days=SAS_EXPIRY_DAYS),
    )
    return f"{svc.url}{CONTAINER}/{blob_name}?{token}"


def resolve_url(value: str | None) -> str | None:
    """Turn a stored value into a usable URL.

    - None/empty -> None
    - already a full http(s) URL -> returned as-is (backward compatible)
    - otherwise treated as a blob name -> a fresh SAS URL
    """
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    try:
        return sas_url(value)
    except Exception as e:
        logger.error(f"Could not build SAS url for '{value}': {e}")
        return None
