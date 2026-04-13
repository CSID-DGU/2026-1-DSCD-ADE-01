"""shared.storage.gcs_client 단위 테스트."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from shared.storage.gcs_client import GCSClient, StorageError, get_gcs_client


def _make_client() -> GCSClient:
    """storage.Client를 mock한 GCSClient 인스턴스를 반환한다."""
    with patch("shared.storage.gcs_client.storage.Client") as mock_storage:
        mock_storage.return_value = MagicMock()
        client = GCSClient(bucket_name="test-bucket")
    return client


# --- StorageError ---

def test_storage_error_is_runtime_error_subclass() -> None:
    assert issubclass(StorageError, RuntimeError)


# --- get_gcs_client (lazy factory) ---

def test_get_gcs_client_returns_gcs_client_instance() -> None:
    """get_gcs_client()가 GCSClient 인스턴스를 반환한다."""
    import shared.storage.gcs_client as mod
    with patch("shared.storage.gcs_client.storage.Client"):
        mod._gcs_client = None
        client = get_gcs_client()
        assert isinstance(client, GCSClient)
        mod._gcs_client = None


def test_get_gcs_client_returns_same_instance() -> None:
    """get_gcs_client()가 동일 인스턴스를 반환한다 (싱글턴)."""
    import shared.storage.gcs_client as mod
    with patch("shared.storage.gcs_client.storage.Client"):
        mod._gcs_client = None
        first = get_gcs_client()
        second = get_gcs_client()
        assert first is second
        mod._gcs_client = None


# --- bucket_name property ---

def test_bucket_name_property() -> None:
    """bucket_name 프로퍼티가 버킷 이름을 반환한다."""
    client = _make_client()
    assert client.bucket_name == "test-bucket"


# --- upload_bytes ---

def test_upload_bytes_calls_upload_from_string() -> None:
    """upload_bytes()가 blob.upload_from_string()을 호출한다."""
    client = _make_client()
    mock_blob = MagicMock()
    client._bucket.blob.return_value = mock_blob

    client.upload_bytes("test/hello.txt", b"Hello!", "text/plain")

    client._bucket.blob.assert_called_once_with("test/hello.txt")
    mock_blob.upload_from_string.assert_called_once_with(b"Hello!", content_type="text/plain")


def test_upload_bytes_default_content_type() -> None:
    """upload_bytes() content_type 미지정 시 기본값 사용."""
    client = _make_client()
    mock_blob = MagicMock()
    client._bucket.blob.return_value = mock_blob

    client.upload_bytes("test/data.bin", b"\x00\x01")

    mock_blob.upload_from_string.assert_called_once_with(
        b"\x00\x01", content_type="application/octet-stream"
    )


def test_upload_bytes_wraps_exception() -> None:
    """upload_bytes() 중 예외 발생 시 StorageError로 래핑한다."""
    client = _make_client()
    client._bucket.blob.side_effect = RuntimeError("업로드 실패")

    with pytest.raises(StorageError) as exc_info:
        client.upload_bytes("test/fail.txt", b"data")
    assert "업로드 실패" in str(exc_info.value)


def test_upload_bytes_preserves_cause() -> None:
    """StorageError는 원본 예외를 __cause__로 보존한다."""
    client = _make_client()
    original = RuntimeError("원본 오류")
    client._bucket.blob.side_effect = original

    with pytest.raises(StorageError) as exc_info:
        client.upload_bytes("test/fail.txt", b"data")
    assert exc_info.value.__cause__ is original


# --- upload_file ---

def test_upload_file_calls_upload_from_filename() -> None:
    """upload_file()이 blob.upload_from_filename()을 호출한다."""
    client = _make_client()
    mock_blob = MagicMock()
    client._bucket.blob.return_value = mock_blob

    client.upload_file("test/data.csv", "/tmp/data.csv", "text/csv")

    client._bucket.blob.assert_called_once_with("test/data.csv")
    mock_blob.upload_from_filename.assert_called_once_with("/tmp/data.csv", content_type="text/csv")


def test_upload_file_accepts_path_object() -> None:
    """upload_file()이 pathlib.Path 객체를 받을 수 있다."""
    client = _make_client()
    mock_blob = MagicMock()
    client._bucket.blob.return_value = mock_blob

    client.upload_file("test/data.csv", Path("/tmp/data.csv"), "text/csv")

    mock_blob.upload_from_filename.assert_called_once_with("/tmp/data.csv", content_type="text/csv")


def test_upload_file_wraps_exception() -> None:
    """upload_file() 중 예외 발생 시 StorageError로 래핑한다."""
    client = _make_client()
    client._bucket.blob.side_effect = RuntimeError("파일 없음")

    with pytest.raises(StorageError):
        client.upload_file("test/fail.txt", "/tmp/nope.txt")


# --- download_bytes ---

def test_download_bytes_returns_bytes() -> None:
    """download_bytes()가 바이트 데이터를 반환한다."""
    client = _make_client()
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = b"file content"
    client._bucket.blob.return_value = mock_blob

    result = client.download_bytes("test/hello.txt")

    assert result == b"file content"
    client._bucket.blob.assert_called_once_with("test/hello.txt")


def test_download_bytes_wraps_exception() -> None:
    """download_bytes() 중 예외 발생 시 StorageError로 래핑한다."""
    client = _make_client()
    client._bucket.blob.side_effect = RuntimeError("다운로드 실패")

    with pytest.raises(StorageError):
        client.download_bytes("test/fail.txt")


# --- download_file ---

def test_download_file_calls_download_to_filename() -> None:
    """download_file()이 blob.download_to_filename()을 호출한다."""
    client = _make_client()
    mock_blob = MagicMock()
    client._bucket.blob.return_value = mock_blob

    client.download_file("test/data.csv", "/tmp/out.csv")

    mock_blob.download_to_filename.assert_called_once_with("/tmp/out.csv")


def test_download_file_accepts_path_object() -> None:
    """download_file()이 pathlib.Path 객체를 받을 수 있다."""
    client = _make_client()
    mock_blob = MagicMock()
    client._bucket.blob.return_value = mock_blob

    client.download_file("test/data.csv", Path("/tmp/out.csv"))

    mock_blob.download_to_filename.assert_called_once_with("/tmp/out.csv")


def test_download_file_wraps_exception() -> None:
    """download_file() 중 예외 발생 시 StorageError로 래핑한다."""
    client = _make_client()
    client._bucket.blob.side_effect = RuntimeError("저장 실패")

    with pytest.raises(StorageError):
        client.download_file("test/fail.txt", "/tmp/out.txt")


# --- delete ---

def test_delete_calls_blob_delete() -> None:
    """delete()가 blob.delete()를 호출한다."""
    client = _make_client()
    mock_blob = MagicMock()
    client._bucket.blob.return_value = mock_blob

    client.delete("test/hello.txt")

    client._bucket.blob.assert_called_once_with("test/hello.txt")
    mock_blob.delete.assert_called_once()


def test_delete_wraps_exception() -> None:
    """delete() 중 예외 발생 시 StorageError로 래핑한다."""
    client = _make_client()
    client._bucket.blob.side_effect = RuntimeError("삭제 실패")

    with pytest.raises(StorageError):
        client.delete("test/fail.txt")


# --- exists ---

def test_exists_returns_true_when_blob_exists() -> None:
    """exists()가 파일 존재 시 True를 반환한다."""
    client = _make_client()
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    client._bucket.blob.return_value = mock_blob

    assert client.exists("test/hello.txt") is True


def test_exists_returns_false_when_blob_missing() -> None:
    """exists()가 파일 미존재 시 False를 반환한다."""
    client = _make_client()
    mock_blob = MagicMock()
    mock_blob.exists.return_value = False
    client._bucket.blob.return_value = mock_blob

    assert client.exists("test/nope.txt") is False


def test_exists_wraps_exception() -> None:
    """exists() 중 예외 발생 시 StorageError로 래핑한다."""
    client = _make_client()
    client._bucket.blob.side_effect = RuntimeError("확인 실패")

    with pytest.raises(StorageError):
        client.exists("test/fail.txt")


# --- list_blobs ---

def test_list_blobs_returns_blob_names() -> None:
    """list_blobs()가 blob 이름 리스트를 반환한다."""
    client = _make_client()
    mock_blob1 = MagicMock()
    mock_blob1.name = "reports/a.txt"
    mock_blob2 = MagicMock()
    mock_blob2.name = "reports/b.txt"
    client._client.list_blobs.return_value = [mock_blob1, mock_blob2]

    result = client.list_blobs("reports/")

    assert result == ["reports/a.txt", "reports/b.txt"]
    client._client.list_blobs.assert_called_once_with("test-bucket", prefix="reports/")


def test_list_blobs_empty_prefix_passes_none() -> None:
    """list_blobs() 빈 prefix일 때 None으로 전달한다."""
    client = _make_client()
    client._client.list_blobs.return_value = []

    result = client.list_blobs("")

    assert result == []
    client._client.list_blobs.assert_called_once_with("test-bucket", prefix=None)


def test_list_blobs_returns_empty_list() -> None:
    """list_blobs() 결과 없으면 빈 리스트를 반환한다."""
    client = _make_client()
    client._client.list_blobs.return_value = []

    result = client.list_blobs("empty/")

    assert result == []


def test_list_blobs_wraps_exception() -> None:
    """list_blobs() 중 예외 발생 시 StorageError로 래핑한다."""
    client = _make_client()
    client._client.list_blobs.side_effect = RuntimeError("목록 조회 실패")

    with pytest.raises(StorageError):
        client.list_blobs("fail/")
