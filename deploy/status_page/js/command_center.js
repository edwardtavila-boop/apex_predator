// eta_engine/deploy/status_page/js/command_center.js
// 10 JARVIS panels for the Command Center view.
// Wave-7 dashboard, 2026-04-27.

import { Panel, formatPct, formatR, formatTime, escapeHtml, selection } from '/js/panels.js';
import { liveStream, poller } from '/js/live.js';
import { onAuthenticated, authedPost } from '/js/auth.js';

// --- 1. Live verdict stream (SSE) ---
class VerdictStreamPanel extends Panel {
  constructor() {
    super('cc-verdict-stream', null, 'Live Verdict Stream');
    this.rows = [];
    if (this.body) this.body.innerHTML = '<div data-list class="space-y-1 text-xs font-mono max-h-96 overflow-y-auto"></div>';
    this.list = this.body?.querySelector('[data-list]');
    liveStream.on('verdict', (v) => this.add(v));
  }
  add(v) {
    this.rows.unshift(v);
    if (this.rows.length > 50) this.rows.length = 50;
    this.repaint();
  }
  repaint() {
    if (!this.list) return;
    this.list.innerHTML = this.rows.map(v => {
      const verdict = v?.response?.verdict || '?';
      const cls = verdict === 'APPROVED' ? 'text-emerald-400'
                : verdict === 'CONDITIONAL' ? 'text-amber-400'
                : verdict === 'DENIED' ? 'text-red-400' : 'text-zinc-400';
      const sym = v?.request?.payload?.symbol || '?';
      const action = v?.request?.action || '?';
      const sage = (v?.response?.conditions || []).filter(c => c.startsWith('v22_')).join(',');
      return `<div><span class="text-zinc-500">${escapeHtml(formatTime(v.ts))}</span> <span class="${cls}">${escapeHtml(verdict)}</span> ${escapeHtml(sym)} ${escapeHtml(action)} ${sage ? `<span class="text-purple-400">[${escapeHtml(sage)}]</span>` : ''}</div>`;
    }).join('');
  }
  refresh() { /* SSE-driven; no poll */ }
}

// --- 2. Sage explain ---
class SageExplainPanel extends Panel {
  constructor() {
    super('cc-sage-explain', `/api/jarvis/sage_explain?symbol=${selection.symbol}&side=long`, 'Sage Explain');
    window.addEventListener('selection-changed', (e) => {
      this.endpoint = `/api/jarvis/sage_explain?symbol=${e.detail.symbol}&side=long`;
      this.refresh();
    });
  }
  render(data) {
    if (data._warning) { this.body.innerHTML = `<div class="text-zinc-500 text-sm">${escapeHtml(data._warning)}</div>`; return; }
    if (data.error_code) { this.setError(data.error_code); return; }
    this.body.innerHTML = `
      <div class="text-sm leading-relaxed text-zinc-200">${escapeHtml(data.narrative || '—')}</div>
      <div class="text-xs text-zinc-500 mt-2 font-mono">${escapeHtml(data.summary_line || '')}</div>`;
  }
}

// --- 3. Sage health alerts ---
class SageHealthPanel extends Panel {
  constructor() { super('cc-sage-health', '/api/jarvis/health', 'Sage Health'); }
  render(data) {
    const issues = data.issues || [];
    if (issues.length === 0) {
      this.body.innerHTML = '<div class="text-emerald-400 text-sm">✓ all schools healthy</div>';
      return;
    }
    this.body.innerHTML = '<ul class="space-y-1 text-xs">' + issues.map(i => {
      const cls = i.severity === 'critical' ? 'text-red-400' : 'text-amber-400';
      return `<li><span class="${cls}">●</span> ${escapeHtml(i.school)} ${formatPct(i.neutral_rate)} neutral (${i.n_consultations})</li>`;
    }).join('') + '</ul>';
  }
}

// --- 4. Disagreement heatmap ---
class DisagreementHeatmapPanel extends Panel {
  constructor() {
    super('cc-disagreement-heatmap', `/api/jarvis/sage_disagreement_heatmap?symbol=${selection.symbol}`, '23-School Disagreement');
    window.addEventListener('selection-changed', (e) => {
      this.endpoint = `/api/jarvis/sage_disagreement_heatmap?symbol=${e.detail.symbol}`;
      this.refresh();
    });
  }
  render(data) {
    const matrix = data.matrix || [];
    if (matrix.length === 0) {
      this.body.innerHTML = `<div class="text-zinc-500 text-sm">${escapeHtml(data._warning || 'no data')}</div>`;
      return;
    }
    const html = matrix.map(row => {
      return `<div class="flex gap-px">${row.cells.map(c => {
        const intensity = Math.abs(c.score);
        const color = c.score > 0 ? `rgba(16,185,129,${intensity})` : `rgba(239,68,68,${intensity})`;
        return `<div class="w-3 h-3" style="background:${color}" title="${escapeHtml(c.school_a)} vs ${escapeHtml(c.school_b)}: ${c.score.toFixed(2)}"></div>`;
      }).join('')}</div>`;
    }).join('');
    this.body.innerHTML = `<div class="space-y-px">${html}</div>`;
  }
}

// --- 5. Stress / mood ---
class StressMoodPanel extends Panel {
  constructor() { super('cc-stress-mood', '/api/jarvis/summary', 'Stress + Session'); }
  render(data) {
    if (data._warning) { this.body.innerHTML = `<div class="text-zinc-500 text-sm">${escapeHtml(data._warning)}</div>`; return; }
    const stress = data.stress_composite ?? 0;
    const phase = data.session_phase || '—';
    const kill = data.kill_switch_state || 'unknown';
    const killCls = kill === 'tripped' ? 'text-red-400' : kill === 'armed' ? 'text-amber-400' : 'text-emerald-400';
    this.body.innerHTML = `
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs text-zinc-500">stress</span>
        <span class="text-2xl font-mono">${formatPct(stress)}</span>
      </div>
      <div class="text-xs text-zinc-500">session: <span class="text-zinc-100">${escapeHtml(phase)}</span></div>
      <div class="text-xs text-zinc-500">kill-switch: <span class="${killCls}">${escapeHtml(kill)}</span></div>`;
  }
}

// --- 6. Policy diff ---
class PolicyDiffPanel extends Panel {
  constructor() { super('cc-policy-diff', '/api/jarvis/policy_diff', 'Bandit Policy Diff'); }
  render(data) {
    if (data._warning) { this.body.innerHTML = `<div class="text-zinc-500 text-sm">${escapeHtml(data._warning)}</div>`; return; }
    const arms = data.arms || {};
    this.body.innerHTML = '<table class="text-xs w-full">' +
      '<tr><th class="text-left">arm</th><th>verdict</th><th>cap</th></tr>' +
      Object.entries(arms).map(([arm, v]) =>
        `<tr><td>${escapeHtml(arm)}</td><td>${escapeHtml(v.verdict)}</td><td>${formatPct(v.size_cap_mult ?? 1)}</td></tr>`
      ).join('') + '</table>';
  }
}

// --- 7. V22 toggle (operator-action panel) ---
class V22TogglePanel extends Panel {
  constructor() { super('cc-v22-toggle', '/api/jarvis/sage_modulation_toggle', 'V22 Sage Modulation'); }
  render(data) {
    const enabled = !!data.enabled;
    const cls = enabled ? 'bg-emerald-600' : 'bg-zinc-700';
    this.body.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="text-sm">${enabled ? 'ON' : 'OFF'}</span>
        <button id="v22-toggle-btn" class="${cls} hover:opacity-80 px-3 py-1 rounded text-sm">flip</button>
      </div>
      <div class="text-xs text-zinc-500 mt-2">flag: ${escapeHtml(data.flag_name || 'ETA_FF_V22_SAGE_MODULATION')}</div>`;
    document.getElementById('v22-toggle-btn').addEventListener('click', async () => {
      try {
        const r = await authedPost('/api/jarvis/sage_modulation_toggle',
          { enabled: !enabled },
          { stepUpReason: 'Flipping V22 sage modulation. PIN required.' });
        if (r && r.ok) this.refresh();
      } catch (e) { console.error('v22 toggle failed', e); }
    });
    // Also reflect on top bar
    const topEl = document.getElementById('top-v22-toggle');
    if (topEl) topEl.innerHTML = `<span class="${enabled ? 'text-emerald-400' : 'text-zinc-500'}">v22 ${enabled ? 'ON' : 'off'}</span>`;
  }
}

// --- 8. Edge tracker leaderboard ---
class EdgeLeaderboardPanel extends Panel {
  constructor() { super('cc-edge-leaderboard', '/api/jarvis/edge_leaderboard', 'Edge Leaderboard'); }
  render(data) {
    const top = data.top || [];
    const bot = data.bottom || [];
    const row = s => `<tr><td>${escapeHtml(s.school)}</td><td class="text-right">${formatR(s.avg_r)}</td><td class="text-right text-zinc-500">${s.n_aligned}</td></tr>`;
    this.body.innerHTML = `
      <div class="grid grid-cols-2 gap-3 text-xs">
        <div><div class="text-emerald-400 mb-1">top</div><table class="w-full">${top.map(row).join('') || '<tr><td>—</td></tr>'}</table></div>
        <div><div class="text-red-400 mb-1">bottom</div><table class="w-full">${bot.map(row).join('') || '<tr><td>—</td></tr>'}</table></div>
      </div>`;
  }
}

// --- 9. Model tier ---
class ModelTierPanel extends Panel {
  constructor() { super('cc-model-tier', '/api/jarvis/model_tier', 'Model Tier'); }
  render(data) {
    if (data._warning) { this.body.innerHTML = `<div class="text-zinc-500 text-sm">${escapeHtml(data._warning)}</div>`; return; }
    this.body.innerHTML = `
      <div class="text-2xl font-mono text-emerald-400">${escapeHtml(data.tier || '—')}</div>
      <div class="text-xs text-zinc-500 mt-2">subsystem: ${escapeHtml(data.subsystem || '—')}</div>
      <div class="text-xs text-zinc-500">category: ${escapeHtml(data.task_category || '—')}</div>
      <div class="text-xs text-zinc-500">at: ${formatTime(data.ts)}</div>`;
  }
}

// --- 10. Latest kaizen ticket ---
class KaizenLatestPanel extends Panel {
  constructor() { super('cc-kaizen-latest', '/api/jarvis/kaizen_latest', 'Latest Kaizen Ticket'); }
  render(data) {
    if (data._warning) { this.body.innerHTML = `<div class="text-zinc-500 text-sm">${escapeHtml(data._warning)}</div>`; return; }
    this.body.innerHTML = `
      <div class="font-semibold mb-1">${escapeHtml(data.title || '—')}</div>
      <pre class="text-xs whitespace-pre-wrap text-zinc-400 max-h-48 overflow-y-auto">${escapeHtml(data.markdown || '')}</pre>`;
  }
}

// --- Initialize all 10 ---
onAuthenticated(() => {
  const panels = [
    new VerdictStreamPanel(),
    new SageExplainPanel(),
    new SageHealthPanel(),
    new DisagreementHeatmapPanel(),
    new StressMoodPanel(),
    new PolicyDiffPanel(),
    new V22TogglePanel(),
    new EdgeLeaderboardPanel(),
    new ModelTierPanel(),
    new KaizenLatestPanel(),
  ];
  panels.forEach(p => { if (p.endpoint) poller.register(p); });
});
