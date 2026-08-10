"""Storage abstraction for uploaded dataset files.

Two backends are supported:
- ``local`` : filesystem under ``settings.upload_dir`` (default, no external dep)
- ``minio`` : MinIO object storage (requires a running MinIO instance)

The backend is selected by ``settings.storage_backend``. The same ``key``
(returned by :meth:`save`) is used for :meth:`load` / :meth:`delete`, so the
rest of the app is agnostic to where bytes actually live.
"""
from __future__ import annotations

import abc
import asyncio
import os
from datetime import datetime, timezone

from app.core.config import settings


class StorageError(Exception):
    pass


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    async def save(self, key: str, data: bytes, content_type: str) -> str:
        ...

    @abc.abstractmethod
    async def load(self, key: str) -> bytes:
        ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        ...


class LocalStorageBackend(StorageBackend):
    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key: str) -> str:
        # Guard against path traversal: keep key inside root.
        safe = key.lstrip("./\\")
        full = os.path.abspath(os.path.join(self.root, safe))
        if not full.startswith(self.root + os.sep) and full != self.root:
            raise StorageError("invalid storage key")
        return full

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        def _write() -> None:
            path = self._path(key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)

        await asyncio.to_thread(_write)
        return key

    async def load(self, key: str) -> bytes:
        def _read() -> bytes:
            with open(self._path(key), "rb") as fh:
                return fh.read()

        try:
            return await asyncio.to_thread(_read)
        except FileNotFoundError as exc:  # noqa: BLE001
            raise StorageError("file not found") from exc

    async def delete(self, key: str) -> None:
        def _remove() -> None:
            try:
                os.remove(self._path(key))
            except FileNotFoundError:
                pass

        await asyncio.to_thread(_remove)


class MinioStorageBackend(StorageBackend):
    def __init__(self) -> None:
        try:
            from minio import Minio
        except ImportError as exc:  # noqa: BLE001
            raise StorageError(
                "minio package not installed; run `pip install minio` or set "
                "STORAGE_BACKEND=local"
            ) from exc

        endpoint = settings.minio_endpoint
        self.bucket = settings.minio_bucket
        self._client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
        # Ensure bucket exists.
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        def _put() -> None:
            self._client.put_object(
                self.bucket, key, data=__import__("io").BytesIO(data),
                length=len(data), content_type=content_type,
            )

        await asyncio.to_thread(_put)
        return key

    async def load(self, key: str) -> bytes:
        def _get() -> bytes:
            resp = self._client.get_object(self.bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"minio load failed: {exc}") from exc

    async def delete(self, key: str) -> None:
        def _rm() -> None:
            self._client.remove_object(self.bucket, key)

        await asyncio.to_thread(_rm)


def build_storage() -> StorageBackend:
    backend = (settings.storage_backend or "local").lower()
    if backend == "minio":
        return MinioStorageBackend()
    if backend == "local":
        return LocalStorageBackend(settings.upload_dir)
    raise StorageError(f"unknown storage_backend: {backend}")


def make_storage_key(file_name: str) -> str:
    """Deterministic-ish unique key under <year>/<month>/<uuid>_<filename>."""
    now = datetime.now(timezone.utc)
    stem = uuid_key()
    return f"{now.year}/{now.month:02d}/{stem}_{file_name}"


def uuid_key() -> str:
    import uuid

    return str(uuid.uuid4())
