"""CV link server: Python 3.12+, no third-party dependencies."""
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
import zipfile

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CV_DATA_DIR', ROOT / 'data'))
MAX_UPLOAD = 10 * 1024 * 1024


def db():
    connection = sqlite3.connect(DATA / 'cv.sqlite3', timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'uploads').mkdir(exist_ok=True)
    with db() as connection:
        connection.executescript('''
        CREATE TABLE IF NOT EXISTS cvs (
            slug TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, name TEXT NOT NULL,
            email TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, slug TEXT NOT NULL, visited REAL NOT NULL,
            visitor_hash TEXT NOT NULL, mail_status TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS events_slug ON events(slug, visited);
        ''')


def mail_enabled():
    return bool(os.environ.get('SMTP_HOST') and os.environ.get('SMTP_FROM'))


def send_notification(event_id, recipient, name):
    status = 'sent'
    try:
        message = EmailMessage()
        message['Subject'] = 'Seu currículo foi acessado'
        message['From'] = os.environ['SMTP_FROM']
        message['To'] = recipient
        message.set_content(f'O PDF do seu currículo "{name}" foi acessado.\n\nEste registro indica uma abertura do arquivo, não confirma a leitura por uma pessoa.\nConsulte o histórico no seu painel CV Link.')
        with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT', '587')), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.environ.get('SMTP_USER'):
                smtp.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
            smtp.send_message(message)
    except Exception:
        status = 'failed'
    with db() as connection:
        connection.execute('UPDATE events SET mail_status=? WHERE id=?', (status, event_id))


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass  # Public links and owner tokens do not belong in logs.

    def respond(self, status, body, content_type='application/json; charset=utf-8', headers=None):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def error(self, status, message):
        self.respond(status, {'error': message})

    def public_origin(self):
        configured = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
        if configured:
            return configured
        # In development only, constrain the host used to construct links.
        host = self.headers.get('Host', 'localhost:8000')
        if not re.fullmatch(r'(localhost|127\.0\.0\.1)(:\d{1,5})?', host):
            host = 'localhost:8000'
        return 'http://' + host

    def read_body(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_UPLOAD:
            return None
        return self.rfile.read(length)

    def render_docx(self, data, template):
        from xml.sax.saxutils import escape

        def esc(text):
            return escape(str(text or ''))

        def paragraphs(text):
            return ''.join(f'<w:p><w:r><w:t>{esc(line)}</w:t></w:r></w:p>' for line in str(text or '').split('\n') if line.strip()) or '<w:p><w:r><w:t></w:t></w:r></w:p>'

        contact = ' · '.join(filter(None, [data.get('email', ''), data.get('phone', ''), data.get('location', '')]))
        summary = paragraphs(data.get('summary', ''))
        experience = data.get('experience', []) or []
        education = data.get('education', []) or []
        skills = data.get('skills', []) or []

        exp_blocks = []
        for item in experience:
            if not any(item.get(k) for k in item):
                continue
            date = ' – '.join(filter(None, [item.get('start', ''), item.get('end', '')]))
            exp_blocks.append(
                f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>{esc(item.get("role", ""))}</w:t></w:r>'
                f'<w:r><w:t xml:space="preserve">{(" — " + esc(item.get("company", ""))) if item.get("company") else ""}</w:t></w:r></w:p>'
                f'<w:p><w:r><w:t>{esc(date)}</w:t></w:r></w:p>'
                + paragraphs(item.get('description', ''))
            )
        edu_blocks = []
        for item in education:
            if not any(item.get(k) for k in item):
                continue
            date = ' – '.join(filter(None, [item.get('start', ''), item.get('end', '')]))
            edu_blocks.append(
                f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>{esc(item.get("course", ""))}</w:t></w:r>'
                f'<w:r><w:t xml:space="preserve">{(" — " + esc(item.get("institution", ""))) if item.get("institution") else ""}</w:t></w:r></w:p>'
                f'<w:p><w:r><w:t>{esc(date)}</w:t></w:r></w:p>'
            )

        accent = {'modern': '2E7D4A', 'minimal': '5A6B61', 'classic': '216854'}.get(template, '216854')
        accent_rgb = ','.join(str(int(accent[i:i+2], 16)) for i in (0, 2, 4))

        document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:rPr><w:color w:val="{esc(accent)}"/></w:rPr><w:t>{esc(data.get('name', 'Currículo'))}</w:t></w:r></w:p>
    <w:p><w:r><w:t>{esc(data.get('title', ''))}</w:t></w:r></w:p>
    <w:p><w:r><w:t>{esc(contact)}</w:t></w:r></w:p>
    {f"<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>Resumo</w:t></w:r></w:p>{summary}" if data.get('summary') else ""}
    {f"<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>Experiência profissional</w:t></w:r></w:p>{''.join(exp_blocks)}" if exp_blocks else ""}
    {f"<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>Formação</w:t></w:r></w:p>{''.join(edu_blocks)}" if edu_blocks else ""}
    {f"<w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>Habilidades</w:t></w:r></w:p><w:p><w:r><w:t>{esc(", ".join(s.get("name", "") for s in skills if s.get("name")))}</w:t></w:r></w:p>" if skills else ""}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="0" w:footer="0"/></w:sectPr>
  </w:body>
</w:document>'''

        styles_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:pPr><w:spacing w:after="120"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:sz w:val="40"/><w:color w:val="{esc(accent)}"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:pPr><w:spacing w:before="240" w:after="80"/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{esc(accent)}"/></w:pBdr></w:pPr><w:rPr><w:b/><w:sz w:val="24"/><w:color w:val="{esc(accent)}"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:pPr><w:spacing w:before="120" w:after="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
</w:styles>'''

        rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
        content_types_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('[Content_Types].xml', content_types_xml)
            zf.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')
            zf.writestr('word/_rels/document.xml.rels', rels_xml)
            zf.writestr('word/document.xml', document_xml)
            zf.writestr('word/styles.xml', styles_xml)
        buffer.seek(0)
        return buffer.read()

    def do_POST(self):
        if self.path == '/api/export/docx':
            body = self.read_body()
            if body is None:
                return self.error(413, 'Payload muito grande.')
            try:
                payload = json.loads(body.decode('utf-8'))
                data = payload.get('data', {})
                template = payload.get('template', 'classic')
                if not isinstance(data, dict) or not isinstance(template, str):
                    raise ValueError('Formato inválido.')
                if not data.get('name', '').strip():
                    return self.error(400, 'O nome completo é obrigatório.')
            except Exception:
                return self.error(400, 'JSON inválido.')
            docx = self.render_docx(data, template)
            return self.respond(200, docx, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', {'Content-Disposition': 'attachment; filename="curriculo.docx"'})
        if self.path != '/api/cvs':
            return self.error(404, 'Rota não encontrada.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.error(400, 'Tamanho de arquivo inválido.')
        if length <= 0 or length > MAX_UPLOAD:
            self.close_connection = True
            return self.error(413, 'Envie um PDF de até 10 MB.')
        name = unquote(self.headers.get('X-CV-Name', 'Currículo')).strip()[:120]
        email = unquote(self.headers.get('X-Owner-Email', '')).strip()
        if email and (len(email) > 254 or not re.fullmatch(r'[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+', email)):
            self.close_connection = True
            return self.error(400, 'Informe um e-mail válido.')
        body = self.rfile.read(length)
        if len(body) != length or not body.startswith(b'%PDF-') or b'%%EOF' not in body[-4096:]:
            return self.error(400, 'O arquivo precisa ser um PDF válido.')
        slug = secrets.token_urlsafe(6)
        owner_token = secrets.token_urlsafe(32)
        file_path = DATA / 'uploads' / (slug + '.pdf')
        file_path.write_bytes(body)
        with db() as connection:
            connection.execute('INSERT INTO cvs VALUES (?, ?, ?, ?, ?)', (slug, hashlib.sha256(owner_token.encode()).hexdigest(), name or 'Currículo', email, time.time()))
        self.respond(201, {'slug': slug, 'owner_token': owner_token, 'short_url': self.public_origin() + '/c/' + slug, 'name': name or 'Currículo', 'email_enabled': bool(email and mail_enabled())})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/config':
            return self.respond(200, {'email_available': mail_enabled(), 'max_upload': MAX_UPLOAD})
        if path in ('/', '/index.html', '/app.js', '/styles.css', '/builder.html', '/builder.js'):
            filename = 'index.html' if path == '/' else path.lstrip('/')
            mime = {
                'index.html': 'text/html; charset=utf-8',
                'app.js': 'text/javascript; charset=utf-8',
                'styles.css': 'text/css; charset=utf-8',
                'builder.html': 'text/html; charset=utf-8',
                'builder.js': 'text/javascript; charset=utf-8'
            }[filename]
            return self.respond(200, (ROOT / filename).read_bytes(), mime)
        match = re.fullmatch(r'/api/cvs/([A-Za-z0-9_-]{8})', path)
        if match:
            slug = match[1]
            with db() as connection:
                cv = connection.execute('SELECT * FROM cvs WHERE slug=?', (slug,)).fetchone()
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                if not cv or not secrets.compare_digest(cv['owner_hash'], hashlib.sha256(token.encode()).hexdigest()):
                    return self.error(403, 'Chave de acesso ao painel inválida.')
                events = [dict(row) for row in connection.execute('SELECT id, visited, mail_status FROM events WHERE slug=? ORDER BY id DESC LIMIT 100', (slug,))]
                count = connection.execute('SELECT COUNT(*) FROM events WHERE slug=?', (slug,)).fetchone()[0]
            return self.respond(200, {'name': cv['name'], 'short_url': self.public_origin() + '/c/' + slug, 'count': count, 'events': events, 'email_enabled': bool(cv['email'] and mail_enabled())})
        match = re.fullmatch(r'/(c|file)/([A-Za-z0-9_-]{8})', path)
        if match:
            route, slug = match.groups()
            with db() as connection:
                cv = connection.execute('SELECT * FROM cvs WHERE slug=?', (slug,)).fetchone()
            if not cv:
                return self.error(404, 'Currículo não encontrado.')
            if route == 'c':
                name = html.escape(cv['name'])
                return self.respond(200, f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{name} · CV Link</title><link rel="stylesheet" href="/styles.css"><body class="viewer"><header><a class="logo" href="/">▤ cv<span>link.</span></a><strong>{name}</strong><a class="button small" href="/file/{slug}">Abrir PDF ↗</a></header><p class="access-notice">A abertura deste PDF é registrada e pode notificar o proprietário.</p><iframe title="{name}" src="/file/{slug}"></iframe><p>Se a prévia não aparecer, use “Abrir PDF”.</p></body></html>''', 'text/html; charset=utf-8', {'X-Robots-Tag': 'noindex, nofollow', 'Content-Security-Policy': "default-src 'self'; style-src 'self'; frame-src 'self'; object-src 'self'"})
            file_path = DATA / 'uploads' / (slug + '.pdf')
            if not file_path.exists():
                return self.error(404, 'Arquivo indisponível.')
            headers = {'Content-Disposition': 'inline; filename="curriculo.pdf"', 'X-Robots-Tag': 'noindex, nofollow'}
            if self.command != 'HEAD':
                cookies = SimpleCookie()
                try:
                    cookies.load(self.headers.get('Cookie', ''))
                except Exception:
                    pass
                visitor = cookies['cv_visitor'].value if 'cv_visitor' in cookies else ''
                if not re.fullmatch(r'[A-Za-z0-9_-]{32}', visitor):
                    visitor = secrets.token_urlsafe(24)
                    secure = '; Secure' if self.public_origin().startswith('https://') else ''
                    headers['Set-Cookie'] = f'cv_visitor={visitor}; Path=/; Max-Age=86400; HttpOnly; SameSite=Lax{secure}'
                visitor_hash = hashlib.sha256(visitor.encode()).hexdigest()
                now = time.time()
                with db() as connection:
                    connection.execute('BEGIN IMMEDIATE')
                    recent = connection.execute('SELECT id FROM events WHERE slug=? AND visitor_hash=? AND visited>?', (slug, visitor_hash, now - 60)).fetchone()
                    if not recent:
                        status = 'pending' if cv['email'] and mail_enabled() else 'disabled'
                        event_id = connection.execute('INSERT INTO events(slug, visited, visitor_hash, mail_status) VALUES (?, ?, ?, ?)', (slug, now, visitor_hash, status)).lastrowid
                    else:
                        event_id = None
                if event_id and status == 'pending':
                    threading.Thread(target=send_notification, args=(event_id, cv['email'], cv['name']), daemon=True).start()
            return self.respond(200, file_path.read_bytes(), 'application/pdf', headers)
        self.error(404, 'Página não encontrada.')


if __name__ == '__main__':
    init_db()
    address = (os.environ.get('HOST', '127.0.0.1'), int(os.environ.get('PORT', '8000')))
    print(f'CV Link disponível em http://{address[0]}:{address[1]}', flush=True)
    ThreadingHTTPServer(address, Handler).serve_forever()
