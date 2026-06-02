# AI 座舱埋点看板系统 — 产品与技术规格 v3.0

> 版本：v3.0  
> 日期：2026-06-01  
> 状态：**可交付**（已通过 19 项集成测试 + 前端生产构建）  
> 工作区：`D:\AIG_Projects\AI_DashBoard`

---

## 1. 产品概述

### 1.1 目标

面向座舱埋点运营/产品/数据同学，提供**自然语言驱动的分析看板**：用户描述分析问题 → 系统理解意图 → 自动选分析类型与图表 → 基于数据池 CSV 聚合 → 渲染可视化与运营叙事。

### 1.2 核心价值

| 能力 | 说明 |
|------|------|
| 零 SQL | 自然语言提问，无需手写查询 |
| 数据池即插即用 | 将 CSV 放入 `backend/data/`，自动合并分析，无需选手动文件 |
| 智能 + 精准 + 探索 | 三种分析模式，兼顾效率与全面性 |
| 字典增强 | 1312 事件埋点字典提供属性语义；映射失败时 CSV 兜底，不阻断分析 |
| 运营叙事 | LLM 对图表面板分区、起标题、写洞察 |

### 1.3 非目标（v3.0）

- 不接 ClickHouse / 实时 OLAP
- 不做用户权限与多租户
- 不做 CSV 上传 UI（文件由运维/脚本放入 data 目录）

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│  前端 React + Vite + ECharts                                 │
│  InputPanel → useAnalysis → Dashboard / ExploratoryDashboard │
└───────────────────────────┬─────────────────────────────────┘
                            │ POST /api/analyze
┌───────────────────────────▼─────────────────────────────────┐
│  FastAPI (main.py)                                           │
│  ├─ load_data_pool()        合并 data/*.csv                  │
│  ├─ generate_plan()         DeepSeek → AnalysisPlan          │
│  ├─ field_resolver          事件/字段 CSV 优先解析           │
│  ├─ exploratory_analyzer    探索模式批量面板                 │
│  ├─ csv_processor           21 种 analysis_type 聚合       │
│  ├─ chart_builder           ChartConfig                      │
│  └─ dashboard_narrator      看板分区与文案                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  events_dict.json     backend/data/*.csv    DeepSeek API
  (1312 事件)          (数据池)              (deepseek-v4-flash)
```

### 2.1 设计原则

1. **LLM 只选意图**：`analysis_type`、指标、图表、时间范围；不编造聚合逻辑。
2. **后端注册表驱动**：21 种 `analysis_type` + 12 种 `chart_type` 在 `analysis_registry.py` 注册，LLM 从 catalog 中选择。
3. **CSV 为事实来源，字典为增强**：event 列取值、CSV 列名优先；字典提供属性说明与别名。
4. **不因名称不匹配而 502**：解析失败走虚拟 event / 列模糊匹配，降级为 partial 而非整体失败。

---

## 3. 数据层

### 3.1 数据池

| 配置项 | 说明 |
|--------|------|
| `CSV_DATA_PATH` | CSV 目录，默认 `./data` |
| 加载方式 | `load_data_pool()` 读取目录下全部 `.csv` 并 `pd.concat` |
| 空目录 | 返回 422，提示放入 CSV |

**当前样例数据**：`Carlog.csv`，约 103,916 行；列 `vin_code`, `date`, `event`；event 含 `carlog_entry/exit/record` 等 5 种。

### 3.2 事件字典

- 路径：`backend/data/events_dict.json`
- 启动时由 `DictPreprocessor` 构建索引：`events`, `alias_index`, `normalized_index`, `modules`
- **别名策略**：属性 `label`（CSV event code）**覆盖注册**；泛化别名（模块名等）**setdefault**，避免 `carlog` 误绑错误事件

### 3.3 字段解析（field_resolver.py）

解析优先级：

```
精确 canonical / alias
  → CSV event 值反查（含上下文消歧）
  → 字典模糊匹配
  → CSV 虚拟 event（unmapped=true，分析仍继续）
```

列名解析：`normalize → 字典属性 → 子串 → difflib 模糊`

模块级 query（如「carlog」）通过 `infer_related_csv_events` 纳入全部 `carlog_*` 事件过滤。

---

## 4. 分析能力

### 4.1 分析类型（21 种）

| 类别 | analysis_type |
|------|---------------|
| 基础 | time_series, dimension_breakdown, top_n_ranking, summary_kpi, penetration, cross_dimension |
| 用户行为 | usage_retention, usage_distribution, active_days_distribution, new_vs_returning, repeat_rate, percentile_stats |
| 时间 | period_pattern, growth_rate, heatmap_time, first_touch_trend, cohort_retention |
| 活跃/转化 | active_users, stickiness, funnel, event_comparison |

定义文件：`backend/services/analysis_registry.py`

### 4.2 图表类型（12 种）

`line` `area` `multi_line` `dual_axis` `bar` `horizontal_bar` `stacked_bar` `pie` `table` `heatmap` `gauge` `funnel_chart`

LLM 选择不在允许范围时，`normalize_visualization_chart()` 回退 default。

### 4.3 分析模式

| 模式 | 请求值 | 行为 |
|------|--------|------|
| 智能 | `auto` | 意图明确 → 单图；模糊/低置信度 → 探索 |
| 精准 | `precise` | 始终执行 LLM 单一计划 |
| 探索 | `exploratory` | 批量运行数据池可行分析（Carlog 约 16 面板） |

---

## 5. API 规格

### 5.1 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 服务状态、事件数、数据池就绪 |
| GET | `/api/events` | 按模块分组的事件列表 |
| GET | `/api/recommendations` | 基于数据池画像的 LLM 分析推荐 |
| GET | `/api/analysis-types` | 分析类型 + 图表注册表 |
| POST | `/api/analyze` | **主分析接口** |

> v3.0 已移除 `/api/csv-files`（不再支持选手动 CSV）。

### 5.2 POST /api/analyze

**请求体**

```json
{
  "query": "carlog最近7天每日趋势",
  "analysis_mode": "auto"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 1–500 字自然语言 |
| analysis_mode | string | 否 | `auto` / `precise` / `exploratory`，默认 auto |

**响应（single）**

```json
{
  "mode": "single",
  "plan": { "analysis_type": "time_series", "matched_event": "Carlog_进入", "...": "..." },
  "execution": {
    "status": "success",
    "total_rows": 103916,
    "filtered_rows": 96702,
    "unavailable_dimensions": [],
    "execution_time_ms": 1200
  },
  "chart_config": { "chart_type": "line", "title": "...", "data": [] },
  "panel_count": 1,
  "presentation": {
    "headline": "...",
    "sections": []
  }
}
```

**响应（exploratory）** 额外字段：`panels[]`, `panel_count`, `exploratory_reason`

**错误码**

| HTTP | 场景 |
|------|------|
| 422 | 数据池为空、参数校验失败 |
| 502 | LLM 调用失败、计划 JSON 校验失败 |
| 503 | 事件字典尚未加载 |
| 500 | 数据处理异常 |

---

## 6. 前端规格

### 6.1 技术栈

React 18、TypeScript、Vite 5、Tailwind 3、echarts-for-react

### 6.2 页面结构

- **InputPanel**：自然语言输入、三档分析模式、聚焦时 LLM 分析推荐（无 CSV 文件选择）
- **Dashboard**：单图模式
- **ExploratoryDashboard**：多面板分区（KPI / 趋势 / 行为），max-width 1400px
- **样式**：玻璃拟态 + 渐变，参照 `ref/座舱埋点运营看板_v3.3.html`

### 6.3 代理与超时

- Vite dev：`/api` → `http://127.0.0.1:8000`
- 请求超时：120s（探索模式可能 30–70s）

---

## 7. 配置与部署

### 7.1 环境变量（backend/.env）

```env
DEEPSEEK_API_KEY=sk-...
CSV_DATA_PATH=./data
```

### 7.2 启动

```bash
# 后端
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 前端
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

- 前端：http://127.0.0.1:5173  
- API 文档：http://127.0.0.1:8000/docs  

### 7.3 新增数据流程

1. 将新 CSV 放入 `backend/data/`
2. 重启后端（或依赖 `--reload`）
3. 数据池自动合并；推荐缓存随文件 mtime 失效

---

## 8. 测试与验收

### 8.1 自动化测试

```bash
cd backend
python -m unittest tests.test_integration -v
```

**覆盖范围（19 项）**

| 套件 | 内容 |
|------|------|
| TestDataPool | 数据池加载、event 列、数据画像 |
| TestFieldResolver | carlog 消歧、别名变体、列解析 |
| TestProcessCsv | 带 event 过滤 override 的时间序列聚合 |
| TestApiNoLlm | health / events / analysis-types / 空 query / csv-files 已移除 |
| TestApiWithLlm | 推荐、carlog auto、精准趋势、探索、留存分桶 |

### 8.2 验收场景（已通过）

| 场景 | 预期 |
|------|------|
| `carlog` + auto | matched=Carlog_进入，filtered>0，exploratory 16 panels |
| `Carlog进入最近7天每日趋势` + precise | single + 折线图 |
| `全面分析一下carlog` + exploratory | ≥2 panels |
| `carlog使用1次和2次的车辆数` + precise | usage_retention 有数据 |
| 输入框聚焦 | 推荐 ≥3 条 |

### 8.3 前端构建

```bash
cd frontend && npm run build   # tsc + vite build，须通过
```

---

## 9. 关键文件索引

| 文件 | 职责 |
|------|------|
| `backend/main.py` | 路由、数据池、分析分发 |
| `backend/config.py` | 环境变量、数据池路径 |
| `backend/services/field_resolver.py` | **事件/字段统一解析（CSV 优先）** |
| `backend/services/llm_planner.py` | DeepSeek 计划生成与修复 |
| `backend/services/csv_processor.py` | 数据池加载、聚合 |
| `backend/services/exploratory_analyzer.py` | 探索模式 |
| `backend/services/analysis_registry.py` | 分析/图表注册表 |
| `backend/services/dashboard_narrator.py` | 看板叙事 |
| `backend/services/recommendation_service.py` | 智能推荐 |
| `backend/tests/test_integration.py` | 集成测试 |
| `frontend/src/components/InputPanel.tsx` | 输入与推荐 |
| `frontend/src/components/ExploratoryDashboard.tsx` | 多面板布局 |

---

## 10. 已知限制与后续

| 项 | 说明 |
|----|------|
| 探索模式耗时 | 16 面板 + LLM 叙事，约 30–70s |
| 时间粒度 | 当前 Carlog CSV 的 date 均为 00:00:00，按小时模式仅 1 桶 |
| 维度列 | 无额外维度列时，dimension_breakdown / funnel 等在探索中跳过 |
| 未映射事件 | 可分析但 `event_resolution.unmapped=true`，建议补字典 |
| 大数据 | 10 万行 CSV 可跑；百万级需 OLAP |
| 前端包体积 | ECharts 导致 bundle >500KB，可后续 code-split |

---

## 11. v2.0 → v3.0 变更摘要

| 变更 | v2.0 | v3.0 |
|------|------|------|
| 数据源 | 单 CSV + 文件选择 UI | **数据池**自动合并 `data/*.csv` |
| 事件校验 | LLM 白名单硬拒绝 → 502 | **field_resolver** CSV 优先，虚拟 event 兜底 |
| carlog 解析 | 易误绑 / 502 | 上下文消歧 + 多 event 过滤 |
| API | `/api/csv-files` | 已移除 |
| 看板叙事 | 无 | LLM sections + presentation |
| 测试 | 无 | 19 项集成测试 |
| 推荐 | 事件快捷选择 | LLM 基于数据画像推荐 |

---

## 12. 交付清单

- [x] 自然语言分析主流程
- [x] 数据池自动加载（无选手动文件）
- [x] 21 分析类型 + 12 图表
- [x] 三种分析模式 + 探索多面板
- [x] 事件/字段 CSV 优先解析
- [x] LLM 推荐 + 看板叙事
- [x] 集成测试 19/19 通过
- [x] 前端生产构建通过
- [x] 规格文档 v3.0

---

*本文档取代 v2.0 docx 中与实现不一致的部分，以本仓库代码与测试为准。*
