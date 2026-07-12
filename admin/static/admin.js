/**
 * Multiai Admin — Utility JS
 * Vanilla JS utilities for the admin panel.
 */

/* ============ API Helper ============ */

async function fetchAPI(url, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };
  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) {
    window.location.href = '/admin/login';
    throw new Error('Unauthorized');
  }
  return res;
}

/* ============ Toast Notification ============ */

function toast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

/* ============ Number Formatting ============ */

function formatNumber(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('fa-IR');
}

function formatCurrency(n, currency) {
  if (n == null) return '—';
  const formatted = Number(n).toLocaleString('fa-IR');
  return currency ? formatted + ' ' + currency : formatted;
}

function formatTokens(n) {
  if (n == null) return '—';
  n = Number(n);
  if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
  return n.toString();
}

/* ============ Date Formatting ============ */

function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fa-IR', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit'
    });
  } catch {
    return iso;
  }
}

function formatDateShort(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fa-IR', {
      year: 'numeric', month: '2-digit', day: '2-digit'
    });
  } catch {
    return iso;
  }
}

/* ============ Debounce ============ */

function debounce(fn, ms = 300) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}

/* ============ Pagination Helper ============ */

class Pagination {
  constructor(containerId, opts = {}) {
    this.container = document.getElementById(containerId);
    this.page = 1;
    this.perPage = opts.perPage || 20;
    this.total = 0;
    this.onChange = opts.onChange || (() => {});
  }

  get totalPages() {
    return Math.max(1, Math.ceil(this.total / this.perPage));
  }

  get offset() {
    return (this.page - 1) * this.perPage;
  }

  setTotal(total) {
    this.total = total;
    this.render();
  }

  goTo(page) {
    this.page = Math.max(1, Math.min(page, this.totalPages));
    this.render();
    this.onChange(this.page, this.offset);
  }

  render() {
    if (!this.container) return;
    const tp = this.totalPages;
    if (tp <= 1) { this.container.innerHTML = ''; return; }

    let html = '<div class="pagination">';
    html += `<button ${this.page <= 1 ? 'disabled' : ''} onclick="window._pagination.goTo(${this.page - 1})">قبلی</button>`;

    const start = Math.max(1, this.page - 2);
    const end = Math.min(tp, this.page + 2);
    if (start > 1) {
      html += `<button onclick="window._pagination.goTo(1)">1</button>`;
      if (start > 2) html += '<span class="page-info">…</span>';
    }
    for (let i = start; i <= end; i++) {
      html += `<button class="${i === this.page ? 'active' : ''}" onclick="window._pagination.goTo(${i})">${i}</button>`;
    }
    if (end < tp) {
      if (end < tp - 1) html += '<span class="page-info">…</span>';
      html += `<button onclick="window._pagination.goTo(${tp})">${tp}</button>`;
    }

    html += `<button ${this.page >= tp ? 'disabled' : ''} onclick="window._pagination.goTo(${this.page + 1})">بعدی</button>`;
    html += '</div>';
    this.container.innerHTML = html;
  }
}

/* ============ Sidebar Toggle (Mobile) ============ */

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebarOverlay').classList.toggle('show');
}

/* ============ Safe HTML Escape ============ */

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/* ============ Loading Helper ============ */

function showLoading(containerId) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = '<div class="loading"><div class="spinner"></div><span>در حال بارگذاری...</span></div>';
}

function showEmpty(containerId, message, icon) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `<div class="empty-state"><div class="empty-icon">${icon || '📭'}</div><div class="empty-text">${message || 'موردی یافت نشد'}</div></div>`;
}
