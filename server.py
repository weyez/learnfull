import os, sys, ssl, socket, ipaddress, http.client, urllib.parse, time, threading, collections, hashlib, hmac, secrets, html, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent / 'public'
KEY = os.environ.get('ACCESS_KEY', '')
PORT = int(os.environ.get('PORT', '8080'))
LIMIT = 3 * 1024 * 1024
SLOTS = threading.BoundedSemaphore(4)
RATE = collections.defaultdict(collections.deque)
LOCK = threading.Lock()
ALLOWED_TAGS = set('html head body title p br hr h1 h2 h3 h4 h5 h6 a img ul ol li dl dt dd blockquote pre code strong b em i u s del table thead tbody tfoot tr th td caption div span section article main header footer nav figure figcaption details summary time sup sub'.split())
READER_CSS = 'body{font:17px/1.65 system-ui,sans-serif;color:#2c2c2b;background:#fff;max-width:850px;margin:auto;padding:24px}a{color:#1668ac}img{max-width:100%;height:auto}pre,table{display:block;max-width:100%;overflow:auto}pre{background:#f4f4f4;padding:16px}th,td{padding:8px;border:1px solid #ddd}blockquote{border-left:3px solid #ddd;margin-left:0;padding-left:20px}.notice{font-size:14px;color:#595650;background:#f5f4f2;padding:12px;margin-bottom:24px;border-radius:8px}h1,h2,h3{line-height:1.25}'

def target_url(value):
    if len(value) > 4096: raise ValueError('Слишком длинный адрес.')
    try:
        p = urllib.parse.urlsplit(value)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            raise ValueError('Нужен адрес HTTP или HTTPS без логина и пароля.')
        port = p.port or (443 if p.scheme == 'https' else 80)
        if port != (443 if p.scheme == 'https' else 80): raise ValueError('Поддерживаются только стандартные порты 80 и 443.')
        host = p.hostname.encode('idna').decode('ascii')
        if any(c.isspace() for c in value) or any(ord(c) < 32 for c in value): raise ValueError('Некорректный адрес.')
        ips = [entry[4][0] for entry in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('Локальные, служебные и внутренние адреса запрещены.')
        return p, host, port, ips[0]
    except (UnicodeError, socket.gaierror): raise ValueError('Не удалось найти сервер сайта.')

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, ip):
        super().__init__(host, port, timeout=12, context=ssl.create_default_context())
        self.ip = ip
    def connect(self):
        self.sock = self._context.wrap_socket(socket.create_connection((self.ip, self.port), self.timeout), server_hostname=self.host)

def fetch(url):
    # DNS is validated on every redirect; connection uses the validated IP, not a second DNS lookup.
    for _ in range(6):
        p, host, port, ip = target_url(url)
        conn = PinnedHTTPS(host, port, ip) if p.scheme == 'https' else http.client.HTTPConnection(ip, port, timeout=12)
        authority = f'[{host}]' if ':' in host else host
        path = urllib.parse.quote(p.path or '/', safe="/%:@!$&'()*+,;=-._~")
        if p.query: path += '?' + urllib.parse.quote(p.query, safe="%/?@:!$&'()*+,;=-._~")
        try:
            conn.request('GET', path, headers={'Host': authority, 'User-Agent': 'WindowReader/1.0', 'Accept-Encoding': 'identity', 'Accept': 'text/html,text/plain,image/png,image/jpeg,image/webp,image/gif,image/avif'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location: raise ValueError('Сайт вернул пустое перенаправление.')
                url = urllib.parse.urljoin(url, location)
                continue
            if response.status >= 400: raise ValueError(f'Сайт ответил ошибкой {response.status}. Возможно, он не разрешает прокси.')
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity': raise ValueError('Сайт использует неподдерживаемое сжатие.')
            declared = response.getheader('Content-Length')
            if declared and int(declared) > LIMIT: raise ValueError('Страница или файл больше 3 МБ.')
            data = response.read(LIMIT + 1)
            if len(data) > LIMIT: raise ValueError('Страница или файл больше 3 МБ.')
            return data, response.getheader('Content-Type', 'application/octet-stream'), url
        finally: conn.close()
    raise ValueError('Слишком много перенаправлений.')

def rewrite(value, base, route):
    resolved = urllib.parse.urljoin(base, value)
    p = urllib.parse.urlsplit(resolved)
    if p.scheme not in ('http', 'https'): return None
    return route + '?url=' + urllib.parse.quote(resolved, safe='')

def reader(data, content_type, final_url):
    if content_type.split(';')[0].strip().lower() == 'text/plain':
        content = '<pre>' + html.escape(data.decode('utf-8', 'replace')) + '</pre>'
    else:
        soup = BeautifulSoup(data, 'html.parser')
        base = final_url
        base_tag = soup.find('base', href=True)
        if base_tag:
            candidate = urllib.parse.urljoin(final_url, base_tag['href'])
            if urllib.parse.urlsplit(candidate).scheme in ('http', 'https'): base = candidate
        for t in list(soup.find_all(['script','style','iframe','object','embed','svg','math','link','meta','base','template','noscript','input','button','textarea','select'])): t.decompose()
        for t in list(soup.find_all(True)):
            if t.name not in ALLOWED_TAGS:
                t.unwrap(); continue
            original = dict(t.attrs); t.attrs = {}
            if t.name == 'a':
                href = rewrite(original.get('href', ''), base, '/view') if original.get('href') else None
                if href: t['href'] = href
            elif t.name == 'img':
                src = rewrite(original.get('src', ''), base, '/asset') if original.get('src') else None
                if src: t['src'] = src; t['loading'] = 'lazy'
                t['alt'] = str(original.get('alt', ''))[:500]
            elif t.name in ('th','td'):
                for attr in ('colspan','rowspan'):
                    value = str(original.get(attr, ''))
                    if value.isdecimal() and 0 < int(value) <= 100: t[attr] = value
        content = ''.join(str(x) for x in (soup.body.contents if soup.body else soup.contents))
    safe_url = html.escape(final_url)
    return f'<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{READER_CSS}</style><body><div class="notice">Режим чтения · {safe_url}<br>Скрипты, формы, вход в аккаунты и видео отключены.</div>{content}</body></html>'.encode()

def session_value():
    exp = str(int(time.time()) + 8 * 3600)
    return exp + '.' + hmac.new(KEY.encode(), exp.encode(), hashlib.sha256).hexdigest()

def valid_cookie(cookie):
    from http.cookies import SimpleCookie
    try:
        c = SimpleCookie(cookie); token = c['window_session'].value
        exp, signature = token.split('.')
        expected = hmac.new(KEY.encode(), exp.encode(), hashlib.sha256).hexdigest()
        return time.time() < int(exp) <= time.time() + 8*3600 and hmac.compare_digest(signature, expected)
    except Exception: return False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass  # Never log destination URLs, keys, or content.
    def send(self, status, data, kind='text/html; charset=utf-8', cookie=None, reader_page=False):
        self.send_response(status)
        self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer'); self.send_header('X-Frame-Options','SAMEORIGIN')
        csp = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'; sandbox allow-same-origin" if reader_page else "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        self.send_header('Content-Security-Policy', csp)
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        if cookie: self.send_header('Set-Cookie', cookie)
        self.end_headers(); self.wfile.write(data)
    def error(self, status, message):
        self.send(status, f'<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{READER_CSS}</style><body><h2>Не удалось открыть страницу</h2><p>{html.escape(message)}</p><p>Попробуйте обычную текстовую страницу. Приложения со скриптами не поддерживаются.</p></body></html>'.encode(), reader_page=True)
    def allowed(self):
        now = time.monotonic()
        with LOCK:
            # Fixed global budget prevents unbounded per-client state behind hosting proxies.
            queue = RATE['global']
            while queue and now - queue[0] > 60: queue.popleft()
            if len(queue) >= 180: return False
            queue.append(now); return True
    def authenticated(self): return valid_cookie(self.headers.get('Cookie',''))
    def do_GET(self):
        p = urllib.parse.urlsplit(self.path)
        if p.path in ('/', '/app.js', '/style.css'):
            name = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[p.path]
            mime = {'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]
            return self.send(200, (ROOT/name).read_bytes(), mime)
        if p.path == '/health': return self.send(200,b'ok','text/plain')
        if p.path == '/session': return self.send(200 if self.authenticated() else 401,b'{}','application/json')
        if p.path not in ('/view','/asset'): return self.error(404,'Страница не найдена.')
        if not self.authenticated(): return self.error(401,'Введите ключ доступа на главной странице.')
        if not self.allowed(): return self.error(429,'Слишком много запросов. Подождите минуту.')
        if not SLOTS.acquire(blocking=False): return self.error(503,'Сервер занят. Повторите позже.')
        try:
            url = urllib.parse.parse_qs(p.query).get('url',[''])[0]
            data, kind, final_url = fetch(url)
            mime = kind.split(';')[0].strip().lower()
            if p.path == '/asset':
                if mime not in ('image/png','image/jpeg','image/gif','image/webp','image/avif'): raise ValueError('Этот тип изображения не поддерживается.')
                self.send(200,data,mime)
            elif mime in ('text/html','application/xhtml+xml','text/plain'):
                self.send(200,reader(data,kind,final_url),reader_page=True)
            else: raise ValueError('Поддерживаются HTML и текстовые страницы, но не загрузки, PDF или видео.')
        except ValueError as e: self.error(400,str(e))
        except (OSError, http.client.HTTPException): self.error(502,'Сайт недоступен, соединение прервано или время ожидания истекло.')
        except Exception: self.error(502,'Не удалось обработать ответ сайта.')
        finally: SLOTS.release()
    def do_POST(self):
        if self.path not in ('/login','/logout'): return self.error(404,'Страница не найдена.')
        origin = self.headers.get('Origin')
        if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get('Host'): return self.error(403,'Недопустимый источник запроса.')
        if not self.allowed(): return self.error(429,'Подождите минуту.')
        if self.path == '/logout': return self.send(200,b'{}','application/json','window_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict')
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 1024: return self.error(400,'Некорректный запрос.')
            self.connection.settimeout(10)
            supplied = urllib.parse.parse_qs(self.rfile.read(size).decode()).get('key',[''])[0]
            if not hmac.compare_digest(supplied.encode(),KEY.encode()): return self.send(401,b'{}','application/json')
            secure = '; Secure' if os.environ.get('COOKIE_SECURE','1') == '1' else ''
            cookie = f'window_session={session_value()}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800{secure}'
            self.send(200,b'{}','application/json',cookie)
        except Exception: self.error(400,'Некорректный запрос.')

if __name__ == '__main__':
    if len(KEY) < 16:
        sys.exit('Set ACCESS_KEY to a secret of at least 16 characters. See README.md.')
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    server.daemon_threads = True
    print(f'Window reader listening on port {PORT}', flush=True)
    server.serve_forever()
