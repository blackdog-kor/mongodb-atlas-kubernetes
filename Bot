"""bot.py — Telegram 봇 (Claude 모든 기능 통합)"""
import os, base64, logging, aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ChatAction
import db, monitor

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_KEY  = os.environ["ANTHROPIC_API_KEY"]
ADMIN_CHAT_ID  = int(os.environ.get("ADMIN_CHAT_ID", "0"))
ALLOWED_USERS  = set(
    int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()
)
CLAUDE_MODEL = "claude-sonnet-4-20250514"

PRESETS = {
    "general":  ("🧠 범용 비서",
        "당신은 EVE, 최고 수준의 AI 비서입니다. 정확하고 간결하게 한국어로 답변합니다. 이미지가 첨부되면 상세히 분석합니다."),
    "marketer": ("📈 마케터",
        "당신은 카지노 어필리에이트 마케팅 전문가입니다. 전환율 최적화, 트래픽, 수익화 전략에 집중한 조언을 데이터 기반으로 제공합니다."),
    "coder":    ("💻 코드 디버거",
        "당신은 시니어 풀스택 개발자입니다. 코드 오류 분석, 아키텍처 개선, 최적화 솔루션을 코드 블록과 함께 제공합니다. 이미지의 에러 화면도 분석합니다."),
    "analyst":  ("🔍 분석가",
        "당신은 비즈니스 인텔리전스 전문가입니다. 스크린샷, 차트, 데이터를 분석하여 실행 가능한 인사이트를 제공합니다."),
}

# 런타임 상태
_sessions: dict[int, list] = {}   # chat_id → history
_preset:   dict[int, str]  = {}   # chat_id → preset key
_search:   dict[int, bool] = {}   # chat_id → web search on/off

def is_allowed(chat_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return chat_id in ALLOWED_USERS or chat_id == ADMIN_CHAT_ID

def get_system(chat_id: int) -> str:
    return PRESETS.get(_preset.get(chat_id, "general"), PRESETS["general"])[1]

# ── Claude API 호출 ───────────────────────────────────
async def call_claude(chat_id: int, text: str,
                       image_b64: str = None, image_type: str = "image/jpeg") -> str:
    history = _sessions.get(chat_id, [])[-20:]

    if image_b64:
        content = [{"type":"image","source":{"type":"base64","media_type":image_type,"data":image_b64}}]
        if text:
            content.append({"type":"text","text":text})
        db.inc_stat("images_total")
        db.inc_daily("images")
    else:
        content = text

    user_msg = {"role":"user","content":content}
    messages = history + [user_msg]

    payload = {
        "model":   CLAUDE_MODEL,
        "max_tokens": 1500,
        "system":  get_system(chat_id),
        "messages": messages,
    }
    if _search.get(chat_id):
        payload["tools"] = [{"type":"web_search_20250305","name":"web_search"}]
        db.inc_stat("searches_total")
        db.inc_daily("searches")

    headers = {
        "x-api-key":          ANTHROPIC_KEY,
        "anthropic-version":  "2023-06-01",
        "content-type":       "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            data = await resp.json()

    if "error" in data:
        raise Exception(data["error"]["message"])

    reply = "".join(
        b["text"] for b in data.get("content",[]) if b.get("type")=="text"
    ) or "(응답 없음)"

    # 히스토리 갱신
    if chat_id not in _sessions:
        _sessions[chat_id] = []
    _sessions[chat_id].append(user_msg)
    _sessions[chat_id].append({"role":"assistant","content":reply})

    db.inc_stat("messages_total")
    db.inc_daily("messages")
    return reply

async def send_chunks(update: Update, text: str):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await update.message.reply_text(chunk, parse_mode="Markdown")

# ── 커맨드 핸들러 ─────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_allowed(cid):
        await update.message.reply_text("❌ 접근 권한이 없습니다.")
        return

    preset_name = PRESETS.get(_preset.get(cid,"general"), PRESETS["general"])[0]
    search_st   = "✅ ON" if _search.get(cid) else "❌ OFF"

    keyboard = [
        [InlineKeyboardButton("🧠 범용", callback_data="p:general"),
         InlineKeyboardButton("📈 마케터", callback_data="p:marketer")],
        [InlineKeyboardButton("💻 코드", callback_data="p:coder"),
         InlineKeyboardButton("🔍 분석가", callback_data="p:analyst")],
        [InlineKeyboardButton(f"🔍 웹검색 [{search_st}]", callback_data="toggle_search")],
        [InlineKeyboardButton("📊 현황 리포트", callback_data="report"),
         InlineKeyboardButton("🗑 대화 초기화", callback_data="clear")],
    ]
    await update.message.reply_text(
        f"⚡ *EVE AI 비서*\n\n"
        f"현재 모드: *{preset_name}*\n"
        f"웹 검색: *{search_st}*\n\n"
        f"텍스트, 이미지, 스크린샷으로 대화하세요:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _sessions.pop(update.effective_chat.id, None)
    await update.message.reply_text("🗑 대화 기록이 초기화되었습니다.")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if cid != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ 관리자 전용 명령어입니다.")
        return
    await ctx.bot.send_chat_action(cid, ChatAction.TYPING)
    text = await monitor.build_report_text("수동 요청 리포트")
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_pipelines(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """파이프라인 목록 + 상태 확인"""
    from pipeline import list_pipelines
    statuses = {p["name"]: p for p in db.get_pipeline_statuses()}
    pipes    = list_pipelines()
    lines    = ["⚙ *파이프라인 목록*\n"]
    for p in pipes:
        st = statuses.get(p["name"], {})
        last = st.get("last_status", "미실행")
        cnt  = st.get("run_count", 0)
        lines.append(f"*{p['name']}*\n  {p['description']}\n  상태: {last} | 실행: {cnt}회\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *EVE AI 명령어*\n\n"
        "/start — 모드 선택 메뉴\n"
        "/clear — 대화 기록 초기화\n"
        "/status — 시스템 현황 (관리자)\n"
        "/pipelines — 파이프라인 목록/상태 (관리자)\n"
        "/help — 이 도움말\n\n"
        "💡 사진을 전송하면 이미지 분석\n"
        "💡 웹검색 ON 시 최신 정보 조회",
        parse_mode="Markdown"
    )

# ── 콜백 버튼 ─────────────────────────────────────────
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid  = query.message.chat_id
    data = query.data

    if data.startswith("p:"):
        key = data[2:]
        _preset[cid] = key
        _sessions.pop(cid, None)
        label = PRESETS[key][0]
        await query.edit_message_text(
            f"✅ *{label}* 모드로 전환\n대화 기록 초기화됨",
            parse_mode="Markdown"
        )

    elif data == "toggle_search":
        _search[cid] = not _search.get(cid, False)
        st = "✅ ON" if _search[cid] else "❌ OFF"
        await query.edit_message_text(f"🔍 웹 검색: *{st}*", parse_mode="Markdown")

    elif data == "report":
        if cid != ADMIN_CHAT_ID:
            await query.edit_message_text("❌ 관리자 전용 기능입니다.")
            return
        text = await monitor.build_report_text("수동 요청 리포트")
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "clear":
        _sessions.pop(cid, None)
        await query.edit_message_text("🗑 대화 기록 초기화 완료")

# ── 메시지 핸들러 ─────────────────────────────────────
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_allowed(cid):
        return
    await ctx.bot.send_chat_action(cid, ChatAction.TYPING)
    try:
        reply = await call_claude(cid, update.message.text)
        await send_chunks(update, reply)
    except Exception as e:
        db.inc_stat("errors_total")
        db.log_event("error:text", {"chat_id": cid, "error": str(e)})
        await update.message.reply_text(f"⚠ 오류: {str(e)[:300]}")

async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_allowed(cid):
        return
    await ctx.bot.send_chat_action(cid, ChatAction.TYPING)
    caption = update.message.caption or "이 이미지를 상세히 분석해주세요."
    photo   = update.message.photo[-1]
    file    = await ctx.bot.get_file(photo.file_id)
    async with aiohttp.ClientSession() as s:
        async with s.get(file.file_path) as r:
            b64 = base64.b64encode(await r.read()).decode()
    try:
        reply = await call_claude(cid, caption, image_b64=b64)
        await send_chunks(update, reply)
    except Exception as e:
        db.inc_stat("errors_total")
        await update.message.reply_text(f"⚠ 이미지 분석 오류: {str(e)[:300]}")

# ── 앱 빌드 ───────────────────────────────────────────
def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("clear",     cmd_clear))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("pipelines", cmd_pipelines))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app

async def send_to_admin(app: Application, text: str):
    """파이프라인 알림 전송용"""
    if ADMIN_CHAT_ID:
        try:
            await app.bot.send_message(
                chat_id=ADMIN_CHAT_ID, text=text, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Admin send error: {e}")

