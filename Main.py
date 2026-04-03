"""main.py — 진입점: 봇 + 대시보드 + 스케줄러 동시 기동"""
import asyncio, logging, threading, os
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db, bot, web
from pipeline import PIPELINE_REGISTRY, PipelineContext

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("main")

async def main():
    # 1. DB 초기화
    db.init_db()
    logger.info("✅ DB initialized")

    # 2. Flask 대시보드 (별도 스레드)
    t = threading.Thread(target=web.run_flask, daemon=True)
    t.start()
    logger.info("✅ Dashboard started")

    # 3. Telegram 봇 빌드
    application = bot.build_app()

    # 4. 파이프라인 컨텍스트 (봇 알림 전송 연결)
    async def send_alert(text: str):
        await bot.send_to_admin(application, text)

    ctx = PipelineContext(
        send_alert=send_alert,
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY",""),
    )

    # 5. 스케줄러 — 파이프라인 자동 등록
    scheduler = AsyncIOScheduler()
    for name, PipeClass in PIPELINE_REGISTRY.items():
        instance = PipeClass()
        if instance.schedule == "interval":
            scheduler.add_job(
                lambda p=instance: asyncio.create_task(p.safe_run(ctx)),
                "interval",
                minutes=instance.interval_min,
                id=name,
                max_instances=1,
                misfire_grace_time=60,
            )
            logger.info(f"⏱ Pipeline [{name}] — interval {instance.interval_min}m")
        elif instance.schedule == "cron" and instance.cron:
            scheduler.add_job(
                lambda p=instance: asyncio.create_task(p.safe_run(ctx)),
                "cron", **instance.cron,
                id=name, max_instances=1,
            )
            logger.info(f"🕐 Pipeline [{name}] — cron {instance.cron}")

    scheduler.start()
    logger.info(f"✅ Scheduler started — {len(PIPELINE_REGISTRY)} pipelines registered")

    # 6. 시작 알림
    await send_alert(
        "🚀 *EVE AI 봇이 시작되었습니다*\n\n"
        f"파이프라인: {len(PIPELINE_REGISTRY)}개 활성\n"
        "대시보드: Railway URL 접속\n\n"
        "준비 완료 — /start 로 시작하세요"
    )

    # 7. 봇 폴링 (블로킹)
    logger.info("🤖 Bot polling started")
    await application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())

