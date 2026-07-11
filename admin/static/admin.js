const API = '';
let TOKEN = localStorage.getItem('admin_token') || '';

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (TOKEN) headers['Authorization'] = 'Bearer ' + TOKEN;
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { logout(); throw new Error('unauthorized'); }
  return res;
}

async function login() {
  const token = document.getElementById('tokenInput').value.trim();
  if (!token) return toast('توکن را وارد کنید');
  const res = await fetch(API + '/admin/pricing', { headers: { 'Authorization': 'Bearer ' + token } });
  if (res.ok) {
    TOKEN = token;
    localStorage.setItem('admin_token', token);
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('adminPanel').style.display = 'flex';
    loadAll();
  } else {
    toast('توکن نامعتبر است');
  }
}

function logout() {
  TOKEN = '';
  localStorage.removeItem('admin_token');
  document.getElementById('loginScreen').style.display = 'flex';
  document.getElementById('adminPanel').style.display = 'none';
}

// nav
document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
    document.getElementById('page-' + el.dataset.page).classList.add('active');
  });
});

async function loadAll() {
  loadPricing(); loadFeatures(); loadDiscounts(); loadAbout(); loadProxy(); loadModels();
}

// Pricing
async function loadPricing() {
  const res = await api('/admin/pricing');
  const data = await res.json();
  const html = data.map(p => `<div class="item"><span>${p.model} — ${p.input_per_million}/${p.output_per_million} ${p.currency}</span><button class="btn sm" onclick="editPricing('${p.model}')">ویرایش</button></div>`).join('');
  document.getElementById('pricingList').innerHTML = html || '<p style="color:var(--muted)">موردی ثبت نشده</p>';
}
function editPricing(m) { document.getElementById('pz-model').value = m; }
async function savePricing() {
  const payload = { model: document.getElementById('pz-model').value, input_per_million: +document.getElementById('pz-in').value || 0, output_per_million: +document.getElementById('pz-out').value || 0, currency: document.getElementById('pz-cur').value };
  if (!payload.model) return toast('نام مدل الزامی است');
  await api('/admin/pricing', { method: 'POST', body: JSON.stringify(payload) });
  toast('ذخیره شد'); loadPricing();
}

// Features
async function loadFeatures() {
  const res = await api('/admin/features');
  const data = await res.json();
  const html = data.map(f => `<div class="item"><span>${f.icon} ${f.title} ${f.active ? '<span class="badge on">فعال</span>' : '<span class="badge off">غیرفعال</span>'}</span><span><button class="btn sm" onclick="editFeature(${f.id})">ویرایش</button> <button class="btn sm danger" onclick="delFeature(${f.id})">حذف</button></span></div>`).join('');
  document.getElementById('featuresList').innerHTML = html || '<p style="color:var(--muted)">موردی ثبت نشده</p>';
}
function editFeature(id) {
  api('/admin/features').then(r => r.json()).then(d => {
    const f = d.find(x => x.id === id);
    if (f) { document.getElementById('ft-id').value = f.id; document.getElementById('ft-title').value = f.title; document.getElementById('ft-desc').value = f.description; document.getElementById('ft-icon').value = f.icon; document.getElementById('ft-order').value = f.order_idx; document.getElementById('ft-active').value = String(f.active); }
  });
}
async function saveFeature() {
  const payload = { id: document.getElementById('ft-id').value ? +document.getElementById('ft-id').value : null, title: document.getElementById('ft-title').value, description: document.getElementById('ft-desc').value, icon: document.getElementById('ft-icon').value, order_idx: +document.getElementById('ft-order').value || 0, active: document.getElementById('ft-active').value === 'true' };
  if (!payload.title) return toast('عنوان الزامی است');
  await api('/admin/features', { method: 'POST', body: JSON.stringify(payload) });
  toast('ذخیره شد'); loadFeatures();
}
async function delFeature(id) { await api('/admin/features/' + id, { method: 'DELETE' }); toast('حذف شد'); loadFeatures(); }

// Discounts
async function loadDiscounts() {
  const res = await api('/admin/discounts');
  const data = await res.json();
  const html = data.map(d => `<div class="item"><span>${d.code} — ${d.percent}% ${d.active ? '<span class="badge on">فعال</span>' : '<span class="badge off">غیرفعال</span>'}</span><span><button class="btn sm" onclick="editDiscount(${d.id})">ویرایش</button> <button class="btn sm danger" onclick="delDiscount(${d.id})">حذف</button></span></div>`).join('');
  document.getElementById('discountsList').innerHTML = html || '<p style="color:var(--muted)">موردی ثبت نشده</p>';
}
function editDiscount(id) {
  api('/admin/discounts').then(r => r.json()).then(d => {
    const x = d.find(z => z.id === id);
    if (x) { document.getElementById('dc-id').value = x.id; document.getElementById('dc-code').value = x.code; document.getElementById('dc-percent').value = x.percent; document.getElementById('dc-active').value = String(x.active); }
  });
}
async function saveDiscount() {
  const payload = { id: document.getElementById('dc-id').value ? +document.getElementById('dc-id').value : null, code: document.getElementById('dc-code').value, percent: +document.getElementById('dc-percent').value || 0, active: document.getElementById('dc-active').value === 'true' };
  if (!payload.code) return toast('کد تخفیف الزامی است');
  await api('/admin/discounts', { method: 'POST', body: JSON.stringify(payload) });
  toast('ذخیره شد'); loadDiscounts();
}
async function delDiscount(id) { await api('/admin/discounts/' + id, { method: 'DELETE' }); toast('حذف شد'); loadDiscounts(); }

// About
async function loadAbout() {
  const res = await api('/admin/about');
  const d = await res.json();
  document.getElementById('ab-title').value = d.title || '';
  document.getElementById('ab-body').value = d.body || '';
}
async function saveAbout() {
  const payload = { title: document.getElementById('ab-title').value, body: document.getElementById('ab-body').value };
  await api('/admin/about', { method: 'POST', body: JSON.stringify(payload) });
  toast('ذخیره شد');
}

// Proxy
async function loadProxy() {
  const res = await api('/admin/proxy');
  const d = await res.json();
  document.getElementById('px-type').value = d.proxy_type || 'socks5';
  document.getElementById('px-url').value = d.proxy_url || '';
  document.getElementById('px-active').value = String(d.active !== false);
  document.getElementById('px-status').textContent = d.active ? '✅ تونل فعال' : '⚠️ تونل غیرفعال';
}
async function saveProxy() {
  const payload = { proxy_type: document.getElementById('px-type').value, proxy_url: document.getElementById('px-url').value, active: document.getElementById('px-active').value === 'true' };
  await api('/admin/proxy', { method: 'POST', body: JSON.stringify(payload) });
  toast('تنظیمات پروکسی ذخیره شد'); loadProxy();
}

// Models
async function loadModels() {
  const res = await fetch(API + '/v1/models');
  const d = await res.json();
  const models = (d.data || []).map(m => m.id);
  document.getElementById('modelsList').innerHTML = (models.length ? models : ['<p style="color:var(--muted)">مدلی بارگذاری نشده — پروکسی را چک کنید</p>']).map(m => `<div class="item"><span>${m}</span></div>`).join('');
}

// init
if (TOKEN) {
  fetch(API + '/admin/pricing', { headers: { 'Authorization': 'Bearer ' + TOKEN } }).then(r => {
    if (r.ok) { document.getElementById('loginScreen').style.display = 'none'; document.getElementById('adminPanel').style.display = 'flex'; loadAll(); }
  }).catch(() => {});
}
