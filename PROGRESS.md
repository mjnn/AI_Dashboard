# AI 座舱埋点看板 — 进度快照

> 固化时间：2026-06-02  
> 用途：新会话快速恢复上下文；完整规格见 `spec/AI埋点数据看板系统_SPEC_v4.0.md`。  
> 线上：http://47.116.180.173/tools/ai-dashboard/

---

## 1. 项目目标

自然语言驱动的座舱埋点分析看板：用户输入问题 → LLM/Agent 生成分析计划 → 后端按注册表聚合 CSV → 前端 ECharts 渲染，每张图附带可读口径说明。

**工作区**：`D:\AIG_Projects\AI_DashBoard`

---

## 2. 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI、pandas、Pydantic、uvicorn、openai SDK（DeepSeek 兼容） |
| 前端 | React 18、TypeScript、Vite 5、Tailwind 3、echarts-for-react、i18next |
| LLM | `deepseek-v4-flash`（`backend/data/llm_settings.json` 可切换） |
| 数据 | `events_dict.json`（1312 事件）、CSV 数据池（ECS 挂载 `/srv/data/ai-dashboard/csv`） |

---

## 3. 核心架构

```
用户问题 + analysis_mode + locale
    ↓
[Agent 路径] analysis_agent：意图 → 故事 → 可视化提案 → 数据可行性校验 → AnalysisPlan
[Legacy 路径] llm_planner.generate_plan()
    ↓
repair / normalize_plan_for_analysis()  ← analysis_registry.py
    ↓
[exploratory?] → exploratory_analyzer 批量子计划
[single]       → csv_processor.process_csv()
    ↓
chart_builder.build() → ChartConfig（含 caliber_detail）
    ↓
dashboard_narrator → presentation（可选）
    ↓
前端 Dashboard / ExploratoryDashboard + PanelCaliberBlock
```

**设计原则**：LLM 只选 `analysis_type` 和参数；衍生维度（留存分桶、新老用户等）由后端确定性计算，禁止编造 CSV 列名。

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

### 4.2 图表口径说明（2026-06-02 新增）

每张图表面板底部可展开 **PanelCaliberBlock**，后端 `panel_caliber.py` 生成结构化口径：

| 区块 | 内容 |
|------|------|
| **图表构成** | 横纵轴、分析窗口、图表类型怎么读 |
| **统计口径** | 分析类型业务描述（来自注册表） |
| **分组规则** | 衍生维度判定（新老用户、分桶、漏斗步骤等） |
| **使用事件** | 本图实际用到的埋点 |
| **指标计算** | 各 metric 的自然语言公式 |

21 种 analysis_type 全覆盖；探索模式不再使用「探索性分析：XXX」占位文案。

### 4.3 留存分桶（usage_retention）

- **11 个固定分桶**：使用1次 … 使用10次、使用10次以上
- 空桶补 0，图表始终完整
- **频次分布**（usage_distribution）仍为全量逐次分桶（使用11次、使用172次…）

### 4.4 Agent 分析规划

`backend/services/analysis_agent.py`：多轮 LLM 规划 + `data_feasibility` 校验 + `agent_payload_repair` schema 修复。

配套模块：

- `analysis_intent.py` — 意图与范围（集中正则 fallback）
- `analysis_route_memory.py` — 路由签名缓存（`backend/data/analysis_route_cache/`）
- `event_display.py` — 事件名本地化展示
- `multi_event_analysis.py` — 漏斗/多事件对比增强

### 4.5 分析模式

| 模式 | 行为 |
|------|------|
| **auto** | 意图模糊 / 低置信度 → 探索；否则精准单图 |
| **precise** | 始终单一分析 |
| **exploratory** | 批量可行分析（Carlog 约 16 面板） |

### 4.6 其他已实现

- 数据管理页、字典树编辑、边测边改、图表配色主题
- LLM 推荐 + 看板叙事 + i18n（中/英）
- ECS Docker + Nginx subpath `/tools/ai-dashboard/`
- CSV 宿主机持久化 volume
- **测试收敛**：`tests/test_analysis_coverage.py`、`test_analysis_performance.py`、`run_analysis_convergence.py`

---

## 5. 关键文件索引

### 后端

| 文件 | 职责 |
|------|------|
| `main.py` | 路由、Agent/探索/单图分发 |
| `services/analysis_agent.py` | Agent 多轮规划 |
| `services/analysis_registry.py` | 21 分析类型 + 图表目录 + repair |
| `services/csv_processor.py` | 聚合（含留存分桶 1–10+） |
| `services/panel_caliber.py` | **图表口径与构成说明** |
| `services/chart_builder.py` | ChartConfig 组装 |
| `services/exploratory_analyzer.py` | 探索模式 |
| `services/llm_planner.py` | Legacy LLM 计划 |
| `services/dashboard_narrator.py` | 看板叙事 |
| `services/analysis_route_memory.py` | 路由缓存 |
| `tests/fixtures/plan_factory.py` | 21 类型测试计划工厂 |

### 前端

| 文件 | 职责 |
|------|------|
| `components/PanelCaliberBlock.tsx` | **口径展开 UI** |
| `components/AnalysisPanelCard.tsx` | 单面板卡片 |
| `components/Dashboard.tsx` / `ExploratoryDashboard.tsx` | 看板布局 |
| `components/charts/*` | 12 种图表 |

---

## 6. API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 服务状态、数据池 |
| GET | `/api/recommendations` | LLM 分析推荐 |
| POST | `/api/analyze` | 主分析（支持 `locale`） |

---

## 7. 环境与运行

```bash
# 后端
cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 前端
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
```

### 测试（改分析链路后必跑）

```bash
cd backend
python -m pytest tests/test_analysis_coverage.py -k "not llm" -v
python -m pytest tests/test_analysis_performance.py -k "not llm" -v
python -m pytest tests/test_chart_builder_caliber.py -v
python tests/run_analysis_convergence.py
```

### ECS 部署

```bash
./scripts/deploy-to-ecs.sh
# 或 Windows Git Bash：bash scripts/deploy-to-ecs.sh
```

---

## 8. 验证过的场景

- 「Carlog进入最近7天每日趋势」→ time_series
- 「Carlog各使用频次留存」→ usage_retention（11 桶）
- 「Carlog新老用户」→ new_vs_returning + 口径含分组规则
- 「分析一下 Carlog」+ exploratory → 多面板 + 各面板口径
- 漏斗 / 多事件对比（Carlog 多 event CSV）

---

## 9. 已知限制 / 待办

- [ ] `period_pattern` 按小时仅 1 桶（Carlog CSV 时间均为 00:00:00）
- [ ] 探索模式 + LLM 叙事耗时 30–70s
- [ ] 百万级数据需 OLAP
- [ ] 路由缓存、llm_settings 为运行时文件，不进 Git

---

## 10. 新会话恢复清单

1. 读本文档 + `spec/AI埋点数据看板系统_SPEC_v4.0.md`
2. 确认 `backend/.env` 有 `DEEPSEEK_API_KEY`
3. 改口径文案 → `panel_caliber.py` + `PanelCaliberBlock.tsx`
4. 改聚合逻辑 → `csv_processor.py` + `analysis_registry.py`
5. 改 Agent → `analysis_agent.py` + `agent_payload_repair.py`
6. 部署 → `scripts/deploy-to-ecs.sh`

---

## 11. 规格参考

- **`spec/AI埋点数据看板系统_SPEC_v4.0.md`** — 当前可交付规格（首选）
- `spec/AI埋点数据看板系统_SPEC_v3.0.md` — 历史参考
