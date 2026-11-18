from i18n import message, error_message, localize, language_code, LANGUAGES
import argparse
import json
import logging
import os
import secrets
import signal
import sys
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine import Controller
from network import DemoNetwork, Network

ROOT = Path(__file__).resolve().parent


class Server(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def language(self):
        return language_code(self.headers.get('X-Control-Language', 'es'))

    def log_message(self, format, *args):
        pass

    def reply(self, status, value, content_type='application/json; charset=utf-8'):
        data = json.dumps(localize(value, self.language()), ensure_ascii=False).encode('utf-8') if isinstance(value, (dict, list)) else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Language', self.language())
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected:
            self.reply(403, dict(error=message('err_host')))
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + expected:
            self.reply(403, dict(error=message('err_origin')))
            return False
        if self.path.startswith('/api/') and not secrets.compare_digest(
                self.headers.get('X-Control-Token', ''), self.server.token):
            self.reply(403, dict(error=message('err_session')))
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        if self.path == '/api/state':
            snapshot = self.server.controller.snapshot()
            snapshot['language'] = self.language()
            self.reply(200, snapshot)
            return
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8'),
                 '/i18n.js': ('i18n.js', 'text/javascript; charset=utf-8')}
        files.update({f'/locales/{code}.json': (f'locales/{code}.json', 'application/json; charset=utf-8')
                      for code in LANGUAGES})
        if self.path not in files:
            self.reply(404, dict(error=message('err_not_found')))
            return
        name, mime = files[self.path]
        self.reply(200, (ROOT / 'web' / name).read_bytes(), mime)

    def do_POST(self):
        if not self.authorized():
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 4096 or self.headers.get_content_type() != 'application/json':
                raise ValueError(message('err_request'))
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError(message('err_request'))
            action = self.path.removeprefix('/api/')
            if action == 'heartbeat':
                self.server.controller.heartbeat()
            elif action == 'shutdown':
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif action in {'scan', 'select', 'rename', 'block', 'release', 'mode', 'allow', 'resume'}:
                required = {'select': {'id': str}, 'rename': {'mac': str, 'name': str},
                            'block': {'mac': str, 'blocked': bool}, 'mode': {'mode': str},
                            'allow': {'mac': str, 'allowed': bool}}.get(action, {})
                if any(type(body.get(key)) is not kind for key, kind in required.items()):
                    raise ValueError(message('err_payload'))
                if action == 'allow' and 'name' in body and not isinstance(body['name'], str):
                    raise ValueError(message('err_name_type'))
                self.server.controller.submit(action, body)
            else:
                self.reply(404, dict(error=message('err_unknown_action')))
                return
            self.reply(202, dict(ok=True))
        except (ValueError, KeyError) as error:
            self.reply(400, dict(error=error_message(error)))


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='Control de red local')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--lang', choices=LANGUAGES, default='es', help='Console language / Idioma de la consola')
    options = parser.parse_args()
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else ROOT
    data_dir = options.data_dir or base / ('datos-demo' if options.demo else 'datos')
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data_dir / 'app.log', encoding='utf-8', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    port = options.port if options.port is not None else (8766 if options.demo else 8765)
    session_file = data_dir / 'session.json'
    try:
        server = Server(('127.0.0.1', port), Handler)
    except OSError:
        try:
            session = json.loads(session_file.read_text(encoding='utf-8'))
            url = f'http://127.0.0.1:{port}'
            request = urllib.request.Request(url + '/api/state', headers={'X-Control-Token': session['token']})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=2) as response:
                running = json.load(response)
            if running.get('version') != '4.1':
                raise RuntimeError(message('cli_previous_version'))
            webbrowser.open(url + '/#' + session['token'])
            return
        except Exception:
            raise SystemExit(localize(message('cli_port_busy'), options.lang)) from None
    server.token = secrets.token_urlsafe(32)
    session_file.write_text(json.dumps(dict(token=server.token, port=server.server_port)), encoding='utf-8')
    server.controller = Controller(DemoNetwork() if options.demo else Network(), data_dir, options.demo)
    url = f'http://127.0.0.1:{server.server_port}/#{server.token}'
    print(localize(message('app_name'), options.lang) + (' — ' + localize(message('cli_demo'), options.lang) if options.demo else ''))
    print(localize(message('cli_exit_hint'), options.lang))
    print(url, flush=True)
    if not options.no_browser:
        webbrowser.open(url)

    def request_stop(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        restored = server.controller.close()
        server.server_close()
        session_file.unlink(missing_ok=True)
        if not restored:
            logging.error('Restoration incomplete. Recovery journal retained.')
            print(localize(message('cli_restore_pending'), options.lang))


if __name__ == '__main__':
    main()
