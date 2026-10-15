// 퀀트 시그널 PWA
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const TITLES = { today: "오늘", track: "추적", news: "공시", bot: "봇" };
const MARKET = { NASDAQ: "나스닥", KOSPI: "코스피", KOSDAQ: "코스닥" };
const RUN_LABEL = { KR: "한국장", US: "미국장" };
const isKR = (m) => m === "KOSPI" || m === "KOSDAQ";
const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const isIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent);

const state = { tab: "today", overview: null, track: { market: "ALL", days: 7 }, news: "ALL", runs: null, pollTimer: null, wasRunning: false };

// ---------- 공통 ----------
async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 401) { showLogin(); throw new Error("unauthorized"); }
  if (!res.ok) {
    let msg = `오류 (${res.status})`;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  $("#offline").hidden = true;
  return res.json();
}
function handleError(e) {
  if (e.message === "unauthorized") return;
  if (e instanceof TypeError) { $("#offline").hidden = false; return; }  // 네트워크 실패
  toast(e.message);
}
function toast(text, ms = 2400) {
  const t = $("#toast"); t.textContent = text; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function price(v, market) {
  if (v == null || isNaN(v)) return "-";
  return isKR(market) ? `${Math.round(v).toLocaleString("ko-KR")}원` : `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function pct(v, digits = 1) {
  if (v == null || isNaN(v)) return "-";
  const p = v * 100;
  return `${p > 0 ? "+" : ""}${p.toFixed(digits)}%`;
}
const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
function kst(iso, withDate = false) {
  if (!iso) return "-";
  const d = new Date(iso);
  const opt = { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false };
  if (withDate) Object.assign(opt, { month: "numeric", day: "numeric" });
  return d.toLocaleString("ko-KR", opt);
}
function relDay(iso) {
  const fmt = (d) => d.toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" });
  const d = new Date(iso), now = new Date(), y = new Date(Date.now() - 86400000);
  if (fmt(d) === fmt(now)) return `오늘 ${kst(iso)}`;
  if (fmt(d) === fmt(y)) return `어제 ${kst(iso)}`;
  return kst(iso, true);
}
const code = (t) => t.replace(/\.(KS|KQ)$/, "");
const elapsed = (sec) => `${Math.floor(sec / 60)}분 ${String(sec % 60).padStart(2, "0")}초`;

function confirmDialog(title, text, okText = "확인") {
  return new Promise((resolve) => {
    const d = $("#dialog");
    $("#dialog-title").textContent = title; $("#dialog-text").textContent = text; $("#dialog-ok").textContent = okText;
    d.hidden = false;
    const done = (v) => { d.hidden = true; $("#dialog-ok").onclick = $("#dialog-cancel").onclick = null; resolve(v); };
    $("#dialog-ok").onclick = () => done(true);
    $("#dialog-cancel").onclick = () => done(false);
  });
}
function openSheet(html) {
  $("#sheet-content").innerHTML = html;
  $("#sheet").hidden = $("#sheet-backdrop").hidden = false;
  $("#sheet").scrollTop = 0;
}
function closeSheet() {
  $("#sheet").hidden = $("#sheet-backdrop").hidden = true;
  if (state.scheduleEditing) { state.scheduleEditing = false; if (state.tab === "bot") load("bot"); }
}

// ---------- 탭 ----------
function switchTab(tab, push = true) {
  state.tab = tab;
  $$(".tab").forEach((s) => (s.hidden = s.id !== `tab-${tab}`));
  $$(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("#page-title").textContent = TITLES[tab];
  if (push) history.replaceState(null, "", `/?tab=${tab}`);
  window.scrollTo(0, 0);
  load(tab);
}
async function load(tab = state.tab) {
  const btn = $("#refresh-btn"); btn.classList.add("spinning");
  try {
    if (tab === "today") await loadToday();
    if (tab === "track") await loadTrack();
    if (tab === "news") await loadNews();
    if (tab === "bot") await loadBot();
  } catch (e) { handleError(e); }
  btn.classList.remove("spinning");
}

// ---------- 오늘 ----------
async function loadToday() {
  const regimesReq = api("/api/regimes").catch(() => ({}));  // 느릴 수 있어 추천 목록과 따로 그림 (실패 시 확인 불가 표시)
  const o = await api("/api/overview");
  state.overview = o;
  renderRunning(o.running);
  renderToday(o);
  renderRegimes(await regimesReq);
}
function renderRegimes(regimes) {
  $("#regimes").innerHTML = ["NASDAQ", "KOSPI", "KOSDAQ"].map((m) => {
    const r = regimes[m] || {};
    const pill = r.bull == null ? `<span class="pill pill-off">확인 불가</span>`
      : r.bull ? `<span class="pill pill-ok">매수 가능</span>` : `<span class="pill pill-off">하락장 · 매수 차단</span>`;
    const gap = r.gap != null ? `<span class="regime-gap ${tone(r.gap)}">200일선 ${pct(r.gap)}</span>` : "";
    return `<div class="regime"><div><span class="regime-name">${MARKET[m]}</span>${gap}</div>${pill}</div>`;
  }).join("");
}
function renderToday(o) {
  $("#today-count").textContent = o.signals.length ? o.signals.length : "";
  if (!o.signals.length) {
    const next = Object.entries(o.next_runs || {}).sort((a, b) => a[1].localeCompare(b[1]))[0];
    const nextText = next ? `다음 자동 분석: ${RUN_LABEL[next[0]]} ${relDay(next[1])}` : "자동 실행이 꺼져 있어요";
    $("#today-list").innerHTML = `<div class="empty"><span class="emoji">🔍</span><strong>오늘은 아직 추천 종목이 없어요</strong>${esc(nextText)}</div>`;
  } else {
    $("#today-list").innerHTML = o.signals.map(signalCard).join("");
  }
  // 딥링크 (?ticker=) — 알림을 눌러 들어온 경우 해당 종목 바로 열기
  const t = new URLSearchParams(location.search).get("ticker");
  if (t) {
    const s = o.signals.find((x) => x.ticker === t);
    if (s) openSignal(s);
    history.replaceState(null, "", "/?tab=today");
  }
}
function signalCard(s) {
  const tpGap = s.tp && s.price ? s.tp / s.price - 1 : null;
  const slGap = s.sl && s.price ? s.sl / s.price - 1 : null;
  return `<button class="stock" data-signal="${esc(s.ticker)}">
    <div class="stock-top">
      <div class="stock-name"><strong>${esc(s.stock_name)}</strong><span>${esc(code(s.ticker))} · ${MARKET[s.market_type] || esc(s.market_type)}</span></div>
      <div class="score">${Math.round(s.score)}<small>점</small></div>
    </div>
    <div class="metrics">
      <div class="metric"><span>추천가</span><b>${price(s.price, s.market_type)}</b></div>
      <div class="metric"><span>익절</span><b>${price(s.tp, s.market_type)}</b><em class="up">${tpGap != null ? pct(tpGap) : ""}</em></div>
      <div class="metric"><span>손절</span><b>${price(s.sl, s.market_type)}</b><em class="down">${slGap != null ? pct(slGap) : ""}</em></div>
    </div>
    <div class="stock-foot"><span>${relDay(s.created_at)} 추천</span><span>자세히 ›</span></div>
  </button>`;
}
function openSignal(s) {
  const link = isKR(s.market_type)
    ? `https://m.stock.naver.com/domestic/stock/${code(s.ticker)}/total`
    : `https://finance.yahoo.com/quote/${encodeURIComponent(s.ticker)}`;
  const chart = s.chart_url ? `<img class="chart-img" src="${esc(s.chart_url)}" alt="${esc(s.stock_name)} 차트" data-zoom>` : `<div class="empty">차트가 없어요</div>`;
  openSheet(`
    <h3>${esc(s.stock_name)}</h3>
    <p class="sub">${esc(code(s.ticker))} · ${MARKET[s.market_type] || ""} · ${relDay(s.created_at)} 추천 · <b>${Math.round(s.score)}점</b></p>
    ${chart}
    <div class="metrics" style="margin-top:12px">
      <div class="metric"><span>당일 시가</span><b>${price(s.open_price, s.market_type)}</b></div>
      <div class="metric"><span>익절 목표</span><b class="up">${price(s.tp, s.market_type)}</b></div>
      <div class="metric"><span>손절 라인</span><b class="down">${price(s.sl, s.market_type)}</b></div>
    </div>
    <ul class="reasons">${(s.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    <p class="footnote" style="text-align:left;margin-bottom:12px">익절·손절은 당일 시가 기준이에요. 매수 직후 예약 매도를 걸어두세요.</p>
    <div class="sheet-actions">
      <a class="btn btn-ghost" href="${link}" target="_blank" rel="noopener">${isKR(s.market_type) ? "네이버 증권" : "Yahoo Finance"}</a>
      <button class="btn btn-primary" data-close-sheet>닫기</button>
    </div>`);
}

// ---------- 추적 ----------
async function loadTrack() {
  const { market, days } = state.track;
  const data = await api(`/api/positions?days=${days}`);
  let items = data.items;
  if (market === "KR") items = items.filter((i) => isKR(i.market_type));
  if (market === "US") items = items.filter((i) => i.market_type === "NASDAQ");
  const rets = items.map((i) => i.return).filter((v) => v != null);
  const avg = rets.length ? rets.reduce((a, b) => a + b, 0) / rets.length : null;
  const wins = rets.filter((v) => v > 0).length;
  $("#track-summary").innerHTML = `
    <div class="card"><span>평균 수익률</span><b class="${tone(avg)}">${pct(avg)}</b></div>
    <div class="card"><span>상승 종목</span><b>${rets.length ? `${wins}/${rets.length}` : "-"}</b></div>
    <div class="card"><span>갱신</span><b style="font-size:16px">${kst(data.updated)}</b></div>`;
  if (!items.length) {
    $("#track-list").innerHTML = `<div class="empty"><span class="emoji">📭</span><strong>최근 ${days}일 추천 종목이 없어요</strong>기간을 늘려보세요</div>`;
    return;
  }
  const badge = { stop: `<span class="pill pill-down">손절가 이탈</span>`, target: `<span class="pill pill-up">익절가 도달</span>`, hold: "" };
  state.trackItems = items;
  $("#track-list").innerHTML = items.map((i, idx) => `
    <button class="track-row" data-track="${idx}">
      <div class="stock-name"><strong>${esc(i.stock_name)}</strong>
        <span>${relDay(i.created_at)} · ${price(i.price, i.market_type)} → ${price(i.current, i.market_type)}${i.signal_count > 1 ? ` · ${i.signal_count}일 추천` : ""}</span>
        <div style="margin-top:4px">${badge[i.status]}</div></div>
      <div class="track-ret"><b class="${tone(i.return)}">${pct(i.return)}</b><span>${MARKET[i.market_type] || ""}</span></div>
    </button>`).join("");
}
function openTrack(i) {
  const chart = i.chart_url ? `<img class="chart-img" src="${esc(i.chart_url)}" alt="차트" data-zoom>` : "";
  const toTp = i.tp && i.current ? i.tp / i.current - 1 : null;
  const toSl = i.sl && i.current ? i.sl / i.current - 1 : null;
  openSheet(`
    <h3>${esc(i.stock_name)}</h3>
    <p class="sub">${esc(code(i.ticker))} · ${relDay(i.created_at)} 첫 추천 · 현재 <b class="${tone(i.return)}">${pct(i.return)}</b></p>
    ${chart}
    <div class="metrics" style="margin-top:12px">
      <div class="metric"><span>현재가</span><b>${price(i.current, i.market_type)}</b></div>
      <div class="metric"><span>익절까지</span><b class="up">${toTp != null ? pct(toTp) : "-"}</b></div>
      <div class="metric"><span>손절까지</span><b class="down">${toSl != null ? pct(toSl) : "-"}</b></div>
    </div>
    <div class="sheet-actions" style="margin-top:14px"><button class="btn btn-primary" data-close-sheet style="grid-column:1/-1">닫기</button></div>`);
}

// ---------- 공시 ----------
async function loadNews() {
  let rows = await api("/api/disclosures?limit=150");
  if (state.news !== "ALL") rows = rows.filter((r) => r.event_type === state.news);
  if (!rows.length) {
    $("#news-list").innerHTML = `<div class="empty"><span class="emoji">🗞️</span><strong>표시할 공시가 없어요</strong>한국장 분석이 실행되면 쌓여요</div>`;
    return;
  }
  $("#news-list").innerHTML = rows.map((r) => {
    const d = r.rcept_dt; const date = `${d.slice(4, 6)}/${d.slice(6, 8)}`;
    const b = r.event_type === "GOOD" ? `<span class="pill pill-up">호재</span>` : `<span class="pill pill-down">악재</span>`;
    return `<div class="news"><div class="news-head">${b}<span>${esc(r.stock_name)}</span><span>·</span><span>${date}</span></div>
      <div class="news-title">${esc(r.report_title.replace(/^\[(공시|뉴스)\]\s*/, ""))}</div></div>`;
  }).join("");
}

// ---------- 봇 ----------
async function loadBot() {
  const r = await api("/api/runs");
  state.runs = r;
  renderRunning(r.running);
  const nextList = Object.entries(r.next_runs || {}).sort((a, b) => a[1].localeCompare(b[1]));
  if (r.running) {
    $("#bot-status").innerHTML = `<div class="bot-state"><span class="spinner"></span><div><div class="big">${RUN_LABEL[r.running.market]} 분석 중</div>
      <div class="muted small">${r.running.trigger === "manual" ? "수동 실행" : "자동 실행"} · ${elapsed(r.running.elapsed)}</div></div></div>
      <div class="log" id="live-log">로그 불러오는 중…</div>`;
    loadLog(r.running.id, "#live-log", 12);
  } else {
    const next = nextList[0];
    $("#bot-status").innerHTML = `<div class="bot-state"><span class="status-dot status-success"></span><div><div class="big">대기 중</div>
      <div class="muted small">${!r.scheduler ? "서버의 자동 실행이 꺼져 있어요" : next ? `다음 자동 실행 · ${RUN_LABEL[next[0]]} ${relDay(next[1])}` : ""}</div></div></div>`;
  }
  $$("[data-run]").forEach((b) => (b.disabled = !!r.running));
  // 기록
  $("#run-history").innerHTML = r.history.length ? r.history.map((h) => `
    <button class="history-row" data-log="${h.id}">
      <span class="status-dot status-${h.status}"></span>
      <div class="row-body"><strong>${RUN_LABEL[h.market] || h.market} · ${h.trigger === "manual" ? "수동" : "자동"}</strong>
        <span>${relDay(h.started_at)} · ${h.status === "running" ? "실행 중" : h.status === "success" ? `추천 ${h.signals}건` : "실패"}</span></div>
      <span class="muted">›</span>
    </button>`).join("") : `<p class="muted small" style="margin:0">아직 실행 기록이 없어요</p>`;
  renderScheduleSummary(r.schedule, r.next_runs, r.scheduler);
  refreshPushUI();
}
// ---------- 자동 실행 시간표 ----------
const SCHED_META = {
  KR: { flag: "🇰🇷", name: "한국장", tz: "한국 시간", open: "09:00", close: "15:30", hours: "장 09:00–15:30" },
  US: { flag: "🇺🇸", name: "미국장", tz: "뉴욕 시간", open: "09:30", close: "16:00", hours: "장 09:30–16:00 (뉴욕)" },
};
const outOfHours = (m, t) => t < SCHED_META[m].open || t > SCHED_META[m].close;
function renderScheduleSummary(schedule, next, schedulerOn) {
  if (!schedulerOn) {
    $("#schedule").innerHTML = `<p class="muted small" style="margin:0">서버의 자동 실행이 꺼져 있어요 (.env APP_SCHEDULER=0)</p>`;
    return;
  }
  $("#schedule").innerHTML = ["KR", "US"].map((m) => {
    const c = schedule[m], meta = SCHED_META[m];
    const status = !c.enabled ? `<span class="pill pill-off">꺼짐</span>`
      : !c.times.length ? `<span class="pill pill-warn">시간 없음</span>`
      : `<span class="pill pill-ok">하루 ${c.times.length}회</span>`;
    const nextText = c.enabled && next && next[m] ? `다음 ${relDay(next[m])}` : "";
    const times = c.times.map((t) => (m === "US" ? `${t}<small class="muted">(${c.kst[t].replace(" (다음날)", "")})</small>` : t)).join(" · ");
    return `<div class="sched-row${c.enabled ? "" : " is-off"}">
      <div class="row"><div class="row-body"><strong>${meta.flag} ${meta.name}</strong><span class="muted small">${nextText || meta.tz + " 기준"}</span></div>${status}</div>
      ${c.times.length ? `<div class="sched-times">${times}</div>` : ""}
    </div>`;
  }).join("") + `<p class="footnote" style="text-align:left;margin-top:8px">평일만 실행 · 미국장은 뉴욕 시간 기준(괄호는 한국 시간, 서머타임 자동 반영)</p>`;
}
async function openScheduleEditor() {
  try { renderScheduleEditor((await api("/api/schedule")).schedule); } catch (e) { handleError(e); }
}
function renderScheduleEditor(schedule, keepOpen = false) {
  const html = `
    <h3>자동 실행 시간표</h3>
    <p class="sub">평일에만 실행돼요. 바꾸면 바로 저장되고 다음 실행부터 적용돼요.</p>
    ${["KR", "US"].map((m) => {
      const c = schedule[m], meta = SCHED_META[m];
      const chips = c.times.length ? c.times.map((t) => `
        <span class="chip${outOfHours(m, t) ? " chip-warn" : ""}">
          <b>${t}</b>${m === "US" ? `<small>한국 ${esc(c.kst[t])}</small>` : ""}
          <button data-sched-remove="${m}" data-time="${t}" aria-label="${t} 삭제">✕</button>
        </span>`).join("") : `<span class="muted small">설정된 시간이 없어요</span>`;
      return `<section class="sched-sec${c.enabled ? "" : " is-off"}">
        <div class="row"><div class="row-body"><strong>${meta.flag} ${meta.name}</strong><span class="muted small">${meta.tz} · ${meta.hours}</span></div>
          <label class="switch" aria-label="${meta.name} 자동 실행"><input type="checkbox" data-sched-toggle="${m}" ${c.enabled ? "checked" : ""}><span></span></label></div>
        <div class="chips">${chips}</div>
        <div class="add-row">
          <input type="time" id="sched-add-${m}" value="${m === "KR" ? "09:35" : "10:10"}" aria-label="${meta.name} 추가할 시간">
          <button class="btn btn-ghost btn-sm" data-sched-add="${m}">+ 시간 추가</button>
        </div>
      </section>`;
    }).join("")}
    <p class="footnote" style="text-align:left"><span class="legend-warn"></span> 주황색은 장 운영 시간 밖이에요 (장 전에는 전날 데이터로 분석)</p>
    <div class="sheet-actions">
      <button class="btn btn-ghost" data-action="reset-schedule">기본값으로</button>
      <button class="btn btn-primary" data-close-sheet>완료</button>
    </div>`;
  if (keepOpen && !$("#sheet").hidden) { const y = $("#sheet").scrollTop; $("#sheet-content").innerHTML = html; $("#sheet").scrollTop = y; }
  else openSheet(html);
  state.scheduleEditing = true;
}
async function saveSchedule(body, message = "저장했어요") {
  try {
    const r = await api("/api/schedule", { method: "PUT", body: JSON.stringify(body) });
    renderScheduleEditor(r.schedule, true);
    renderScheduleSummary(r.schedule, r.next_runs, r.scheduler);
    toast(message);
  } catch (e) { handleError(e); openScheduleEditor(); }
}
const currentEditorTimes = (m) => $$(`[data-sched-remove="${m}"]`).map((b) => b.dataset.time);

async function loadLog(id, target, lines = 40) {
  try {
    const { lines: l } = await api(`/api/runs/${id}/log?lines=${lines}`);
    const el = $(target); if (!el) return;
    el.textContent = l.length ? l.join("\n") : "로그가 아직 없어요";
    el.scrollTop = el.scrollHeight;
  } catch (e) { handleError(e); }
}
async function runBot(market) {
  const ok = await confirmDialog(`${RUN_LABEL[market]} 분석을 지금 실행할까요?`,
    "몇 분 정도 걸려요. 새 추천 종목이 나오면 슬랙과 이 앱으로 알림이 가요.", "실행");
  if (!ok) return;
  try {
    await api(`/api/runs/${market}`, { method: "POST" });
    toast(`${RUN_LABEL[market]} 분석을 시작했어요`);
    if (navigator.vibrate) navigator.vibrate(10);
    await loadBot();
    startPolling();
  } catch (e) { handleError(e); }
}
function renderRunning(running) {
  $("#bot-dot").hidden = !running;
  $("#running-banner").hidden = !running;
  if (running) $("#running-text").textContent = `${RUN_LABEL[running.market]} 분석 중 · ${elapsed(running.elapsed)}`;
  if (running) startPolling();
  if (state.wasRunning && !running) { toast("분석이 끝났어요"); if (state.tab !== "bot") load(); }
  state.wasRunning = !!running;
}
function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(async () => {
    try {
      const r = await api("/api/runs");
      if (state.tab === "bot") await loadBot(); else renderRunning(r.running);
      if (!r.running) { clearInterval(state.pollTimer); state.pollTimer = null; if (state.tab === "bot") renderRunning(null); }
    } catch (_) {}
  }, 4000);
}

// ---------- 푸시 알림 ----------
const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
async function currentSubscription() {
  if (!pushSupported()) return null;
  // ready는 서비스 워커 등록이 실패하면 영원히 기다리므로 getRegistration 사용
  const reg = await navigator.serviceWorker.getRegistration();
  return reg ? reg.pushManager.getSubscription() : null;
}
function swReady(ms = 8000) {
  return Promise.race([navigator.serviceWorker.ready,
    new Promise((_, rej) => setTimeout(() => rej(new Error("서비스 워커 준비 실패 — 앱을 다시 열어주세요")), ms))]);
}
function b64ToUint8(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}
async function enablePush() {
  if (!pushSupported()) {
    toast(isIOS() && !isStandalone() ? "홈 화면에 추가한 앱에서 알림을 켤 수 있어요" : "이 브라우저는 알림을 지원하지 않아요", 3200);
    return false;
  }
  if (location.protocol !== "https:" && location.hostname !== "localhost") { toast("알림은 https 주소(Tailscale)에서만 켤 수 있어요", 3200); return false; }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") { toast("알림 권한이 거부됐어요. 설정 > 알림에서 허용해주세요", 3500); return false; }
  try {
    const { key } = await api("/api/push/public-key");
    const reg = await swReady();
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(key) });
    await api("/api/push/subscribe", { method: "POST", body: JSON.stringify(sub.toJSON()) });
    toast("알림을 켰어요 🔔");
    return true;
  } catch (e) { toast(`알림 설정 실패: ${e.message}`, 3500); return false; }
}
async function disablePush() {
  const sub = await currentSubscription();
  if (sub) {
    await api("/api/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => {});
    await sub.unsubscribe();
  }
  toast("알림을 껐어요");
}
async function refreshPushUI() {
  const toggle = $("#push-toggle"), status = $("#push-status"), test = $("#push-test");
  let on = false, msg = "";
  if (!pushSupported()) msg = isIOS() && !isStandalone() ? "홈 화면에 추가한 뒤 켤 수 있어요" : "이 브라우저는 지원하지 않아요";
  else if (Notification.permission === "denied") msg = "iPhone 설정 > 알림에서 허용이 필요해요";
  else { on = !!(await currentSubscription()); msg = on ? "새 추천이 나오면 알려드려요" : "꺼져 있어요"; }
  toggle.checked = on; toggle.disabled = !pushSupported() || Notification.permission === "denied";
  status.textContent = msg; test.disabled = !on;
  $("#push-banner").hidden = !(pushSupported() && isStandalone() && !on && Notification.permission !== "denied" && !dismissed("push"));
}
const dismissed = (k) => { try { return localStorage.getItem(`dismiss-${k}`) === "1"; } catch (_) { return false; } };
const dismiss = (k) => { try { localStorage.setItem(`dismiss-${k}`, "1"); } catch (_) {} };

// ---------- 로그인 ----------
function showLogin() { $("#app").hidden = true; $("#login").hidden = false; $("#login-token").focus(); }
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ token: $("#login-token").value }) });
    $("#login").hidden = true; start();
  } catch (err) { $("#login-error").textContent = err.message; $("#login-error").hidden = false; }
});

// ---------- 이벤트 ----------
document.addEventListener("click", async (e) => {
  const t = e.target.closest("button, [data-zoom], a");
  if (!t) return;
  if (t.dataset.tab) return switchTab(t.dataset.tab);
  if (t.dataset.goto) return switchTab(t.dataset.goto);
  if (t.dataset.signal) { const s = state.overview?.signals.find((x) => x.ticker === t.dataset.signal); if (s) openSignal(s); return; }
  if (t.dataset.track) return openTrack(state.trackItems[+t.dataset.track]);
  if (t.dataset.run) return runBot(t.dataset.run);
  if (t.dataset.log) {
    openSheet(`<h3>실행 로그</h3><p class="sub">#${t.dataset.log}</p><div class="log" id="sheet-log" style="max-height:60vh">불러오는 중…</div>
      <div class="sheet-actions" style="margin-top:14px"><button class="btn btn-primary" data-close-sheet style="grid-column:1/-1">닫기</button></div>`);
    return loadLog(t.dataset.log, "#sheet-log", 200);
  }
  if (t.dataset.zoom !== undefined) { const v = $("#viewer"); $("img", v).src = t.src; v.hidden = false; return; }
  if (t.dataset.closeSheet !== undefined) return closeSheet();
  if (t.dataset.dismiss) { dismiss(t.dataset.dismiss); t.closest(".banner").hidden = true; return; }
  if (t.dataset.action === "enable-push") { if (await enablePush()) refreshPushUI(); return; }
  if (t.dataset.action === "edit-schedule") return openScheduleEditor();
  if (t.dataset.schedRemove) {
    const m = t.dataset.schedRemove;
    return saveSchedule({ [m]: { times: currentEditorTimes(m).filter((x) => x !== t.dataset.time) } }, `${t.dataset.time} 삭제했어요`);
  }
  if (t.dataset.schedAdd) {
    const m = t.dataset.schedAdd, v = $(`#sched-add-${m}`).value;
    if (!v) return toast("추가할 시간을 골라주세요");
    if (currentEditorTimes(m).includes(v)) return toast("이미 있는 시간이에요");
    return saveSchedule({ [m]: { times: [...currentEditorTimes(m), v] } }, `${v} 추가했어요`);
  }
  if (t.dataset.action === "reset-schedule") {
    if (!(await confirmDialog("기본 시간표로 되돌릴까요?", "직접 바꾼 시간과 켜기/끄기 설정이 처음 상태로 돌아가요.", "되돌리기"))) return;
    try {
      const r = await api("/api/schedule", { method: "DELETE" });
      renderScheduleEditor(r.schedule, true); renderScheduleSummary(r.schedule, r.next_runs, r.scheduler); toast("기본값으로 되돌렸어요");
    } catch (e) { handleError(e); }
    return;
  }
});
$("#sheet-backdrop").addEventListener("click", closeSheet);
document.addEventListener("change", (e) => {
  const m = e.target.dataset && e.target.dataset.schedToggle;
  if (m) saveSchedule({ [m]: { enabled: e.target.checked } }, `${SCHED_META[m].name} 자동 실행을 ${e.target.checked ? "켰어요" : "껐어요"}`);
});
$("#viewer").addEventListener("click", () => ($("#viewer").hidden = true));
$("#refresh-btn").addEventListener("click", () => load());
$("#push-toggle").addEventListener("change", async (e) => {
  e.target.disabled = true;
  if (e.target.checked) { if (!(await enablePush())) e.target.checked = false; } else await disablePush();
  await refreshPushUI();
});
$("#push-test").addEventListener("click", async () => {
  try { const { sent } = await api("/api/push/test", { method: "POST" }); toast(sent ? "테스트 알림을 보냈어요" : "구독된 기기가 없어요"); } catch (e) { handleError(e); }
});
function bindSegmented(id, onChange) {
  $(id).addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    $$("button", $(id)).forEach((x) => x.classList.toggle("active", x === b));
    onChange(b.dataset.value);
  });
}
bindSegmented("#track-market", (v) => { state.track.market = v; loadTrack().catch(handleError); });
bindSegmented("#track-days", (v) => { state.track.days = +v; loadTrack().catch(handleError); });
bindSegmented("#news-filter", (v) => { state.news = v; loadNews().catch(handleError); });
// 앱으로 돌아오면 자동 새로고침
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(); });
// 시트 아래로 끌어 닫기
(() => {
  let y0 = null; const sheet = $("#sheet");
  sheet.addEventListener("touchstart", (e) => { if (sheet.scrollTop <= 0) y0 = e.touches[0].clientY; }, { passive: true });
  sheet.addEventListener("touchmove", (e) => { if (y0 != null && e.touches[0].clientY - y0 > 0) sheet.style.transform = `translateY(${e.touches[0].clientY - y0}px)`; }, { passive: true });
  sheet.addEventListener("touchend", (e) => {
    if (y0 != null && e.changedTouches[0].clientY - y0 > 110) closeSheet();
    sheet.style.transform = ""; y0 = null;
  });
})();

// ---------- 시작 ----------
async function start() {
  $("#app").hidden = false;
  $("#install-banner").hidden = !(isIOS() && !isStandalone() && !dismissed("install"));
  const tab = new URLSearchParams(location.search).get("tab");
  switchTab(TITLES[tab] ? tab : "today", false);
  refreshPushUI().catch(() => {});
}
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
(async () => {
  try {
    const a = await fetch("/api/auth", { credentials: "same-origin" }).then((r) => r.json());
    if (a.required && !a.ok) showLogin(); else start();
  } catch (_) { start(); $("#offline").hidden = false; }
})();
