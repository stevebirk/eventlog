import unittest
import unittest.mock

# NOTE: this mocks out Store, so import needs to before app
import util

from eventlog.service.application import app

from eventlog.service.core.store import store


class TestFeeds(unittest.TestCase):

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

        # required to get proper 500 errors.
        app.debug = False

    def setUp(self):
        self.app = app.test_client()

        self._feed.reset_mock()

        store.reset_mock()

    def prepare_auth_header(self):
        resp = self.app.get('/token')

        return {'Authorization': 'Bearer ' + resp.get_json()['data']['token']}

    def test_get_all(self):
        rv = self.app.get('/feeds')

        self.assertEqual(rv.status_code, 200)

        util.verify_headers(rv)

        store.get_feeds.assert_called_with(is_public=True)

    def test_get_all_admin_authorized(self):
        rv = self.app.get(
            '/feeds?admin=true',
            headers=self.prepare_auth_header()
        )

        self.assertEqual(rv.status_code, 200)

        util.verify_headers(rv)

        store.get_feeds.assert_called_with(is_public=None)

        self._feed.dict.assert_called_with(admin=True, base_uri='base_uri')

    def test_get_all_admin_authorized_bad_token(self):
        rv = self.app.get(
            '/feeds?admin=true',
            headers={'Authorization': 'Bearer 1234'}
        )

        self.assertEqual(rv.status_code, 200)

        util.verify_headers(rv)

        store.get_feeds.assert_called_with(is_public=True)

        self._feed.dict.assert_called_with(admin=None, base_uri='base_uri')

    def test_get_all_admin_unauthorized(self):
        rv = self.app.get('/feeds?admin=true')

        self.assertEqual(rv.status_code, 200)

        util.verify_headers(rv)

        store.get_feeds.assert_called_with(is_public=True)

        self._feed.dict.assert_called_with(admin=None, base_uri='base_uri')

    def test_get_single(self):
        rv = self.app.get('/feeds/foo')

        self.assertEqual(rv.status_code, 200)

        util.verify_headers(rv)

        store.get_feeds.assert_called_with(is_public=True)

        self._feed.dict.assert_called_with(admin=None, base_uri='base_uri')

    def test_get_single_admin_authorized(self):
        rv = self.app.get(
            '/feeds/foo?admin=true',
            headers=self.prepare_auth_header()
        )

        self.assertEqual(rv.status_code, 200)

        util.verify_headers(rv)

        store.get_feeds.assert_called_with(is_public=None)

        self._feed.dict.assert_called_with(admin=True, base_uri='base_uri')

    def test_get_single_admin_unauthorized(self):
        rv = self.app.get('/feeds/foo?admin=true')

        self.assertEqual(rv.status_code, 200)

        util.verify_headers(rv)

        store.get_feeds.assert_called_with(is_public=True)

        self._feed.dict.assert_called_with(admin=None, base_uri='base_uri')

    def test_get_single_not_found(self):
        rv = self.app.get('/feeds/bar')

        self.assertEqual(rv.status_code, 404)

        util.verify_headers(rv)

        store.get_feeds.assert_called_with(is_public=True)


if __name__ == '__main__':
    unittest.main()
