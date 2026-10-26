"""Read-only public catalog, deliberately separated from the private warehouse server."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import app


class StorefrontHandler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' https:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        assets = {'/': ('shop.html', 'text/html'), '/shop.js': ('shop.js', 'text/javascript'),
                  '/shop.css': ('shop.css', 'text/css')}
        if path.startswith('/media/'):
            image = app.read_image(path, public=True)
            if image is None:
                self.send(404, {'error': '图片不存在或商品尚未上架'})
            else:
                self.send(200, *image)
        elif path in assets:
            filename, content_type = assets[path]
            self.send(200, (app.ROOT / 'static' / filename).read_bytes(), content_type + '; charset=utf-8')
        elif path == '/api/catalog':
            with app.connect() as db:
                # Explicit public allowlist: never serialize private product rows.
                items = app.with_images(db, db.execute('''
                    SELECT id,sku,name,kind,material,price,description,image_url,
                      CASE WHEN quantity > 0 THEN 1 ELSE 0 END AS in_stock
                    FROM products WHERE is_listed=1 ORDER BY id DESC'''))
            self.send(200, items)
        elif path == '/api/shop':
            self.send(200, {'name': os.environ.get('SHOP_NAME', '饰物集'),
                            'contact': os.environ.get('SHOP_CONTACT', ''),
                            'phone': os.environ.get('SHOP_PHONE', ''),
                            'email': os.environ.get('SHOP_EMAIL', '')})
        else:
            self.send(404, {'error': '页面不存在'})

    def reject_write(self):
        self.send(405, {'error': '商品展示站不接受修改操作，请联系店主下单'})

    do_POST = reject_write
    do_PUT = reject_write
    do_PATCH = reject_write
    do_DELETE = reject_write


if __name__ == '__main__':
    app.initialize()
    host = os.environ.get('SHOP_HOST', '127.0.0.1')
    port = int(os.environ.get('SHOP_PORT', '8001'))
    print(f'商品展示站已启动，监听 {host}:{port}', flush=True)
    ThreadingHTTPServer((host, port), StorefrontHandler).serve_forever()
