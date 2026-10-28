"""饰品库存管理，Python 标准库 + SQLite，无第三方运行依赖。"""
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('WAREHOUSE_DB', str(ROOT / 'data' / 'warehouse.sqlite3')))
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_PATH = re.compile(r'/media/[0-9a-f]{64}\.(?:jpg|png|webp)')
IMAGE_TYPES = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}


def save_image(content):
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ValueError('图片不能超过 5 MB')
    if content.startswith(b'\xff\xd8\xff') and content.endswith(b'\xff\xd9'):
        extension = 'jpg'
    elif content.startswith(b'\x89PNG\r\n\x1a\n') and content.endswith(b'\x00\x00\x00\x00IEND\xaeB`\x82'):
        extension = 'png'
    elif (len(content) >= 20 and content[:4] == b'RIFF' and content[8:12] == b'WEBP'
          and int.from_bytes(content[4:8], 'little') == len(content) - 8
          and content[12:16] in (b'VP8 ', b'VP8L', b'VP8X')):
        extension = 'webp'
    else:
        raise ValueError('请选择 JPG、PNG 或 WebP 图片，不支持网页链接、SVG 或其他文件')
    folder = DB.parent / 'images'
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(content).hexdigest() + '.' + extension
    # Publish complete files atomically; original filenames are never used as paths.
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as file:
            temp_name = file.name
            file.write(content)
        os.replace(temp_name, folder / name)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return '/media/' + name


def read_image(path):
    if not IMAGE_PATH.fullmatch(path):
        return None
    file = DB.parent / 'images' / path.rsplit('/', 1)[-1]
    try:
        return file.read_bytes(), IMAGE_TYPES[file.suffix[1:]]
    except FileNotFoundError:
        return None


def connect():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL CHECK(kind IN ('新款','旧款')), material TEXT NOT NULL,
          quantity INTEGER NOT NULL CHECK(quantity >= 0),
          price INTEGER NOT NULL CHECK(price >= 0), cost INTEGER NOT NULL CHECK(cost >= 0),
          notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
        CREATE TABLE IF NOT EXISTS movements (
          id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
          delta INTEGER NOT NULL, balance INTEGER NOT NULL, reason TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
        ''')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(products)')}
        for name, definition in [('is_listed', 'INTEGER NOT NULL DEFAULT 0'),
                                 ('description', "TEXT NOT NULL DEFAULT ''"),
                                 ('image_url', "TEXT NOT NULL DEFAULT ''")]:
            if name not in columns:
                db.execute(f'ALTER TABLE products ADD COLUMN {name} {definition}')
        db.execute('''CREATE TABLE IF NOT EXISTS product_images (
            product_id INTEGER NOT NULL REFERENCES products(id), position INTEGER NOT NULL,
            url TEXT NOT NULL, PRIMARY KEY(product_id, position), UNIQUE(product_id,url))''')
        db.execute('''INSERT INTO product_images(product_id,position,url)
            SELECT p.id,0,p.image_url FROM products p WHERE p.image_url != ''
            AND NOT EXISTS (SELECT 1 FROM product_images i WHERE i.product_id=p.id)''')


def with_images(db, rows):
    products = [dict(row) for row in rows]
    galleries = {p['id']: [] for p in products}
    for row in db.execute('SELECT product_id,url FROM product_images ORDER BY product_id,position'):
        if row['product_id'] in galleries:
            galleries[row['product_id']].append(row['url'])
    for product in products:
        product['images'] = galleries[product['id']]
    return products


def integer(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(label + '必须是整数')
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError(label + '必须是整数')
    if result < minimum or result > 1000000000:
        raise ValueError(label + '超出允许范围')
    return result


def money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > 100000000 or n * 100 != (n * 100).to_integral_value():
            raise ValueError('金额须为非负数，最多两位小数')
        return int(n * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('金额格式不正确')


def text_field(data, key, label, required=True, limit=200):
    value = data.get(key, '')
    if not isinstance(value, str):
        raise ValueError(label + '格式不正确')
    value = value.strip()
    if (required and not value) or len(value) > limit:
        raise ValueError(label + f'不能为空且不能超过 {limit} 字' if required else label + '过长')
    return value


def save_product(data, product_id=None):
    image_url = text_field(data, 'image_url', '商品图片网址', False, 2000)
    images = data.get('images')
    if 'images' not in data:
        images = [image_url] if image_url else []
        if product_id and image_url:
            with connect() as db:
                old = [r['url'] for r in db.execute('SELECT url FROM product_images WHERE product_id=? ORDER BY position', (product_id,))]
                if old and old[0] == image_url:
                    images = old
    if not isinstance(images, list) or len(images) > 9:
        raise ValueError('每款商品最多 9 张图片')
    for url in images:
        if not isinstance(url, str) or not url.strip() or len(url) > 2000:
            raise ValueError('图片地址格式不正确')
        if IMAGE_PATH.fullmatch(url):
            if read_image(url) is None:
                raise ValueError('已上传图片不存在，请重新选择图片')
        else:
            image = urlparse(url)
            if image.scheme != 'https' or not image.hostname or image.username or image.password:
                raise ValueError('请选择电脑上的图片，或填写 HTTPS 图片直链；不支持本地文件路径')
    if len(set(images)) != len(images):
        raise ValueError('同一款商品不能重复添加相同图片')
    image_url = images[0] if images else ''
    fields = (text_field(data, 'name', '款式名称'), text_field(data, 'sku', '款式编号'),
              text_field(data, 'kind', '款式分类'), text_field(data, 'material', '材质'),
              money(data.get('price')), money(data.get('cost')),
              text_field(data, 'notes', '备注', False, 2000))
    if fields[2] not in ('新款', '旧款'):
        raise ValueError('款式分类须为新款或旧款')
    with connect() as db:
        if product_id is None:
            quantity = integer(data.get('quantity', 0), '初始库存')
            cur = db.execute('INSERT INTO products(name,sku,kind,material,price,cost,notes,quantity) VALUES(?,?,?,?,?,?,?,?)', fields + (quantity,))
            product_id = cur.lastrowid
            db.execute('INSERT INTO movements(product_id,delta,balance,reason) VALUES(?,?,?,?)', (product_id, quantity, quantity, '初始库存'))
        else:
            cur = db.execute('UPDATE products SET name=?,sku=?,kind=?,material=?,price=?,cost=?,notes=? WHERE id=?', fields + (product_id,))
            if cur.rowcount == 0:
                raise LookupError('产品不存在')
        db.execute('UPDATE products SET image_url=? WHERE id=?', (image_url, product_id))
        db.execute('DELETE FROM product_images WHERE product_id=?', (product_id,))
        db.executemany('INSERT INTO product_images(product_id,position,url) VALUES(?,?,?)',
                       [(product_id, index, url) for index, url in enumerate(images)])
    return product_id


def move_stock(product_id, data):
    amount = integer(data.get('amount'), '数量', 1)
    direction = data.get('direction')
    if direction not in ('in', 'out'):
        raise ValueError('请选择入库或出库')
    reason = text_field(data, 'reason', '出入库原因', limit=500)
    delta = amount if direction == 'in' else -amount
    with connect() as db:
        # Acquire the write lock before reading the balance, preventing concurrent overselling.
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT quantity FROM products WHERE id=?', (product_id,)).fetchone()
        if row is None:
            raise LookupError('产品不存在')
        balance = row['quantity'] + delta
        if balance < 0:
            raise ValueError('库存不足，无法出库')
        if balance > 1000000000:
            raise ValueError('库存超出允许范围')
        db.execute('UPDATE products SET quantity=? WHERE id=?', (balance, product_id))
        db.execute('INSERT INTO movements(product_id,delta,balance,reason) VALUES(?,?,?,?)', (product_id, delta, balance, reason))
    return balance


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith('/media/'):
            image = read_image(path)
            if image is None:
                self.send(404, {'error': '图片不存在'})
            else:
                self.send(200, *image)
            return
        if path in ('/', '/app.js', '/gallery.js', '/style.css'):
            name = {'/': 'index.html', '/app.js': 'app.js', '/gallery.js': 'gallery.js', '/style.css': 'style.css'}[path]
            types = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}
            self.send(200, (ROOT / 'static' / name).read_bytes(), types[name.split('.')[-1]] + '; charset=utf-8')
            return
        with connect() as db:
            if path == '/api/products':
                self.send(200, with_images(db, db.execute('SELECT * FROM products ORDER BY id DESC')))
            elif path == '/api/movements':
                self.send(200, [dict(r) for r in db.execute('SELECT m.*,p.name,p.sku FROM movements m JOIN products p ON p.id=m.product_id ORDER BY m.id DESC LIMIT 200')])
            elif path == '/api/export':
                stream = io.StringIO()
                writer = csv.writer(stream)
                writer.writerow(['款式编号', '款式名称', '新旧款', '材质', '库存数量', '销售单价', '成本价', '备注'])
                for r in db.execute('SELECT * FROM products ORDER BY id'):
                    values = [r['sku'], r['name'], r['kind'], r['material'], r['quantity'], f"{r['price']/100:.2f}", f"{r['cost']/100:.2f}", r['notes']]
                    writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values])
                self.send(200, '\ufeff' + stream.getvalue(), 'text/csv; charset=utf-8')
            else:
                self.send(404, {'error': '页面不存在'})

    def mutate(self):
        # This local application has no user accounts; reject cross-origin writes.
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            self.send(403, {'error': '不允许跨来源操作'})
            return
        try:
            path = urlparse(self.path).path
            length = int(self.headers.get('Content-Length', '0'))
            if path == '/api/images' and self.command == 'POST':
                if length < 1 or length > MAX_IMAGE_BYTES:
                    raise ValueError('图片不能为空且不能超过 5 MB')
                content = self.rfile.read(length)
                if len(content) != length:
                    raise ValueError('图片上传不完整，请重新选择')
                self.send(201, {'url': save_image(content)})
                return
            if length < 1 or length > 32768:
                raise ValueError('请求内容大小不正确')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('请求内容格式不正确')
            parts = urlparse(self.path).path.strip('/').split('/')
            if self.command == 'POST' and parts == ['api', 'products']:
                self.send(201, {'id': save_product(data)})
            elif len(parts) == 3 and parts[:2] == ['api', 'products'] and self.command == 'PUT':
                self.send(200, {'id': save_product(data, integer(parts[2], '产品编号', 1))})
            elif len(parts) == 4 and parts[:2] == ['api', 'products'] and parts[3] == 'stock' and self.command == 'POST':
                self.send(200, {'balance': move_stock(integer(parts[2], '产品编号', 1), data)})
            else:
                self.send(404, {'error': '接口不存在'})
        except sqlite3.IntegrityError:
            self.send(400, {'error': '款式编号已存在，请使用唯一编号'})
        except (ValueError, UnicodeDecodeError) as e:
            self.send(400, {'error': str(e)})
        except LookupError as e:
            self.send(404, {'error': str(e)})
        except OSError as e:
            self.log_error('Write failed: %s', e)
            self.send(500, {'error': '保存失败，请检查运行窗口及磁盘空间后重试'})

    do_POST = mutate
    do_PUT = mutate


if __name__ == '__main__':
    from updater import project_lock, UpdateError
    try:
        with project_lock(ROOT, ('admin',)):
            initialize()
            host = os.environ.get('HOST', '127.0.0.1')
            port = int(os.environ.get('PORT', '8000'))
            print(f'饰品库存管理已启动，监听 {host}:{port}', flush=True)
            with ThreadingHTTPServer((host, port), Handler) as server:
                server.serve_forever()
    except UpdateError as error:
        raise SystemExit(str(error))
    except KeyboardInterrupt:
        pass
