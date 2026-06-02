# AI 座舱埋点看板 — 进度快照

> 固化时间：2026-06-01  
> 用途：新会话快速恢复上下文；完整规格见 `spec/AI埋点数据看板系统_SPEC_v3.0.md`。

---

## 1. 项目目标

自然语言驱动的座舱埋点分析看板：用户输入问题 → LLM 生成分析计划 → 后端按注册表聚合 CSV → 前端 ECharts 渲染。

**工作区**：`D:\AIG_Projects\AI_DashBoard`

---

## 2. 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI、pandas、Pydantic、uvicorn、openai SDK（DeepSeek 兼容） |
| 前端 | React 18、TypeScript、Vite 5、Tailwind 3、echarts-for-react |
| LLM | `deepseek-v4-flash`，base URL `https://api.deepseek.com/v1` |
| 数据 | `backend/data/events_dict.json`（1312 事件）、`backend/data/*.csv` 数据池（当前 Carlog.csv ~10 万行） |

---

## 3. 核心架构

```
用户问题 + analysis_mode
    ↓
LLM generate_plan() → AnalysisPlan（含 analysis_type、metrics、visualization）
    ↓
normalize_plan_for_analysis()  ← analysis_registry.py
    ↓
[exploratory?] → exploratory_analyzer 批量子计划
[single]       → csv_processor.process_csv()
    ↓
chart_builder.build() → ChartConfig
    ↓
前端 Dashboard / ExploratoryDashboard
```

**设计原则**：LLM 只选 `analysis_type` 和参数；衍生维度（留存分桶、新老用户等）由后端计算，禁止编造 CSV 列名。

---

## 4. 已完成功能

### 4.1 分析类型注册表（21 种）

文件：`backend/services/analysis_registry.py`

| 类别 | analysis_type |
|------|---------------|
| 基础 | time_series, dimension_breakdown, top_n_ranking, summary_kpi, penetration, cross_dimension |
| 用户行为 | usage_retention, usage_distribution, active_days_distribution, new_vs_returning, repeat_rate, percentile_stats |
| 时间 | period_pattern, growth_rate, heatmap_time, first_touch_trend, cohort_retention |
| 活跃/转化 | active_users, stickiness, funnel, event_comparison |

每种含：`chart_types`（可选图表）、`default_chart`、`chart_guide`（选型提示）。

### 4.2 图表类型（12 种）

`line` `area` `multi_line` `dual_axis` `bar` `horizontal_bar` `stacked_bar` `pie` `table` `heatmap` `gauge` `funnel_chart`

- LLM 选的 chart_type 不在允许范围 → `normalize_visualization_chart()` 自动回退 default
- 前端组件：`frontend/src/components/charts/*` + `ChartRouter.tsx`

### 4.3 分析模式（用户可手动切换）

请求字段：`analysis_mode: auto | precise | exploratory`

| 模式 | 行为 |
|------|------|
| **auto**（默认） | 意图模糊 / 低置信度 → 探索；否则精准单图 |
| **precise** | 始终单一分析（LLM 计划） |
| **exploratory** | 始终批量跑 CSV 可行分析（Carlog 约 16 面板） |

前端：`InputPanel.tsx` 三档切换；`useAnalysis` 重试保留模式。

探索触发逻辑：`backend/services/exploratory_analyzer.py` → `should_run_exploratory()`

### 4.4 探索性分析排版

- 响应 `mode: "exploratory"`，`panels[]` 含 layout：`kpi | wide | half | compact`
- 前端三区：核心指标（4 列）→ 趋势与变化（2 列宽图）→ 用户行为与分布（2 列）
- 探索页 max-width 1400px

### 4.5 其他已实现

- 事件字典预处理、模糊匹配、CSV 编码 fallback（utf-8/gbk）
- 时间轴补全、Carlog 事件别名（`Carlog_进入` ↔ `Carlog进入`）
- CORS、路径穿越防护、安全 pd.eval
- 统一错误响应、健康检查 enriched
- **智能分析推荐**：输入框聚焦时调用 `/api/recommendations`，LLM 基于 CSV 数据画像生成 4~6 条可点击的分析问题（替代原「可用事件快捷选择」）
- **看板叙事（LLM）**：分析完成后由 LLM 对图表面板分类（sections）、生成生动标题/洞察文案（`presentation` 字段）；前端样式参照 `ref/座舱埋点运营看板_v3.3.html`（玻璃拟态、渐变背景、分区 sec-head）

---

## 5. 关键文件索引

### 后端

| 文件 | 职责 |
|------|------|
| `main.py` | 路由、探索/单图分发 |
| `config.py` | `.env`、CSV 路径解析 |
| `schemas/analysis.py` | 全部 Pydantic 模型 |
| `services/llm_planner.py` | DeepSeek 调用、prompt、计划校验 |
| `services/analysis_registry.py` | 21 分析类型 + 12 图表目录 |
| `services/csv_processor.py` | CSV 过滤、聚合、各类型 handler |
| `services/exploratory_analyzer.py` | 探索模式计划生成与批量执行 |
| `services/chart_builder.py` | ChartConfig 组装 |
| `services/field_resolver.py` | 事件/字段 CSV 优先解析 |
| `services/event_scope.py` | 模块级 event 范围推断 |
| `services/dict_preprocessor.py` | events_dict.json 索引 |
| `services/data_profiler.py` | CSV 数据画像（行数、时间跨度、事件、VIN 等） |
| `services/recommendation_service.py` | LLM 分析推荐生成与缓存 |
| `services/dashboard_narrator.py` | LLM 看板分类 + 生动标题/洞察文案 |

### 前端

| 文件 | 职责 |
|------|------|
| `App.tsx` | 主流程 |
| `hooks/useAnalysis.ts` | 状态机 + mode |
| `components/InputPanel.tsx` | 输入 + 模式切换 + LLM 分析推荐 |
| `components/Dashboard.tsx` | single / exploratory 路由 |
| `components/ExploratoryDashboard.tsx` | 多面板布局 |
| `components/AnalysisPanelCard.tsx` | 单面板卡片 |
| `services/api.ts` | `/api/analyze` 等 |

---

## 6. API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 服务状态、事件数、数据池 |
| GET | `/api/events` | 按模块分组事件列表 |
| GET | `/api/recommendations` | 基于数据池画像的 LLM 分析推荐 |
| GET | `/api/analysis-types` | 分析类型 + 图表类型注册表 |
| POST | `/api/analyze` | 主分析接口 |

**Analyze 请求体示例**：

```json
{
  "query": "Carlog最近7天每日趋势",
  "analysis_mode": "auto"
}
```

**响应**：`mode`, `plan`, `execution`, `chart_config`, 探索时额外 `panels`, `panel_count`, `exploratory_reason`

---

## 7. 环境与运行

### `.env`（backend/.env）

```
DEEPSEEK_API_KEY=sk-...
CSV_DATA_PATH=./data
# DEFAULT_CSV_FILENAME=Carlog.csv
```

### 启动命令

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
- Vite proxy：`/api` → `:8000`

### 当前 CSV 列

`vin_code`, `date`, `event` — 可支撑约 15 类分析；无额外维度列故 dimension_breakdown / funnel / event_comparison 在探索模式中跳过。

---

## 8. 验证过的场景

- 「Carlog进入最近7天每日趋势」→ time_series 折线
- 「Carlog使用1次和2次的车辆数」→ usage_retention
- 「分析一下 Carlog」+ auto/exploratory → 16 面板探索
- 「分析一下 Carlog」+ precise → 单一 LLM 计划
- 向后兼容：无 `analysis_type` 的旧计划可 infer

---

## 9. 已知限制 / 待办

- [ ] 多事件漏斗/对比需 CSV 含多事件或 `comparison_events`
- [ ] `period_pattern` 按小时仅 1 桶（Carlog CSV 时间均为 00:00:00）
- [ ] 探索模式耗时较长（16 次聚合），前端 timeout 120s
- [ ] cohort_retention 数据量大时面板较密
- [ ] 未接 ClickHouse/OLAP，大数据量需后续扩展
- [ ] git 提交策略：用户未要求则不自动 commit

---

## 10. 新会话恢复清单

1. 读本文档 + `README.md`
2. 确认 `backend/.env` 有 API Key
3. 启动前后端（见 §7）
4. 改分析逻辑 → `analysis_registry.py` + `csv_processor.py`
5. 改探索行为 → `exploratory_analyzer.py` + `main.py`
6. 改 LLM prompt → `llm_planner.py`（catalog 从 registry 注入）
7. 改 UI → `InputPanel` / `ExploratoryDashboard` / chart 组件

---

## 11. 规格参考

- **`spec/AI埋点数据看板系统_SPEC_v3.0.md`** — 当前可交付规格（架构、API、测试、验收）
- `spec/AI埋点数据看板系统_SPEC_v2.0.docx` — 原始产品规格（部分已演进）
