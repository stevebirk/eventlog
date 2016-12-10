import unittest
import unittest.mock
import os
import json

# NOTE: this mocks out Store, so import needs to before app
import util

from eventlog.service.application import app

from eventlog.service.core.store import store

from eventlog.service.util import DEFAULT_CONFIG_FILE, init_config


class TestCommon(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        # setup mock Feed
        feed_attrs = {'dict.return_value': {}}

        cls._feed = unittest.mock.Mock(**feed_attrs)

        # setup mock Store
        attrs = {'get_feeds.return_value': {'foo': cls._feed}}

        store.configure_mock(**attrs)

        # app config
        app.config['STATIC_URL'] = 'base_uri'
        app.config['AUTH_TOKEN_EXPIRY'] = 600
        app.config['SECRET_KEY'] = 'abcd'

        # get EVENTLOG_SETTINGS value
        cls._settings = os.getenv('EVENTLOG_SETTINGS')

    def setUp(self):

        if self._settings:
            os.environ['EVENTLOG_SETTINGS'] = self._settings

        self.app = app.test_client()

        self._feed.reset()

        store.reset()

    def test_load_default_config(self):
        app = unittest.mock.Mock()

        # unset EVENTLOG_SETTINGS
        del os.environ['EVENTLOG_SETTINGS']
        init_config(app)

        app.config.from_pyfile.assert_called_with(DEFAULT_CONFIG_FILE)

    def test_invalid_method(self):
        rv = self.app.post('/feeds')

        self.assertEqual(rv.status_code, 405)

        util.verify_headers(rv)

        resp_data = json.loads(rv.data.decode('utf-8'))

        self.assertIn("meta", resp_data)
        self.assertIn("code", resp_data['meta'])
        self.assertIn("error_type", resp_data['meta'])
        self.assertIn("error_message", resp_data['meta'])

    def test_not_found(self):
        rv = self.app.post('/fewoaij')

        self.assertEqual(rv.status_code, 404)

        util.verify_headers(rv)

        resp_data = json.loads(rv.data.decode('utf-8'))

        self.assertIn("meta", resp_data)
        self.assertIn("code", resp_data['meta'])
        self.assertIn("error_type", resp_data['meta'])
        self.assertIn("error_message", resp_data['meta'])

    def test_not_found_with_close_match(self):
        rv = self.app.post('/fee')

        self.assertEqual(rv.status_code, 404)

        util.verify_headers(rv)

        resp_data = json.loads(rv.data.decode('utf-8'))

        self.assertIn("meta", resp_data)
        self.assertIn("code", resp_data['meta'])
        self.assertIn("error_type", resp_data['meta'])
        self.assertIn("error_message", resp_data['meta'])

    def test_propagated_exception(self):

        def side_effect(*args, **kwargs):
            raise Exception("uh oh!")

        store.get_feeds.side_effect = side_effect

        self.assertRaises(Exception, self.app.get, '/events')
