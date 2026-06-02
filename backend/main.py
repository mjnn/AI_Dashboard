import json
import logging
import os
from typing import Optional
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
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
from services.analysis_registry import (
    ANALYSIS_CATALOG,
    CHART_TYPE_CATALOG,
    wants_comprehensive_analysis,
    wants_funnel_analysis,
)
from services.event_scope import expand_event_scope
from services.analysis_intent import (
    effective_scope_mode,
    should_run_multi_event_dashboard,
    should_widen_event_scope,
)
from services.event_display import (
    clear_display_alias_cache,
    collect_scope_event_refs,
    warm_display_aliases,
)
from services.event_mapping import infer_csv_filter_for_comparison
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
from services.analysis_route_memory import (
    clear_route_cache,
    lookup_cluster,
    remember_cluster,
)
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
from services.multi_event_analysis import run_comprehensive_analysis, run_funnel_dashboard
from services.analysis_agent import generate_plan_via_agent
from schemas.agent_plan import AgentExecutionTrace
from services.event_cluster_discovery import (
    build_discovery_from_scope,
    discover_event_clusters,
)

logger = logging.getLogger(__name__)
events_index: dict[str, Any] = {}


def _use_agent_planner() -> bool:
    return os.getenv("ANALYSIS_USE_AGENT", "true").lower() not in (
        "0",
        "false",
        "no",
    )


def _attach_agent_trace(
    response: AnalysisResponse,
    trace: Optional[AgentExecutionTrace],
) -> AnalysisResponse:
    if trace is None:
        return response
    return response.model_copy(
        update={"agent_trace": trace.model_dump(mode="json")}
    )


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
    clear_route_cache()
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
def get_recommendations(locale: str = Query(default="zh")):
    try:
        ensure_data_pool_not_empty()
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return generate_recommendations(locale=locale)
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
    events_index: dict | None = None,
    locale: str | None = None,
) -> AnalysisResponse:
    data_df, execution = process_csv(
        plan,
        event_def,
        df=df,
        event_filter_override=event_filter_override,
        events_index=events_index,
    )
    display_plan = plan
    if event_filter_override:
        display_plan = plan.model_copy(
            update={"csv_event_filter": sorted(event_filter_override)}
        )
    chart_config = build(
        display_plan,
        _df_to_records(data_df),
        events_index=events_index,
        locale=locale,
    )

    panel = AnalysisPanel(
        panel_id="single",
        analysis_type=plan.analysis_type or "unknown",
        name=chart_config.title,
        layout="kpi" if plan.visualization.chart_type == "gauge" else "wide",
        plan=plan,
        execution=execution,
        chart_config=chart_config,
    )
    presentation = generate_dashboard_presentation(
        [panel],
        plan,
        query or plan.matched_event,
        locale=locale,
        events_index=events_index,
    )
    [panel] = apply_presentation_to_panels([panel], presentation)
    chart_config = panel.chart_config

    return AnalysisResponse(
        mode="single",
        plan=plan,
        execution=execution,
        chart_config=chart_config,
        panels=[panel],
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

    agent_trace: Optional[AgentExecutionTrace] = None
    try:
        if _use_agent_planner():
            plan, agent_trace = generate_plan_via_agent(
                request.query,
                whitelist,
                events_index=events_index,
                csv_event_names=csv_event_names,
                csv_columns=columns,
                df=df,
                locale=request.locale,
                force_fresh=request.force_fresh,
            )
        else:
            plan = generate_plan(
                request.query,
                whitelist,
                events_index=events_index,
                csv_event_names=csv_event_names,
                csv_columns=columns,
                locale=request.locale,
            )
    except MissingApiKeyError as exc:
        return _error_response(502, str(exc))
    except (LLMApiError, AnalysisPlanError) as exc:
        return _error_response(502, str(exc))

    scope_mode = effective_scope_mode(
        query=request.query,
        plan=plan,
        agent_context=agent_trace.context if agent_trace else None,
        analysis_mode=request.analysis_mode,
    )
    widen_scope = should_widen_event_scope(
        scope_mode, request.query, analysis_mode=request.analysis_mode
    )
    multi_event_dashboard = should_run_multi_event_dashboard(
        scope_mode, request.query, analysis_mode=request.analysis_mode
    )

    if widen_scope:
        scope, canonicals = expand_event_scope(
            scope_mode=scope_mode,
            matched_event=plan.matched_event,
            matched_module=plan.matched_module,
            csv_event_filter=plan.csv_event_filter,
            query=request.query,
            events_index=events_index,
            csv_event_names=csv_event_names,
        )
        plan_updates: dict[str, Any] = {"scope_mode": scope_mode}
        if multi_event_dashboard:
            plan_updates["exploratory_mode"] = True
        if len(scope) >= 2 and scope_mode != "single_event":
            plan_updates["csv_event_filter"] = sorted(scope)
            if len(canonicals) >= 2:
                plan_updates["comparison_events"] = canonicals
        plan = plan.model_copy(update=plan_updates)
    elif scope_mode:
        plan = plan.model_copy(update={"scope_mode": scope_mode})

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
    if use_comprehensive and not multi_event_dashboard:
        cached_cluster = None
        if not request.force_fresh:
            cached_cluster = lookup_cluster(request.query, locale=request.locale)
        if cached_cluster:
            try:
                from services.event_cluster_discovery import EventClusterDiscovery

                cluster_discovery = EventClusterDiscovery.model_validate(cached_cluster)
                logger.info("事件聚类缓存命中 query=%s", request.query[:40])
            except Exception as exc:
                logger.warning("聚类缓存反序列化失败: %s", exc)
        if cluster_discovery is None:
            try:
                cluster_discovery = discover_event_clusters(
                    request.query,
                    csv_event_names,
                    events_index,
                    seed_plan=plan,
                    locale=request.locale,
                )
                if cluster_discovery.source != "rules_fallback":
                    remember_cluster(
                        request.query,
                        locale=request.locale,
                        cluster_discovery=cluster_discovery.model_dump(),
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

    if multi_event_dashboard and (
        not event_filter_override or len(event_filter_override) < 2
    ):
        scope, canonicals = expand_event_scope(
            scope_mode=scope_mode if scope_mode != "single_event" else "comprehensive",
            matched_event=plan.matched_event,
            matched_module=plan.matched_module,
            csv_event_filter=plan.csv_event_filter,
            query=request.query,
            events_index=events_index,
            csv_event_names=csv_event_names,
        )
        if len(scope) >= 2:
            event_filter_override = scope
            if len(canonicals) >= 2:
                plan = plan.model_copy(update={"comparison_events": canonicals})

    clear_display_alias_cache()
    alias_refs = collect_scope_event_refs(
        matched_event=plan.matched_event,
        comparison_events=plan.comparison_events,
        csv_event_filter=sorted(event_filter_override)
        if event_filter_override
        else plan.csv_event_filter,
        events_index=events_index,
    )
    warm_display_aliases(
        alias_refs,
        events_index,
        locale=request.locale,
        use_llm=os.getenv("EVENT_DISPLAY_USE_LLM", "false").lower()
        in ("1", "true", "yes"),
    )

    try:
        user_mode = request.analysis_mode

        funnel_focused = wants_funnel_analysis(request.query)
        if funnel_focused and (plan.analysis_type == "funnel" or plan.comparison_events):
            funnel_scope = infer_csv_filter_for_comparison(
                plan.comparison_events or [plan.matched_event],
                events_index,
                csv_event_names,
                query=request.query,
            )
            if funnel_scope:
                event_filter_override = set(funnel_scope)

        comparison_steps = plan.comparison_events or []
        if funnel_focused and len(comparison_steps) >= 2:
            return _attach_agent_trace(
                run_funnel_dashboard(
                    plan,
                    event_def,
                    df,
                    query=request.query,
                    events_index=events_index,
                    csv_event_names=csv_event_names,
                    event_filter_override=event_filter_override,
                    locale=request.locale,
                ),
                agent_trace,
            )

        if (
            use_comprehensive
            and event_filter_override
            and len(event_filter_override) >= 2
            and multi_event_dashboard
            and not funnel_focused
        ):
            if cluster_discovery is None:
                cluster_discovery = build_discovery_from_scope(
                    request.query,
                    event_filter_override,
                    events_index,
                    csv_event_names,
                    seed_plan=plan,
                )
            return _attach_agent_trace(
                run_comprehensive_analysis(
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
                    locale=request.locale,
                ),
                agent_trace,
            )

        if should_run_exploratory(
            plan, request.query, user_mode=user_mode
        ) and not funnel_focused:
            feasible = detect_feasible_analysis_types(columns)
            if len(feasible) >= 2:
                reason = build_exploratory_reason(
                    plan,
                    request.query,
                    user_mode=user_mode,
                    feasible_count=len(feasible),
                )
                return _attach_agent_trace(
                    run_exploratory_analysis(
                        plan,
                        event_def,
                        df,
                        columns,
                        reason=reason,
                        query=request.query,
                        event_filter_override=event_filter_override,
                        events_index=events_index,
                        locale=request.locale,
                    ),
                    agent_trace,
                )

        return _attach_agent_trace(
            _run_single_analysis(
                plan,
                event_def,
                df,
                query=request.query,
                event_filter_override=event_filter_override,
                events_index=events_index,
                locale=request.locale,
            ),
            agent_trace,
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
