"""Start the local inventory app and open it in a browser."""
import os
import webbrowser
from http.server import ThreadingHTTPServer

import app
from updater import project_lock, UpdateError


def main():
    app.initialize()
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8000'))
    try:
        with ThreadingHTTPServer((host, port), app.Handler) as server:
            url = f'http://{host}:{port}'
            print(f'Inventory: {url}')
            print('Keep this window open. Press Ctrl+C to stop.')
            webbrowser.open(url)
            server.serve_forever()
    except OSError as exc:
        print('Startup failed. Check whether the inventory port is already in use.')
        print(exc)
        return 1
    except KeyboardInterrupt:
        print('\nStopping...')
    return 0


if __name__ == '__main__':
    try:
        with project_lock(app.ROOT, ('admin',)):
            raise SystemExit(main())
    except UpdateError as error:
        print(error)
        raise SystemExit(1)
