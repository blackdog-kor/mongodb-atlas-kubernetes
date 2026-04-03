"""web.py — Flask 실시간 대시보드"""
import os, json
from flask import Flask, jsonify, Response
from datetime import datetime
import db, monitor

flask_app = Flask(__name__)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EVE AI Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#07090f;--surface:#0d1117;--border:#1c2133;
    --accent:#6366f1;--accent2:#8b5cf6;--green:#22c55e;
    --red:#ef4444;--yellow:#f59e0b;--text:#e2e8f0;--muted:#64748b;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'IBM Plex Sans','Noto Sans KR',sans-serif;min-height:100vh}
  .header{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 24px;
    display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}
  .logo{display:flex;align-items:center;gap:10px}
  .logo-icon{width:34px;height:34px;border-radius:8px;
    background:linear-gradient(135deg,#6366f1,#8b5cf6);
    display:flex;align-items:center;justify-content:center;font-size:16px;
    box-shadow:0 0 14px rgba(99,102,241,.5)}
  .logo-text{font-weight:700;font-size:15px;color:#c7d2fe;letter-spacing:.08em}
  .live-dot{width:8px;height:8px;border-radius:50%;background:var(--green);
    animation:pulse 2s infinite;display:inline-block;margin-right:6px}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  .main{padding:20px 24px;max-width:1200px;margin:0 auto}
  .grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
  .grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-bottom:20px}
  .grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px}
  .card-title{font-size:11px;color:var(--muted);letter-spacing:.15em;text-transform:uppercase;margin-bottom:14px}
  .stat-num{font-size:32px;font-weight:700;color:var(--accent);line-height:1}
  .stat-label{font-size:12px;color:var(--muted);margin-top:4px}
  .stat-sub{font-size:11px;color:var(--muted);margin-top:8px}
  .badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
  .badge-green{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3)}
  .badge-red{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3)}
  .badge-yellow{background:rgba(245,158,11,.15);color:var(--yellow);border:1px solid rgba(245,158,11,.3)}
  .badge-blue{background:rgba(99,102,241,.2);color:#a5b4fc;border:1px solid rgba(99,102,241,.4)}
  .bar{height:6px;background:rgba(255,255,255,.05);border-radius:3px;overflow:hidden;margin-top:6px}
  .bar-fill{height:100%;border-radius:3px;transition:width .6s ease;
    background:linear-gradient(90deg,var(--accent),var(--accent2))}
  .bar-fill.warn{background:linear-gradient(90deg,var(--yellow),#f97316)}
  .bar-fill.danger{background:linear-gradient(90deg,var(--red),#f97316)}
  .event-item{padding:8px 0;border-bottom:1px solid var(--border);font-size:12px}
  .event-item:last-child{border-bottom:none}
  .event-time{color:var(--muted);font-size:10px;margin-top:2px}
  .pipe-item{display:flex;justify-content:space-between;align-items:center;
    padding:8px 0;border-bottom:1px solid var(--border)}
  .pipe-item:last-child{border-bottom:none}
  .footer{text-align:center;font-size:11px;color:var(--muted);padding:20px;margin-top:10px}
  canvas{max-height:200px}
  @media(max-width:768px){.grid-4{grid-template-columns:repeat(2,1fr)}.grid-2,.grid-3{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="header">
  <div class="logo">
    <div class="logo-icon">⚡</div>
    <div>
      <div class="logo-text">EVE AI</div>
      <div style="font-size:10px;color:var(--muted)">DASHBOARD</div>
    </div>
  </div>
  <div style="font-size:12px;color:var(--muted)">
    <span class="live-dot"></span>
    <span id="last-update">로딩 중...</span>
  </div>
</div>

<div class="main">
  <!-- 핵심 지표 -->
  <div class="grid-4" id="kpis"></div>
  <!-- 시스템 메트릭 -->
  <div class="grid-3">
    <div class="card" id="sys-cpu"></div>
    <div class="card" id="sys-mem"></div>
    <div class="card" id="sys-disk"></div>
  </div>
  <!-- 차트 -->
  <div class="grid-2">
    <div class="card">
      <div class="card-title">메시지 트렌드 (7일)</div>
      <canvas id="msgChart"></canvas>
    </div>
    <div class="card">
      <div class="card-title">수익 트렌드 (7일)</div>
      <canvas id="revChart"></canvas>
    </div>
  </div>
  <!-- Railway + 파이프라인 -->
  <div class="grid-2">
    <div class="card" id="railway-card"></div>
    <div class="card" id="pipeline-card"></div>
  </div>
  <!-- 이벤트 로그 -->
  <div class="card">
    <div class="card-title">최근 이벤트 로그</div>
    <div id="event-log"></div>
  </div>
</div>

<div class="footer">EVE AI Dashboard · 10초 자동 갱신 · <span id="uptime"></span></div>

<script>
let msgChart, revChart;
const $ = id => document.getElementById(id);
const fmt = n => Number(n||0).toLocaleString();
const pct = n => `${Number(n||0).toFixed(1)}%`;
const barClass = p => p > 85 ? 'danger' : p > 65 ? 'warn' : '';

function kpiCard(num, label, badge='', badgeType='blue', sub='') {
  return `<div class="card">
    <div class="stat-num">${num}</div>
    <div class="stat-label">${label}</div>
    ${badge ? `<div style="margin-top:8px"><span class="badge badge-${badgeType}">${badge}</span></div>` : ''}
    ${sub ? `<div class="stat-sub">${sub}</div>` : ''}
  </div>`;
}

function sysCard(el, label, pctVal, detail) {
  const p = parseFloat(pctVal)||0;
  el.innerHTML = `<div class="card-title">${label}</div>
    <div style="font-size:24px;font-weight:700;color:${p>85?'var(--red)':p>65?'var(--yellow)':'var(--accent)'}">
      ${pct(p)}</div>
    <div class="bar"><div class="bar-fill ${barClass(p)}" style="width:${Math.min(p,100)}%"></div></div>
    <div style="font-size:11px;color:var(--muted);margin-top:6px">${detail}</div>`;
}

function initCharts(daily) {
  const labels = daily.map(d => d.day?.slice(5)||'');
  const msgs   = daily.map(d => d.messages||0);
  const revs   = daily.map(d => d.revenue||0);
  const opts   = { responsive:true, plugins:{legend:{display:false}},
    scales:{x:{grid:{color:'rgba(255,255,255,.05)'},ticks:{color:'#64748b'}},
            y:{grid:{color:'rgba(255,255,255,.05)'},ticks:{color:'#64748b'}}} };

  if (msgChart) msgChart.destroy();
  if (revChart) revChart.destroy();

  msgChart = new Chart($('msgChart'), { type:'bar',
    data:{labels, datasets:[{data:msgs, backgroundColor:'rgba(99,102,241,.6)',
      borderColor:'#6366f1', borderWidth:1, borderRadius:4}]}, options:opts });
  revChart = new Chart($('revChart'), { type:'line',
    data:{labels, datasets:[{data:revs, borderColor:'#22c55e', backgroundColor:'rgba(34,197,94,.1)',
      borderWidth:2, tension:.4, fill:true, pointRadius:3}]}, options:opts });
}

async function refresh() {
  try {
    const r = await fetch('/api/full');
    const d = await r.json();
    const {stats, system, railway, daily, pipelines, events} = d;

    // KPIs
    const today = daily[daily.length-1]||{};
    $('kpis').innerHTML =
      kpiCard(fmt(stats.messages_total||0), '총 메시지', '누적', 'blue') +
      kpiCard(fmt(today.messages||0), '오늘 메시지', '금일', 'blue') +
      kpiCard(`$${Number(today.revenue||0).toFixed(2)}`, '오늘 수익', '금일', 'green') +
      kpiCard(fmt(stats.errors_total||0), '누적 오류', stats.errors_total>0?'주의':'정상',
              stats.errors_total>0?'red':'green');

    // 시스템
    sysCard($('sys-cpu'), 'CPU', system.cpu_pct, `${system.cpu_pct}% 사용 중`);
    sysCard($('sys-mem'), 'RAM', system.mem_pct,
            `${system.mem_used_mb}MB / ${system.mem_total_mb}MB`);
    sysCard($('sys-disk'), '디스크', system.disk_pct,
            `여유 ${system.disk_free_gb}GB`);

    // Railway
    const rSt = railway.status||'?';
    const rBadge = rSt==='SUCCESS'||rSt==='ACTIVE' ? 'badge-green' : 'badge-red';
    $('railway-card').innerHTML = `
      <div class="card-title">Railway 배포 상태</div>
      <div style="margin-bottom:10px"><span class="badge ${rBadge}">${rSt}</span></div>
      <div style="font-size:12px;color:var(--muted);line-height:1.8">
        서비스: ${railway.service||'미설정'}<br>
        커밋: ${(railway.commit||'').slice(0,50)||'—'}<br>
        배포: ${railway.deployed ? new Date(railway.deployed).toLocaleString('ko-KR') : '—'}
      </div>`;

    // Pipelines
    $('pipeline-card').innerHTML = `<div class="card-title">파이프라인 상태</div>` +
      (pipelines.length ? pipelines.map(p =>
        `<div class="pipe-item">
          <div><div style="font-size:12px">${p.name}</div>
          <div style="font-size:10px;color:var(--muted)">${p.last_run||'미실행'}</div></div>
          <span class="badge ${p.last_status?.startsWith('✅')?'badge-green':'badge-yellow'}">
            ${p.last_status||'미실행'}</span>
        </div>`).join('') : '<div style="color:var(--muted);font-size:12px">파이프라인 없음</div>');

    // Events
    $('event-log').innerHTML = events.slice(0,8).map(e =>
      `<div class="event-item">
        <div style="color:var(--text)">${e.event_type}</div>
        <div class="event-time">${e.ts}</div>
      </div>`).join('') || '<div style="color:var(--muted);font-size:12px">이벤트 없음</div>';

    // Charts
    initCharts(daily);

    $('last-update').textContent = `마지막 갱신: ${new Date().toLocaleTimeString('ko-KR')}`;
  } catch(e) { console.error(e); }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""

@flask_app.route("/")
def dashboard():
    return DASHBOARD_HTML

@flask_app.route("/api/full")
async def api_full():
    import asyncio
    health  = await monitor.full_health_check()
    daily   = db.get_daily_history(7)
    pipes   = db.get_pipeline_statuses()
    events  = db.get_recent_events(20)
    return jsonify({
        "stats":     health["stats"],
        "system":    health["system"],
        "railway":   health["railway"],
        "alerts":    health["alerts"],
        "daily":     daily,
        "pipelines": pipes,
        "events":    events,
        "ts":        datetime.now().isoformat(),
    })

@flask_app.route("/api/stats")
def api_stats():
    return jsonify(db.get_all_stats())

@flask_app.route("/health")
def health():
    return jsonify({"status":"ok","ts":datetime.now().isoformat()})

# 수익 데이터 수동 입력 API (웹훅 연동 가능)
@flask_app.route("/api/revenue", methods=["POST"])
def api_revenue():
    from flask import request
    data = request.get_json(silent=True) or {}
    clicks      = int(data.get("clicks", 0))
    conversions = int(data.get("conversions", 0))
    revenue     = float(data.get("revenue", 0))
    if clicks:      db.inc_daily("clicks", clicks)
    if conversions: db.inc_daily("conversions", conversions)
    if revenue:     db.inc_daily("revenue", 0, revenue=revenue)
    db.log_event("revenue:webhook", data)
    return jsonify({"ok": True})

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

