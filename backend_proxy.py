"""
DecideX 前端后端代理服务
直接调用 decision-agent graph，无需 LangGraph Dev Studio
"""
try:
    from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from typing import Optional
    import os
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    print("警告: 未安装 FastAPI，请运行: pip install fastapi uvicorn")

import sys
import uuid
import json
import requests
import sqlite3
import hashlib
import secrets
import time

# 确保项目根目录在 path 中
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 加载 .env 文件（容错处理）
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv 不可用或 .env 文件无法读取，直接用已有环境变量
    pass

# 尝试导入 graph
try:
    # 方法1：把 src/decision-agent 目录注册为包
    _agent_dir = os.path.join(_ROOT, "src", "decision-agent")
    _src_dir   = os.path.join(_ROOT, "src")
    for _p in [_ROOT, _src_dir, _agent_dir]:
        if _p not in sys.path:
            sys.path.insert(0, _p)

    # 用 importlib 加载，避免连字符包名问题
    import importlib.util as _ilu

    # 先把子模块注册进 sys.modules，解决相对导入
    _pkg_name = "decision_agent"
    for _fname, _mod_name in [
        ("intent_recognition.py", f"{_pkg_name}.intent_recognition"),
        ("stopping_rules.py",     f"{_pkg_name}.stopping_rules"),
        ("citation.py",           f"{_pkg_name}.citation"),
    ]:
        _fpath = os.path.join(_agent_dir, _fname)
        if os.path.exists(_fpath) and _mod_name not in sys.modules:
            _spec = _ilu.spec_from_file_location(_mod_name, _fpath)
            _m = _ilu.module_from_spec(_spec)
            sys.modules[_mod_name] = _m
            try:
                _spec.loader.exec_module(_m)
            except Exception:
                pass

    # 加载 graph.py 本体
    _graph_path = os.path.join(_agent_dir, "graph.py")
    _spec = _ilu.spec_from_file_location(f"{_pkg_name}.graph", _graph_path,
                submodule_search_locations=[_agent_dir])
    _graph_mod = _ilu.module_from_spec(_spec)
    sys.modules[f"{_pkg_name}.graph"] = _graph_mod
    _spec.loader.exec_module(_graph_mod)
    decision_graph = _graph_mod.graph
    # 直接拿到 full_decision_analysis 工具函数，供"绕过 supervisor"模式使用
    _full_decision_fn = getattr(_graph_mod, "full_decision_analysis", None)
    GRAPH_AVAILABLE = True
    print("✅ decision-agent graph 加载成功")
except Exception as e2:
    GRAPH_AVAILABLE = False
    _full_decision_fn = None
    print(f"⚠️  graph 加载失败: {e2}")
    print("   将使用 mock 模式运行（返回示例响应）")

def _web_search(query: str) -> str:
    """调用真实 DuckDuckGo 搜索，返回摘要文本"""
    # 优先使用 duckduckgo_search 直接调用
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if results:
            snippets = " ".join(r.get("body", "") for r in results)
            return snippets[:350].strip()
        return ""
    except Exception:
        pass
    # 降级：通过 langchain-community
    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        result = DuckDuckGoSearchRun().run(query)
        return result[:350].strip() if result else ""
    except Exception:
        return ""


def _resolve_google_model() -> str:
    forced = os.getenv("GOOGLE_MODEL")
    if forced:
        return forced
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "gemini-2.5-flash"
    try:
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=8,
        )
        resp.raise_for_status()
        models = resp.json().get("models", [])
        candidates = []
        for m in models:
            methods = m.get("supportedGenerationMethods", []) or []
            if "generateContent" in methods:
                name = (m.get("name") or "").split("/")[-1]
                if name:
                    candidates.append(name)

        preferred = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
        for p in preferred:
            if p in candidates:
                return p
        if candidates:
            return candidates[0]
    except Exception as e:
        print(f"⚠️  fallback 模型探测失败: {e}")
    return "gemini-2.5-flash"


_AUTH_DB = os.path.join(_ROOT, "data", "auth.db")


def _init_auth_db() -> None:
    os.makedirs(os.path.dirname(_AUTH_DB), exist_ok=True)
    conn = sqlite3.connect(_AUTH_DB)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                profile_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_AUTH_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return digest.hex()


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _get_user_by_token(token: str) -> Optional[dict]:
    now = int(time.time())
    conn = _db_conn()
    try:
        row = conn.execute(
            """
            SELECT u.id, u.email
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, now),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _upsert_profile(user_id: int, profile: dict) -> None:
    now = int(time.time())
    conn = _db_conn()
    try:
        conn.execute(
            """
            INSERT INTO profiles(user_id, profile_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                profile_json=excluded.profile_json,
                updated_at=excluded.updated_at
            """,
            (user_id, json.dumps(profile, ensure_ascii=False), now),
        )
        conn.commit()
    finally:
        conn.close()


def _get_profile(user_id: int) -> dict:
    conn = _db_conn()
    try:
        row = conn.execute("SELECT profile_json FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return {}
        return json.loads(row["profile_json"] or "{}")
    except Exception:
        return {}
    finally:
        conn.close()


def _build_search_context(message: str) -> dict:
    """根据问题类型决定搜索什么，返回真实搜索结果"""
    has_house   = any(k in message for k in ["买房", "房子", "首付", "月供", "通州", "楼市"])
    has_career  = any(k in message for k in ["工作", "offer", "跳槽", "职业", "转行", "薪资"])
    has_invest  = any(k in message for k in ["投资", "股票", "基金", "理财", "创业公司股权"])
    has_edu     = any(k in message for k in ["考研", "留学", "培训", "课程"])

    results = {}
    if has_house:
        r = _web_search("北京通州二手房均价 2026")
        results["cost_search"] = r or "（搜索无结果，以知识库数据为准）"
        r2 = _web_search("2026年首套房贷利率最新政策")
        results["risk_search"] = r2 or "（搜索无结果，以知识库数据为准）"
    elif has_career:
        r = _web_search("2026年互联网AI行业薪资水平跳槽涨幅")
        results["cost_search"] = r or "（搜索无结果，以知识库数据为准）"
        r2 = _web_search("2026年就业市场形势 互联网裁员")
        results["risk_search"] = r2 or "（搜索无结果，以知识库数据为准）"
    elif has_invest:
        r = _web_search("2026年A股市场行情投资建议")
        results["cost_search"] = r or "（搜索无结果，以知识库数据为准）"
        r2 = _web_search("2026年美联储降息周期权益类资产")
        results["risk_search"] = r2 or "（搜索无结果，以知识库数据为准）"
    elif has_edu:
        r = _web_search("2026年考研报录比 互联网产品岗位要求")
        results["cost_search"] = r or "（搜索无结果，以知识库数据为准）"
        r2 = _web_search("2026年应届生就业形势")
        results["risk_search"] = r2 or "（搜索无结果，以知识库数据为准）"
    else:
        results["cost_search"] = ""
        results["risk_search"] = ""
    return results


def _generate_mock_response(message: str, mode: str = "simple") -> str:
    """根据用户选择的模式生成回复"""
    from datetime import datetime
    current_year = datetime.now().year

    has_house   = any(k in message for k in ["买房", "房子", "首付", "月供", "通州", "楼市"])
    has_career  = any(k in message for k in ["工作", "offer", "跳槽", "职业", "转行"])
    has_invest  = any(k in message for k in ["投资", "股票", "基金", "理财", "股权"])
    has_edu     = any(k in message for k in ["考研", "留学", "课程", "培训"])

    # ── 获取真实搜索数据 ──────────────────────────────────────
    search_ctx = _build_search_context(message)
    cost_search  = search_ctx.get("cost_search", "")
    risk_search  = search_ctx.get("risk_search", "")
    search_label = "🌐 网络搜索（实时）" if (cost_search and "搜索无结果" not in cost_search) else "📚 知识库"

    # ── 按场景生成内容 ──────────────────────────────────────
    if has_house:
        intent      = "purchase · 房产购买决策"
        simple_ans  = "**暂不建议购买。** 月薪3万，月供约1.05万，占收入35%，超出安全线。建议首付提升至80万以上，或等月薪达到3.5万后再入手。"
        cost_body   = f"- 贷款240万，30年等额月供约 **1.05万元**，占月收入 **35%**（建议线30%）[1]\n- {cost_search[:200] if cost_search else f'北京通州 {current_year} 年二手房均价约 3.2–4.2万/㎡'}"
        risk_body   = f"- {risk_search[:200] if risk_search else f'{current_year}年首套房贷利率约 3.5–3.9%，通州属限购区'} [2]\n- 主要风险：月供压力大，抗降薪/失业能力弱"
        value_body  = "- 通州作为北京城市副中心，长期规划利好，有保值预期\n- 短期流动性差，3年内不建议卖出"
        match_body  = "- 首付60万刚达最低门槛，应急储备不足\n- 建议月收入≥3.5万再启动购房"
        conclusion  = "**暂缓购买，目标1–2年后重新评估**\n1. 首付目标提升至80万以上\n2. 关注通州90㎡以下总价≤280万房源\n3. 月薪升至3.5万+可重新评估"

    elif has_career:
        intent      = "career_choice · 职业/工作决策"
        simple_ans  = "**建议接受，但先确认3个条件：** 新薪资≥现薪资×1.25、拿到书面Offer再提离职、新方向与3年规划一致。三条满足2条以上即可跳。"
        cost_body   = f"- 跳槽平均薪资涨幅 20–40%，创业公司通常给得更多但稳定性低 [1]\n- {cost_search[:200] if cost_search else f'{current_year}年AI/互联网行业薪资涨幅约8–15%'}"
        risk_body   = f"- {risk_search[:200] if risk_search else f'{current_year}年就业市场竞争加剧，书面Offer是保障'} [2]\n- 换行业风险比换公司高3–5倍，同赛道跳槽风险最低"
        value_body  = "- 大厂品牌 > 知名独角兽 > 普通公司，对简历长期加分\n- 成长空间和直属领导风格比薪资更影响3年后的竞争力"
        match_body  = "- 涨薪30%在合理区间，需结合股票/期权折现价值综合评估\n- 建议关注：公司融资阶段、产品方向、团队规模"
        conclusion  = "**综合建议：满足条件即可去**\n1. 薪资：新Offer ÷ 现薪资 ≥ 1.25 ✅\n2. 平台：确认新公司融资轮次和行业地位\n3. 方向：与自己的5年目标是否吻合"

    elif has_invest:
        intent      = "investment · 投资理财决策"
        simple_ans  = "**不建议把50万全押创业股权。** 高风险投资建议控制在可投资资产的20%以内，优先确保应急储备，剩余资金做分散定投。"
        cost_body   = f"- 创业股权流动性极差，通常5–8年才能退出，资金长期锁定 [1]\n- {cost_search[:200] if cost_search else f'{current_year}年A股定投年化预期约8–12%，风险远低于股权'}"
        risk_body   = f"- {risk_search[:200] if risk_search else f'{current_year}年一级市场投资回报周期拉长，约80%创业公司未能上市退出'} [2]\n- 10倍回报承诺需谨慎：对应失败概率通常超过70%"
        value_body  = "- 若对创始团队有深度了解，可少量参与（≤10万）\n- 长期来看宽基指数定投风险收益比更优"
        match_body  = "- 投资前确认：资金能否7年不动用？能否承受全部亏损？"
        conclusion  = "**综合建议：分散风险，小仓位参与**\n1. 最多拿出10万参与股权，其余做货币基金+宽基指数\n2. 要求对方提供完整财务和股权结构\n3. 签署正式投资协议，明确退出机制"

    elif has_edu:
        intent      = "education · 学习/教育规划"
        simple_ans  = "**建议先就业，积累1–2年经验后再考虑考研。** 互联网产品岗更看重项目经验，211/985学历门槛相对弹性，工作经验往往比学历更重要。"
        cost_body   = f"- 考研机会成本：2年收入+学费约25–35万，加上时间成本 [1]\n- {cost_search[:200] if cost_search else f'{current_year}年产品岗薪资：应届10–20k，3年经验20–35k'}"
        risk_body   = f"- {risk_search[:200] if risk_search else f'{current_year}年考研报录比约3–5:1，竞争激烈'} [2]\n- 直接就业风险：第一份工作方向选错，后期转型成本高"
        value_body  = "- 互联网产品岗：工作经验 > 学历，但大厂校招仍看院校\n- 考研读名校（985）对求职大厂有一定加成"
        match_body  = "- 非211本科背景，直接拿大厂校招offer难度高\n- 若目标是大厂，考上985研究生性价比较高"
        conclusion  = "**综合建议：优先就业，视情况再读研**\n1. 先找产品实习，验证方向是否适合自己\n2. 若1–2年后仍想进大厂，届时考研更有目的性\n3. 若顺利进入中型互联网公司，不一定需要读研"

    else:
        intent      = "general · 综合决策分析"
        simple_ans  = "根据您的描述，建议从**成本、风险、价值**三个维度逐一评估。如需更精准的建议，请补充预算范围、时间限制和最重要的考量因素。"
        cost_body   = f"- 请评估直接成本（金钱/时间）和机会成本 [1]\n- {current_year}年市场环境：理性消费，性价比优先"
        risk_body   = "- 评估最坏情况的可接受程度 [2]\n- 使用逆向思维：\"如果X发生，我能承受吗？\""
        value_body  = "- 此决策与中长期目标是否一致？\n- 短期牺牲能否换来长期回报？"
        match_body  = "- 结合个人偏好、资源禀赋和历史决策模式综合判断"
        conclusion  = "**补充信息后可给出更精准建议**\n1. 可用预算/资源上限\n2. 时间紧迫程度\n3. 最重要的考量维度"

    # ── 简洁模式：只返回结论 ─────────────────────────────────
    if mode == "simple":
        search_note = ""
        if cost_search and "搜索无结果" not in cost_search:
            search_note = f"\n\n> 🌐 **实时数据参考：** {cost_search[:120]}..."
        return f"{simple_ans}{search_note}"

    # ── 详细模式：完整4 Agent分析 ────────────────────────────
    search_src = f"[2] {search_label}\n    {(cost_search or risk_search)[:150]}..." if (cost_search or risk_search) else "[2] 📚 知识库 · Risk\n    领域风险评估规则文档..."

    return f"""### 🎯 意图识别
**{intent}**
> 问题已结构化，进入 Multi-Agent 并行分析...

---

### 💰 成本分析 Agent
{cost_body}

---

### ⚠️ 风险评估 Agent
{risk_body}

---

### 🎯 价值评估 Agent
{value_body}

---

### 👤 个人匹配度 Agent
{match_body}

---

### ✅ 综合建议
{conclusion}

---

📎 **决策依据来源**
[1] 📚 知识库 · Cost（相关度 0.91）
    领域成本分析框架与行业基准数据...
{search_src}

> 💡 演示模式 · 如需完整 AI 分析请配置 API Key"""


if HAS_FASTAPI:
    _init_auth_db()
    app = FastAPI(title="DecideX Backend Proxy")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class ChatRequest(BaseModel):
        agent: str
        message: str
        conversation_id: Optional[str] = None
        mode: Optional[str] = "simple"  # "simple" | "detailed"
        user_id: Optional[str] = None
        user_profile: Optional[dict] = None

    class ChatResponse(BaseModel):
        response: str
        conversation_id: Optional[str] = None

    class AuthRequest(BaseModel):
        email: str
        password: str

    class ProfileRequest(BaseModel):
        profile: dict

    @app.get("/")
    async def root():
        return {
            "status": "running",
            "graph_available": GRAPH_AVAILABLE,
            "message": "DecideX Backend Service",
        }

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest, authorization: Optional[str] = Header(default=None)):
        conversation_id = request.conversation_id or str(uuid.uuid4())[:8]
        token = _extract_bearer(authorization)
        authed_user = _get_user_by_token(token) if token else None

        mode = request.mode or "simple"

        if not GRAPH_AVAILABLE:
            mock_response = _generate_mock_response(request.message, mode)
            return ChatResponse(response=mock_response, conversation_id=conversation_id)

        # 合并用户画像
        merged_profile = {}
        if authed_user:
            merged_profile = _get_profile(authed_user["id"])
        if request.user_profile:
            merged_profile.update(request.user_profile)
        if authed_user and merged_profile:
            _upsert_profile(authed_user["id"], merged_profile)

        # ── 两种模式都先跑完整详细分析，保证分析依据100%一致 ─────────────────────
        # simple 模式：完整分析完成后，再做一次快速二次压缩（保证结论来自同一份分析）
        # detailed 模式：直接返回完整报告
        try:
            import asyncio
            profile_json = json.dumps(merged_profile, ensure_ascii=False) if merged_profile else ""

            if _full_decision_fn is not None:
                # 第一步：始终以 detailed 模式跑完整分析
                loop = asyncio.get_running_loop()
                detailed_result = await loop.run_in_executor(
                    None,
                    lambda: _full_decision_fn.invoke({
                        "decision_query": request.message,
                        "user_profile": profile_json,
                        "mode": "detailed",
                    })
                )
                if not detailed_result or len(str(detailed_result).strip()) < 50:
                    raise ValueError("full_decision_analysis 返回内容过短，降级处理")

                # 第二步：simple 模式对完整报告做二次压缩（结论来自同一份分析，保证一致）
                if mode == "simple":
                    result = await loop.run_in_executor(
                        None,
                        lambda: _compress_to_simple(str(detailed_result))
                    )
                else:
                    result = detailed_result

                return ChatResponse(response=str(result), conversation_id=conversation_id)

            # 兜底：full_decision_fn 不可用时走旧的 graph stream 路径
            from langchain_core.messages import HumanMessage
            config = {"recursion_limit": 40}
            profile_ctx = ""
            if merged_profile:
                profile_ctx = (
                    "【用户画像】\n"
                    f"{json.dumps(merged_profile, ensure_ascii=False)}\n\n"
                    "请在个人匹配度分析中优先参考该画像。\n\n"
                )
            inputs = {
                "messages": [HumanMessage(content=f"{profile_ctx}【用户问题】{request.message}")]
            }
            result = await _run_graph(inputs, config)
            return ChatResponse(response=result, conversation_id=conversation_id)

        except Exception as e:
            return ChatResponse(
                response=f"❌ 分析出错：{str(e)}\n\n请检查 API Key 是否正确配置（`.env` 文件中的 GOOGLE_API_KEY）。",
                conversation_id=conversation_id
            )

    @app.post("/auth/register")
    async def auth_register(payload: AuthRequest):
        email = payload.email.strip().lower()
        password = payload.password.strip()
        if "@" not in email:
            raise HTTPException(status_code=400, detail="邮箱格式不正确")
        if len(password) < 6:
            raise HTTPException(status_code=400, detail="密码至少6位")
        salt = secrets.token_hex(16)
        pwd_hash = _hash_password(password, salt)
        now = int(time.time())
        conn = _db_conn()
        try:
            cur = conn.execute(
                "INSERT INTO users(email, password_hash, salt, created_at) VALUES(?, ?, ?, ?)",
                (email, pwd_hash, salt, now),
            )
            user_id = cur.lastrowid
            token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES(?, ?, ?, ?)",
                (token, user_id, now + 30 * 24 * 3600, now),
            )
            conn.commit()
            _upsert_profile(user_id, {"email": email})
            return {"token": token, "email": email}
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="邮箱已注册")
        finally:
            conn.close()

    @app.post("/auth/login")
    async def auth_login(payload: AuthRequest):
        email = payload.email.strip().lower()
        password = payload.password.strip()
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT id, password_hash, salt FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="账号或密码错误")
            if _hash_password(password, row["salt"]) != row["password_hash"]:
                raise HTTPException(status_code=401, detail="账号或密码错误")
            now = int(time.time())
            token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES(?, ?, ?, ?)",
                (token, row["id"], now + 30 * 24 * 3600, now),
            )
            conn.commit()
            return {"token": token, "email": email}
        finally:
            conn.close()

    @app.post("/auth/logout")
    async def auth_logout(authorization: Optional[str] = Header(default=None)):
        token = _extract_bearer(authorization)
        if not token:
            return {"ok": True}
        conn = _db_conn()
        try:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True}

    @app.get("/auth/me")
    async def auth_me(authorization: Optional[str] = Header(default=None)):
        token = _extract_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="未登录")
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="登录已过期")
        return {"email": user["email"], "user_id": user["id"]}

    @app.get("/profile")
    async def get_profile(authorization: Optional[str] = Header(default=None)):
        token = _extract_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="未登录")
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="登录已过期")
        return {"profile": _get_profile(user["id"])}

    @app.post("/profile")
    async def save_profile(payload: ProfileRequest, authorization: Optional[str] = Header(default=None)):
        token = _extract_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="未登录")
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="登录已过期")
        profile = payload.profile or {}
        profile["email"] = user["email"]
        _upsert_profile(user["id"], profile)
        return {"ok": True}

    @app.post("/profile/reset")
    async def reset_profile(authorization: Optional[str] = Header(default=None)):
        token = _extract_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="未登录")
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="登录已过期")
        conn = _db_conn()
        try:
            conn.execute("DELETE FROM profiles WHERE user_id = ?", (user["id"],))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "message": "用户画像已重置"}

    def _compress_to_simple(detailed_report: str) -> str:
        """
        用 LLM 对完整详细报告做二次提炼，生成真正精简的摘要。
        LLM 只允许提炼/复述报告中已有的结论，不能新增分析，保证与详细模式一致。
        Citation 块直接透传，不经 LLM。
        """
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage, SystemMessage

        # ── 分离 citation 块（不经 LLM，直接透传）────────────────────────────
        citation_block = ""
        citation_marker = "\n\n---\n📎 **决策依据来源**"
        if citation_marker in detailed_report:
            idx = detailed_report.index(citation_marker)
            citation_block = detailed_report[idx:]
            detailed_report = detailed_report[:idx]

        # ── 用 LLM 提炼精简摘要 ───────────────────────────────────────────────
        try:
            _llm = ChatGoogleGenerativeAI(model=_resolve_google_model(), temperature=0.1)
            system = (
                "你是一个报告摘要助手。你的任务是从用户提供的完整决策报告中提炼精简摘要。\n"
                "严格规则：\n"
                "1. 只能提炼/复述报告中已有的结论，禁止添加任何报告中没有的新内容\n"
                "2. 每个要点用一句完整的中文（有句号结尾），不超过30字\n"
                "3. 严格按以下格式输出，不要输出其他任何内容：\n\n"
                "# 【DecideX 决策建议】\n\n"
                "## ✅ 核心建议\n"
                "[一句话核心结论，直接从综合推荐章节提炼，15-25字]\n\n"
                "## 📌 关键理由\n"
                "- 💰 成本：[一句话，≤20字]\n"
                "- ⚠️ 风险：[一句话，≤20字]\n"
                "- 🎯 价值：[一句话，≤20字]\n"
                "- 👤 匹配度：[一句话，≤20字]\n\n"
                "## ⚡ 注意事项\n"
                "- [第一条行动建议，≤25字]\n"
                "- [第二条行动建议，≤25字]"
            )
            resp = _llm.invoke([
                SystemMessage(content=system),
                HumanMessage(content=f"请提炼以下报告：\n\n{detailed_report[:3000]}")
            ])
            simple_body = resp.content.strip()
        except Exception:
            # LLM 失败时的兜底：直接截取综合推荐段
            import re as _re
            m = _re.search(r'## ✅ 综合推荐\s*\n([\s\S]*?)(?=\n##|\Z)', detailed_report)
            fallback = m.group(1).strip()[:200] if m else "请切换至详细模式查看完整建议。"
            simple_body = (
                f"# 【DecideX 决策建议】\n\n"
                f"## ✅ 核心建议\n{fallback}\n\n"
                f"## ⚡ 注意事项\n- 建议切换至详细模式查看完整分析"
            )

        return simple_body + citation_block

    def _simple_llm_answer(message: str, user_profile: dict = None) -> str:
        """Simple 模式：直接调 LLM 给出简洁直接的回答（无需 graph，3-5s）"""
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage as _HM, SystemMessage as _SM
        from datetime import datetime
        current_year = datetime.now().year

        _llm = ChatGoogleGenerativeAI(model=_resolve_google_model(), temperature=0.3)
        profile_hint = ""
        if user_profile:
            profile_hint = f"\n用户画像参考：{json.dumps(user_profile, ensure_ascii=False)}\n"

        system = (
            f"你是 DecideX 智能决策助手（当前年份：{current_year}年）。\n"
            "用户选择了「快速模式」，需要简洁直接的回答。\n"
            "要求：\n"
            "1. 先给出**明确的行动建议**（一句话结论）\n"
            "2. 给出 3 条最关键的理由（每条 30 字以内）\n"
            "3. 如有风险，列出最重要的 1-2 个注意点\n"
            f"4. 所有数据、政策、价格均使用 {current_year} 年最新信息\n"
            "总字数控制在 200 字以内，使用 Markdown 格式。"
        )
        resp = _llm.invoke([_SM(content=system), _HM(content=f"{profile_hint}问题：{message}")])
        content = resp.content
        if isinstance(content, list):
            content = " ".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    async def _run_graph(inputs: dict, config: dict) -> str:
        """用 stream 收集所有消息，智能提取最佳结果"""
        import asyncio
        loop = asyncio.get_running_loop()

        def _extract_text(content) -> str:
            """兼容 Gemini list 格式、dict 和普通字符串"""
            if isinstance(content, dict):
                # dict 必须用 json.dumps，否则 str(dict) 产生单引号格式，json.loads 会失败
                return json.dumps(content, ensure_ascii=False)
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        parts.append(item.get("text", "") or json.dumps(item, ensure_ascii=False))
                    else:
                        parts.append(str(item))
                return " ".join(parts)
            return str(content or "")

        def _invoke():
            print("[DEBUG] streaming graph ...")
            all_msgs = []
            try:
                for chunk in decision_graph.stream(inputs, config, stream_mode="values"):
                    msgs = chunk.get("messages", []) if isinstance(chunk, dict) else []
                    all_msgs = msgs
                    # 简化日志，只打印最后一条
                    if msgs:
                        m = msgs[-1]
                        mtype = getattr(m, "type", "?")
                        tcalls = getattr(m, "tool_calls", [])
                        tnames = [t.get("name","?") if isinstance(t,dict) else getattr(t,"name","?") for t in tcalls]
                        text = _extract_text(getattr(m, "content", "") or "")
                        print(f"[DEBUG]   msg type={mtype} tool_calls={tnames} len={len(text)} preview={text[:60]}")
            except Exception as e:
                print(f"[DEBUG] stream error: {e}")

            print(f"[DEBUG] total messages after stream: {len(all_msgs)}")

            # ── 策略1：在 tool 消息中找 full_decision_analysis 的输出 ─────────────
            # full_decision_analysis 返回的是长报告（>500字），transfer 消息很短（<100字）
            # 只要 tool 消息够长且不是 transfer 消息，就是分析报告
            _TRANSFER_KEYWORDS = ("Successfully transferred", "transfer", "FINISH")

            def _unwrap_tool_json(text: str) -> str:
                """
                处理两种 JSON 包装情况：
                1. LangGraph 包装: {"full_decision_analysis_response": {"output": "Markdown..."}}
                2. LLM 直接返回结构化 JSON（应转成 Markdown）
                """
                stripped = text.strip()
                if not stripped.startswith("{"):
                    return text
                try:
                    obj = json.loads(stripped)
                except Exception:
                    return text  # 不是合法 JSON，原样返回

                # ── 情况1：LangGraph 包装，找 output 字段 ──────────────────────
                for _key, _val in obj.items():
                    if isinstance(_val, dict) and "output" in _val:
                        inner = str(_val["output"]).strip()
                        # output 里可能又是 JSON，递归解一层
                        return _unwrap_tool_json(inner)
                    if isinstance(_val, str) and len(_val) > 100:
                        return _val

                # ── 情况2：LLM 直接返回分析 JSON，转成 Markdown ────────────────
                md_parts = ["# 【DecideX 综合决策报告】\n"]

                def _fmt_dict(d: dict, depth: int = 0) -> str:
                    lines = []
                    for k, v in d.items():
                        if isinstance(v, dict):
                            lines.append(f"{'  ' * depth}**{k}**：")
                            lines.append(_fmt_dict(v, depth + 1))
                        elif isinstance(v, list):
                            lines.append(f"{'  ' * depth}**{k}**：" + "、".join(str(i) for i in v))
                        else:
                            lines.append(f"{'  ' * depth}**{k}**：{v}")
                    return "\n".join(lines)

                section_map = {
                    "cost_analysis": "## 💰 成本分析",
                    "risk_assessment": "## ⚠️ 风险评估",
                    "value_assessment": "## 🎯 价值评估",
                    "personal_match_assessment": "## 👤 个人匹配度",
                    "decision_summary": "## ✅ 综合推荐",
                }
                for key, header in section_map.items():
                    if key in obj:
                        val = obj[key]
                        md_parts.append(f"\n{header}\n")
                        if key == "decision_summary":
                            rec = val.get("recommendation", "")
                            just = val.get("justification", "")
                            alts = val.get("alternative_options", [])
                            if rec:
                                md_parts.append(f"**建议：{rec}**\n\n{just}")
                            if alts:
                                md_parts.append("\n**替代方案：**")
                                for a in alts:
                                    md_parts.append(f"- {a}")
                        else:
                            md_parts.append(_fmt_dict(val) if isinstance(val, dict) else str(val))

                if len(md_parts) > 1:
                    return "\n".join(md_parts)

                # 都没匹配上，原样返回
                return text

            for msg in reversed(all_msgs):
                if getattr(msg, "type", "") == "tool":
                    text = _extract_text(getattr(msg, "content", "") or "").strip()
                    is_transfer = any(kw in text for kw in _TRANSFER_KEYWORDS)
                    if len(text) > 300 and not is_transfer:
                        unwrapped = _unwrap_tool_json(text)  # 解包 LangGraph JSON 包装
                        # 解包后若仍是 JSON（以 { 开头），说明解包失败，跳过这条消息
                        if unwrapped.strip().startswith("{"):
                            print(f"[DEBUG] ⚠️ tool msg still JSON after unwrap, skipping, preview={unwrapped[:60]}")
                            continue
                        print(f"[DEBUG] ✅ found tool analysis result, len={len(unwrapped)}, preview={unwrapped[:80]}")
                        return unwrapped

            # ── 策略2：在 AI 消息中找有实质内容的中文分析（排除 LLM 内心独白）───
            for msg in reversed(all_msgs):
                mtype = getattr(msg, "type", "")
                if mtype != "ai":
                    continue
                text = _extract_text(getattr(msg, "content", "") or "").strip()
                # 必须含中文分析关键词，避免返回英文内心独白
                if len(text) > 300 and "FINISH" not in text:
                    if "成本" in text and ("风险" in text or "推荐" in text):
                        print(f"[DEBUG] ✅ found ai analysis msg, len={len(text)}")
                        return text

            # ── 策略3：找最后一条有实质内容的 AI 消息（排除 FINISH）───────────────
            for msg in reversed(all_msgs):
                mtype = getattr(msg, "type", "")
                text = _extract_text(getattr(msg, "content", "") or "").strip()
                if mtype == "ai" and text and "FINISH" not in text and len(text) > 100:
                    print(f"[DEBUG] found fallback ai msg, len={len(text)}")
                    return text

            # ── 最终兜底：直接调 LLM ─────────────────────────────────────────────
            print("[DEBUG] no useful content, falling back to direct LLM")
            return _direct_llm_fallback(inputs["messages"][0].content)

        return await loop.run_in_executor(None, _invoke)

    def _direct_llm_fallback(user_message: str) -> str:
        """当 graph 无输出时，直接调 Gemini 生成决策分析"""
        try:
            import os
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage, SystemMessage
            _llm = ChatGoogleGenerativeAI(
                model=_resolve_google_model(),
                temperature=0.3,
            )
            system = (
                "你是 DecideX 智能决策助手，专注于帮助用户做理性决策。\n"
                "请从**成本分析、风险评估、价值判断、个人匹配度**四个维度分析用户的决策问题，\n"
                "给出结构化的分析报告，最后给出明确的建议。\n"
                "用 Markdown 格式输出，带标题和要点。"
            )
            resp = _llm.invoke([SystemMessage(content=system), HumanMessage(content=user_message)])
            return resp.content or "分析完成，请重试。"
        except Exception as e:
            return f"❌ 分析失败：{e}\n\n请确认 GOOGLE_API_KEY 已正确设置。"

    @app.post("/transcribe")
    async def transcribe(
        audio: UploadFile = File(...),
        agent: str = Form(...)
    ):
        audio_data = await audio.read()
        return {
            "text": "语音识别功能需要配置 OpenAI Whisper API Key",
            "note": f"音频已接收，大小: {len(audio_data)} 字节"
        }

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "graph_available": GRAPH_AVAILABLE,
            "mode": "direct" if GRAPH_AVAILABLE else "mock",
        }

    if __name__ == "__main__":
        import uvicorn
        port = int(os.getenv("PORT", 8123))
        print(f"🚀 启动 DecideX 后端服务...")
        print(f"🌐 服务地址: http://localhost:{port}")
        print(f"📝 API 文档: http://localhost:{port}/docs")
        print(f"🤖 Graph 模式: {'直接调用' if GRAPH_AVAILABLE else 'Mock 演示'}")
        uvicorn.run(app, host="0.0.0.0", port=port)
else:
    print("请先安装依赖: pip install fastapi uvicorn")
