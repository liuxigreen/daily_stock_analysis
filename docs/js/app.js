/**
 * 每日选股 - Mobile App
 */

const BASE_PATH = location.hostname === 'localhost' || location.hostname === '127.0.0.1'
  ? '.' : '/daily_stock_analysis';

let state = {
  picks: null,
  analysis: null,
  history: null,
  currentTab: 'today',
  historyView: 'daily'
};

// ===== Tab Switching =====
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    switchTab(tab);
  });
});

function switchTab(tab) {
  state.currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === `tab-${tab}`));
}

// ===== Date Utils =====
function todayStr() { return new Date().toISOString().slice(0, 10); }
function formatDate(str) {
  const d = new Date(str);
  const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
  return `${d.getMonth()+1}/${d.getDate()} 周${weekdays[d.getDay()]}`;
}
function getISOWeek(dateStr) {
  const d = new Date(dateStr);
  const yearStart = new Date(d.getFullYear(), 0, 1);
  const weekNo = Math.ceil(((d - yearStart) / 86400000 + yearStart.getDay() + 1) / 7);
  return `${d.getFullYear()}年 第${weekNo}周`;
}
function getMonth(dateStr) {
  const d = new Date(dateStr);
  return `${d.getFullYear()}年${d.getMonth()+1}月`;
}
function fmtPrice(v) { return Number(v).toFixed(2); }
function fmtPct(v) { const n = Number(v); return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`; }

// ===== Fetch Data =====
async function fetchJSON(path) {
  const url = `${BASE_PATH}${path}?t=${Date.now()}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

async function loadData() {
  const el = document.getElementById('loading');
  el.style.display = 'flex';
  try {
    const today = todayStr();
    let picksData, analysisData, historyData;
    try { picksData = await fetchJSON(`/data/picks.json`); } catch { picksData = null; }
    try { analysisData = await fetchJSON(`/data/analysis.json`); } catch { analysisData = null; }
    try { historyData = await fetchJSON(`/data/history.json`); } catch { historyData = null; }

    state.picks = picksData;
    state.analysis = analysisData;
    state.history = historyData;

    if (picksData) {
      document.getElementById('dateDisplay').textContent = formatDate(picksData.date || today);
      document.getElementById('marketContext').textContent = picksData.market_context?.main_line || '暂无';
      if (picksData.market_context?.sentiment) {
        const badge = document.getElementById('marketBadge');
        const s = picksData.market_context.sentiment;
        badge.textContent = s === 'bullish' ? '🔥' : s === 'bearish' ? '⚠️' : s === 'neutral' ? '➡️' : '📊';
      }
    }

    renderToday();
    renderAnalysis();
    renderHistory();
  } catch (err) {
    document.getElementById('loading').style.display = 'none';
    document.querySelector('#tab-today').innerHTML =
      `<div class="error-state"><div class="icon">⚠️</div><p>数据加载失败：${err.message}</p></div>`;
  } finally {
    el.style.display = 'none';
  }
}

// ===== Render: Today =====
function renderToday() {
  const list = document.getElementById('stockList');
  if (!state.picks || !state.picks.picks || state.picks.picks.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="icon">📭</div><p>暂无今日选股数据</p></div>`;
    document.getElementById('todayCount').textContent = '';
    return;
  }
  const picks = state.picks.picks;
  document.getElementById('todayCount').textContent = `${picks.length}只`;
  list.innerHTML = picks.map((s, i) => renderStockCard(s, i)).join('');
}

function renderStockCard(s, idx) {
  const changeClass = s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : 'flat';
  const changeStr = fmtPct(s.change_pct);
  return `
    <div class="stock-card" onclick="openModal(${idx})" style="animation-delay:${idx * 0.05}s">
      <div class="stock-card-header">
        <div>
          <div class="stock-name">${s.name || '--'}</div>
          <span class="stock-code">${s.code || '--'}</span>
        </div>
        <div class="stock-price-change">
          <span class="stock-price">${fmtPrice(s.price)}</span>
          <span class="stock-change ${changeClass}">${changeStr}</span>
        </div>
      </div>
      <div class="stock-card-tags">
        ${s.score ? `<span class="tag tag-score">评分${s.score}</span>` : ''}
        ${s.target ? `<span class="tag tag-target">目标${fmtPrice(s.target)}</span>` : ''}
        ${s.stop_loss ? `<span class="tag tag-stop">止损${fmtPrice(s.stop_loss)}</span>` : ''}
        ${s.highlight ? `<span class="tag tag-highlight">${s.highlight}</span>` : ''}
      </div>
      <div class="stock-card-reason">${s.reason || s.buy_reason || ''}</div>
    </div>
  `;
}

// ===== Modal =====
function openModal(idx) {
  if (!state.picks?.picks?.[idx]) return;
  const s = state.picks.picks[idx];
  const changeClass = s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : 'flat';
  const changeStr = fmtPct(s.change_pct);

  document.getElementById('modalBody').innerHTML = `
    <h3>${s.name || '--'}</h3>
    <div class="sub-code">${s.code || '--'}</div>
    <div class="modal-info-grid">
      <div class="modal-info-item">
        <div class="modal-info-label">现价</div>
        <div class="modal-info-value">${fmtPrice(s.price)}</div>
      </div>
      <div class="modal-info-item">
        <div class="modal-info-label">涨跌幅</div>
        <div class="modal-info-value ${changeClass}">${changeStr}</div>
      </div>
      ${s.score ? `<div class="modal-info-item">
        <div class="modal-info-label">蓄势评分</div>
        <div class="modal-info-value">${s.score}/100</div>
      </div>` : ''}
      ${s.target ? `<div class="modal-info-item">
        <div class="modal-info-label">目标价</div>
        <div class="modal-info-value" style="color:var(--green)">${fmtPrice(s.target)}</div>
      </div>` : ''}
      ${s.stop_loss ? `<div class="modal-info-item">
        <div class="modal-info-label">止损价</div>
        <div class="modal-info-value" style="color:var(--red)">${fmtPrice(s.stop_loss)}</div>
      </div>` : ''}
      ${s.buy_range ? `<div class="modal-info-item">
        <div class="modal-info-label">买入区间</div>
        <div class="modal-info-value">${s.buy_range}</div>
      </div>` : ''}
      ${s.expected_return ? `<div class="modal-info-item">
        <div class="modal-info-label">预期收益</div>
        <div class="modal-info-value" style="color:var(--green)">${s.expected_return}</div>
      </div>` : ''}
      ${s.market_cap ? `<div class="modal-info-item">
        <div class="modal-info-label">市值</div>
        <div class="modal-info-value">${s.market_cap}</div>
      </div>` : ''}
      ${s.sector ? `<div class="modal-info-item">
        <div class="modal-info-label">板块</div>
        <div class="modal-info-value">${s.sector}</div>
      </div>` : ''}
    </div>
    <div class="modal-reason">${s.reason || s.buy_reason || ''}</div>
    ${s.analysis ? `
      <hr style="border-color:var(--border);margin:16px 0">
      <div style="font-size:0.875rem;color:var(--text-muted)">
        <h4 style="color:var(--text);margin-bottom:8px">📊 AI 分析</h4>
        <p>${s.analysis}</p>
      </div>
    ` : ''}
  `;
  document.getElementById('modal').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modal').classList.add('hidden');
}

document.getElementById('modalClose').addEventListener('click', closeModal);
document.getElementById('modalOverlay').addEventListener('click', closeModal);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ===== Render: Analysis =====
function renderAnalysis() {
  const list = document.getElementById('analysisList');
  if (!state.analysis || !state.analysis.stocks || state.analysis.stocks.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="icon">🤖</div><p>深度分析数据将在收盘后更新</p></div>`;
    return;
  }
  list.innerHTML = state.analysis.stocks.map((s, i) => renderAnalysisCard(s, i)).join('');
}

function renderAnalysisCard(s, i) {
  const score = Number(s.score) || 0;
  const scoreClass = score >= 70 ? 'score-good' : score >= 40 ? 'score-mid' : 'score-bad';
  const signalClass = s.signal === '买入' || s.signal === 'buy' ? 'signal-buy'
    : s.signal === '卖出' || s.signal === 'sell' ? 'signal-sell' : 'signal-hold';
  const detail = [
    s.trend ? `趋势：${s.trend}` : '',
    s.support ? `支撑：${s.support}` : '',
    s.resistance ? `压力：${s.resistance}` : '',
    s.volume_analysis ? `量能：${s.volume_analysis}` : ''
  ].filter(Boolean).join(' | ');
  return `
    <div class="analysis-card" style="animation-delay:${i * 0.05}s">
      <div class="analysis-card-header">
        <div>
          <div style="font-weight:600">${s.name} <span style="font-size:0.75rem;color:var(--text-muted)">${s.code}</span></div>
          <span style="font-size:0.75rem;color:var(--text-muted)">${fmtPrice(s.price)}</span>
        </div>
        <div class="analysis-score ${scoreClass}">${score}</div>
      </div>
      <div class="score-bar"><div class="score-fill" style="width:${score}%"></div></div>
      <div class="analysis-signal ${signalClass}">${s.signal || '--'}</div>
      <div class="analysis-detail">${detail}</div>
    </div>
  `;
}

// ===== Render: History (with daily/weekly/monthly) =====
function switchHistoryView(view) {
  state.historyView = view;
  document.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  renderHistory();
}

function renderHistory() {
  const list = document.getElementById('historyList');
  if (!state.history || !state.history.records || state.history.records.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="icon">📊</div><p>暂无历史记录</p></div>`;
    return;
  }

  switch (state.historyView) {
    case 'weekly': renderWeekly(); break;
    case 'monthly': renderMonthly(); break;
    default: renderDaily(); break;
  }
}

function renderDaily() {
  const list = document.getElementById('historyList');
  list.innerHTML = state.history.records.map((r, i) => `
    <div class="history-item" style="animation-delay:${i * 0.05}s">
      <div class="history-date">${formatDate(r.date)}</div>
      <div class="history-stats">
        <div class="stat-box">
          <div class="stat-value ${r.avg_return >= 0 ? 'green' : 'red'}">${fmtPct(r.avg_return || 0)}</div>
          <div class="stat-label">平均收益</div>
        </div>
        <div class="stat-box">
          <div class="stat-value" style="color:var(--accent)">${r.total_count || 0}</div>
          <div class="stat-label">推荐数量</div>
        </div>
        <div class="stat-box">
          <div class="stat-value ${(r.win_count/r.total_count*100) >= 50 ? 'green' : 'red'}">
            ${Math.round(r.win_count / r.total_count * 100)}%
          </div>
          <div class="stat-label">胜率</div>
        </div>
      </div>
      <div class="history-picks">
        ${(r.picks || []).map(p =>
          `<span class="history-pick"><span class="code">${p.code}</span> <span class="${Number(p.return||0) >= 0 ? 'up' : 'down'}">${fmtPct(p.return||0)}</span></span>`
        ).join('')}
      </div>
      ${r.review ? `<div style="font-size:0.8125rem;color:var(--text-muted);margin-top:8px">${r.review}</div>` : ''}
    </div>
  `).join('');
}

function renderWeekly() {
  const groups = groupHistory('week');
  const list = document.getElementById('historyList');
  list.innerHTML = Object.entries(groups).sort().reverse().map(([week, days]) => {
    const total = days.reduce((s, d) => s + (d.picks?.length || d.total_count || 0), 0);
    const wins = days.reduce((s, d) => s + (d.win_count || 0), 0);
    const totalCount = days.reduce((s, d) => s + d.total_count, 0);
    const avgRet = days.reduce((s, d) => s + (d.avg_return || 0), 0) / days.length;
    const winRate = totalCount > 0 ? Math.round(wins / totalCount * 100) : 0;
    return `
      <div class="history-item" style="border-left:3px solid var(--accent)">
        <div class="history-date" style="font-size:0.9375rem">📅 ${week}</div>
        <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:8px">${days.length}个交易日</div>
        <div class="history-stats">
          <div class="stat-box">
            <div class="stat-value ${avgRet >= 0 ? 'green' : 'red'}">${fmtPct(avgRet)}</div>
            <div class="stat-label">日均收益</div>
          </div>
          <div class="stat-box">
            <div class="stat-value" style="color:var(--accent)">${total}</div>
            <div class="stat-label">推荐总数</div>
          </div>
          <div class="stat-box">
            <div class="stat-value ${winRate >= 50 ? 'green' : 'red'}">${winRate}%</div>
            <div class="stat-label">周胜率</div>
          </div>
        </div>
        <details style="font-size:0.8125rem">
          <summary style="color:var(--accent);cursor:pointer">查看每日明细 (${days.length}天)</summary>
          <div style="margin-top:8px">
            ${days.map(d => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
              <span>${formatDate(d.date)}</span>
              <span class="${d.avg_return >= 0 ? 'up' : 'down'}">${fmtPct(d.avg_return)}</span>
            </div>`).join('')}
          </div>
        </details>
      </div>
    `;
  }).join('');
}

function renderMonthly() {
  const groups = groupHistory('month');
  const list = document.getElementById('historyList');
  list.innerHTML = Object.entries(groups).sort().reverse().map(([month, days]) => {
    const total = days.reduce((s, d) => s + (d.picks?.length || d.total_count || 0), 0);
    const wins = days.reduce((s, d) => s + (d.win_count || 0), 0);
    const totalCount = days.reduce((s, d) => s + d.total_count, 0);
    const avgRet = days.reduce((s, d) => s + (d.avg_return || 0), 0) / days.length;
    const winRate = totalCount > 0 ? Math.round(wins / totalCount * 100) : 0;
    return `
      <div class="history-item" style="border-left:3px solid var(--purple)">
        <div class="history-date" style="font-size:0.9375rem">📆 ${month}</div>
        <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:8px">${days.length}个交易日</div>
        <div class="history-stats">
          <div class="stat-box">
            <div class="stat-value ${avgRet >= 0 ? 'green' : 'red'}">${fmtPct(avgRet)}</div>
            <div class="stat-label">日均收益</div>
          </div>
          <div class="stat-box">
            <div class="stat-value" style="color:var(--accent)">${total}</div>
            <div class="stat-label">推荐总数</div>
          </div>
          <div class="stat-box">
            <div class="stat-value ${winRate >= 50 ? 'green' : 'red'}">${winRate}%</div>
            <div class="stat-label">月胜率</div>
          </div>
        </div>
        <details style="font-size:0.8125rem">
          <summary style="color:var(--accent);cursor:pointer">查看每日明细 (${days.length}天)</summary>
          <div style="margin-top:8px">
            ${days.map(d => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
              <span>${formatDate(d.date)}</span>
              <span class="${d.avg_return >= 0 ? 'up' : 'down'}">${fmtPct(d.avg_return)}</span>
            </div>`).join('')}
          </div>
        </details>
      </div>
    `;
  }).join('');
}

function groupHistory(period) {
  const records = state.history.records;
  const groups = {};
  records.forEach(r => {
    const key = period === 'week' ? getISOWeek(r.date) : getMonth(r.date);
    if (!groups[key]) groups[key] = [];
    groups[key].push(r);
  });
  return groups;
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', loadData);