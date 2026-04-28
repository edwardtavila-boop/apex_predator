// eta_engine/deploy/status_page/js/panels.js
// Panel base class + formatters + tab manager.
// Wave-7 dashboard, 2026-04-27.

const STALE_AFTER_MS = 30_000;

export class Panel {
  /**
   * @param {string} containerId - the data-panel-id value (without #)
   * @param {string} endpoint    - HTTP endpoint to fetch
   * @param {string} title       - human-readable panel title
   */
  constructor(containerId, endpoint, title) {
    this.containerId = containerId;
    this.endpoint = endpoint;
    this.title = title;
    this.lastRefreshAt = null;
    this.lastError = null;
    this.element = document.querySelector(`[data-panel-id="${containerId}"]`);
    if (this.element) {
      this.element.innerHTML = `<div class="panel-title">${title}</div><div data-panel-body></div><div class="panel-refresh"></div>`;
      this.body = this.element.querySelector('[data-panel-body]');
      this.refreshLabel = this.element.querySelector('.panel-refresh');
    }
  }

  setLoading() {
    if (!this.element) return;
    this.element.classList.add('loading');
    this.element.classList.remove('error', 'stale');
  }

  setError(message) {
    if (!this.element) return;
    this.element.classList.add('error');
    this.element.classList.remove('loading');
    this.body.innerHTML = `<div class="text-red-400 text-xs">${escapeHtml(message)}</div>`;
    this.lastError = message;
  }

  markStale() {
    if (!this.element) return;
    this.element.classList.add('stale');
  }

  /** Subclasses override this. */
  render(_data) {
    if (!this.body) return;
    this.body.textContent = JSON.stringify(_data, null, 2);
  }

  /** Called by Poller. Fetches + renders + handles errors. */
  async refresh() {
    if (!this.element) return;
    this.setLoading();
    try {
      const resp = await fetch(this.endpoint, {
        credentials: 'same-origin',
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        const code = body?.detail?.error_code || body?.error_code || `http_${resp.status}`;
        this.setError(`${code}`);
        return;
      }
      const data = await resp.json();
      try {
        this.render(data);
        this.element.classList.remove('loading', 'error', 'stale');
        this.lastRefreshAt = Date.now();
        this.updateRefreshLabel();
      } catch (e) {
        console.error(`render failed for ${this.containerId}`, e);
        this.setError(`render: ${e.message}`);
      }
    } catch (e) {
      console.error(`fetch failed for ${this.containerId}`, e);
      this.setError(`network: ${e.message}`);
    }
  }

  updateRefreshLabel() {
    if (!this.refreshLabel || !this.lastRefreshAt) return;
    const ageS = Math.floor((Date.now() - this.lastRefreshAt) / 1000);
    if (ageS > STALE_AFTER_MS / 1000) {
      this.markStale();
      this.refreshLabel.textContent = `stale ${ageS}s`;
    } else {
      this.refreshLabel.textContent = `updated ${ageS}s ago`;
    }
  }
}

// --- formatters ---

export function formatNumber(n, digits = 2) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return Number(n).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPct(p, digits = 2) {
  if (p === null || p === undefined || isNaN(p)) return '—';
  return `${(Number(p) * 100).toFixed(digits)}%`;
}

export function formatR(r) {
  if (r === null || r === undefined || isNaN(r)) return '—';
  const sign = r >= 0 ? '+' : '';
  return `${sign}${Number(r).toFixed(2)}R`;
}

export function formatTime(isoOrEpoch) {
  if (!isoOrEpoch) return '—';
  const d = typeof isoOrEpoch === 'number' ? new Date(isoOrEpoch * 1000) : new Date(isoOrEpoch);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString();
}

export function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

// --- tab manager ---

export function initTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      tabBtns.forEach(b => {
        b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
        b.classList.toggle('border-emerald-500', b === btn);
        b.classList.toggle('text-emerald-400', b === btn);
        b.classList.toggle('border-transparent', b !== btn);
        b.classList.toggle('text-zinc-400', b !== btn);
      });
      document.querySelectorAll('section[id^="view-"]').forEach(sec => {
        sec.classList.toggle('hidden', sec.id !== `view-${target}`);
      });
    });
  });
}

// --- selection state ---

export const selection = {
  botId: 'mnq',     // default selected bot
  symbol: 'MNQ',
};

export function selectBot(botId, symbol) {
  selection.botId = botId;
  selection.symbol = symbol;
  window.dispatchEvent(new CustomEvent('selection-changed', {
    detail: { botId, symbol },
  }));
}
