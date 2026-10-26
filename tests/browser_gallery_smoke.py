import base64,tempfile,threading,json,os,sys
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from storefront import StorefrontHandler

with tempfile.TemporaryDirectory() as tmp:
    app.DB=Path(tmp)/'browser.sqlite3';app.initialize()
    servers=[ThreadingHTTPServer(('127.0.0.1',0), h) for h in [app.Handler,StorefrontHandler]]
    for server in servers:threading.Thread(target=server.serve_forever,daemon=True).start()
    admin=f'http://127.0.0.1:{servers[0].server_port}'
    shop=f'http://127.0.0.1:{servers[1].server_port}'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True, **({'executable_path':os.environ['CHROMIUM_EXECUTABLE']} if os.environ.get('CHROMIUM_EXECUTABLE') else {}))
            page=browser.new_page(viewport={'width':1280,'height':960});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(admin)
            files=[]
            for i,color in enumerate(['#a06030','#3060a0','#60a030']):
                url=page.evaluate('''color=>{const c=document.createElement('canvas');c.width=120;c.height=80;const x=c.getContext('2d');x.fillStyle=color;x.fillRect(0,0,120,80);x.fillStyle='#d0b080';x.fillRect(0,0,60,40);return c.toDataURL('image/png');}''',color)
                file=Path(tmp)/f'photo{i}.png';file.write_bytes(base64.b64decode(url.split(',')[1]));files.append(str(file))
            page.get_by_role('button',name='＋ 新增款式').click()
            for name,value in [('name','多图手镯'),('sku','GALLERY-001'),('material','合金'),('price','15'),('cost','3'),('quantity','2000')]:page.locator(f'[name="{name}"]').fill(value)
            page.locator('[name="is_listed"]').select_option('1')
            page.locator('#image-file').set_input_files(files)
            page.wait_for_function("document.querySelectorAll('.gallery-card').length === 3 && !document.querySelector('#product-form').inert")
            # Limit must reject the whole additional batch rather than discard previous photos.
            page.locator('#image-file').set_input_files(files*3)
            page.wait_for_function("document.querySelector('#image-status').textContent.includes('最多 9')")
            assert page.locator('.gallery-card').count()==3
            page.locator('.gallery-card').nth(1).get_by_role('button',name='设为主图',exact=True).click()
            page.locator('.gallery-card').first.get_by_role('button',name='调整参数').click()
            page.locator('#image-editor').wait_for(state='visible')
            before=page.locator('#edit-canvas').evaluate('(c)=>Array.from(c.getContext("2d").getImageData(c.width/2,c.height/2,1,1).data)')
            page.locator('#image-brightness').fill('130')
            after=page.locator('#edit-canvas').evaluate('(c)=>Array.from(c.getContext("2d").getImageData(c.width/2,c.height/2,1,1).data)')
            assert before!=after,(before,after)
            page.locator('#reset-image').click();assert page.locator('#image-brightness').input_value()=='100'
            page.locator('#crop-ratio').select_option('0.8')
            page.locator('#image-rotation').select_option('90')
            for selector,value in [('brightness','120'),('contrast','110'),('saturation','70'),('quality','75')]:page.locator('#image-'+selector).fill(value)
            assert page.locator('#edit-canvas').evaluate('(c)=>[c.width,c.height]')==[80,100]
            page.locator('#apply-image').click();page.wait_for_function("!document.querySelector('#image-editor').open")
            page.get_by_role('button',name='保存款式',exact=True).click()
            page.wait_for_function("!document.querySelector('#product-dialog').open")
            saved=page.request.get(admin+'/api/products').json()[0]
            assert len(saved['images'])==3 and saved['image_url'].endswith('.jpg'),saved
            first=saved['image_url'];assert saved['quantity']==2000
            page.get_by_role('button',name='编辑',exact=True).click()
            page.locator('.gallery-card').nth(2).get_by_role('button',name='前移',exact=True).click()
            page.get_by_role('button',name='保存款式',exact=True).click()
            page.wait_for_function("!document.querySelector('#product-dialog').open")
            reordered=page.request.get(admin+'/api/products').json()[0]
            assert reordered['images']==[saved['images'][0],saved['images'][2],saved['images'][1]]
            page.goto(shop);page.locator('[data-product]').click()
            page.wait_for_function("document.querySelector('.detail-photo img')?.naturalWidth === 80")
            assert page.locator('.detail-photo img').evaluate('i=>i.naturalHeight')==100
            page.get_by_role('button',name='下一张图片',exact=True).click()
            assert page.locator('#gallery-position').inner_text()=='2 / 3'
            page.keyboard.press('ArrowRight');assert page.locator('#gallery-position').inner_text()=='3 / 3'
            page.get_by_role('button',name='查看第 1 张图片',exact=True).click()
            assert page.locator('.detail-photo img').get_attribute('src')==first
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.goto(admin);page.get_by_role('button',name='编辑',exact=True).click()
            page.locator('.gallery-card').nth(2).get_by_role('button',name='移除',exact=True).click()
            page.get_by_role('button',name='保存款式',exact=True).click()
            page.wait_for_function("!document.querySelector('#product-dialog').open")
            assert len(page.request.get(admin+'/api/products').json()[0]['images'])==2
            assert not errors,errors
            browser.close()
            print('PASS: multi-select, limit, main image, live pixel filter, reset, crop/rotation dimensions, JPEG save, reorder, reload, public gallery, keyboard, mobile, remove; stock preserved; no JS errors')
    finally:
        for server in servers:server.shutdown();server.server_close()
