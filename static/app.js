let products = [];
const $ = selector => document.querySelector(selector);
const yuan = cents => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(cents / 100);
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作失败，请重试');
  return data;
}
let noticeTimer;
function notify(message) {
  $('#notice').textContent = message;
  $('#notice').hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { $('#notice').hidden = true; }, 5000);
}
function render() {
  $('#total-styles').textContent = products.length;
  $('#total-stock').textContent = products.reduce((s, p) => s + p.quantity, 0).toLocaleString('zh-CN');
  $('#total-cost').textContent = yuan(products.reduce((s, p) => s + p.quantity * p.cost, 0));
  $('#total-value').textContent = yuan(products.reduce((s, p) => s + p.quantity * p.price, 0));
  const term = $('#search').value.trim().toLowerCase();
  const kind = $('#kind-filter').value;
  const stock = $('#stock-filter').value;
  const shown = products.filter(p => `${p.name} ${p.sku} ${p.material}`.toLowerCase().includes(term) && (!kind || p.kind === kind) && (!stock || (stock === 'empty' ? p.quantity === 0 : p.quantity > 0)));
  $('#result-count').textContent = shown.length;
  $('#products').innerHTML = shown.map(p => `<tr><td><strong>${escapeHTML(p.name)}</strong><small>${escapeHTML(p.sku)}</small></td><td><span class="badge ${p.kind === '新款' ? 'new' : ''}">${p.kind}</span></td><td>${escapeHTML(p.material)}</td><td><b class="${p.quantity === 0 ? 'zero' : ''}">${p.quantity}</b><span class="muted"> 件</span></td><td>${yuan(p.price)}</td><td class="muted">${yuan(p.cost)}</td><td class="row-actions"><button class="link" data-edit="${p.id}">编辑</button><button class="link" data-stock="${p.id}">出入库</button></td></tr>`).join('');
  $('#empty').hidden = shown.length > 0;
  $('#empty h3').textContent = products.length ? '没有找到匹配的款式' : '从第一款饰品开始';
  $('#empty p').textContent = products.length ? '试试其他关键词或筛选条件。' : '点击「新增款式」，录入材质、价格与初始库存。';
}
async function load() {
  const [items, history] = await Promise.all([api('/api/products'), api('/api/movements')]);
  products = items;
  render();
  $('#movements').innerHTML = history.length ? history.map(m => `<tr><td class="muted">${escapeHTML(new Date(m.created_at).toLocaleString('zh-CN'))}</td><td>${escapeHTML(m.name)}<small>${escapeHTML(m.sku)}</small></td><td class="${m.delta >= 0 ? 'positive' : 'zero'}">${m.delta > 0 ? '+' : ''}${m.delta}</td><td>${m.balance}</td><td>${escapeHTML(m.reason)}</td></tr>`).join('') : '<tr><td colspan="5" class="empty-row">还没有出入库记录</td></tr>';
}
function openProduct(product) {
  const form = $('#product-form');
  form.reset();
  form.querySelector('.form-error').textContent = '';
  form.elements.id.value = product?.id || '';
  $('#form-title').textContent = product ? '编辑款式' : '新增款式';
  $('#quantity-label').hidden = Boolean(product);
  form.elements.quantity.disabled = Boolean(product);
  if (product) for (const key of ['name', 'sku', 'kind', 'material', 'price', 'cost', 'notes']) form.elements[key].value = ['price', 'cost'].includes(key) ? (product[key] / 100).toFixed(2) : product[key];
  galleryEditor.open(product?.images || (product?.image_url ? [product.image_url] : []));
  $('#product-dialog').showModal();
}
$('#new-product').onclick = () => openProduct();
document.addEventListener('click', event => {
  const target = event.target.closest('button');
  if (!target) return;
  if (target.dataset.close) $('#' + target.dataset.close).close();
  if (target.dataset.edit) openProduct(products.find(p => p.id === Number(target.dataset.edit)));
  if (target.dataset.stock) {
    const p = products.find(p => p.id === Number(target.dataset.stock));
    $('#stock-form').reset();
    $('#stock-form .form-error').textContent = '';
    $('#stock-form').elements.id.value = p.id;
    $('#stock-product').textContent = `${p.name}（${p.sku}） · 当前库存 ${p.quantity} 件`;
    $('#stock-dialog').showModal();
  }
});
for (const id of ['search', 'kind-filter', 'stock-filter']) $('#' + id).addEventListener('input', render);
for (const type of ['product', 'stock']) {
  $('#' + type + '-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target;
    const data = Object.fromEntries(new FormData(form));
    const id = data.id;
    delete data.id;
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    form.inert = true;
    form.querySelector('.form-error').textContent = '';
    let saved = false;
    try {
      if (type === 'product') data.images = await galleryEditor.upload(api);
      const path = type === 'stock' ? `/api/products/${id}/stock` : `/api/products${id ? '/' + id : ''}`;
      await api(path, { method: type === 'product' && id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
      saved = true;
      $('#' + type + '-dialog').close();
      await load();
      notify(type === 'stock' ? '库存已更新，变动已记录' : '款式已保存');
    } catch (error) {
      if (saved) notify('已保存，但列表刷新失败。请点击刷新数据，勿重复提交。');
      else {
        form.querySelector('.form-error').textContent = error instanceof TypeError ? '无法连接后台，请确认黑色运行窗口仍开启后重试。' : error.message;
        if (type === 'product') $('#image-status').textContent = '';
      }
    } finally { button.disabled = false; form.inert = false; }
  });
}
$('#refresh').onclick = () => load().then(() => notify('数据已刷新')).catch(e => notify(e.message));
load().catch(() => notify('数据加载失败，请检查服务并刷新页面。'));

$('#product-dialog').addEventListener('cancel', event => { if ($('#product-form').inert || galleryEditor.busy) event.preventDefault(); });
