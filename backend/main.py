# -*- coding: utf-8 -*-
"""
锦语 · AI 文化导览后端
端点：
  GET  /api/health            健康检查 + Key 配置状态
  GET  /api/resolve?code=     二维码内容解析（校验 + 访问日志）
  POST /api/recognize         拍照识文物（GLM-4V，multipart 图片）
  GET  /api/tts?lang=&text=   语音合成（edge-tts 神经音色）
  GET  /api/cite?relic_id=    引用来源（馆方知识库分片）
  POST /api/ask               AI 问答（GLM，带知识库上下文）
  POST /api/report            观展报告生成（GLM）
  GET  /api/stats             扫码访问统计（调研用）
"""
import base64
import json
import os
import re
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

BASE = Path(__file__).parent
SEED = BASE / "seed"
GLM_KEY = os.environ.get("GLM_API_KEY", "").strip()
GLM_BASE = "https://open.bigmodel.cn/api/paas/v4"
SCAN_LOG = BASE / "scans.log"

app = FastAPI(title="Jinyu Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RELICS = json.loads((SEED / "relics.json").read_text(encoding="utf-8"))
BY_ID = {r["id"]: r for r in RELICS}

MODE_LABEL = {
    "child": "儿童版（讲故事口吻，活泼亲切）",
    "general": "通用版（面向普通观众）",
    "pro": "专业版（考据深度，可使用专业术语）",
}

JSON_TMPL = "{'text':'...','badge':'...'}"


def relic_brief(r):
    return {
        "id": r["id"], "name": r["name"], "enName": r["enName"],
        "mono": r["mono"], "era": r["era"], "point": r["point"],
    }


def knowledge(r, mode="general"):
    zh = r["zh"][mode]
    qa = "\n".join("问：%s 答：%s" % (q, a) for q, a, *rest in r.get("qa", []))
    return (
        "《%s》（%s），%s，%s。%s。\n讲解词（%s）：%s\n馆方问答：\n%s"
        % (r["name"], r["enName"], r["era"], r["origin"], r["hero"],
           mode, zh, qa)
    )


async def glm_chat(messages, model="glm-4-flash", temperature=0.7, max_tokens=900):
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(
            GLM_BASE + "/chat/completions",
            headers={"Authorization": "Bearer " + GLM_KEY},
            json={"model": model, "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens},
        )
        if r.status_code != 200:
            raise HTTPException(502, "GLM 接口错误：%s %s" % (r.status_code, r.text[:200]))
        j = r.json()
        return j["choices"][0]["message"]["content"]


# ── 健康检查 ──────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"ok": True, "api_key_configured": bool(GLM_KEY),
            "relics": len(RELICS), "version": "锦语后端 v1.0"}


# ── 二维码解析 ────────────────────────────────────────────
def parse_code(code):
    """支持三种形态：完整 URL(?r=xxx) / jinyu:xxx / 裸 relic_id"""
    code = (code or "").strip()
    m = re.search(r"[?&]r=([a-z0-9\-]+)", code)
    if m:
        return m.group(1)
    m = re.match(r"^jinyu:([a-z0-9\-]+)$", code)
    if m:
        return m.group(1)
    return code


@app.get("/api/resolve")
def resolve(code: str = ""):
    rid = parse_code(code)
    hit = BY_ID.get(rid)
    # 访问日志：时间、目标、是否命中
    try:
        with SCAN_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "code": code[:120], "relic_id": rid, "hit": bool(hit),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if not hit:
        return JSONResponse(
            {"ok": False, "relic_id": None, "detail": "未识别的二维码内容"},
            status_code=404)
    return {"ok": True, "relic_id": rid, "relic": relic_brief(hit)}


# ── 拍照识别：参考图比对 + 语义兜底（GLM-4V） ───────────────
import ast

REF_DIR = BASE.parent / "assets"


def extract_json(content):
    """从模型输出中提取含 relic_id 的 JSON（兼容单引号、思维链前置文本）"""
    for m in reversed(list(re.finditer(r"\{[^{}]*\}", content))):
        raw = m.group(0)
        try:
            cand = json.loads(raw)
        except json.JSONDecodeError:
            try:
                cand = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                continue
        if isinstance(cand, dict) and "relic_id" in cand:
            return cand
    return None


@app.post("/api/recognize")
async def recognize(file: UploadFile = File(...)):
    if not GLM_KEY:
        raise HTTPException(503, "未配置 GLM_API_KEY，识别不可用")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "图片过大（限 8MB）")
    b64 = base64.b64encode(data).decode()

    catalog = "；".join("%d.%s(%s)" % (k + 1, r["id"], r["name"])
                        for k, r in enumerate(RELICS))

    # 主路径：把 5 张馆藏参考图与观众照片一起交给模型做视觉比对
    ref_imgs = []
    if REF_DIR.exists():
        for r in RELICS:
            p = REF_DIR / (r["id"] + ".jpg")
            if p.exists():
                ref_imgs.append((r["id"], p))
    if len(ref_imgs) == len(RELICS):
        parts = [{
            "type": "text", "text":
            "你是博物馆文物识别助手。下面前 %d 张图是馆藏展品的参考照片，依次对应编号：%s。"
            "最后一张是观众在展厅内拍摄的照片。请判断最后一张照片与哪一张参考图展示的是同一件"
            "展品（允许场景相同但角度不同）。严格只输出 JSON："
            "{'relic_id':'参考图对应的 id','confidence':0到1之间的小数}。"
            "若与任何参考图都不是同一件展品，relic_id 输出 null。"
            "不要输出其他文字。" % (len(ref_imgs), catalog),
        }]
        for rid, p in ref_imgs:
            parts.append({"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," +
                       base64.b64encode(p.read_bytes()).decode()}})
        parts.append({"type": "image_url",
                      "image_url": {"url": "data:image/jpeg;base64," + b64}})
        content = await glm_chat([{"role": "user", "content": parts}],
                                 model="glm-4.1v-thinking-flash",
                                 temperature=0.1, max_tokens=2000)
    else:
        # 兜底：参考图缺失时退化为纯语义分类
        prompt = (
            "你是博物馆文物识别助手。馆内候选文物目录：" + catalog +
            "。请识别照片中的文物属于目录中哪一件，严格只输出 JSON："
            "{'relic_id':'目录中的 id','confidence':0到1之间的小数}。"
            "区分要点：全身板甲(plate-armour)是人形的整套盔甲；"
            "战马具装(barded-horse)是展厅中庭场景，若画面同时出现人形盔甲与马匹，"
            "应判定为战马具装；马面甲(shaffron)是罩在马脸上的面具；"
            "仪仗头盔(parade-helmet)是顶部可插羽饰的头盔；"
            "骑士长剑(sword)是带十字护手的剑。"
            "若均不匹配，relic_id 输出 null。不要输出其他文字。")
        content = await glm_chat(
            [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ]}], model="glm-4.1v-thinking-flash", temperature=0.1,
            max_tokens=2000)

    j = extract_json(content)
    if j is None:
        raise HTTPException(502, "模型返回无法解析：" + content[:120])
    rid = j.get("relic_id")
    # 兼容模型返回参考图编号（"1"–"5"）的情况
    if isinstance(rid, str) and rid.strip().isdigit():
        n = int(rid.strip())
        if 1 <= n <= len(RELICS):
            rid = RELICS[n - 1]["id"]
        else:
            rid = None
    try:
        conf = float(j.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if not rid or rid not in BY_ID or conf < 0.5:
        return {"relic_id": None, "confidence": round(conf, 3)}
    return {"relic_id": rid, "confidence": round(min(conf, 1.0), 3)}


# ── 语音合成（edge-tts） ──────────────────────────────────
VOICES = {"zh": "zh-CN-XiaoxiaoNeural",
          "en": "en-US-AriaNeural",
          "cy": "zh-CN-YunxiNeural"}


@app.get("/api/tts")
async def tts(lang: str = "zh", text: str = ""):
    if not text.strip():
        raise HTTPException(400, "text 为空")
    try:
        import edge_tts
    except ImportError:
        raise HTTPException(500, "edge-tts 未安装")
    voice = VOICES.get(lang, VOICES["zh"])
    buf = b""
    try:
        async for chunk in edge_tts.Communicate(text[:300], voice).stream():
            if chunk["type"] == "audio":
                buf += chunk["data"]
    except Exception as e:
        raise HTTPException(502, "语音合成失败：%s" % e)
    if not buf:
        raise HTTPException(502, "语音合成无结果")
    return Response(buf, media_type="audio/mpeg",
                    headers={"X-TTS-Engine": "edge-tts"})


# ── 引用来源 ──────────────────────────────────────────────
@app.get("/api/cite")
def cite(relic_id: str = ""):
    r = BY_ID.get(relic_id)
    if not r:
        raise HTTPException(404, "未找到该文物")
    chunks = [
        {"text": r["zh"]["general"][:120] + "……", "source": "馆方知识库 · 讲解词"},
        {"text": "问：" + r["qa"][0][0] + "　答：" + str(r["qa"][0][1])[:80] + "……",
         "source": "馆方知识库 · 问答"},
        {"text": "%s（%s），%s，%s。" % (r["name"], r["enName"], r["era"], r["origin"]),
         "source": "馆方知识库 · 藏品档案"},
    ]
    return {"relic_id": relic_id, "chunks": chunks}


# ── AI 问答 ──────────────────────────────────────────────
@app.post("/api/ask")
async def ask(body: dict):
    rid = body.get("relic_id", "")
    r = BY_ID.get(rid)
    if not r:
        raise HTTPException(404, "未找到该文物")
    if not GLM_KEY:
        raise HTTPException(503, "未配置 GLM_API_KEY，问答不可用")
    q = (body.get("question") or "").strip()
    if not q:
        raise HTTPException(400, "question 为空")
    mode = body.get("mode") or "general"
    lang = body.get("lang") or "zh"
    hist = [h for h in (body.get("history") or [])[-6:]
            if h.get("role") in ("user", "assistant") and h.get("content")]
    if lang == "en":
        style = "Answer in English"
    elif mode == "child":
        style = "用简体中文回答，语气活泼，适合儿童理解"
    elif mode == "pro":
        style = "用简体中文回答，可以使用专业考据术语"
    else:
        style = "用简体中文回答"
    system = (
        "你是成都博物馆「钢铁与荣耀」特展的智能导览员「锦语」。"
        "只能依据下方馆方知识库回答，知识库未涵盖的内容要明确说不知道，绝不编造；"
        "回答简明、口语化、有温度，不超过 220 字。\n\n"
        "知识库（%s）：\n%s\n\n%s" % (MODE_LABEL.get(mode, "通用版"),
                                      knowledge(r, mode), style))
    messages = [{"role": "system", "content": system}]
    messages += hist
    messages.append({"role": "user", "content": q})
    ans = await glm_chat(messages, model="glm-4-flash")
    return {"answer": ans.strip(),
            "sources": [{"source": "馆方知识库 · " + r["hero"]}]}


# ── 观展报告 ──────────────────────────────────────────────
@app.post("/api/report")
async def report(body: dict):
    if not GLM_KEY:
        raise HTTPException(503, "未配置 GLM_API_KEY，报告不可用")
    items = body.get("items") or []
    if not items:
        raise HTTPException(400, "items 为空")
    lang = body.get("lang") or "zh"
    en = lang == "en"
    lines = "；".join("%s（追问 %s 次）" % (i.get("name"), i.get("questions", 0))
                     for i in items)
    if en:
        head = (
            "You are Jinyu, an AI museum guide at Chengdu Museum's 'Steel of "
            "Glory' exhibition. Write a warm, literate visit summary (max 120 "
            "words) based on the visitor's footprint below. Then output a 4-8 "
            "character badge title. Output strict JSON " + JSON_TMPL +
            ". Footprint: ")
    else:
        head = (
            "你是成都博物馆「钢铁与荣耀」特展的 AI 导览员「锦语」。根据以下观展足迹写一段 "
            "80 字以内、有温度、有文气的观展总结，并起一个 4–8 字的纪念章称号。"
            "严格只输出 JSON：" + JSON_TMPL + "。观展足迹：")
    content = await glm_chat([{"role": "user", "content": head + lines}],
                             model="glm-4-flash", temperature=0.8)
    m = re.search(r"\{.*?\}", content, re.S)
    if not m:
        raise HTTPException(502, "模型返回无法解析：" + content[:120])
    try:
        j = json.loads(m.group(0))
        return {"text": j["text"].strip(), "badge": j["badge"].strip()}
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(502, "模型返回无法解析：" + content[:120])


# ── 扫码统计（调研用） ────────────────────────────────────
@app.get("/api/stats")
def stats():
    scans = []
    if SCAN_LOG.exists():
        for line in SCAN_LOG.read_text(encoding="utf-8").splitlines()[-500:]:
            try:
                scans.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    per = {}
    for s in scans:
        if s.get("hit"):
            per[s["relic_id"]] = per.get(s["relic_id"], 0) + 1
    return {"total_scans": len(scans), "hits": per}
