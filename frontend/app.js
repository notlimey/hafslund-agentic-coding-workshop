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
  renderPriceChart(prices, win, blocked);
}

function renderPriceChart(prices, win, blocked) {
  const svg = document.getElementById('price-chart');
  const SVG_NS = 'http://www.w3.org/2000/svg';
  svg.innerHTML = '';
  if (!prices.length) {
    svg.removeAttribute('viewBox');
    svg.style.height = '';
    return;
  }

  // Vertical bars on a time x-axis. Numbers are SVG user units; the outer
  // `class="w-full"` scales horizontally and `preserveAspectRatio="none"`
  // lets bars stretch to fill — y-axis labels stay readable via a separate
  // text style outside the scaling region (here we just pick a viewBox that
  // works at typical widths).
  const padL = 40;   // y-axis labels
  const padR = 10;
  const padT = 10;
  const padB = 22;   // x-axis labels
  const width = 720;
  const height = 220;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const barGap = 2;
  const barW = plotW / prices.length - barGap;

  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.style.height = `${height}px`;

  const maxPrice = Math.max(...prices.map((p) => p.NOK_per_kWh), 0.001);
  // Round the y-axis ceiling to a friendly number above max.
  const yMax = niceCeil(maxPrice);
  const winStart = win ? new Date(win.start).getTime() : null;
  const winEnd = win ? new Date(win.end).getTime() : null;

  // y-axis gridlines + labels (0, mid, top).
  for (const frac of [0, 0.5, 1]) {
    const y = padT + plotH * (1 - frac);
    const line = document.createElementNS(SVG_NS, 'line');
    line.setAttribute('x1', padL);
    line.setAttribute('x2', width - padR);
    line.setAttribute('y1', y);
    line.setAttribute('y2', y);
    line.setAttribute('stroke', '#e2e8f0');
    line.setAttribute('stroke-width', '1');
    svg.appendChild(line);

    const label = document.createElementNS(SVG_NS, 'text');
    label.setAttribute('x', padL - 6);
    label.setAttribute('y', y + 4);
    label.setAttribute('font-size', '11');
    label.setAttribute('font-family', 'ui-monospace, monospace');
    label.setAttribute('fill', '#64748b');
    label.setAttribute('text-anchor', 'end');
    label.textContent = (yMax * frac).toFixed(2);
    svg.appendChild(label);
  }

  prices.forEach((p, i) => {
    const startDate = new Date(p.time_start);
    const startMs = startDate.getTime();
    const inWindow = winStart !== null && startMs >= winStart && startMs < winEnd;
    const isBlocked = blocked.has(startDate.getHours());

    const barH = (p.NOK_per_kWh / yMax) * plotH;
    const x = padL + i * (barW + barGap);
    const y = padT + plotH - barH;

    let fill = '#94a3b8'; // slate-400
    if (inWindow) fill = '#10b981'; // emerald-500
    if (isBlocked) fill = '#e2e8f0'; // slate-200

    const rect = document.createElementNS(SVG_NS, 'rect');
    rect.setAttribute('x', x);
    rect.setAttribute('y', y);
    rect.setAttribute('width', Math.max(barW, 1));
    rect.setAttribute('height', Math.max(barH, 1));
    rect.setAttribute('fill', fill);
    rect.setAttribute('rx', '1');
    const title = document.createElementNS(SVG_NS, 'title');
    title.textContent = `${fmtTime(p.time_start)} — ${p.NOK_per_kWh.toFixed(3)} NOK/kWh`;
    rect.appendChild(title);
    svg.appendChild(rect);

    // x-axis tick label every 3 hours to avoid clutter.
    if (startDate.getHours() % 3 === 0) {
      const tick = document.createElementNS(SVG_NS, 'text');
      tick.setAttribute('x', x + barW / 2);
      tick.setAttribute('y', height - 6);
      tick.setAttribute('font-size', '11');
      tick.setAttribute('font-family', 'ui-monospace, monospace');
      tick.setAttribute('fill', '#64748b');
      tick.setAttribute('text-anchor', 'middle');
      tick.textContent = String(startDate.getHours()).padStart(2, '0');
      svg.appendChild(tick);
    }
  });
}

async function loadPriceHistory() {
  let resp;
  try {
    resp = await fetch('/api/prices/history');
  } catch (e) {
    showHistoryError('Could not load price history — backend unreachable.');
    return;
  }
  if (!resp.ok) {
    showHistoryError(`Could not load price history (HTTP ${resp.status}).`);
    return;
  }
  const body = await resp.json();
  if (body.missing_days && body.missing_days.length > 0) {
    const warn = document.getElementById('history-warning');
    warn.textContent = `Some days excluded from averages: ${body.missing_days.join(', ')}.`;
    warn.hidden = false;
  }
  renderHistoryLegend();
  renderHistorySummary(body.weekday, body.weekend);
  renderHistoryChart(body.weekday, body.weekend);
}

function renderHistorySummary(weekday, weekend) {
  const el = document.getElementById('history-summary');
  const wdAvg = weightedMean(weekday);
  const weAvg = weightedMean(weekend);
  if (wdAvg === null || weAvg === null) {
    el.hidden = true;
    return;
  }
  const diff = weAvg - wdAvg;
  const cheaper = diff < 0 ? 'weekends' : 'weekdays';
  const magnitude = Math.abs(diff);
  el.textContent =
    `Average: weekday ${wdAvg.toFixed(3)} NOK/kWh, weekend ${weAvg.toFixed(3)} NOK/kWh — ` +
    `${cheaper} are ${magnitude.toFixed(3)} NOK/kWh cheaper on average.`;
  el.hidden = false;
}

function weightedMean(buckets) {
  let totalPrice = 0;
  let totalCount = 0;
  for (const b of buckets) {
    totalPrice += b.avg_NOK_per_kWh * b.count;
    totalCount += b.count;
  }
  return totalCount > 0 ? totalPrice / totalCount : null;
}

function showHistoryError(msg) {
  const el = document.getElementById('history-error');
  el.textContent = msg;
  el.hidden = false;
  const svg = document.getElementById('history-chart');
  svg.innerHTML = '';
  svg.removeAttribute('viewBox');
  svg.style.height = '';
  document.getElementById('history-legend').hidden = true;
  document.getElementById('history-summary').hidden = true;
}

function renderHistoryLegend() {
  const legend = document.getElementById('history-legend');
  legend.innerHTML = '';
  legend.hidden = false;
  for (const [label, color] of [['Weekday (Mon–Fri)', '#64748b'], ['Weekend (Sat–Sun)', '#10b981']]) {
    const item = document.createElement('span');
    item.className = 'inline-flex items-center gap-1';
    const swatch = document.createElement('span');
    swatch.style.cssText = `display:inline-block;width:10px;height:10px;background:${color};border-radius:2px;`;
    item.appendChild(swatch);
    item.appendChild(document.createTextNode(label));
    legend.appendChild(item);
  }
}

function renderHistoryChart(weekday, weekend) {
  const svg = document.getElementById('history-chart');
  const SVG_NS = 'http://www.w3.org/2000/svg';
  svg.innerHTML = '';

  const padL = 40;
  const padR = 10;
  const padT = 10;
  const padB = 22;
  const width = 720;
  const height = 220;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const groupGap = 4;
  const groupW = plotW / 24;
  const barW = (groupW - groupGap) / 2;

  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.style.height = `${height}px`;

  const maxPrice = Math.max(
    ...weekday.map((b) => b.avg_NOK_per_kWh),
    ...weekend.map((b) => b.avg_NOK_per_kWh),
    0.001,
  );
  const yMax = niceCeil(maxPrice);

  for (const frac of [0, 0.5, 1]) {
    const y = padT + plotH * (1 - frac);
    const line = document.createElementNS(SVG_NS, 'line');
    line.setAttribute('x1', padL);
    line.setAttribute('x2', width - padR);
    line.setAttribute('y1', y);
    line.setAttribute('y2', y);
    line.setAttribute('stroke', '#e2e8f0');
    line.setAttribute('stroke-width', '1');
    svg.appendChild(line);

    const label = document.createElementNS(SVG_NS, 'text');
    label.setAttribute('x', padL - 6);
    label.setAttribute('y', y + 4);
    label.setAttribute('font-size', '11');
    label.setAttribute('font-family', 'ui-monospace, monospace');
    label.setAttribute('fill', '#64748b');
    label.setAttribute('text-anchor', 'end');
    label.textContent = (yMax * frac).toFixed(2);
    svg.appendChild(label);
  }

  for (let h = 0; h < 24; h++) {
    const groupX = padL + h * groupW;
    drawBar(svg, SVG_NS, groupX, weekday[h], '#64748b', barW, padT, plotH, yMax, 'Weekday');
    drawBar(svg, SVG_NS, groupX + barW, weekend[h], '#10b981', barW, padT, plotH, yMax, 'Weekend');

    if (h % 3 === 0) {
      const tick = document.createElementNS(SVG_NS, 'text');
      tick.setAttribute('x', groupX + (groupW - groupGap) / 2);
      tick.setAttribute('y', height - 6);
      tick.setAttribute('font-size', '11');
      tick.setAttribute('font-family', 'ui-monospace, monospace');
      tick.setAttribute('fill', '#64748b');
      tick.setAttribute('text-anchor', 'middle');
      tick.textContent = String(h).padStart(2, '0');
      svg.appendChild(tick);
    }
  }
}

function drawBar(svg, SVG_NS, x, bucket, color, barW, padT, plotH, yMax, seriesLabel) {
  const barH = (bucket.avg_NOK_per_kWh / yMax) * plotH;
  const y = padT + plotH - barH;
  const rect = document.createElementNS(SVG_NS, 'rect');
  rect.setAttribute('x', x);
  rect.setAttribute('y', y);
  rect.setAttribute('width', Math.max(barW, 1));
  rect.setAttribute('height', Math.max(barH, 1));
  rect.setAttribute('fill', color);
  rect.setAttribute('rx', '1');
  const title = document.createElementNS(SVG_NS, 'title');
  title.textContent =
    `${seriesLabel} ${String(bucket.hour).padStart(2, '0')}:00 — ` +
    `${bucket.avg_NOK_per_kWh.toFixed(3)} NOK/kWh (${bucket.count} days)`;
  rect.appendChild(title);
  svg.appendChild(rect);
}

function niceCeil(v) {
  // Round to the next 0.5 step so the y-axis ceiling reads cleanly.
  return Math.ceil(v * 2) / 2;
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
  loadPriceHistory();
});
