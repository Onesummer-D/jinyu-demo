# 锦语 · AI 文化导览 v1.0（jinyu-demo）

面向成都博物馆「钢铁与荣耀——意大利都灵皇宫博物馆藏骑士文物展」的智慧文博导览原型。
本项目为暑期个人实践「赴四川省成都市成都博物馆开展智慧文博调研与 AI 文化导览设计」的技术成果：

- 线上体验（GitHub Pages 静态托管）：**https://onesummer-d.github.io/jinyu-demo/**
- 代码仓库：https://github.com/Onesummer-D/jinyu-demo

> 线上地址为纯静态部署，打开后自动进入「演示模式」（内置调研种子数据，完整展示全部界面与流程）；
> AI 问答、拍照识别等实时接口需按下方说明部署后端后使用。

## 功能一览

| 模块 | 说明 |
| --- | --- |
| 扫码识文物 | 调用相机识别展品二维码（html5-qrcode），识别后自动打开对应展品讲解 |
| 拍照识文物 | 拍摄展品或其说明牌，GLM-4V 视觉模型返回展品 ID 与置信度 |
| AI 问答 | 基于展品知识库上下文向 GLM 提问，答案附馆方知识库引用 |
| 三版讲解 | 每件展品提供儿童版（故事口吻）/ 通用版 / 专业版（考据深度）三种文案 |
| 多语语音 | 中文、英语、四川话三语讲解语音（edge-tts 神经音色合成） |
| 观展报告 | 依据当日足迹一键生成个性化观展报告，可保存分享海报 |
| 数字纪念章 | 看满 3 件 / 5 件展品解锁对应纪念章，问答互动另有成就 |
| 展厅地图 | 全馆 7 个识别点位导览，标记已看 / 未看展品 |
| 访问统计 | 后端记录二维码扫描日志（`scans.log`），用于实践调研数据分析 |

## 技术架构

```
浏览器（单页应用 index.html，原生 HTML/CSS/JS，无构建步骤）
   │  相机扫码 / 拍照上传 / 语音播放 / 海报生成
   ▼
FastAPI 后端（backend/main.py）
   ├─ /api/resolve    二维码内容解析（校验 + 访问日志）
   ├─ /api/recognize  拍照识文物（GLM-4V 视觉识别，多图比对）
   ├─ /api/ask        AI 问答（GLM，携带知识库上下文与引用）
   ├─ /api/report     观展报告生成（GLM）
   ├─ /api/tts        语音合成（edge-tts，中 / 英 / 川话）
   ├─ /api/cite       引用来源（馆方知识库分片）
   ├─ /api/stats      扫码访问统计
   └─ /api/health     健康检查 + Key 配置状态
```

- **前端**：单文件 `index.html`（约 1200 行，零依赖、零构建），相机能力依赖浏览器 `getUserMedia`，需 HTTPS 或 localhost 环境。
- **AI 模型**：智谱 GLM 系列（`https://open.bigmodel.cn/api/paas/v4`），拍照识别使用 GLM-4V 多图比对。
- **降级策略**：前端检测不到后端时自动进入演示模式，内置与 `backend/seed/relics.json` 同源的种子数据，保证离线 / 静态托管环境下全流程可演示。

## 目录结构

```
index.html            前端单页应用（含演示模式种子数据）
assets/               展品图片、三语讲解音频、前端识别库（html5-qrcode）
backend/
  main.py             FastAPI 后端服务
  requirements.txt    Python 依赖（fastapi / uvicorn / httpx / edge-tts）
  .env.example        环境变量示例（GLM_API_KEY，勿提交真实 Key）
  seed/relics.json    展品知识库（6 件骑士文物，三版讲解文案）
  seed/points.json    展厅识别点位数据
  make_qr.py          展品二维码生成脚本
qr/                   已生成的展品二维码图片与打印标签页
```

## 本地运行

```bash
cd backend
pip install -r requirements.txt

# 到 https://open.bigmodel.cn/ 申请 Key，写入 .env（参考 .env.example）
echo "GLM_API_KEY=你的Key" > .env

uvicorn main:app --host 0.0.0.0 --port 8000
```

前端直接用浏览器打开 `index.html`（或任意静态服务器托管）；
页面访问地址为 localhost 时自动连接 `http://localhost:8000` 的真实后端，否则进入演示模式。

## 公网部署说明

- **前端**：推送到本仓库 `gh-pages` 分支即由 GitHub Pages 托管，公网地址见上方。
- **后端**：GitHub Pages 无法运行 Python 服务。如需公网体验完整 AI 功能，请将 `backend/` 部署至公网服务器（并配置 HTTPS），然后将 `index.html` 中的 `API()` 基地址指向该服务。

## 实践信息

- 项目版本：锦语 v1.0 · 2026-11-20
- 调研地点：成都博物馆「钢铁与荣耀」特展展厅（2026.04.30–08.30，一层特展厅）
- 配套成果：实践照片、调研报告、个人实践手记、系统原型演示视频（见实践提交文件夹「其他成果」）
