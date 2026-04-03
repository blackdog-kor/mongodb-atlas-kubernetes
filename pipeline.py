"""pipeline.py — 확장 가능 자동화 파이프라인 프레임워크

새 파이프라인 추가 방법:
    @register_pipeline
    class MyPipeline(Pipeline):
        name        = "my_pipe"
        description = "설명"
        schedule    = "interval"   # interval | cron | manual
        interval_min = 30
        async def run(self, ctx: PipelineContext) -> str:
            # ... 작업 수행
            return "결과 메시지"
"""

import logging, asyncio, aiohttp, os
from dataclasses import dataclass, field
from typing import Callable, Awaitable
from datetime import datetime
import db, monitor

logger = logging.getLogger(__name__)

PIPELINE_REGISTRY: dict[str, type] = {}

def register_pipeline(cls):
    PIPELINE_REGISTRY[cls.name] = cls
    return cls

@dataclass
class PipelineContext:
    """파이프라인 실행 컨텍스트 — 필요 데이터 전부 여기에"""
    send_alert: Callable[[str], Awaitable[None]]  # Telegram 알림 전송 함수
    anthropic_key: str = ""
    extra: dict = field(default_factory=dict)

class Pipeline:
    name: str = "base"
    description: str = ""
    schedule: str = "manual"   # interval | cron | manual
    interval_min: int = 60
    cron: str = ""             # schedule=cron 일 때 APScheduler cron 표현식

    async def run(self, ctx: PipelineContext) -> str:
        raise NotImplementedError

    async def safe_run(self, ctx: PipelineContext):
        try:
            result = await self.run(ctx)
            db.update_pipeline_status(self.name, "✅ 성공")
            db.log_event(f"pipeline:{self.name}", {"status": "ok", "result": result[:200]})
            return result
        except Exception as e:
            msg = f"파이프라인 '{self.name}' 오류: {e}"
            logger.error(msg)
            db.update_pipeline_status(self.name, f"❌ {str(e)[:60]}")
            db.log_event(f"pipeline:{self.name}", {"status": "error", "error": str(e)})
            db.inc_stat("errors_total")
            raise

# ══════════════════════════════════════════════════
#  내장 파이프라인들
# ══════════════════════════════════════════════════

@register_pipeline
class HealthAlertPipeline(Pipeline):
    """CPU/메모리/Railway 이상 감지 → 즉시 알림"""
    name         = "health_alert"
    description  = "시스템 이상 감지 및 Telegram 알림"
    schedule     = "interval"
    interval_min = 5

    async def run(self, ctx: PipelineContext) -> str:
        health = await monitor.full_health_check()
        if health["alerts"]:
            msg = "🚨 *시스템 알림*\n\n" + "\n".join(health["alerts"])
            await ctx.send_alert(msg)
        return f"헬스체크 완료 — 알림 {len(health['alerts'])}건"


@register_pipeline
class HourlyReportPipeline(Pipeline):
    """시간별 운영 현황 요약 리포트"""
    name         = "hourly_report"
    description  = "시간별 현황 리포트 자동 발송"
    schedule     = "interval"
    interval_min = int(os.environ.get("REPORT_INTERVAL_MIN", "60"))

    async def run(self, ctx: PipelineContext) -> str:
        text = await monitor.build_report_text("시간별 현황 리포트")
        await ctx.send_alert(text)
        return "리포트 발송 완료"


@register_pipeline
class DailyDigestPipeline(Pipeline):
    """매일 오전 9시 일일 요약 + 수익 리포트"""
    name        = "daily_digest"
    description = "일일 요약 — 매일 09:00 발송"
    schedule    = "cron"
    cron        = {"hour": 9, "minute": 0}

    async def run(self, ctx: PipelineContext) -> str:
        daily = db.get_daily_history(7)
        total_rev = sum(d.get("revenue", 0) for d in daily)
        total_msg = sum(d.get("messages", 0) for d in daily)
        total_cnv = sum(d.get("conversions", 0) for d in daily)

        # 전일 대비
        today = daily[-1] if daily else {}
        yesterday = daily[-2] if len(daily) > 1 else {}
        rev_diff = today.get("revenue", 0) - yesterday.get("revenue", 0)
        diff_icon = "📈" if rev_diff >= 0 else "📉"

        lines = [
            "☀️ *일일 다이제스트*",
            f"📅 {datetime.now().strftime('%Y년 %m월 %d일')}",
            "",
            "📊 *오늘 현황*",
            f"  메시지: {today.get('messages',0)}건",
            f"  클릭: {today.get('clicks',0)}건",
            f"  전환: {today.get('conversions',0)}건",
            f"  수익: ${today.get('revenue',0):.2f} {diff_icon} (전일比 ${rev_diff:+.2f})",
            "",
            "📈 *7일 누적*",
            f"  총 메시지: {total_msg}건 | 전환: {total_cnv}건 | 수익: ${total_rev:.2f}",
        ]

        await ctx.send_alert("\n".join(lines))
        return "일일 다이제스트 발송 완료"


@register_pipeline
class RevenueTrackerPipeline(Pipeline):
    """수익/전환 데이터 집계 — 외부 API 연동 확장 가능"""
    name         = "revenue_tracker"
    description  = "수익·전환 데이터 집계 (외부 API 연동)"
    schedule     = "interval"
    interval_min = 30

    # ── 확장 포인트: 이 함수를 오버라이드하여 실제 어필리에이트 API 연동 ──
    async def fetch_revenue_data(self) -> dict:
        """
        예시: ClickBank, CJ Affiliate, 자체 트래킹 서버 등
        실제 연동 시 아래 로직을 교체하세요.
        """
        api_url = os.environ.get("REVENUE_API_URL", "")
        api_key = os.environ.get("REVENUE_API_KEY", "")

        if not api_url:
            # 데모 데이터 (실제 연동 전까지)
            return {"clicks": 0, "conversions": 0, "revenue": 0.0}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                return await resp.json()

    async def run(self, ctx: PipelineContext) -> str:
        data = await self.fetch_revenue_data()
        clicks      = data.get("clicks", 0)
        conversions = data.get("conversions", 0)
        revenue     = float(data.get("revenue", 0))

        if clicks:
            db.inc_daily("clicks", clicks)
        if conversions:
            db.inc_daily("conversions", conversions)
        if revenue:
            db.inc_daily("revenue", 0, revenue=revenue)

        return f"수익 집계 완료: 클릭 {clicks}, 전환 {conversions}, 수익 ${revenue:.2f}"


@register_pipeline
class ErrorAlertPipeline(Pipeline):
    """오류 급증 감지 → 즉시 알림"""
    name         = "error_alert"
    description  = "오류 급증 시 즉시 알림"
    schedule     = "interval"
    interval_min = 10
    _last_error_count = 0

    async def run(self, ctx: PipelineContext) -> str:
        current = int(db.get_stat("errors_total", 0))
        diff    = current - self._last_error_count

        if diff >= 5:  # 10분 내 5건 이상 오류
            await ctx.send_alert(
                f"🚨 *오류 급증 감지*\n"
                f"최근 {self.__class__.interval_min}분간 오류 {diff}건 발생\n"
                f"누적 오류: {current}건\n\n"
                f"로그 확인: `/status` 명령어 실행"
            )
        self.__class__._last_error_count = current
        return f"오류 모니터링 — 최근 {diff}건"


# ── 파이프라인 목록 조회 ──────────────────────────────
def list_pipelines() -> list[dict]:
    return [
        {
            "name":        cls.name,
            "description": cls.description,
            "schedule":    cls.schedule,
            "interval_min": getattr(cls, "interval_min", None),
        }
        for cls in PIPELINE_REGISTRY.values()
    ]

