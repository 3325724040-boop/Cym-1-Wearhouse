const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const price = cents => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(cents / 100);
let items = [], kind = '';
function image(product) {
  return product.image_url ? `<img src="${esc(product.image_url)}" alt="${esc(product.name)}" loading="lazy" referrerpolicy="no-referrer">` : '<div class="no-image"><span>◇</span><small>商品图片待补充</small></div>';
}
function render() {
  const query = $('#search').value.trim().toLowerCase();
  const shown = items.filter(p => (!kind || p.kind === kind) && `${p.name} ${p.material} ${p.sku}`.toLowerCase().includes(query));
  $('#count').textContent = `${shown.length} 款精选饰品`;
  $('#catalog').innerHTML = shown.map(p => `<button class="product" data-product="${p.id}"><div class="photo">${image(p)}<span class="tag">${p.kind === '新款' ? '新品' : '经典款'}</span></div><div class="product-info"><small>${esc(p.material)}</small><h3>${esc(p.name)}</h3><div><strong>${price(p.price)}</strong><span>${p.in_stock ? '有现货' : '暂时缺货'}</span></div><p>${esc(p.sku)} <span>查看详情 ↗</span></p></div></button>`).join('');
  $('#empty').hidden = shown.length > 0;
  $('#empty h3').textContent = items.length ? '没有找到匹配的饰品' : '美好的款式，正在准备中';
  $('#empty p').textContent = items.length ? '换个关键词或分类再看看。' : '欢迎稍后再来，或联系店主了解详情。';
}
function showDetail(product) {
  $('#detail-content').innerHTML = `<div class="detail-photo">${image(product)}</div><p class="eyebrow">${esc(product.sku)} · ${product.kind === '新款' ? '新品' : '经典款'}</p><h2>${esc(product.name)}</h2><p>${esc(product.material)} · ${product.in_stock ? '有现货' : '暂时缺货，请咨询补货时间'}</p><strong class="detail-price">${price(product.price)}</strong><p class="description">${esc(product.description || '更多款式细节，欢迎联系店主咨询。')}</p>`;
  $('#detail').showModal();
}
document.addEventListener('click', event => {
  const tab = event.target.closest('[data-kind]');
  if (tab) {
    kind = tab.dataset.kind;
    document.querySelectorAll('[data-kind]').forEach(b => {
      b.classList.toggle('selected', b === tab);
      b.setAttribute('aria-pressed', String(b === tab));
    });
    render();
  }
  const card = event.target.closest('[data-product]');
  if (card) showDetail(items.find(p => p.id === Number(card.dataset.product)));
});
document.addEventListener('error', event => {
  if (event.target.tagName === 'IMG') {
    const fallback = document.createElement('div');
    fallback.className = 'no-image';
    fallback.textContent = '图片暂不可用';
    event.target.replaceWith(fallback);
  }
}, true);
$('#close-detail').onclick = () => $('#detail').close();
$('#detail-contact').onclick = () => $('#detail').close();
$('#search').addEventListener('input', render);
async function load() {
  $('#load-error').hidden = true;
  try {
    const responses = await Promise.all([fetch('/api/catalog'), fetch('/api/shop')]);
    if (responses.some(r => !r.ok)) throw new Error('load');
    const [products, shop] = await Promise.all(responses.map(r => r.json()));
    items = products;
    $('#brand').textContent = shop.name;
    $('#footer-brand').textContent = shop.name;
    document.title = shop.name + ' · 精选饰品';
    $('#contact-value').textContent = shop.contact || '店主尚未公开联系方式，请稍后再来。';
    const links = $('#contact-links');
    links.replaceChildren();
    for (const [label, value, prefix, valid] of [
      ['拨打电话', shop.phone, 'tel:', /^[+0-9 ()-]{5,30}$/],
      ['发送邮件', shop.email, 'mailto:', /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/]
    ]) {
      if (!value || !valid.test(value)) continue;
      const link = document.createElement('a');
      link.textContent = label;
      link.href = prefix + value;
      links.appendChild(link);
    }
    render();
  } catch {
    $('#load-error').hidden = false;
    $('#count').textContent = '商品暂时无法加载';
    $('#contact-value').textContent = '联系方式加载失败，请重试。';
  }
}
$('#retry').onclick = load;
load();
