import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import (
    ConfigError,
    EVENTS_DICT_PATH,
    ensure_data_pool_not_empty,
    get_deepseek_api_key,
    list_csv_files,
    resolve_csv_data_dir,
)
from schemas.analysis import (
    AnalysisPanel,
    AnalysisResponse,
    AnalysisTypesResponse,
    AnalyzeRequest,
    CsvFilesResponse,
    CsvUploadResponse,
    DictionaryEventDetail,
    DictionaryEventUpdate,
    DictionaryEventUpdateResponse,
    DictionaryTestRequest,
    DictionaryTestResponse,
    DictionaryTreeResponse,
    EventsListResponse,
    LlmSettingsResponse,
    LlmSettingsUpdate,
    RecommendationsResponse,
)
from services.analysis_registry import ANALYSIS_CATALOG, CHART_TYPE_CATALOG
from services.chart_builder import build
from services.csv_processor import load_data_pool, process_csv
from services.dashboard_narrator import (
    apply_presentation_to_panels,
    generate_dashboard_presentation,
)
from services.event_mapping import resolve_event_filter
from services.exploratory_analyzer import (
    build_exploratory_reason,
    detect_feasible_analysis_types,
    run_exploratory_analysis,
    should_run_exploratory,
)
from services.data_profiler import list_distinct_csv_events
from services.dict_preprocessor import DictPreprocessor
from services.llm_planner import (
    AnalysisPlanError,
    LLMApiError,
    MissingApiKeyError,
    build_events_whitelist,
    generate_plan,
)
from services.recommendation_service import generate_recommendations, clear_recommendations_cache
from services.csv_storage import (
    build_csv_files_response,
    delete_csv_file,
    save_csv_upload,
)
from services.dict_storage import (
    build_dictionary_tree,
    get_event_raw,
    load_raw_dictionary,
    reload_events_index,
    save_raw_dictionary,
    update_event_raw,
)
from services.dict_tester import test_event_against_pool
from services.llm_settings import (
    get_deepseek_model,
    list_deepseek_model_options,
    set_deepseek_model,
)
from services.metadata_resolver import MetadataResolverError, resolve
from services.multi_event_analysis import run_comprehensive_analysis
from services.event_cluster_discovery import (
    build_discovery_from_scope,
    discover_event_clusters,
)

logger = logging.getLogger(__name__)
events_index: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global events_index
    if not EVENTS_DICT_PATH.exists():
        raise RuntimeError(f"埋点字典文件不存在: {EVENTS_DICT_PATH}")
    preprocessor = DictPreprocessor(EVENTS_DICT_PATH)
    events_index = preprocessor.index
    logger.info("Loaded %d events from dictionary", len(events_index.get("event_names", [])))
    yield


app = FastAPI(title="AI Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": True, "message": message},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(422, str(exc.errors()))


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))


@app.get("/health")
@app.get("/api/health")
def health():
    csv_dir = None
    csv_file_count = 0
    data_pool_ready = False
    try:
        csv_dir = resolve_csv_data_dir()
        csv_file_count = len(list_csv_files())
        data_pool_ready = csv_file_count > 0
    except ConfigError:
        pass

    return {
        "status": "ok" if events_index and data_pool_ready else "degraded",
        "events_loaded": bool(events_index.get("event_names")),
        "event_count": len(events_index.get("event_names", [])),
        "api_key_configured": bool(get_deepseek_api_key()),
        "llm_model": get_deepseek_model(),
        "csv_data_dir": str(csv_dir) if csv_dir else None,
        "csv_file_count": csv_file_count,
        "data_pool_ready": data_pool_ready,
    }


@app.get("/api/events", response_model=EventsListResponse)
def list_events():
    modules = events_index.get("modules", [])
    total_events = len(events_index.get("event_names", []))
    return EventsListResponse(modules=modules, total_events=total_events)


@app.get("/api/csv-files", response_model=CsvFilesResponse)
def get_csv_files():
    try:
        return build_csv_files_response()
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/csv-files/upload", response_model=CsvUploadResponse)
async def upload_csv_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=422, detail="未选择文件")
    content = await file.read()
    try:
        return save_csv_upload(content, file.filename)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/csv-files/{filename}", response_model=CsvFilesResponse)
def remove_csv_file(filename: str):
    try:
        return delete_csv_file(filename)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _reload_dictionary_index() -> None:
    global events_index
    events_index = reload_events_index(EVENTS_DICT_PATH)
    clear_recommendations_cache()
    logger.info("Reloaded dictionary index: %d events", len(events_index.get("event_names", [])))


@app.get("/api/dictionary", response_model=DictionaryTreeResponse)
def get_dictionary_tree():
    raw = load_raw_dictionary()
    return build_dictionary_tree(raw)


@app.get("/api/dictionary/events/{event_name}", response_model=DictionaryEventDetail)
def get_dictionary_event(event_name: str):
    raw = load_raw_dictionary()
    event = get_event_raw(raw, event_name)
    if event is None:
        raise HTTPException(status_code=404, detail=f"事件不存在: {event_name}")
    module_name = ""
    for module in raw.get("功能列表", []):
        for item in module.get("事件列表", []):
            if item.get("事件") == event_name:
                module_name = module.get("功能", "")
                break
        if module_name:
            break
    return DictionaryEventDetail(module=module_name, event=event)


@app.put(
    "/api/dictionary/events/{event_name}",
    response_model=DictionaryEventUpdateResponse,
)
def update_dictionary_event(event_name: str, body: DictionaryEventUpdate):
    raw = load_raw_dictionary()
    if get_event_raw(raw, event_name) is None:
        raise HTTPException(status_code=404, detail=f"事件不存在: {event_name}")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="未提供可更新字段")

    try:
        updated = update_event_raw(raw, event_name, updates)
        save_raw_dictionary(raw)
        _reload_dictionary_index()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DictionaryEventUpdateResponse(
        event_name=event_name,
        message="字典已保存并重新加载",
        event=updated,
        total_events=len(events_index.get("event_names", [])),
    )


@app.post("/api/dictionary/test-event", response_model=DictionaryTestResponse)
def test_dictionary_event(body: DictionaryTestRequest):
    if body.event_name not in events_index.get("events", {}):
        raise HTTPException(status_code=404, detail=f"事件不存在: {body.event_name}")
    try:
        result = test_event_against_pool(
            body.event_name,
            events_index,
            csv_labels=body.csv_labels,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DictionaryTestResponse(**result)


@app.get("/api/settings/llm", response_model=LlmSettingsResponse)
def get_llm_settings():
    return LlmSettingsResponse(
        model=get_deepseek_model(),
        available_models=list_deepseek_model_options(),
    )


@app.put("/api/settings/llm", response_model=LlmSettingsResponse)
def update_llm_settings(body: LlmSettingsUpdate):
    try:
        set_deepseek_model(body.model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    clear_recommendations_cache()
    return LlmSettingsResponse(
        model=get_deepseek_model(),
        available_models=list_deepseek_model_options(),
    )


@app.get("/api/recommendations", response_model=RecommendationsResponse)
def get_recommendations():
    try:
        ensure_data_pool_not_empty()
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return generate_recommendations()
    except (LLMApiError, AnalysisPlanError) as exc:
        return _error_response(502, str(exc))


@app.get("/api/analysis-types", response_model=AnalysisTypesResponse)
def list_analysis_types():
    chart_types = [
        {"id": chart_id, **meta} for chart_id, meta in CHART_TYPE_CATALOG.items()
    ]
    return AnalysisTypesResponse(
        types=ANALYSIS_CATALOG,
        total=len(ANALYSIS_CATALOG),
        chart_types=chart_types,
    )


def _run_single_analysis(
    plan,
    event_def: dict,
    df: pd.DataFrame,
    query: str = "",
    *,
    event_filter_override: set[str] | None = None,
) -> AnalysisResponse:
    data_df, execution = process_csv(
        plan,
        event_def,
        df=df,
        event_filter_override=event_filter_override,
    )
    chart_config = build(plan, _df_to_records(data_df))

    panel = AnalysisPanel(
        panel_id="single",
        analysis_type=plan.analysis_type or "unknown",
        name=chart_config.title,
        layout="kpi" if plan.visualization.chart_type == "gauge" else "wide",
        plan=plan,
        execution=execution,
        chart_config=chart_config,
    )
    presentation = generate_dashboard_presentation([panel], plan, query or plan.matched_event)
    [panel] = apply_presentation_to_panels([panel], presentation)
    chart_config = panel.chart_config

    return AnalysisResponse(
        mode="single",
        plan=plan,
        execution=execution,
        chart_config=chart_config,
        panel_count=1,
        presentation=presentation,
    )


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze(request: AnalyzeRequest):
    global events_index
    if not events_index.get("events"):
        return _error_response(503, "事件字典尚未加载完成，请稍后重试")
    try:
        ensure_data_pool_not_empty()
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    whitelist = build_events_whitelist(events_index.get("modules", []))

    try:
        df = load_data_pool()
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    csv_event_names = list_distinct_csv_events(df)
    columns = list(df.columns)

    try:
        plan = generate_plan(
            request.query,
            whitelist,
            events_index=events_index,
            csv_event_names=csv_event_names,
            csv_columns=columns,
        )
    except MissingApiKeyError as exc:
        return _error_response(502, str(exc))
    except (LLMApiError, AnalysisPlanError) as exc:
        return _error_response(502, str(exc))

    try:
        resolution = resolve(
            plan,
            events_index,
            csv_event_names=csv_event_names,
            csv_columns=columns,
            query=request.query,
        )
    except MetadataResolverError as exc:
        return _error_response(422, str(exc))

    event_def = resolution["event_def"]
    use_comprehensive = request.analysis_mode != "precise"
    cluster_discovery = None
    if use_comprehensive:
        try:
            cluster_discovery = discover_event_clusters(
                request.query,
                csv_event_names,
                events_index,
                seed_plan=plan,
            )
        except (MissingApiKeyError, LLMApiError) as exc:
            logger.warning("Event cluster discovery failed: %s", exc)

    event_filter_override, _filter_source = resolve_event_filter(
        csv_event_filter=plan.csv_event_filter,
        matched_event=plan.matched_event,
        comparison_events=plan.comparison_events,
        events_index=events_index,
        csv_event_names=csv_event_names,
        query=request.query,
        comprehensive=use_comprehensive,
        cluster_discovery=cluster_discovery,
    )
    if event_filter_override:
        event_filter_override = set(event_filter_override)
    else:
        event_filter_override = None

    try:
        user_mode = request.analysis_mode

        if (
            use_comprehensive
            and event_filter_override
            and len(event_filter_override) >= 2
        ):
            if cluster_discovery is None:
                cluster_discovery = build_discovery_from_scope(
                    request.query,
                    event_filter_override,
                    events_index,
                    csv_event_names,
                    seed_plan=plan,
                )
            return run_comprehensive_analysis(
                plan,
                event_def,
                df,
                columns,
                query=request.query,
                user_mode=user_mode,
                events_index=events_index,
                csv_event_names=csv_event_names,
                event_filter_override=event_filter_override,
                cluster_discovery=cluster_discovery,
            )

        if should_run_exploratory(plan, request.query, user_mode=user_mode):
            feasible = detect_feasible_analysis_types(columns)
            if len(feasible) >= 2:
                reason = build_exploratory_reason(
                    plan,
                    request.query,
                    user_mode=user_mode,
                    feasible_count=len(feasible),
                )
                return run_exploratory_analysis(
                    plan,
                    event_def,
                    df,
                    columns,
                    reason=reason,
                    query=request.query,
                    event_filter_override=event_filter_override,
                    events_index=events_index,
                )

        return _run_single_analysis(
            plan,
            event_def,
            df,
            query=request.query,
            event_filter_override=event_filter_override,
        )
    except Exception as exc:
        logger.exception("CSV processing failed")
        return _error_response(500, f"数据处理失败: {exc}")


def _frontend_dist() -> Path | None:
    raw = os.getenv("FRONTEND_DIST", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_dir() and (path / "index.html").is_file():
        return path
    return None


_frontend_root = _frontend_dist()
if _frontend_root is not None:
    app.mount("/assets", StaticFiles(directory=_frontend_root / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        index = _frontend_root / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="Frontend not built")
        return FileResponse(index)
