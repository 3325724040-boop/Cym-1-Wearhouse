/* Draft gallery and local canvas editing. No third-party runtime dependencies. */
window.galleryEditor = (() => {
  const $ = selector => document.querySelector(selector);
  let images = [], resources = [], editing = null, bitmap = null, locked = false;
  const defaults = { 'crop-ratio': 'original', 'image-rotation': '0', 'image-zoom': '100', 'image-pan-x': '0', 'image-pan-y': '0', 'image-brightness': '100', 'image-contrast': '100', 'image-saturation': '100', 'image-max-edge': '1600', 'image-quality': '90' };
  function objectURL(blob) {
    const url = URL.createObjectURL(blob);
    resources.push(url);
    return url;
  }
  function report(message) { $('#image-status').textContent = message; }
  function render() {
    const list = $('#gallery-list');
    list.replaceChildren();
    images.forEach((item, index) => {
      const card = document.createElement('div'); card.className = 'gallery-card';
      const image = document.createElement('img'); image.src = item.preview || item.url;
      image.alt = `商品图片 ${index + 1}`; image.referrerPolicy = 'no-referrer';
      image.onerror = () => { image.alt = '图片加载失败，请更换图片'; };
      card.append(image);
      const title = document.createElement('strong'); title.textContent = index === 0 ? '主图' : `详情图 ${index}`; card.append(title);
      const controls = document.createElement('div'); controls.className = 'gallery-controls';
      function button(label, action, disabled = false) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
        button.disabled = disabled; button.onclick = action; controls.append(button);
      }
      button('设为主图', () => { images.unshift(images.splice(index, 1)[0]); render(); }, index === 0);
      button('前移', () => { [images[index - 1], images[index]] = [images[index], images[index - 1]]; render(); }, index === 0);
      button('后移', () => { [images[index + 1], images[index]] = [images[index], images[index + 1]]; render(); }, index === images.length - 1);
      button('调整参数', () => openEditor(item));
      button('移除', () => { images.splice(index, 1); render(); report('已从本次编辑中移除，保存款式后生效。'); });
      card.append(controls); list.append(card);
    });
  }
  async function decode(source) {
    const image = new Image(); image.src = source; await image.decode();
    if (image.naturalWidth * image.naturalHeight > 40000000) throw new Error('图片尺寸过大，请先缩小至 4000 万像素以内');
    return image;
  }
  $('#image-file').addEventListener('change', async event => {
    if (locked) return;
    locked = true;
    $('#product-form').inert = true;
    const files = Array.from(event.target.files);
    event.target.disabled = true;
    const save = $('#product-form [type="submit"]'); save.disabled = true;
    try {
      if (images.length + files.length > 9) throw new Error('每款最多 9 张，请先移除不需要的图片');
      const additions = [];
      for (const file of files) {
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('请选择 JPG、PNG 或 WebP 图片');
        if (file.size > 5 * 1024 * 1024) throw new Error('单张图片不能超过 5 MB');
        const preview = objectURL(file); await decode(preview);
        additions.push({ file, preview, source: preview, settings: { ...defaults } });
      }
      images.push(...additions); render(); report(`已添加 ${additions.length} 张，共 ${images.length}/9 张。保存款式后生效。`);
    } catch (e) { report(e.message); }
    finally { event.target.value = ''; event.target.disabled = false; save.disabled = false; locked = false; $('#product-form').inert = false; }
  });
  $('#add-image-link').onclick = () => {
    if (locked) return;
    try {
      if (images.length >= 9) throw new Error('每款最多 9 张图片');
      const url = $('#image-link').value.trim(); const parsed = new URL(url);
      if (parsed.protocol !== 'https:' || parsed.username || parsed.password) throw new Error('请填写 HTTPS 图片直链');
      if (images.some(i => i.url === url)) throw new Error('已添加这张图片');
      images.push({ url }); $('#image-link').value = ''; render(); report('图片直链已添加。外链不能直接调整参数，请上传本地图片。');
    } catch (e) { report(e instanceof TypeError ? '请填写有效的 HTTPS 图片直链' : e.message); }
  };
  function settings() { return Object.fromEntries(Object.keys(defaults).map(id => [id, $('#' + id).value])); }
  async function openEditor(item) {
    if (locked) return;
    const source = item.source || item.url;
    if (!source?.startsWith('blob:') && !source?.startsWith('/media/')) {
      report('外链图片请先保存到电脑，再通过“选择文件”上传后调整。'); return;
    }
    locked = true;
    try {
      bitmap = await decode(source); editing = item;
      for (const [id, value] of Object.entries(item.settings || defaults)) $('#' + id).value = value;
      $('#editor-error').textContent = ''; draw(); $('#image-editor').showModal();
    } catch { report('无法读取图片，请重新上传本地图片。'); }
    finally { locked = false; }
  }
  function draw() {
    if (!bitmap) return;
    const s = settings(), angle = Number(s['image-rotation']);
    const scale = Math.min(1, 2400 / Math.max(bitmap.naturalWidth, bitmap.naturalHeight));
    const width = Math.max(1, Math.round(bitmap.naturalWidth * scale)), height = Math.max(1, Math.round(bitmap.naturalHeight * scale));
    const rotated = document.createElement('canvas');
    rotated.width = angle % 180 ? height : width; rotated.height = angle % 180 ? width : height;
    const ctx = rotated.getContext('2d');
    ctx.translate(rotated.width / 2, rotated.height / 2); ctx.rotate(angle * Math.PI / 180);
    ctx.drawImage(bitmap, -width / 2, -height / 2, width, height);
    const ratio = s['crop-ratio'] === 'original' ? rotated.width / rotated.height : Number(s['crop-ratio']);
    let cropWidth = rotated.width, cropHeight = cropWidth / ratio;
    if (cropHeight > rotated.height) { cropHeight = rotated.height; cropWidth = cropHeight * ratio; }
    cropWidth /= Number(s['image-zoom']) / 100; cropHeight /= Number(s['image-zoom']) / 100;
    const x = (rotated.width - cropWidth) * (Number(s['image-pan-x']) + 100) / 200;
    const y = (rotated.height - cropHeight) * (Number(s['image-pan-y']) + 100) / 200;
    const canvas = $('#edit-canvas'), outputScale = Math.min(1, Number(s['image-max-edge']) / Math.max(cropWidth, cropHeight));
    canvas.width = Math.max(1, Math.round(cropWidth * outputScale)); canvas.height = Math.max(1, Math.round(cropHeight * outputScale));
    const target = canvas.getContext('2d'); target.fillStyle = '#fff'; target.fillRect(0, 0, canvas.width, canvas.height);
    target.filter = `brightness(${s['image-brightness']}%) contrast(${s['image-contrast']}%) saturate(${s['image-saturation']}%)`;
    target.drawImage(rotated, x, y, cropWidth, cropHeight, 0, 0, canvas.width, canvas.height);
    for (const name of ['brightness', 'contrast', 'saturation', 'quality']) $('#' + name + '-value').textContent = s['image-' + name] + '%';
    $('#zoom-value').textContent = (Number(s['image-zoom']) / 100).toFixed(2) + '×';
    for (const axis of ['x', 'y']) $('#pan-' + axis + '-value').textContent = s['image-pan-' + axis];
    $('#editor-dimensions').textContent = `导出尺寸：${canvas.width} × ${canvas.height} 像素`;
  }
  for (const id of Object.keys(defaults)) $('#' + id).addEventListener('input', draw);
  $('#reset-image').onclick = () => { for (const [id, value] of Object.entries(defaults)) $('#' + id).value = value; draw(); };
  $('#close-image-editor').onclick = () => { if (!locked) $('#image-editor').close(); };
  $('#image-editor').addEventListener('cancel', e => { if (locked) e.preventDefault(); });
  $('#apply-image').onclick = async () => {
    if (locked || !editing) return;
    locked = true; $('#apply-image').disabled = true;
    try {
      const s = settings();
      const blob = await new Promise(resolve => $('#edit-canvas').toBlob(resolve, 'image/jpeg', Number(s['image-quality']) / 100));
      if (!blob || blob.size > 5 * 1024 * 1024) throw new Error('导出图片过大，请降低尺寸或 JPEG 清晰度后重试');
      editing.source ||= editing.url;
      editing.file = new File([blob], 'product-edited.jpg', { type: 'image/jpeg' });
      editing.preview = objectURL(blob); editing.settings = s;
      $('#image-editor').close(); render(); report('调整已应用到预览，点击“保存款式”后生效。');
    } catch (e) { $('#editor-error').textContent = e.message; }
    finally { locked = false; $('#apply-image').disabled = false; }
  };
  return {
    get busy() { return locked; },
    open(urls) {
      resources.forEach(URL.revokeObjectURL); resources = []; editing = null; bitmap = null;
      images = urls.map(url => ({ url })); report(''); $('#image-link').value = ''; render();
    },
    async upload(api) {
      if (locked) throw new Error('图片仍在处理中，请稍后保存');
      locked = true;
      try {
        for (const [index, item] of images.entries()) {
          if (!item.file) continue;
          report(`正在上传第 ${index + 1}/${images.length} 张图片…`);
          const result = await api('/api/images', { method: 'POST', headers: { 'Content-Type': item.file.type }, body: item.file });
          item.url = result.url; item.file = null;
        }
        return images.map(i => i.url);
      } finally { locked = false; }
    }
  };
})();
