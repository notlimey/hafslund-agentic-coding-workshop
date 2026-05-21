async function loadHealth() {
  try {
    const r = await fetch('/api/health');
    if (!r.ok) throw new Error('health request failed');
    const data = await r.json();
    document.getElementById('status').textContent = data.status;
  } catch (e) {
    showError('Backend unreachable — could not load /api/health.');
  }
}

async function loadPings() {
  try {
    const r = await fetch('/api/pings');
    if (!r.ok) throw new Error('pings request failed');
    const data = await r.json();
    document.getElementById('ping-count').textContent = `Pings: ${data.length}`;
  } catch (e) {
    showError('Backend unreachable — could not load /api/pings.');
  }
}

async function sendPing() {
  try {
    const r = await fetch('/api/pings', { method: 'POST' });
    if (!r.ok) throw new Error('post request failed');
    await loadPings();
  } catch (e) {
    showError('Backend unreachable — could not POST /api/pings.');
  }
}

let scheduledTimerId = null;
let lastWindow = null;

async function planCharge() {
  const area = document.getElementById('area').value;
  const hours = Number(document.getElementById('hours').value);
  const day = document.getElementById('day').value;
  const awayStart = document.getElementById('away-start').value;
  const awayEnd = document.getElementById('away-end').value;

  const params = new URLSearchParams({ area });
  if (day) params.set('day', day);

  const pricesResp = await fetch(`/api/prices?${params}`);
  if (!pricesResp.ok) {
    showError(`Could not load prices (HTTP ${pricesResp.status}).`);
    return;
  }
  const pricesBody = await pricesResp.json();

  const blocked = blockedHourSet(awayStart, awayEnd);

  if (!pricesBody.published) {
    renderRecommendation(`Prices for ${pricesBody.date} in ${area} are not published yet — try again after 13:00 CET.`);
    renderPriceList([], null, blocked);
    lastWindow = null;
    return;
  }

  const windowParams = new URLSearchParams({ area, hours: String(hours) });
  if (day) windowParams.set('day', day);
  if (awayStart && awayEnd) {
    windowParams.set('away_start', awayStart);
    windowParams.set('away_end', awayEnd);
  }

  const windowResp = await fetch(`/api/prices/cheapest?${windowParams}`);
  if (windowResp.status === 404) {
    renderRecommendation(`No ${hours}h window fits outside the blocked hours — widen your availability or shorten the charge.`);
    renderPriceList(pricesBody.prices, null, blocked);
    lastWindow = null;
    return;
  }
  if (!windowResp.ok) {
    showError(`Could not compute cheapest window (HTTP ${windowResp.status}).`);
    return;
  }
  const win = await windowResp.json();
  lastWindow = win;

  renderRecommendation(
    `Charge ${area} from ${fmtTime(win.start)} to ${fmtTime(win.end)} — ` +
    `avg ${win.avg_NOK_per_kWh.toFixed(3)} NOK/kWh (${win.hours}h).`
  );
  renderPriceList(pricesBody.prices, win, blocked);
}

function blockedHourSet(start, end) {
  if (!start || !end) return new Set();
  const sh = Number(start.slice(0, 2));
  const eh = Number(end.slice(0, 2));
  if (sh === eh) return new Set();
  const hours = new Set();
  if (sh < eh) {
    for (let h = sh; h < eh; h++) hours.add(h);
  } else {
    for (let h = sh; h < 24; h++) hours.add(h);
    for (let h = 0; h < eh; h++) hours.add(h);
  }
  return hours;
}

function renderRecommendation(text) {
  document.getElementById('charge-recommendation').textContent = text;
}

function renderPriceList(prices, win, blocked = new Set()) {
  const list = document.getElementById('price-list');
  list.innerHTML = '';
  const winStart = win ? new Date(win.start).getTime() : null;
  const winEnd = win ? new Date(win.end).getTime() : null;
  for (const p of prices) {
    const li = document.createElement('li');
    const startDate = new Date(p.time_start);
    const startMs = startDate.getTime();
    const inWindow = winStart !== null && startMs >= winStart && startMs < winEnd;
    const isBlocked = blocked.has(startDate.getHours());
    const classes = ['px-2', 'py-1', 'flex', 'justify-between'];
    if (inWindow) classes.push('bg-emerald-100', 'font-semibold');
    if (isBlocked) classes.push('text-slate-400', 'line-through');
    li.className = classes.join(' ');
    const tag = isBlocked ? ' <span class="text-xs not-italic">(away)</span>' : '';
    li.innerHTML =
      `<span>${fmtTime(p.time_start)}${tag}</span>` +
      `<span>${p.NOK_per_kWh.toFixed(3)} NOK/kWh</span>`;
    list.appendChild(li);
  }
}

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

async function enableNotification() {
  const statusEl = document.getElementById('notify-status');
  if (!('Notification' in window)) {
    statusEl.textContent = 'Browser does not support notifications.';
    return;
  }
  if (!lastWindow) {
    statusEl.textContent = 'Plan a charge first, then enable notification.';
    return;
  }

  let permission = Notification.permission;
  if (permission === 'default') permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    statusEl.textContent = `Notification permission ${permission}.`;
    return;
  }

  const delayMs = new Date(lastWindow.start).getTime() - Date.now();
  if (delayMs <= 0) {
    statusEl.textContent = 'Charge window has already started.';
    return;
  }
  // Cap at 24h so a stale `setTimeout` can't sit around forever.
  if (delayMs > 24 * 60 * 60 * 1000) {
    statusEl.textContent = 'Window is more than 24h away — refusing to schedule.';
    return;
  }

  if (scheduledTimerId !== null) clearTimeout(scheduledTimerId);
  const win = lastWindow;
  scheduledTimerId = setTimeout(() => {
    new Notification('EV charge window starting', {
      body: `${win.area}: charge until ${fmtTime(win.end)} (avg ${win.avg_NOK_per_kWh.toFixed(3)} NOK/kWh).`,
    });
    scheduledTimerId = null;
  }, delayMs);

  const minutes = Math.round(delayMs / 60000);
  statusEl.textContent = `Notification scheduled in ${minutes} min (at ${fmtTime(win.start)}).`;
}

function showError(msg) {
  const el = document.getElementById('error');
  el.textContent = msg;
  el.hidden = false;
}

function todayIsoLocal() {
  const now = new Date();
  const tzOffsetMs = now.getTimezoneOffset() * 60 * 1000;
  return new Date(now.getTime() - tzOffsetMs).toISOString().slice(0, 10);
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('day').value = todayIsoLocal();
  document.getElementById('send-ping').addEventListener('click', sendPing);
  document.getElementById('plan-charge').addEventListener('click', planCharge);
  document.getElementById('enable-notify').addEventListener('click', enableNotification);
  loadHealth();
  loadPings();
});
