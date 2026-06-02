# AI 座舱埋点看板

基于自然语言的 AI 埋点数据分析看板系统。

## 技术栈

- **后端**: Python FastAPI + pandas + openai (DeepSeek 兼容) + pydantic + uvicorn
- **前端**: React 18 + TypeScript + Vite 5 + Tailwind CSS 3 + ECharts 5

## 快速开始

### 后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 编辑填入 DEEPSEEK_API_KEY 和 CSV_DATA_PATH
uvicorn main:app --reload
```

健康检查: `GET http://localhost:8000/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://127.0.0.1:5173，输入自然语言分析问题即可生成图表。

生产环境可通过 `VITE_API_BASE` 指定 API 地址（默认使用相对路径 `/api`）。

## 目录结构

```
backend/          FastAPI 服务
frontend/         React 前端
spec/             产品规格文档
PROGRESS.md       当前进度快照（新会话必读）
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（仅存于 backend/.env，勿提交） |
| `CSV_DATA_PATH` | CSV **数据目录**（相对 backend），如 `./data`；目录下放多个 `.csv` |
| `DEFAULT_CSV_FILENAME` | 可选，未指定分析文件时使用的默认 CSV 文件名 |

修改 `.env` 后无需重启，下次分析请求自动生效。

## 安全说明

- `.env` 已加入 `.gitignore`，请勿将 API Key 提交到版本库
- `csv_filename` 仅允许 `CSV_DATA_PATH` 目录下的 `.csv` 文件名
- LLM 公式指标仅允许安全字符，防止代码注入
