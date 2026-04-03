"""monitor.py — 시스템 + Railway + 봇 상태 모니터링"""
import os, asyncio, aiohttp, psutil, logging
from datetime import datetime
import db

logger = logging.getLogger(__name__)

RAILWAY_TOKEN    = os.environ.get("RAILWAY_TOKEN", "")
RAILWAY_SERVICE  = os.environ.get("RAILWAY_SERVICE_ID", "")
ALERT_CPU_PCT    = float(os.environ.get("ALERT_CPU_PCT", "85"))
ALERT_MEM_PCT    = float(os.environ.get("ALERT_MEM_PCT", "85"))

# ── 시스템 메트릭 ─────────────────────────────────────
def get_system_metrics() -> dict:
    cpu  = psutil.cpu_percent(interval=1)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_pct":      round(cpu, 1),
        "mem_pct":      round(mem.percent, 1),
        "mem_used_mb":  round(mem.used / 1024**2),
        "mem_total_mb": round(mem.total / 1024**2),
        "disk_pct":     round(disk.percent, 1),
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "ts":           datetime.now().isoformat(),
    }

# ── Railway 배포 상태 ─────────────────────────────────
async def get_railway_status() -> dict:
    if not RAILWAY_TOKEN or not RAILWAY_SERVICE:
        return {"status": "unconfigured", "detail": "RAILWAY_TOKEN 미설정"}

    query = """
    query ServiceStatus($serviceId: String!) {
      service(id: $serviceId) {
        id name
        deployments(first: 1) {
          edges { node { status createdAt meta { commitMessage } } }
        }
      }
    }
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://backboard.railway.app/graphql/v2",
                json={"query": query, "variables": {"serviceId": RAILWAY_SERVICE}},
                headers={"Authorization": f"Bearer {RAILWAY_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()

        svc = data.get("data", {}).get("service", {})
        edges = svc.get("deployments", {}).get("edges", [])
        if edges:
            deploy = edges[0]["node"]
            return {
                "status":    deploy.get("status", "UNKNOWN"),
                "deployed":  deploy.get("createdAt", ""),
                "commit":    (deploy.get("meta") or {}).get("commitMessage", ""),
                "service":   svc.get("name", ""),
            }
    except Exception as e:
        logger.error(f"Railway API error: {e}")
    return {"status": "ERROR", "detail": "API 호출 실패"}

# ── 통합 헬스 체크 ────────────────────────────────────
async def full_health_check() -> dict:
    metrics = get_system_metrics()
    railway = await get_railway_status()
    stats   = db.get_all_stats()
    alerts  = []

    if metrics["cpu_pct"] > ALERT_CPU_PCT:
        alerts.append(f"🔴 CPU 과부하: {metrics['cpu_pct']}%")
    if metrics["mem_pct"] > ALERT_MEM_PCT:
        alerts.append(f"🔴 메모리 과부하: {metrics['mem_pct']}%")
    if railway.get("status") not in ("SUCCESS", "ACTIVE", "unconfigured"):
        alerts.append(f"🚨 Railway 이상: {railway.get('status')}")

    # DB에 현재 메트릭 기록
    db.set_stat("cpu_pct",    metrics["cpu_pct"])
    db.set_stat("mem_pct",    metrics["mem_pct"])
    db.set_stat("deploy_status", railway.get("status", ""))

    return {
        "system":  metrics,
        "railway": railway,
        "stats":   stats,
        "alerts":  alerts,
        "healthy": len(alerts) == 0,
    }

# ── 빠른 텍스트 리포트 생성 ───────────────────────────
async def build_report_text(title: str = "정기 현황 리포트") -> str:
    health = await full_health_check()
    sys_m  = health["system"]
    rail   = health["railway"]
    stats  = health["stats"]
    daily  = db.get_daily_history(7)
    today  = daily[-1] if daily else {}

    lines = [
        f"📊 *{title}*",
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "⚙ *시스템 상태*",
        f"  CPU: {sys_m['cpu_pct']}% | RAM: {sys_m['mem_pct']}% ({sys_m['mem_used_mb']}MB/{sys_m['mem_total_mb']}MB)",
        f"  디스크 여유: {sys_m['disk_free_gb']}GB",
        "",
        "🚂 *Railway 배포*",
        f"  상태: {rail.get('status','?')} | 커밋: {rail.get('commit','')[:40]}",
        "",
        "💬 *봇 현황 (오늘)*",
        f"  메시지: {today.get('messages',0)}건 | 이미지: {today.get('images',0)}건 | 검색: {today.get('searches',0)}건",
        f"  클릭: {today.get('clicks',0)}건 | 전환: {today.get('conversions',0)}건 | 수익: ${today.get('revenue',0):.2f}",
        "",
        "📈 *누적*",
        f"  총 메시지: {stats.get('messages_total',0)}건 | 오류: {stats.get('errors_total',0)}건",
    ]

    if health["alerts"]:
        lines += ["", "🚨 *알림*"] + [f"  {a}" for a in health["alerts"]]
    else:
        lines.append("\n✅ 모든 시스템 정상")

    return "\n".join(lines)

