import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EVENTS_DICT_PATH = DATA_DIR / "events_dict.json"

_CSV_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\u4e00-\u9fff]+\.csv$")


class ConfigError(ValueError):
    """配置或路径解析错误。"""


def get_deepseek_api_key() -> str:
    """每次调用时重新读取 API Key。"""
    load_dotenv(override=True)
    return os.getenv("DEEPSEEK_API_KEY", "")


def _resolve_under_data(path: Path) -> Path:
    """解析路径并确保位于 data 目录内。"""
    data_root = DATA_DIR.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(data_root):
        raise ConfigError(f"路径必须在 data 目录内: {resolved}")
    return resolved


def resolve_csv_data_dir() -> Path:
    """解析 CSV 数据目录（CSV_DATA_PATH 指向文件夹）。"""
    load_dotenv(override=True)
    raw = os.getenv("CSV_DATA_PATH", "").strip()

    if not raw:
        return _resolve_under_data(DATA_DIR)

    path = Path(raw)
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    else:
        path = path.resolve()

    if path.is_file():
        if path.suffix.lower() != ".csv":
            raise ConfigError(f"CSV_DATA_PATH 指向非 CSV 文件: {path}")
        return _resolve_under_data(path.parent)

    if not path.is_dir():
        raise ConfigError(f"CSV 数据目录不存在: {path}")

    return _resolve_under_data(path)


def list_csv_files() -> list[dict]:
    """列出 CSV 数据目录下全部 .csv 文件（按修改时间倒序）。"""
    csv_dir = resolve_csv_data_dir()
    if not csv_dir.exists():
        return []

    files: list[dict] = []
    for path in csv_dir.glob("*.csv"):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "filename": path.name,
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )

    files.sort(key=lambda item: item["modified_at"], reverse=True)
    return files


def _pick_default_csv_filename(files: list[dict]) -> str | None:
    """未指定文件时的默认选择策略。"""
    load_dotenv(override=True)
    explicit = os.getenv("DEFAULT_CSV_FILENAME", "").strip()
    if explicit:
        return explicit

    if not files:
        return None
    if len(files) == 1:
        return files[0]["filename"]
    return files[0]["filename"]


def list_csv_paths() -> list[Path]:
    """返回数据目录下全部 CSV 文件路径（按修改时间倒序）。"""
    csv_dir = resolve_csv_data_dir()
    return [(csv_dir / item["filename"]).resolve() for item in list_csv_files()]


def data_pool_cache_key() -> str:
    """数据池缓存键（随目录内文件变更而失效）。"""
    parts: list[str] = []
    for path in list_csv_paths():
        stat = path.stat()
        parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts) if parts else "empty"


def ensure_data_pool_not_empty() -> Path:
    """确认数据目录存在且至少有一个 CSV 文件。"""
    csv_dir = resolve_csv_data_dir()
    if not list_csv_files():
        raise ConfigError(
            f"数据目录为空: {csv_dir}，请将 CSV 文件放入该目录（CSV_DATA_PATH）"
        )
    return csv_dir


def resolve_csv_path(csv_filename: str | None = None) -> Path:
    """解析 CSV 文件路径；csv_filename 为数据目录下的文件名。"""
    csv_dir = resolve_csv_data_dir()
    available = list_csv_files()

    if csv_filename:
        if not _CSV_FILENAME_PATTERN.match(csv_filename):
            raise ConfigError(
                f"csv_filename 无效，仅允许数据目录下的 .csv 文件名: {csv_filename}"
            )
        path = (csv_dir / csv_filename).resolve()
        if not path.is_relative_to(csv_dir.resolve()):
            raise ConfigError("csv_filename 必须在 CSV 数据目录内")
        return path

    default_name = _pick_default_csv_filename(available)
    if not default_name:
        raise ConfigError(
            f"CSV 数据目录为空: {csv_dir}，请放入 .csv 文件或设置 DEFAULT_CSV_FILENAME"
        )

    return (csv_dir / default_name).resolve()


def get_default_csv_filename() -> str | None:
    """返回当前默认将使用的 CSV 文件名。"""
    try:
        return resolve_csv_path().name
    except ConfigError:
        return None
