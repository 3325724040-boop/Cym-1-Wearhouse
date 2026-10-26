import concurrent.futures
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

import app


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db = app.DB
        app.DB = Path(self.tmp.name) / 'test.sqlite3'
        app.initialize()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        app.DB = self.original_db
        self.tmp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        payload = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.base + path, data=payload, method=method,
                                     headers=headers or {'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def product(self, **overrides):
        values = dict(name='珍珠耳饰', sku='ER-001', kind='新款', material='925银', quantity=5,
                      price='29.90', cost='12.35', notes='白色')
        values.update(overrides)
        status, body = self.request('/api/products', 'POST', values)
        self.assertEqual(status, 201, body)
        return json.loads(body)['id'], values

    def test_lifecycle_and_persistence(self):
        product_id, data = self.product()
        self.assertEqual(self.request('/')[0], 200)
        self.assertEqual(self.request('/app.js')[0], 200)
        for direction, amount, balance in [('in', 3, 8), ('out', 2, 6)]:
            status, body = self.request(f'/api/products/{product_id}/stock', 'POST',
                                        dict(direction=direction, amount=amount, reason='测试流水'))
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['balance'], balance)
        data.update(name='珍珠耳饰升级款', kind='旧款', quantity=999)
        self.assertEqual(self.request(f'/api/products/{product_id}', 'PUT', data)[0], 200)
        app.initialize()  # Idempotent startup must preserve saved records.
        row = json.loads(self.request('/api/products')[1])[0]
        self.assertEqual((row['quantity'], row['price'], row['cost'], row['kind']), (6, 2990, 1235, '旧款'))
        history = json.loads(self.request('/api/movements')[1])
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]['balance'], 6)
        status, body = self.request('/api/export')
        self.assertEqual(status, 200)
        self.assertIn('珍珠耳饰升级款', body.decode('utf-8-sig'))

    def test_invalid_input_is_rejected(self):
        product_id, data = self.product()
        self.assertEqual(self.request('/api/products', 'POST', data)[0], 400)
        for changes in [dict(price='1.001', sku='X'), dict(cost='NaN', sku='X'),
                        dict(quantity=-1, sku='X'), dict(quantity=1.5, sku='X'), dict(name='', sku='X')]:
            self.assertEqual(self.request('/api/products', 'POST', data | changes)[0], 400)
        for amount in [6, 0, -1, 1.5]:
            self.assertEqual(self.request(f'/api/products/{product_id}/stock', 'POST',
                             dict(direction='out', amount=amount, reason='出库'))[0], 400)
        self.assertEqual(json.loads(self.request('/api/products')[1])[0]['quantity'], 5)
        self.assertEqual(len(json.loads(self.request('/api/movements')[1])), 1)
        self.assertEqual(self.request('/api/products/999/stock', 'POST', dict(direction='in', amount=1, reason='test'))[0], 404)

    def test_concurrent_outbound_cannot_oversell(self):
        product_id, _ = self.product(quantity=1)
        def sell(_):
            return self.request(f'/api/products/{product_id}/stock', 'POST',
                                dict(direction='out', amount=1, reason='销售'))[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(sell, range(2)))
        self.assertEqual(sorted(statuses), [200, 400])
        self.assertEqual(json.loads(self.request('/api/products')[1])[0]['quantity'], 0)
        self.assertEqual(len(json.loads(self.request('/api/movements')[1])), 2)

    def test_export_escapes_spreadsheet_formulas_and_rejects_cross_origin(self):
        self.product(name='=1+1')
        self.assertIn("'=1+1", self.request('/api/export')[1].decode('utf-8-sig'))
        self.assertEqual(self.request('/api/products', 'POST', {}, {'Origin': 'https://other.example'})[0], 403)


if __name__ == '__main__':
    unittest.main()
