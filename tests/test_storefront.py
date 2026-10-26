import json
import os
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
from storefront import StorefrontHandler
import test_app


class StorefrontTests(test_app.WarehouseFixture):

    def setUp(self):
        super().setUp()
        self.public = ThreadingHTTPServer(('127.0.0.1', 0), StorefrontHandler)
        self.public_thread = threading.Thread(target=self.public.serve_forever, daemon=True)
        self.public_thread.start()
        self.admin_base = self.base
        self.public_base = f'http://127.0.0.1:{self.public.server_port}'

    def tearDown(self):
        self.public.shutdown()
        self.public.server_close()
        self.public_thread.join()
        super().tearDown()

    def public_request(self, *args, **kwargs):
        self.base = self.public_base
        try:
            return self.request(*args, **kwargs)
        finally:
            self.base = self.admin_base

    def test_public_schema_hides_private_fields_and_unlisted_products(self):
        self.product(sku='PRIVATE', name='未上架款')
        product_id, data = self.product(is_listed='1', description='客户可见介绍', notes='内部供应商信息')
        status, body = self.public_request('/api/catalog')
        self.assertEqual(status, 200)
        catalog = json.loads(body)
        self.assertEqual(len(catalog), 1)
        self.assertEqual(set(catalog[0]), {'id', 'sku', 'name', 'kind', 'material', 'price', 'description', 'image_url', 'in_stock'})
        self.assertEqual(catalog[0]['description'], '客户可见介绍')
        self.assertNotIn('内部供应商信息', body.decode())
        self.assertNotIn('PRIVATE', body.decode())
        self.request(f'/api/products/{product_id}/stock', 'POST', dict(direction='out', amount=5, reason='销售'))
        self.assertEqual(json.loads(self.public_request('/api/catalog')[1])[0]['in_stock'], 0)
        self.request(f'/api/products/{product_id}', 'PUT', data | {'is_listed': '0'})
        self.assertEqual(json.loads(self.public_request('/api/catalog')[1]), [])

    def test_public_server_never_exposes_admin_routes_or_accepts_writes(self):
        for path in ['/api/products', '/api/movements', '/api/export', '/app.js', '/app.py', '/data/warehouse.sqlite3', '/%2e%2e/app.py']:
            self.assertEqual(self.public_request(path)[0], 404)
        for method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            self.assertEqual(self.public_request('/api/products', method, {})[0], 405)
        for path in ['/', '/shop.js', '/shop.css']:
            self.assertEqual(self.public_request(path)[0], 200)

    def test_shop_settings_and_image_validation(self):
        with patch.dict(os.environ, {'SHOP_NAME': '测试店铺', 'SHOP_CONTACT': '公开邮箱：shop@example.com'}):
            data = json.loads(self.public_request('/api/shop')[1])
            self.assertEqual(data['name'], '测试店铺')
            self.assertEqual(data['contact'], '公开邮箱：shop@example.com')
        _, data = self.product()
        for image in ['javascript:alert(1)', 'http://example.com/a.jpg', 'https://user:pass@example.com/a.jpg']:
            self.assertEqual(self.request('/api/products', 'POST', data | {'sku': 'BAD', 'image_url': image})[0], 400)

    def test_uploaded_images_are_available_only_for_listed_products(self):
        status, body = self.request('/api/images', 'POST', test_app.TEST_PNG)
        self.assertEqual(status, 201)
        url = json.loads(body)['url']
        self.assertEqual(self.public_request(url)[0], 404)
        product_id, data = self.product(image_url=url, is_listed='1')
        self.assertEqual(self.public_request(url), (200, test_app.TEST_PNG))
        self.assertEqual(json.loads(self.public_request('/api/catalog')[1])[0]['image_url'], url)
        self.assertEqual(self.public_request('/api/images', 'POST', test_app.TEST_PNG)[0], 405)
        self.request(f'/api/products/{product_id}', 'PUT', data | {'is_listed': '0'})
        self.assertEqual(self.public_request(url)[0], 404)
