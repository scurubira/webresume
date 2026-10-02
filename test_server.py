import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock
import server


class FlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        server.DATA = Path(cls.temp.name)
        server.init_db()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def upload(self, email=''):
        status, _, body = self.request('POST', '/api/cvs', b'%PDF-1.4\nSample test\n%%EOF', {'X-CV-Name': 'Test', 'X-Owner-Email': email})
        self.assertEqual(status, 201)
        return json.loads(body)

    def owner_data(self, cv):
        status, _, body = self.request('GET', '/api/cvs/' + cv['slug'], headers={'Authorization': 'Bearer ' + cv['owner_token']})
        self.assertEqual(status, 200)
        return json.loads(body)

    def test_full_upload_and_access_flow(self):
        cv = self.upload()
        self.assertEqual(self.owner_data(cv)['count'], 0)
        self.assertEqual(self.request('GET', '/c/' + cv['slug'])[0], 200)
        self.assertEqual(self.request('HEAD', '/file/' + cv['slug'])[0], 200)
        self.assertEqual(self.owner_data(cv)['count'], 0)
        status, headers, body = self.request('GET', '/file/' + cv['slug'])
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b'%PDF-'))
        data = self.owner_data(cv)
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['events'][0]['mail_status'], 'disabled')
        cookie = headers['Set-Cookie'].split(';')[0]
        self.request('GET', '/file/' + cv['slug'], headers={'Cookie': cookie})
        self.assertEqual(self.owner_data(cv)['count'], 1)
        self.request('GET', '/file/' + cv['slug'])
        self.assertEqual(self.owner_data(cv)['count'], 2)

    def test_panel_requires_private_key(self):
        cv = self.upload()
        self.assertEqual(self.request('GET', '/api/cvs/' + cv['slug'])[0], 403)
        self.assertEqual(self.request('GET', '/data/cv.sqlite3')[0], 404)
        with server.db() as connection:
            value = connection.execute('SELECT owner_hash FROM cvs WHERE slug=?', (cv['slug'],)).fetchone()[0]
        self.assertEqual(value, hashlib.sha256(cv['owner_token'].encode()).hexdigest())

    def test_reject_invalid_pdf_and_email(self):
        self.assertEqual(self.request('POST', '/api/cvs', b'not a pdf')[0], 400)
        self.assertEqual(self.request('POST', '/api/cvs', b'%PDF-1.4\n%%EOF', {'X-Owner-Email': 'invalid'})[0], 400)
        self.assertEqual(self.request('POST', '/api/cvs', b'', {'Content-Length': str(server.MAX_UPLOAD + 1)})[0], 413)

    def test_mail_success_and_failure_status(self):
        cv = self.upload('owner@example.com')
        self.request('GET', '/file/' + cv['slug'])
        event_id = self.owner_data(cv)['events'][0]['id']
        smtp = MagicMock()
        with patch.dict(server.os.environ, {'SMTP_HOST': 'smtp.example.com', 'SMTP_FROM': 'sender@example.com'}), patch('server.smtplib.SMTP', return_value=smtp):
            server.send_notification(event_id, 'owner@example.com', 'Test')
        smtp.__enter__.return_value.send_message.assert_called_once()
        self.assertEqual(self.owner_data(cv)['events'][0]['mail_status'], 'sent')
        with patch.dict(server.os.environ, {'SMTP_HOST': 'smtp.example.com', 'SMTP_FROM': 'sender@example.com'}), patch('server.smtplib.SMTP', side_effect=OSError):
            server.send_notification(event_id, 'owner@example.com', 'Test')
        self.assertEqual(self.owner_data(cv)['events'][0]['mail_status'], 'failed')


if __name__ == '__main__':
    unittest.main()
