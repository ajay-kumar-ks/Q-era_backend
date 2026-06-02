import hashlib
import time
from urllib.parse import urlparse

try:
    from backend.config import settings
except ImportError:
    from config import settings

try:
    import requests
except ImportError as exc:
    raise RuntimeError("The requests package is required for Cloudinary uploads.") from exc

CLOUDINARY_UPLOAD_BASE = "https://api.cloudinary.com/v1_1/{cloud_name}/auto/upload"


def _parse_cloudinary_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    if parsed.scheme != "cloudinary":
        raise ValueError("CLOUDINARY_URL must use the cloudinary:// scheme")
    if not parsed.username or not parsed.password or not parsed.hostname:
        raise ValueError("CLOUDINARY_URL must include api_key, api_secret, and cloud name")
    return parsed.hostname, parsed.username, parsed.password


def _get_cloudinary_config() -> tuple[str, str, str]:
    if settings.CLOUDINARY_URL:
        return _parse_cloudinary_url(settings.CLOUDINARY_URL)

    if not (settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
        raise RuntimeError("Cloudinary configuration is missing. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET.")

    return settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET


def _build_signature(params: dict[str, str], secret: str) -> str:
    payload = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None and v != "")
    return hashlib.sha1((payload + secret).encode("utf-8")).hexdigest()


def upload_to_cloudinary(filename: str, file_bytes: bytes, content_type: str | None = None, folder: str | None = None) -> dict:
    folder = folder or settings.CLOUDINARY_UPLOAD_FOLDER
    cloud_name, api_key, api_secret = _get_cloudinary_config()
    upload_url = CLOUDINARY_UPLOAD_BASE.format(cloud_name=cloud_name)
    timestamp = str(int(time.time()))
    params = {"timestamp": timestamp}
    if folder:
        params["folder"] = folder
    signature = _build_signature(params, api_secret)

    form_data = {
        "api_key": api_key,
        "timestamp": timestamp,
        "signature": signature,
    }
    if folder:
        form_data["folder"] = folder

    files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}
    response = requests.post(upload_url, data=form_data, files=files, timeout=120)
    response.raise_for_status()
    return response.json()
