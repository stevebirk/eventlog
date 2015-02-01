import unittest
import json
import mock

# NOTE: this mocks out Store, so import needs to before app
import util

from eventlog.service.application import app

from eventlog.service.core.store import store


class TestFeeds(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        # setup mock Feed
        feed_attrs = {'dict.return_value': {}}

        cls._feed = mock.Mock(**feed_attrs)

        # setup mock Store
        attrs = {'get_feeds.return_value': {'foo': cls._feed}}

        store.configure_mock(**attrs)

        # app config
        app.config['STATIC_URL'] = 'base_uri'
        app.config['AUTH_TOKEN_EXPIRY'] = 600
        app.config['SECRET_KEY'] = 'abcd'

    def setUp(self):
        self.app = app.test_client()

        self._feed.reset()

        store.reset()

    def test_get_all(self):
        rv = self.app.get('/feeds')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_feeds.assert_called_with(is_public=True)

    def test_get_all_admin_authorized(self):
        # get an auth token
        token_rv = self.app.get('/token')

        token = json.loads(token_rv.data)['data']['token']

        rv = self.app.get('/feeds?admin=true&access_token=' + token)

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_feeds.assert_called_with(is_public=None)

        self._feed.dict.assert_called_with(admin=True, base_uri='base_uri')

    def test_get_all_admin_authorized_bad_token(self):
        rv = self.app.get('/feeds?admin=true&access_token=1234')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_feeds.assert_called_with(is_public=True)

        self._feed.dict.assert_called_with(admin=None, base_uri='base_uri')

    def test_get_all_admin_unauthorized(self):
        rv = self.app.get('/feeds?admin=true')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_feeds.assert_called_with(is_public=True)

        self._feed.dict.assert_called_with(admin=None, base_uri='base_uri')

    def test_get_single(self):
        rv = self.app.get('/feeds/foo')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_feeds.assert_called_with(is_public=True)

        self._feed.dict.assert_called_with(admin=None, base_uri='base_uri')

    def test_get_single_admin_authorized(self):
        # get an auth token
        token_rv = self.app.get('/token')

        token = json.loads(token_rv.data)['data']['token']

        rv = self.app.get('/feeds/foo?admin=true&access_token=' + token)

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_feeds.assert_called_with(is_public=None)

        self._feed.dict.assert_called_with(admin=True, base_uri='base_uri')

    def test_get_single_admin_unauthorized(self):
        rv = self.app.get('/feeds/foo?admin=true')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_feeds.assert_called_with(is_public=True)

        self._feed.dict.assert_called_with(admin=None, base_uri='base_uri')

    def test_get_single_not_found(self):
        rv = self.app.get('/feeds/bar')

        self.assertEqual(rv.status_code, 404)

        util.verify_response(rv)

        store.get_feeds.assert_called_with(is_public=True)

if __name__ == '__main__':
    unittest.main()
