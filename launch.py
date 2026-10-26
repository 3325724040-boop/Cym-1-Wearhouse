"""Start the private inventory app and public catalog locally, then open a browser."""
import os
import threading
import webbrowser
from http.server import ThreadingHTTPServer

import app
from storefront import StorefrontHandler
from updater import project_lock, UpdateError


def main():
    defaults = {
        'SHOP_NAME': '义乌市艾霓工艺品有限公司',
        'SHOP_CONTACT': '电话：13967489245 · 邮箱：3325724040@qq.com',
        'SHOP_PHONE': '13967489245',
        'SHOP_EMAIL': '3325724040@qq.com',
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)
    app.initialize()
    servers = []
    threads = []
    try:
        for port, handler in [(8000, app.Handler), (8001, StorefrontHandler)]:
            servers.append(ThreadingHTTPServer(('127.0.0.1', port), handler))
    except OSError as exc:
        for server in servers:
            server.server_close()
        print('Startup failed. Check whether ports 8000 and 8001 are already in use.')
        print(exc)
        return 1
    for server in servers:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        threads.append(thread)
    try:
        print('Inventory: http://127.0.0.1:8000')
        print('Catalog:   http://127.0.0.1:8001')
        print('Keep this window open. Press Ctrl+C to stop.')
        webbrowser.open('http://127.0.0.1:8000')
        webbrowser.open('http://127.0.0.1:8001')
        threading.Event().wait()
    except KeyboardInterrupt:
        print('\nStopping...')
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()
    return 0


if __name__ == '__main__':
    try:
        with project_lock(app.ROOT, ('admin', 'shop')):
            raise SystemExit(main())
    except UpdateError as error:
        print(error)
        raise SystemExit(1)
