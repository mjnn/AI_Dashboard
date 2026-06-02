"""CSV 数据池文件上传与列表。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import (
    ConfigError,
    _CSV_FILENAME_PATTERN,
    get_default_csv_filename,
    list_csv_files,
    resolve_csv_data_dir,
)
from schemas.analysis import CsvFileInfo, CsvFilesResponse, CsvUploadResponse

MAX_CSV_UPLOAD_BYTES = 200 * 1024 * 1024


def sanitize_upload_filename(raw_name: str) -> str:
    """校验并规范化上传文件名，防止路径穿越。"""
    name = Path(raw_name or "").name.strip()
    if not name.lower().endswith(".csv"):
        raise ConfigError("仅支持 .csv 文件")
    if not _CSV_FILENAME_PATTERN.match(name):
        raise ConfigError(
            "文件名无效，仅允许字母、数字、下划线、连字符与中文，且以 .csv 结尾"
        )
    return name


def _validate_csv_content(path: Path) -> None:
    """确认文件可被 pandas 读取且非空。"""
    last_error: Exception | None = None
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=encoding, nrows=5)
            if df.empty or len(df.columns) == 0:
                raise ConfigError("CSV 文件无有效列")
            return
        except UnicodeDecodeError as exc:
            last_error = exc
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError(f"无法解析 CSV: {exc}") from exc
    if last_error:
        raise ConfigError(f"无法解析 CSV 编码: {last_error}") from last_error


def build_csv_files_response() -> CsvFilesResponse:
    csv_dir = resolve_csv_data_dir()
    files = [
        CsvFileInfo(
            filename=item["filename"],
            size_bytes=item["size_bytes"],
            modified_at=item["modified_at"],
        )
        for item in list_csv_files()
    ]
    return CsvFilesResponse(
        data_dir=str(csv_dir),
        default_filename=get_default_csv_filename(),
        files=files,
        total=len(files),
    )


def save_csv_upload(content: bytes, raw_filename: str) -> CsvUploadResponse:
    """保存上传的 CSV 到数据池目录。"""
    if len(content) == 0:
        raise ConfigError("文件为空")
    if len(content) > MAX_CSV_UPLOAD_BYTES:
        max_mb = MAX_CSV_UPLOAD_BYTES // (1024 * 1024)
        raise ConfigError(f"文件过大，单文件上限 {max_mb} MB")

    filename = sanitize_upload_filename(raw_filename)
    csv_dir = resolve_csv_data_dir()
    csv_dir.mkdir(parents=True, exist_ok=True)
    target = (csv_dir / filename).resolve()
    if not target.is_relative_to(csv_dir.resolve()):
        raise ConfigError("非法文件路径")

    target.write_bytes(content)
    try:
        _validate_csv_content(target)
    except ConfigError:
        target.unlink(missing_ok=True)
        raise

    from services.recommendation_service import clear_recommendations_cache
    from services.analysis_route_memory import clear_route_cache
    from services.csv_processor import invalidate_data_pool_cache

    clear_recommendations_cache()
    clear_route_cache()
    invalidate_data_pool_cache()

    listing = build_csv_files_response()
    return CsvUploadResponse(
        filename=filename,
        size_bytes=target.stat().st_size,
        message=f"已上传 {filename}，数据池共 {listing.total} 个文件",
        pool=listing,
    )


def delete_csv_file(filename: str) -> CsvFilesResponse:
    """从数据池删除指定 CSV（内置字典文件不可删）。"""
    safe_name = sanitize_upload_filename(filename)
    if safe_name.lower() == "events_dict.json":
        raise ConfigError("不能删除字典文件")

    csv_dir = resolve_csv_data_dir()
    target = (csv_dir / safe_name).resolve()
    if not target.is_relative_to(csv_dir.resolve()):
        raise ConfigError("非法文件路径")
    if not target.is_file():
        raise ConfigError(f"文件不存在: {safe_name}")

    target.unlink()

    from services.recommendation_service import clear_recommendations_cache
    from services.analysis_route_memory import clear_route_cache
    from services.csv_processor import invalidate_data_pool_cache

    clear_recommendations_cache()
    clear_route_cache()
    invalidate_data_pool_cache()
    return build_csv_files_response()
