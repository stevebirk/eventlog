import unittest
import json
import datetime

import mock

# NOTE: this mocks out Store, so import needs to before app
import util

from eventlog.service.application import app

from eventlog.service.core.store import store


class TestEvents(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # app config
        app.config['STATIC_URL'] = 'base_uri'
        app.config['AUTH_TOKEN_EXPIRY'] = 600
        app.config['SECRET_KEY'] = 'abcd'
        app.config['PAGE_SIZE_DEFAULT'] = 10
        app.config['PAGE_SIZE_MAX'] = 100

    def setUp(self):
        # setup mock Feed
        feed_dict = {
            'short_name': 'bar'
        }

        feed_attrs = {
            'dict.return_value': {},
            '__getitem__': lambda x, y: feed_dict[y]
        }

        self._bar_feed = mock.Mock(**feed_attrs)
        self._foo_feed = mock.Mock(**feed_attrs)
        self._jazz_feed = mock.Mock(**feed_attrs)
        self._bazz_feed = mock.Mock(**feed_attrs)

        # setup mock Page
        page_attrs = {'events': [], 'next': True, 'prev': True}

        self._page = mock.Mock(**page_attrs)

        # setup mock EventSet
        event_set_attrs = {'get_page.return_value': self._page}

        self._event_set = mock.Mock(**event_set_attrs)

        # setup mock Store
        attrs = {
            'get_events.return_value': self._event_set,
            'get_feeds.return_value': {
                'foo': self._foo_feed,
                'bar': self._bar_feed,
                'jazz': self._jazz_feed
            },
            'get_feeds.side_effect': None,
            'get_events_by_timerange.return_value': self._event_set,
            'get_events_by_date.return_value': self._event_set,
            'get_events_by_ids.return_value': self._event_set,
            'get_events_by_search.return_value': self._event_set
        }

        store.configure_mock(**attrs)

        self._all_feeds = {
            'foo': self._foo_feed,
            'bar': self._bar_feed,
            'jazz': self._jazz_feed
        }

        app.debug = False
        self.app = app.test_client()

    def test_get_all(self):
        rv = self.app.get('/events')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events.assert_called_with(
            feeds=self._all_feeds,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.get_page.assert_called_with(1)

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)
        self.assertIn("pagination", resp_data)
        self.assertIn("next", resp_data["pagination"])
        self.assertIn("prev", resp_data["pagination"])

    def test_get_all_with_invalid_page(self):
        self._event_set.get_page.return_value = None
        self._event_set.num_pages = 1

        rv = self.app.get('/events?page=2')

        self.assertEqual(rv.status_code, 400)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_all_with_timezone(self):
        rv = self.app.get('/events?tz=America/Toronto')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events.assert_called_with(
            feeds=self._all_feeds,
            pagesize=10,
            embed_related=True,
            timezone="America/Toronto"
        )

        self._event_set.get_page.assert_called_with(1)

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)
        self.assertIn("pagination", resp_data)
        self.assertIn("next", resp_data["pagination"])
        self.assertIn("prev", resp_data["pagination"])

    def test_get_all_with_invalid_timezone(self):
        rv = self.app.get('/events?tz=boo')

        self.assertEqual(rv.status_code, 400)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_all_with_limit(self):
        rv = self.app.get('/events?limit=20')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events.assert_called_with(
            feeds=self._all_feeds,
            pagesize=20,
            embed_related=True,
            timezone=None
        )

        self._event_set.get_page.assert_called_with(1)

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)
        self.assertIn("pagination", resp_data)
        self.assertIn("next", resp_data["pagination"])
        self.assertIn("prev", resp_data["pagination"])

    def test_get_all_with_invalid_limit(self):
        rv = self.app.get('/events?limit=9999')

        self.assertEqual(rv.status_code, 400)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_all_with_after(self):

        datestr = '2014-01-01 12:01:01.00'

        dt = datetime.datetime.strptime(datestr, '%Y-%m-%d %H:%M:%S.%f')

        rv = self.app.get('/events?after=' + datestr)

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events_by_timerange.assert_called_with(
            start=dt,
            feeds=self._all_feeds,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.get_page.assert_called_with(1)

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)
        self.assertIn("pagination", resp_data)
        self.assertIn("next", resp_data["pagination"])
        self.assertIn("prev", resp_data["pagination"])

    def test_get_all_with_invalid_after(self):

        datestr = 'abz'

        rv = self.app.get('/events?after=' + datestr)

        self.assertEqual(rv.status_code, 400)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_all_with_before(self):

        datestr = '2014-01-01 12:01:01.00'

        dt = datetime.datetime.strptime(datestr, '%Y-%m-%d %H:%M:%S.%f')

        rv = self.app.get('/events?before=' + datestr)

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events_by_timerange.assert_called_with(
            end=dt,
            feeds=self._all_feeds,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.get_page.assert_called_with(1)

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)
        self.assertIn("pagination", resp_data)
        self.assertIn("next", resp_data["pagination"])
        self.assertIn("prev", resp_data["pagination"])

    def test_get_all_with_after_and_before(self):

        after_datestr = '2014-01-01 12:01:01.00'
        before_datestr = '2014-02-01 12:01:01.00'

        after_dt = datetime.datetime.strptime(
            after_datestr, '%Y-%m-%d %H:%M:%S.%f'
        )

        before_dt = datetime.datetime.strptime(
            before_datestr, '%Y-%m-%d %H:%M:%S.%f'
        )

        rv = self.app.get(
            '/events?after=' + after_datestr + '&before=' + before_datestr
        )

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events_by_timerange.assert_called_with(
            start=after_dt,
            end=before_dt,
            feeds=self._all_feeds,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.get_page.assert_called_with(1)

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)
        self.assertIn("pagination", resp_data)
        self.assertIn("next", resp_data["pagination"])
        self.assertIn("prev", resp_data["pagination"])

    def test_get_all_with_inconsistent_after_and_before(self):

        before_datestr = '2014-01-01 12:01:01.00'
        after_datestr = '2014-02-01 12:01:01.00'

        after_dt = datetime.datetime.strptime(
            after_datestr, '%Y-%m-%d %H:%M:%S.%f'
        )

        before_dt = datetime.datetime.strptime(
            before_datestr, '%Y-%m-%d %H:%M:%S.%f'
        )

        rv = self.app.get(
            '/events?after=' + after_datestr + '&before=' + before_datestr
        )

        self.assertEqual(rv.status_code, 400)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_all_with_on(self):

        datestr = '2014-01-01'

        dt = datetime.datetime.strptime(datestr, '%Y-%m-%d')

        rv = self.app.get('/events?on=' + datestr)

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events_by_date.assert_called_with(
            dt,
            feeds=self._all_feeds,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.get_page.assert_called_with(1)

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)
        self.assertIn("pagination", resp_data)
        self.assertIn("next", resp_data["pagination"])
        self.assertIn("prev", resp_data["pagination"])

    def test_get_all_with_invalid_on(self):

        datestr = 'abcd'

        rv = self.app.get('/events?on=' + datestr)

        self.assertEqual(rv.status_code, 400)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_all_with_malformed_feeds(self):

        rv = self.app.get('/events?feeds=')

        self.assertEqual(rv.status_code, 400)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_all_with_feeds(self):

        rv = self.app.get('/events?feeds=foo,bar')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events.assert_called_with(
            feeds=['foo', 'bar'],
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)
        self.assertIn("pagination", resp_data)
        self.assertIn("next", resp_data["pagination"])
        self.assertIn("prev", resp_data["pagination"])

    def test_get_all_with_invalid_feeds(self):

        rv = self.app.get('/events?feeds=blu')

        self.assertEqual(rv.status_code, 400)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_all_with_search(self):

        query = 'bar'

        rv = self.app.get('/events?q=' + query)

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events_by_search.assert_called_with(
            query,
            to_mask=None,
            to_filter=[],
            pagesize=10,
            timezone=None
        )

        resp_data = json.loads(rv.data)

    def test_get_all_with_search_with_unsearchable_feeds(self):

        self._all_feeds.update({
            'bazz': self._bazz_feed
        })

        def side_effect(*args, **kwargs):
            if 'is_searchable' in kwargs:
                if kwargs['is_searchable'] is False:
                    return {
                        'bar': self._bar_feed,
                        'foo': self._foo_feed
                    }
            else:
                return self._all_feeds

        store.get_feeds.side_effect = side_effect

        query = 'bar'

        rv = self.app.get('/events?feeds=jazz,bazz&q=' + query)

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events_by_search.assert_called_with(
            query,
            to_mask=['foo', 'bar'],
            to_filter=None,
            pagesize=10,
            timezone=None
        )

        resp_data = json.loads(rv.data)

    def test_get_single(self):

        def iterable(obj):
            event_attrs = {'dict.return_value': {}}

            yield mock.Mock(feed=self._bar_feed, **event_attrs)

        self._event_set.count = 1
        self._event_set.__iter__ = iterable

        rv = self.app.get('/events/1')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events_by_ids.assert_called_with(
            ['1'],
            timezone=None
        )

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)

    def test_get_single_invalid_id(self):
        self._event_set.count = 0

        rv = self.app.get('/events/1')

        self.assertEqual(rv.status_code, 404)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

    def test_get_single_with_timezone(self):

        def iterable(obj):
            event_attrs = {'dict.return_value': {}}

            yield mock.Mock(feed=self._bar_feed, **event_attrs)

        self._event_set.count = 1
        self._event_set.__iter__ = iterable

        rv = self.app.get('/events/1?tz=America/Toronto')

        self.assertEqual(rv.status_code, 200)

        util.verify_response(rv)

        store.get_events_by_ids.assert_called_with(
            ['1'],
            timezone="America/Toronto"
        )

        resp_data = json.loads(rv.data)

        self.assertIn("data", resp_data)

    def test_get_all_unexpected_exception(self):

        def side_effect(*args, **kwargs):
            raise Exception("uh oh!")

        store.get_feeds.side_effect = side_effect

        rv = self.app.get('/events')

        self.assertEqual(rv.status_code, 500)

        util.verify_response(rv)

        resp_data = json.loads(rv.data)

        self.assertIn("meta", resp_data)
        self.assertIn("code", resp_data['meta'])
        self.assertIn("error_type", resp_data['meta'])
        self.assertIn("error_message", resp_data['meta'])
