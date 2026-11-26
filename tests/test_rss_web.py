"""Exercise RSS pages and form handling against the installed ASGI stack."""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.db_operations import DBOperations
from models.models import Base
from rss.app.routes import auth, rss
from rss.main import app


class RSSWebTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine)
        operations = DBOperations()
        for module in (auth, rss):
            for name, value in (('get_session', sessions), ('db_ops', operations)):
                patcher = patch.object(module, name, value)
                patcher.start()
                self.addCleanup(patcher.stop)
        self.client = TestClient(app, follow_redirects=False)
        self.addCleanup(self.client.close)

    def register(self):
        return self.client.post('/register', data={
            'username': 'reader',
            'password': 'test-password',
            'confirm_password': 'test-password',
        })

    def test_first_run_renders_registration_and_redirects_login(self):
        response = self.client.get('/register')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template.name, 'register.html')
        self.assertIn('request', response.context)
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['location'], '/register')

    def test_registration_password_mismatch_renders_error(self):
        response = self.client.post('/register', data={
            'username': 'reader', 'password': 'one', 'confirm_password': 'two',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.template.name, 'register.html')
        self.assertIn('两次输入的密码不一致', response.text)

    def test_failed_registration_renders_error(self):
        with patch.object(auth.db_ops, 'create_user', AsyncMock(return_value=None)):
            response = self.register()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.template.name, 'register.html')
        self.assertIn('创建用户失败', response.text)

    def test_failed_login_renders_error(self):
        self.assertEqual(self.register().status_code, 302)
        self.client.cookies.clear()
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template.name, 'login.html')
        response = self.client.post('/login', data={
            'username': 'reader', 'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.template.name, 'login.html')
        self.assertIn('用户名或密码错误', response.text)

    def test_registration_login_dashboard_and_logout(self):
        response = self.client.get('/rss/dashboard')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['location'], '/login')
        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('access_token', self.client.cookies)
        self.client.cookies.clear()
        response = self.client.post('/login', data={
            'username': 'reader', 'password': 'test-password',
        })
        self.assertEqual(response.status_code, 302)
        response = self.client.get('/')
        self.assertEqual(response.headers['location'], '/rss/dashboard')
        response = self.client.get('/rss/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template.name, 'rss_dashboard.html')
        self.assertEqual(response.context['user'].username, 'reader')
        self.assertEqual(response.context['rss_configs'], [])
        self.assertEqual(response.context['rules'], [])
        response = self.client.get('/logout')
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('access_token', self.client.cookies)
        self.assertEqual(self.client.get('/rss/dashboard').headers['location'], '/login')


if __name__ == '__main__':
    unittest.main()
