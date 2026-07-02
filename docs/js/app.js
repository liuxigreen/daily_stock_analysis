/**
 * 每日选股 - Mobile App
 */

const BASE_PATH = location.hostname === 'localhost' || location.hostname === '127.0.0.1'
  ? '.' : '/daily_stock_analysis';

let state = {
  picks: null,
  analysis: null,
  aiAnalysis: null,
  history: null,
  currentTab: 'today',
  historyView: 'daily',
  todaySort: 'default',
  catalysts: null,
  watchpool: null
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
    let catalystsData, watchpoolData, aiAnalysisData;
    try { catalystsData = await fetchJSON(`/data/catalyst_calendar.json`); } catch { catalystsData = null; }
    try { watchpoolData = await fetchJSON(`/data/watch_pool_report.json`); } catch { watchpoolData = null; }
    try { aiAnalysisData = await fetchJSON(`/data/ai_analysis.json`); } catch { aiAnalysisData = null; }

    state.picks = picksData;
    state.analysis = analysisData;
    state.aiAnalysis = aiAnalysisData;
    state.history = historyData;
    state.catalysts = catalystsData;
    state.watchpool = watchpoolData;

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
    renderCatalysts();
    renderWatchpool();
  } catch (err) {
    document.getElementById('loading').style.display = 'none';
    document.querySelector('#tab-today').innerHTML =
      `<div class="error-state"><div class="icon">⚠️</div><p>数据加载失败：${err.message}</p></div>`;
  } finally {
    el.style.display = 'none';
  }
}

// ===== 龙虎榜排序 =====
function switchTodaySort(sort) {
  state.todaySort = sort;
  document.querySelectorAll('#todaySortTabs .sub-tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.sort === sort));
  renderToday();
}

function renderToday() {
  const list = document.getElementById('stockList');
  if (!state.picks || !state.picks.picks || state.picks.picks.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="icon">📭</div><p>暂无今日选股数据</p></div>`;
    document.getElementById('todayCount').textContent = '';
    return;
  }

  let picks = [...state.picks.picks];
  if (state.todaySort === 'gainers') {
    picks.sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
  } else if (state.todaySort === 'losers') {
    picks.sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0));
  }

  document.getElementById('todayCount').textContent = `${picks.length}只`;
  list.innerHTML = picks.map((s, i) => renderStockCard(s, i)).join('');
}

function renderStockCard(s, idx) {
  const changeClass = s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : 'flat';
  const changeStr = fmtPct(s.change_pct);
  const rankNum = idx + 1;
  const rankClass = rankNum <= 3 ? `rank-${rankNum}` : 'rank-other';
  const showRank = state.todaySort !== 'default';
  return `
    <div class="stock-card" onclick="openModal(${idx})" style="animation-delay:${idx * 0.05}s">
      <div class="stock-card-header">
        <div style="display:flex;align-items:center">
          ${showRank ? `<span class="rank-badge ${rankClass}">${rankNum}</span>` : ''}
          <div>
            <div class="stock-name">${s.name || '--'}</div>
            <span class="stock-code">${s.code || '--'}</span>
          </div>
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
  // Sort-aware lookup
  let picks = [...state.picks.picks];
  if (state.todaySort === 'gainers') picks.sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
  else if (state.todaySort === 'losers') picks.sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0));
  const s = picks[idx];
  if (!s) return;
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
  const hasAiData = state.aiAnalysis && state.aiAnalysis.picks && state.aiAnalysis.picks.length > 0;
  const hasAnalysisData = state.analysis && state.analysis.stocks && state.analysis.stocks.length > 0;
  if (!hasAiData && !hasAnalysisData) {
    list.innerHTML = `<div class="empty-state"><div class="icon">🤖</div><p>深度分析数据将在收盘后更新</p></div>`;
    return;
  }
  let html = '';
  // Show main theme banner if available
  if (state.aiAnalysis && state.aiAnalysis.main_theme) {
    html += `<div class="analysis-theme-banner"><span class="analysis-theme-icon">🎯</span><div><div class="analysis-theme-label">今日主线</div><div class="analysis-theme-text">${state.aiAnalysis.main_theme}</div></div></div>`;
  }
  // Show AI picks if available
  if (hasAiData) {
    html += `<div class="analysis-section-header"><h3>🤖 AI 精选</h3><span class="analysis-section-count">${state.aiAnalysis.picks.length}只</span></div>`;
    html += state.aiAnalysis.picks.map((p, i) => renderAiPickCard(p, i)).join('');
  }
  // Show strategy analysis scores if available
  if (hasAnalysisData) {
    html += `<div class="analysis-section-header" style="margin-top:16px"><h3>📊 策略评分</h3><span class="analysis-section-count">${state.analysis.stocks.length}只</span></div>`;
    html += state.analysis.stocks.map((s, i) => renderAnalysisCard(s, i + (hasAiData ? state.aiAnalysis.picks.length : 0))).join('');
  }
  list.innerHTML = html;
}

function renderAiPickCard(p, i) {
  const score = Number(p.score) || 0;
  const scoreClass = score >= 70 ? 'score-good' : score >= 40 ? 'score-mid' : 'score-bad';
  const changePct = p.change_pct != null ? Number(p.change_pct) : null;
  const changeClass = changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'flat';
  const changeStr = changePct != null ? fmtPct(changePct) : '';
  return `
    <div class="analysis-card ai-pick-card" style="animation-delay:${i * 0.05}s">
      <div class="analysis-card-header">
        <div>
          <div style="font-weight:600">${p.name || '--'} <span style="font-size:0.75rem;color:var(--text-muted)">${p.code || '--'}</span></div>
          <div style="display:flex;align-items:center;gap:6px;margin-top:2px">
            <span style="font-size:0.875rem;font-weight:600">${fmtPrice(p.price)}</span>
            ${changeStr ? `<span class="stock-change ${changeClass}" style="font-size:0.75rem">${changeStr}</span>` : ''}
            ${p.sector ? `<span class="tag tag-sector">${p.sector}</span>` : ''}
          </div>
        </div>
        <div class="analysis-score ${scoreClass}">${score}</div>
      </div>
      <div class="score-bar"><div class="score-fill" style="width:${score}%"></div></div>
      <div class="ai-pick-grid">
        ${p.buy_range ? `<div class="ai-pick-item"><div class="ai-pick-label">买入区间</div><div class="ai-pick-value" style="color:var(--accent)">${p.buy_range}</div></div>` : ''}
        ${p.stop_loss ? `<div class="ai-pick-item"><div class="ai-pick-label">止损价</div><div class="ai-pick-value" style="color:var(--red)">${fmtPrice(p.stop_loss)}</div></div>` : ''}
        ${p.target ? `<div class="ai-pick-item"><div class="ai-pick-label">目标价</div><div class="ai-pick-value" style="color:var(--green)">${fmtPrice(p.target)}</div></div>` : ''}
        ${p.expected_return ? `<div class="ai-pick-item"><div class="ai-pick-label">预期收益</div><div class="ai-pick-value" style="color:var(--green)">${p.expected_return}</div></div>` : ''}
        ${p.market_cap ? `<div class="ai-pick-item"><div class="ai-pick-label">市值</div><div class="ai-pick-value">${p.market_cap}</div></div>` : ''}
      </div>
      ${p.highlight ? `<div class="ai-pick-highlight">⭐ ${p.highlight}</div>` : ''}
      ${p.reason ? `<div class="analysis-detail" style="margin-top:6px">${p.reason}</div>` : ''}
    </div>
  `;
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

// ===== Render: History (daily/weekly/monthly/review) =====
function switchHistoryView(view) {
  state.historyView = view;
  document.querySelectorAll('.sub-tab-btn:not(#todaySortTabs .sub-tab-btn)').forEach(b =>
    b.classList.toggle('active', b.dataset.view === view));
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
    case 'review': renderReview(); break;
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
          <summary style="color:var(--accent);cursor:pointer">每日明细 (${days.length}天)</summary>
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
          <summary style="color:var(--accent);cursor:pointer">每日明细 (${days.length}天)</summary>
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

// ===== 复盘 =====
function renderReview() {
  const records = state.history.records;
  const allPicks = records.flatMap(r =>
    (r.picks || []).map(p => ({ ...p, date: r.date, review: r.review }))
  );

  // Collect all failing picks
  const fails = allPicks.filter(p => Number(p.return || 0) < 0).sort((a, b) => a.return - b.return);
  const winners = allPicks.filter(p => Number(p.return || 0) > 5).sort((a, b) => b.return - a.return);

  const totalPicks = allPicks.length;
  const winCount = allPicks.filter(p => Number(p.return || 0) >= 0).length;
  const failCount = totalPicks - winCount;
  const avgRet = allPicks.reduce((s, p) => s + Number(p.return || 0), 0) / totalPicks;
  const bestPick = allPicks.reduce((a, b) => Number(a.return||0) > Number(b.return||0) ? a : b, {name:'--', return:0});
  const worstPick = allPicks.reduce((a, b) => Number(a.return||0) < Number(b.return||0) ? a : b, {name:'--', return:0});

  const list = document.getElementById('historyList');
  let html = '';

  // Overall stats
  html += `
    <div class="review-summary">
      <div class="review-summary-header">
        <span class="review-summary-title">📊 总体复盘</span>
        <span style="font-size:0.75rem;color:var(--text-muted)">${records.length}个交易日</span>
      </div>
      <div class="review-summary-stats">
        <div class="review-stat">
          <div class="review-stat-val" style="color:${avgRet >= 0 ? 'var(--green)' : 'var(--red)'}">${fmtPct(avgRet)}</div>
          <div class="review-stat-label">平均收益</div>
        </div>
        <div class="review-stat">
          <div class="review-stat-val" style="color:var(--accent)">${Math.round(winCount/totalPicks*100)}%</div>
          <div class="review-stat-label">胜率</div>
        </div>
        <div class="review-stat">
          <div class="review-stat-val">${totalPicks}</div>
          <div class="review-stat-label">总推荐</div>
        </div>
      </div>
      <div style="font-size:0.8125rem;color:var(--text-muted)">
        🏆 最佳：${bestPick.name} ${fmtPct(bestPick.return)} · 
        💀 最差：${worstPick.name} ${fmtPct(worstPick.return)}
      </div>
    </div>
  `;

  // Recommended action breakdown
  const actionCounts = {};
  records.forEach(r => {
    const action = r.recommended_action || r.strategy || '无';
    if (!actionCounts[action]) actionCounts[action] = { count: 0, wins: 0, total: 0 };
    (r.picks || []).forEach(p => {
      actionCounts[action].count++;
      actionCounts[action].total++;
      if (Number(p.return || 0) >= 0) actionCounts[action].wins++;
    });
  });

  // Failures section
  if (fails.length > 0) {
    html += `<h3 style="font-size:0.9375rem;margin:16px 0 10px">💀 失败案例 (${fails.length})</h3>`;
    html += fails.map(p => `
      <div class="review-fail">
        <div class="review-fail-header">
          <div>
            <span class="review-fail-name">${p.name}</span>
            <span class="review-fail-date"> · ${formatDate(p.date)}</span>
          </div>
          <span class="review-fail-return">${fmtPct(p.return)}</span>
        </div>
        <div class="review-fail-reason">${p.review || '暂无复盘'}</div>
      </div>
    `).join('');
  }

  // Top winners section
  if (winners.length > 0) {
    html += `<h3 style="font-size:0.9375rem;margin:16px 0 10px">🏆 暴赚案例 ( >+5%，${winners.length})</h3>`;
    html += winners.slice(0, 10).map(p => `
      <div class="review-win">
        <div class="review-win-header">
          <div>
            <span class="review-win-name">${p.name}</span>
            <span class="review-fail-date"> · ${formatDate(p.date)}</span>
          </div>
          <span class="review-win-return">${fmtPct(p.return)}</span>
        </div>
        <div class="review-fail-reason">${p.review || '暂无复盘'}</div>
      </div>
    `).join('');
  }

  list.innerHTML = html;
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

// ===== Render: Catalysts =====
function renderCatalysts() {
  const list = document.getElementById('catalystList');
  const countEl = document.getElementById('catalystCount');
  const data = state.catalysts;
  if (!data || !data.upcoming || data.upcoming.length === 0) {
    list.innerHTML = '<div class="empty-state"><div class="icon">⚡</div><p>暂无催化剂事件</p></div>';
    countEl.textContent = '';
    return;
  }
  const items = data.upcoming;
  countEl.textContent = items.length + '条';
  list.innerHTML = items.map(function(c, i) { return renderCatalystCard(c, i); }).join('');
}

function renderCatalystCard(c, i) {
  var urgency = c.importance || 'low';
  var status = c.status || 'pending';
  var statusLabels = { pending: '待确认', confirmed: '已确认', delayed: '已延迟', failed: '已失效' };
  return '<div class="catalyst-card" style="animation-delay:' + (i * 0.05) + 's">' +
    '<div class="catalyst-card-header">' +
      '<div class="catalyst-title">' + (c.event || '--') + '</div>' +
      '<span class="catalyst-urgency urgency-' + urgency + '">' + (urgency === 'high' ? '高' : urgency === 'medium' ? '中' : '低') + '</span>' +
    '</div>' +
    '<div class="catalyst-chain">' +
      (c.stock_name || '') + ' <span class="stock-code">' + (c.stock_code || '') + '</span>' +
      (c.date ? '<span style="margin-left:6px">📅 ' + c.date + '</span>' : '') +
      '<span style="margin-left:6px"><span class="catalyst-dot dot-' + status + '"></span> ' + (statusLabels[status] || status) + '</span>' +
    '</div>' +
  '</div>';
}

// ===== Render: Watch Pool =====
function renderWatchpool() {
  var list = document.getElementById('watchpoolList');
  var summaryEl = document.getElementById('watchpoolSummary');
  var countEl = document.getElementById('watchpoolCount');
  var data = state.watchpool;
  if (!data || !data.stocks || data.stocks.length === 0) {
    list.innerHTML = '<div class="empty-state"><div class="icon">👁️</div><p>暂无观察池数据</p></div>';
    summaryEl.innerHTML = '';
    countEl.textContent = '';
    return;
  }
  var s = data.summary || {};
  countEl.textContent = data.stocks.length + '只';
  summaryEl.innerHTML =
    '<div class="watchpool-stat"><div class="watchpool-stat-val" style="color:var(--accent)">' + (s.total || 0) + '</div><div class="watchpool-stat-label">总数</div></div>' +
    '<div class="watchpool-stat"><div class="watchpool-stat-val" style="color:var(--accent)">' + (s.watching || 0) + '</div><div class="watchpool-stat-label">观察中</div></div>' +
    '<div class="watchpool-stat"><div class="watchpool-stat-val" style="color:' + ((s.avg_pnl_pct||0) >= 0 ? 'var(--green)' : 'var(--red)') + '">' + (s.total_pnl || '--') + '</div><div class="watchpool-stat-label">总盈亏</div></div>';
  list.innerHTML = data.stocks.map(function(st, i) { return renderWatchpoolCard(st, i); }).join('');
}

function renderWatchpoolCard(st, i) {
  var statusClass = st.status === 'holding' ? 'status-holding' : st.status === 'exited' ? 'status-exited' : 'status-watching';
  var statusLabel = st.status === 'holding' ? '持仓' : st.status === 'exited' ? '已退出' : '观察中';
  var pnl = Number(st.pnl_pct || 0);
  var pnlClass = pnl > 0 ? 'pnl-positive' : pnl < 0 ? 'pnl-negative' : 'pnl-flat';
  var alerts = st.catalyst_alerts || [];
  var alertsHtml = '';
  if (alerts.length > 0) {
    alertsHtml = '<div class="watchpool-catalysts">' +
      alerts.map(function(a) {
        return '<div class="watchpool-catalyst-item">' +
          '<span class="catalyst-dot dot-' + (a.user_status || a.auto_status || 'pending') + '"></span>' +
          '<span>' + (a.event || '') + '</span>' +
          (a.expected_date ? '<span style="color:var(--text-dim)">' + a.expected_date + '</span>' : '') +
        '</div>';
      }).join('') +
    '</div>';
  }
  return '<div class="watchpool-card" style="animation-delay:' + (i * 0.05) + 's">' +
    '<div class="watchpool-card-header">' +
      '<div>' +
        '<span class="watchpool-name">' + (st.name || '--') + '</span>' +
        '<span class="stock-code">' + (st.code || '') + '</span>' +
        '<span class="watchpool-status ' + statusClass + '">' + statusLabel + '</span>' +
      '</div>' +
      '<div style="text-align:right">' +
        '<div class="watchpool-price">' + fmtPrice(st.current_price) + '</div>' +
        '<div class="watchpool-pnl ' + pnlClass + '">' + (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + '%</div>' +
      '</div>' +
    '</div>' +
    alertsHtml +
    (st.thesis ? '<div class="watchpool-thesis">💡 ' + st.thesis + '</div>' : '') +
  '</div>';
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', loadData);