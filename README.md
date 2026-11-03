# 可研报告生成Agent

氢能项目可行性研究报告生成 Agent。当前进度：**阶段 2-3（查看修改 + 导出 Word + 埋点 + 评测）**，后端 MVP 到此结束。正式界面属于阶段 3（本次不上线，D13）。

## 一、这个阶段能做什么

| 功能 | 状态 |
| --- | --- |
| F1 资料上传（PDF / .docx / .md / .txt，≤100 MB，批量，逐份状态，可删除） | ✅ |
| 页面 | 首页（报告列表）/ 资料库 / 创建报告 / 大纲编辑（3-2）；进度与查看导出在 3-3 |
| F2 报告列表（名称、状态、章数） | ✅ |
| F3 创建报告（标题、目标字数 ≤18,000、补充要求） | ✅ |
| F4 生成大纲（真调 DeepSeek，8–13 章，字数调平、可编辑保存） | ✅ |
| F5 一键写全文：提炼关键事实 → 逐章检索/写/控字数/审计/重写（≤2）→ 定稿；进度可看、刷新不中断、失败可从第 N 章继续 | ✅ |
| F6 查看与修改：章节目录带状态、`[待补充]` 黄底、待人工章错误句红底 + 「应为××，依据××（文件名）」、章末提示、本章参考资料、正文可改可存 | ✅ |
| F7 导出 Word：标题 + 每章一级标题 + 段落，`[待补充]` 黄色高亮，句末 `[文件名]` 保留；同时算改动比例（<15% 算采纳） | ✅ |
| 埋点 E1–E3、13 题评测与 10 条程序检查 | ✅ |
| 正式界面 | 阶段 3 |

## 二、启动（两个终端）

**终端 1：后端（端口 8010）**

```bash
cd projects/可研报告生成Agent/backend
cp .env.example .env          # 第一次：复制配置模板
# 编辑 .env，把 DEEPSEEK_API_KEY= 后面填上你的 Key
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

**终端 2：前端（端口 3000，阶段 3 正式界面）**

```bash
cd projects/可研报告生成Agent/frontend
cp .env.example .env.local    # 第一次；里面只有 BACKEND_URL=http://127.0.0.1:8010
npm install                   # 第一次
npm run build && npm run start   # 或开发时用 npm run dev
```

浏览器打开 **http://127.0.0.1:3000**。
前端通过 `proxy.ts` 把 `/api/*` 同源转发到后端，浏览器不直连 8010、也不接触任何密钥。
阶段 2 的临时验收界面（后端 `/`）已在 3-1 废弃，现在访问 8010 只会看到一句说明。

- Key 去哪拿：<https://platform.deepseek.com> → 注册/登录 → 充值（10 元够用很久）→ 左侧「API keys」→「创建 API key」→ 复制（只显示一次）→ 粘贴到 `.env` 的 `DEEPSEEK_API_KEY=` 后面 → 重启服务。
- 没有 Key 也能用完资料上传、建报告；点「生成大纲」会提示「还没有配置 DeepSeek API Key」。

### 环境（已在本机装好，换机器时按这里来）

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.12.16 | 用 `uv` 装在 `~/.local/share/uv/python/`；虚拟环境在 `backend/.venv` |
| 依赖 | 见 `backend/requirements.txt` | `.venv/bin/pip install -r requirements.txt` |
| 数据库 | SQLite | `data/app.db`，迁移用 `backend/.venv/bin/alembic upgrade head` |
| 模型 | DeepSeek `deepseek-chat` | OpenAI 兼容接口，`base_url=https://api.deepseek.com` |

## 三、怎么验证这一步是对的

### 自动检查（几十秒）

```bash
cd projects/可研报告生成Agent/frontend
npm run lint && npx tsc --noEmit && npm test -- --run && npm run build   # 前端四项
cd ../backend
.venv/bin/python -m pytest -q                      # 后端 mock 测试，应该 76 passed
cd ../../..                                        # 回到工具包根目录
bash verify.sh 可研报告生成Agent 阶段2-1            # 六项闸门检查
```

### 真实模型冒烟（会真花几分钱）

```bash
cd projects/可研报告生成Agent
backend/.venv/bin/python scripts/smoke.py 阶段2-3     # 走当前阶段的真实链路
```

### 评测（13 题 × 3 次，约 0.6 元、3 分钟）

```bash
backend/.venv/bin/python scripts/eval_run.py            # 全跑，写 docs/evidence/阶段2-3/评测报告.md
backend/.venv/bin/python scripts/eval_run.py T03 T08    # 只跑指定题
```

跑完会在 `docs/evidence/阶段2-1/冒烟记录.md` 追加真实调用记录（时间、token、耗时、结构校验、重试次数、结果）。没配 Key 时脚本不跑、不写记录，如实记「待验」。

### 手点一遍（产品经理验收用）

见 `docs/evidence/阶段2-1/照着做清单.md`。

## 四、目录

```
backend/
  app/main.py            FastAPI 入口（API + 临时界面）
  app/api/               资料、报告、大纲、健康检查
  app/core/              配置、数据库、统一错误、日志
  app/models/            SQLAlchemy 模型（documents/segments/reports/chapters/model_calls）
  app/schemas/           请求与响应结构
  app/services/          文件校验、解析、切段、DeepSeek 调用、大纲生成
  app/services/prompts/  提示词（大纲）
  app/services/templates/发改委 2023 版编写参考大纲（内置范本，不进资料库）
  static/index.html      临时验收界面
  tests/                 pytest（假模型，离线可跑）
  alembic/               数据库迁移
scripts/
  eval_data/             评测资料 10 份 + 标准答案（D14）
  restart-check.sh       重启恢复检查钩子（verify.sh 调用）
  smoke.py               真实模型冒烟
data/                    app.db、上传原件、模型调用日志（已 gitignore）
```

## 五、接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务状态、模型名、是否配了 Key |
| POST | `/api/documents` | 上传资料（multipart `files`），每份单独返回可用/无文字/失败 |
| GET / DELETE | `/api/documents{/id}` | 资料列表 / 删除 |
| POST / GET | `/api/reports` | 创建 / 列表 |
| GET / DELETE | `/api/reports/{id}` | 详情（含章节）/ 删除 |
| POST | `/api/reports/{id}/outline` | 生成大纲（真调模型） |
| PUT | `/api/reports/{id}/outline` | 保存编辑后的大纲（合计 >18,000 拒绝） |
| POST | `/api/reports/{id}/outline/confirm` | 确认大纲并开始写全文（返回任务） |
| POST | `/api/reports/{id}/write` | 直接开始写全文 |
| GET | `/api/reports/{id}/progress` | 写作进度：任务状态、逐章状态/字数/重写次数/截断、待人工数、冲突提示 |
| POST | `/api/reports/{id}/resume` | 从失败/暂停处继续（沿用同一份关键事实） |
| GET | `/api/reports/{id}/view` | 查看页：目录、顶部汇总、当前章正文与红黄标记、参考资料 |
| GET | `/api/reports/{id}/chapters/{seq}` | 单章正文与标记 |
| PUT | `/api/reports/{id}/chapters/{seq}/body` | 保存改稿（AI 原稿保留，用于算改动比例） |
| GET | `/api/reports/{id}/summary` | 顶部汇总：待人工章、`[待补充]`、去重冲突提示 |
| POST / GET | `/api/reports/{id}/export`、`export.docx` | 导出 / 下载 Word（落 E3） |
| GET | `/api/reports/{id}/events` | 埋点 E1–E3 |

错误统一为 `{"error": {"code", "message"}}`。

## 六、已知限制（本阶段）

1. 临时界面只按桌面宽度设计，手机端适配在阶段 3。
2. 本版不做登录（D5），数据归属字段固定为 `local`。
3. 检索用关键词方案（BM25）在阶段 2-2 引入；本阶段大纲不检索资料（与评测 C01 一致）。
4. 章节编号按发改委 2023 官方十章顺序，评测时按章节标题匹配（见 `docs/阶段文档/阶段2-1技术开发文档.md` 第十二节）。
5. **字数控制靠程序不靠模型**：实测 DeepSeek 对"不超过 N 字"的遵守度差（写 1,283 字 → 压缩后仍 1,240 字，仅减 3%），所以每章超上限时先压缩一次、仍超就按 PRD 截断并标记「本章超长已截断」。整份 12,000 字报告仍控制在 2 万字以内。
6. 同一时间只允许一份报告在写（单线程）；服务重启后正在跑的任务会自动标为「已暂停」，点「从第 N 章继续」即可，已完成章节不重写。
