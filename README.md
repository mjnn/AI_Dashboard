# AI 座舱埋点看板

基于自然语言的 AI 埋点数据分析看板系统。

**线上入口**：http://47.116.180.173/tools/ai-dashboard/  
**进度快照**：见 [PROGRESS.md](./PROGRESS.md)  
**完整规格**：见 [spec/AI埋点数据看板系统_SPEC_v4.0.md](./spec/AI埋点数据看板系统_SPEC_v4.0.md)

## 技术栈

- **后端**: Python FastAPI + pandas + openai (DeepSeek 兼容) + pydantic + uvicorn
- **前端**: React 18 + TypeScript + Vite 5 + Tailwind CSS 3 + ECharts 5 + i18next

## 快速开始

### 后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 编辑填入 DEEPSEEK_API_KEY 和 CSV_DATA_PATH
uvicorn main:app --reload
```

健康检查: `GET http://localhost:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://127.0.0.1:5173，输入自然语言分析问题即可生成图表。每张图可展开查看 **图表构成 / 统计口径 / 指标计算**。

## 目录结构

```
backend/          FastAPI 服务
frontend/         React 前端
spec/             产品规格文档
PROGRESS.md       当前进度快照（新会话必读）
scripts/          ECS 部署脚本
```

## 测试

```bash
cd backend
python -m pytest tests/test_analysis_coverage.py -k "not llm" -q
python -m pytest tests/test_chart_builder_caliber.py -q
python tests/run_analysis_convergence.py   # 覆盖 + 性能一键收敛
```

## 部署（ECS）

```bash
bash scripts/deploy-to-ecs.sh
```

构建前端 → 打包上传 → Docker 构建推送 ACR → compose up → Nginx reload。详见规格文档 §2.2。

## 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（仅存于 backend/.env 或 ECS `.env.runtime`，勿提交） |
| `CSV_DATA_PATH` | CSV **数据目录**；ECS 默认挂载 `/data/csv` |
| `VITE_BASE` / `VITE_API_BASE` | 生产 subpath，须与 Nginx 一致 |

## 安全说明

- `.env` 已加入 `.gitignore`，请勿将 API Key 提交到版本库
- LLM 公式指标仅允许安全字符，防止代码注入
