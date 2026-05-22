"""
MinIO 对象存储客户端

管理 MinIO 的连接和操作
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import io
import logging
from typing import Optional, BinaryIO
from datetime import timedelta, datetime, timezone

from minio import Minio
from minio.error import S3Error
import minio.time as minio_time
import urllib3
from email.utils import parsedate_to_datetime

from app.config.settings import settings

logger = logging.getLogger(__name__)


class MinIOError(Exception):
    """MinIO 操作错误的包装类，用于避免 S3Error 的 frozen 属性问题"""

    def __init__(self, message: str, code: Optional[str] = None, original_error: Optional[S3Error] = None):
        super().__init__(message)
        self.code = code
        self.original_error = original_error


class MinIOClient:
    """MinIO 客户端管理器"""

    _client: Optional[Minio] = None
    _bucket_ensured: bool = False
    _time_offset: Optional[timedelta] = None
    _original_utcnow = minio_time.utcnow
    _last_sync_check: Optional[datetime] = None
    _sync_interval: timedelta = timedelta(minutes=5)

    @classmethod
    def _get_synced_utcnow(cls):
        """带时间补偿的 utcnow"""
        offset = cls._time_offset or timedelta(0)
        return cls._original_utcnow() + offset

    @classmethod
    def _ensure_time_sync(cls) -> None:
        """检测并补偿本地系统与 MinIO 服务器的时间偏差"""
        now = datetime.now(timezone.utc)
        if (
            cls._last_sync_check
            and (now - cls._last_sync_check) < cls._sync_interval
        ):
            return

        cls._last_sync_check = now

        try:
            http = urllib3.PoolManager()
            scheme = "https" if settings.minio_secure else "http"
            url = f"{scheme}://{settings.minio_endpoint}/minio/health/live"
            resp = http.request("HEAD", url, timeout=5.0)
            server_date = resp.headers.get("Date")
            if server_date:
                server_time = parsedate_to_datetime(server_date)
                local_time = datetime.now(timezone.utc)
                new_offset = server_time - local_time
                old_offset = cls._time_offset or timedelta(0)

                # 偏移量变化超过 30 秒才更新，避免频繁抖动
                if abs((new_offset - old_offset).total_seconds()) > 30:
                    cls._time_offset = new_offset
                    minio_time.utcnow = cls._get_synced_utcnow

                    if abs(new_offset.total_seconds()) > 60:
                        logger.warning(
                            "检测到 MinIO 服务器时间偏差: %.0f 秒，已自动补偿。"
                            "建议同步系统时间（system clock synchronized: no）。",
                            new_offset.total_seconds(),
                        )
                    else:
                        logger.info(
                            "MinIO 服务器时间已同步，当前偏差: %.0f 秒。",
                            new_offset.total_seconds(),
                        )
        except Exception:
            # 静默忽略，不影响正常功能
            pass

    @classmethod
    def get_client(cls) -> Minio:
        """获取 MinIO 客户端实例"""
        cls._ensure_time_sync()
        if cls._client is None:
            cls._client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
                region=settings.minio_region,
            )
        return cls._client

    @classmethod
    def ensure_bucket(cls) -> None:
        """确保存储桶存在"""
        if cls._bucket_ensured:
            return

        client = cls.get_client()
        bucket_name = settings.minio_bucket

        try:
            if not client.bucket_exists(bucket_name):
                client.make_bucket(bucket_name)
        except S3Error as e:
            # 桶已存在，忽略错误
            if e.code != "BucketAlreadyOwnedByYou":
                raise MinIOError(
                    f"Failed to ensure bucket exists: {e.message}",
                    code=e.code,
                    original_error=e
                )

        cls._bucket_ensured = True
    
    @classmethod
    def upload_file(
        cls,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        上传文件到 MinIO

        Args:
            object_name: 对象名称（存储路径）
            data: 文件数据流
            length: 文件长度
            content_type: 内容类型

        Returns:
            str: 对象名称
        """
        try:
            cls.ensure_bucket()
            client = cls.get_client()

            client.put_object(
                bucket_name=settings.minio_bucket,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type,
            )

            return object_name
        except S3Error as e:
            raise MinIOError(
                f"Failed to upload file '{object_name}': {e.message}",
                code=e.code,
                original_error=e
            )
    
    @classmethod
    def upload_bytes(
        cls,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        上传字节数据到 MinIO
        
        Args:
            object_name: 对象名称
            data: 字节数据
            content_type: 内容类型
            
        Returns:
            str: 对象名称
        """
        return cls.upload_file(
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
    
    @classmethod
    def download_file(cls, object_name: str) -> bytes:
        """
        从 MinIO 下载文件

        Args:
            object_name: 对象名称

        Returns:
            bytes: 文件内容
        """
        try:
            client = cls.get_client()

            response = client.get_object(
                bucket_name=settings.minio_bucket,
                object_name=object_name,
            )

            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as e:
            raise MinIOError(
                f"Failed to download file '{object_name}': {e.message}",
                code=e.code,
                original_error=e
            )
    
    @classmethod
    def get_presigned_url(
        cls,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """
        获取预签名 URL（用于下载）

        Args:
            object_name: 对象名称
            expires: 过期时间

        Returns:
            str: 预签名 URL
        """
        try:
            client = cls.get_client()

            return client.presigned_get_object(
                bucket_name=settings.minio_bucket,
                object_name=object_name,
                expires=expires,
            )
        except S3Error as e:
            raise MinIOError(
                f"Failed to get presigned URL for '{object_name}': {e.message}",
                code=e.code,
                original_error=e
            )

    @classmethod
    def delete_file(cls, object_name: str) -> None:
        """
        从 MinIO 删除文件

        Args:
            object_name: 对象名称
        """
        try:
            client = cls.get_client()

            client.remove_object(
                bucket_name=settings.minio_bucket,
                object_name=object_name,
            )
        except S3Error as e:
            raise MinIOError(
                f"Failed to delete file '{object_name}': {e.message}",
                code=e.code,
                original_error=e
            )

    @classmethod
    def file_exists(cls, object_name: str) -> bool:
        """
        检查文件是否存在

        Args:
            object_name: 对象名称

        Returns:
            bool: 是否存在
        """
        try:
            client = cls.get_client()

            client.stat_object(
                bucket_name=settings.minio_bucket,
                object_name=object_name,
            )
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise MinIOError(
                f"Failed to check if file '{object_name}' exists: {e.message}",
                code=e.code,
                original_error=e
            )

