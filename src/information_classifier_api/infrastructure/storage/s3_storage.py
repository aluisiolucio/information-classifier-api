import asyncio

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ...domain.exceptions import StorageUnavailableError


class S3ObjectStorage:
    """Adaptador fino para S3/MinIO. Blobs grandes nunca vão para o Postgres."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region,
        )

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get_object(self, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            raise StorageUnavailableError(
                f"objeto não disponível no bucket {self._bucket!r}: {key!r}"
            ) from exc
        body = response["Body"]
        try:
            return await asyncio.to_thread(body.read)
        finally:
            body.close()

    async def delete_object(self, key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket, Key=key
        )

    def _ensure_bucket_sync(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise StorageUnavailableError(
                    f"falha ao verificar bucket {self._bucket!r}"
                ) from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError(
                f"storage indisponível para o bucket {self._bucket!r}"
            ) from exc
        try:
            self._client.create_bucket(Bucket=self._bucket)
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailableError(
                f"falha ao criar bucket {self._bucket!r}"
            ) from exc
