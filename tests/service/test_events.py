import unittest
import unittest.mock
import json
import datetime
import uuid
import urllib.parse

# NOTE: this mocks out Store, so import needs to be before app
import util

from eventlog.lib.store.pagination import (InvalidPage, ByTimeRangeCursor,
                                           BySearchCursor)

from eventlog.service.application import app

from eventlog.service.core.inputs import DATETIME_FMT
from eventlog.service.core.store import store

import eventlog.service.core.cursor


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
            '__getitem__': lambda x, y: feed_dict[y],
            'is_searchable': False,
            'is_public': True
        }

        self._bar_feed = unittest.mock.Mock(**feed_attrs)
        self._foo_feed = unittest.mock.Mock(**feed_attrs)
        self._jazz_feed = unittest.mock.Mock(**feed_attrs)
        self._bazz_feed = unittest.mock.Mock(**feed_attrs)

        # setup mock Page
        page_attrs = {
            'events': [],
            'next': None,
            '__iter__': unittest.mock.Mock(return_value=iter([]))
        }

        self._page = unittest.mock.Mock(**page_attrs)

        # setup mock EventSet
        event_set_attrs = {
            'page.return_value': self._page,
            'latest': None
        }

        self._event_set = unittest.mock.Mock(**event_set_attrs)

        # setup mock Store
        attrs = {
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

        self._all_feeds_names = list(self._all_feeds.keys())

        app.debug = False
        self.app = app.test_client()

    def verify_response(self, resp, code=200, pagination=None, data=None):
        util.verify_headers(resp)

        self.assertEqual(resp.status_code, code, resp.data)

        resp_data = json.loads(resp.data.decode('utf-8'))

        # meta is always expected
        self.assertIn("meta", resp_data)
        self.assertIn("code", resp_data["meta"])
        self.assertEqual(code, resp_data["meta"]["code"])

        if resp.status_code / 200 != 1:
            self.assertIn("error_type", resp_data["meta"])
            self.assertIn("error_message", resp_data["meta"])

        # extra checks around BadRequest response
        if resp.status_code == 400:
            self.assertEquals(resp_data["meta"]["error_type"], "BadRequest")
            self.assertIn("Invalid", resp_data["meta"]["error_message"])

        # data always expected
        self.assertIn("data", resp_data)

        if data is not None:
            self.assertEquals(data, resp_data["data"])

        if pagination is not None:
            self.assertIn("pagination", resp_data)

            expected_next = pagination.get("next")

            if expected_next is not None:
                self.assertIn("next", resp_data["pagination"])

                self.assertEquals(
                    urllib.parse.parse_qs(
                        urllib.parse.urlparse(expected_next).query
                    ),
                    urllib.parse.parse_qs(
                        urllib.parse.urlparse(
                            resp_data["pagination"]["next"]
                        ).query
                    )
                )
        else:
            self.assertNotIn("pagination", resp_data)

    def test_get_all(self):
        rv = self.app.get('/events')

        self.verify_response(rv, pagination={})

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=None,
            feeds=self._all_feeds_names,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_next(self):
        self._page.next = ByTimeRangeCursor(
            datetime.datetime.utcnow(),
            str(uuid.uuid4())
        )

        expected_next = (
            "/events?limit=10&embed_related=full&cursor=%s" % (
                eventlog.service.core.cursor.serialize(self._page.next)
            )
        )

        rv = self.app.get('/events')

        self.verify_response(
            rv,
            pagination={"next": expected_next}
        )

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=None,
            feeds=self._all_feeds_names,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_search_and_next(self):
        page = 2
        query = "test"

        latest = datetime.datetime.utcnow()

        self._page.next = BySearchCursor(page)

        self._event_set.latest = latest

        before = latest + datetime.timedelta(microseconds=1)

        expected_next = (
            "/events?limit=10&embed_related=full&cursor=%s&before=%s&q=%s" % (
                eventlog.service.core.cursor.serialize(self._page.next),
                before.strftime(DATETIME_FMT),
                query
            )
        )

        rv = self.app.get('/events?q=' + query)

        self.verify_response(
            rv,
            pagination={"next": expected_next}
        )

        store.get_events_by_search.assert_called_with(
            query,
            to_mask=None,
            before=None,
            after=None,
            to_filter=[],
            pagesize=10,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_on_and_next(self):
        self._page.next = ByTimeRangeCursor(
            datetime.datetime.utcnow(),
            str(uuid.uuid4())
        )

        datestr = '2014-01-01'

        dt = datetime.datetime.strptime(datestr, '%Y-%m-%d')

        expected_next = (
            "/events?limit=10&embed_related=full&cursor=%s&on=%s" % (
                eventlog.service.core.cursor.serialize(self._page.next),
                datestr
            )
        )

        rv = self.app.get('/events?on=' + datestr)

        self.verify_response(
            rv,
            pagination={"next": expected_next}
        )

        store.get_events_by_date.assert_called_with(
            dt,
            embed_related=True,
            feeds=self._all_feeds_names,
            pagesize=10,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_on_and_before(self):
        self._page.next = ByTimeRangeCursor(
            datetime.datetime.utcnow(),
            str(uuid.uuid4())
        )

        datestr = '2014-01-01 12:01:01.000000'

        dt = datetime.datetime.strptime(datestr, DATETIME_FMT)

        expected_next = (
            "/events?limit=10&embed_related=full&cursor=%s&before=%s" % (
                eventlog.service.core.cursor.serialize(self._page.next),
                datestr
            )
        )

        rv = self.app.get('/events?before=' + datestr)

        self.verify_response(
            rv,
            pagination={"next": expected_next}
        )

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=dt,
            embed_related=True,
            feeds=self._all_feeds_names,
            pagesize=10,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_on_and_after(self):
        self._page.next = ByTimeRangeCursor(
            datetime.datetime.utcnow(),
            str(uuid.uuid4())
        )

        datestr = '2014-01-01 12:01:01.000000'

        dt = datetime.datetime.strptime(datestr, DATETIME_FMT)

        expected_next = (
            "/events?limit=10&embed_related=full&cursor=%s&after=%s" % (
                eventlog.service.core.cursor.serialize(self._page.next),
                datestr
            )
        )

        rv = self.app.get('/events?after=' + datestr)

        self.verify_response(
            rv,
            pagination={"next": expected_next}
        )

        store.get_events_by_timerange.assert_called_with(
            before=None,
            after=dt,
            embed_related=True,
            feeds=self._all_feeds_names,
            pagesize=10,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_invalid_page(self):
        def side_effect(*args, **kwargs):
            raise InvalidPage

        self._event_set.page.side_effect = side_effect
        self._event_set.num_pages = 1

        rv = self.app.get('/events?cursor=2&q=test')

        self.verify_response(rv, code=400)

    def test_get_all_with_timezone(self):
        rv = self.app.get('/events?tz=America/Toronto')

        self.verify_response(rv, pagination={})

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=None,
            feeds=self._all_feeds_names,
            pagesize=10,
            embed_related=True,
            timezone="America/Toronto"
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_invalid_timezone(self):
        rv = self.app.get('/events?tz=boo')

        self.verify_response(rv, code=400)

    def test_get_all_with_limit(self):
        rv = self.app.get('/events?limit=20')

        self.verify_response(rv, pagination={})

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=None,
            feeds=self._all_feeds_names,
            pagesize=20,
            embed_related=True,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_invalid_limit(self):
        rv = self.app.get('/events?limit=9999')

        self.verify_response(rv, code=400)

    def test_get_all_with_after(self):

        datestr = '2014-01-01 12:01:01.00'

        dt = datetime.datetime.strptime(datestr, DATETIME_FMT)

        rv = self.app.get('/events?after=' + datestr)

        self.verify_response(rv, pagination={})

        store.get_events_by_timerange.assert_called_with(
            after=dt,
            before=None,
            feeds=self._all_feeds_names,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_invalid_after(self):
        rv = self.app.get('/events?after=abz')

        self.verify_response(rv, code=400)

    def test_get_all_with_before(self):

        datestr = '2014-01-01 12:01:01.00'

        dt = datetime.datetime.strptime(datestr, DATETIME_FMT)

        rv = self.app.get('/events?before=' + datestr)

        self.verify_response(rv, pagination={})

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=dt,
            feeds=self._all_feeds_names,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_cursor(self):

        datestr = '2014-01-01 12:01:01.00'
        dt = datetime.datetime.strptime(datestr, DATETIME_FMT)

        cursor = ByTimeRangeCursor(dt, str(uuid.uuid4()))

        rv = self.app.get(
            '/events?cursor=%s' % (
                eventlog.service.core.cursor.serialize(cursor)
            )
        )

        self.verify_response(rv, pagination={})

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=None,
            feeds=self._all_feeds_names,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=cursor)

    def test_get_all_with_bad_cursors(self):

        bad_cursors = [
            '2014-01-01 12:01:01.00,1',  # bad UUID
            '1,%s' % (str(uuid.uuid4())),  # bad datetime
            '2014-01-01 12:01:01.00,%s,1' % (str(uuid.uuid4()))  # too many
        ]

        # reset called count
        store.get_events_by_timerange.reset_mock()

        for cursor in bad_cursors:
            rv = self.app.get('/events?cursor=' + cursor)

            self.verify_response(rv, code=400)

            store.get_events_by_timerange.assert_not_called()

    def test_get_all_with_after_and_before(self):

        after_datestr = '2014-01-01 12:01:01.00'
        before_datestr = '2014-02-01 12:01:01.00'

        after_dt = datetime.datetime.strptime(
            after_datestr, DATETIME_FMT
        )

        before_dt = datetime.datetime.strptime(
            before_datestr, DATETIME_FMT
        )

        rv = self.app.get(
            '/events?after=' + after_datestr + '&before=' + before_datestr
        )

        self.verify_response(rv, pagination={})

        store.get_events_by_timerange.assert_called_with(
            after=after_dt,
            before=before_dt,
            feeds=self._all_feeds_names,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_inconsistent_after_and_before(self):

        before_datestr = '2014-01-01 12:01:01.00'
        after_datestr = '2014-02-01 12:01:01.00'

        after_dt = datetime.datetime.strptime(
            after_datestr, DATETIME_FMT
        )

        before_dt = datetime.datetime.strptime(
            before_datestr, DATETIME_FMT
        )

        rv = self.app.get(
            '/events?after=' + after_datestr + '&before=' + before_datestr
        )

        self.verify_response(rv, code=400)

    def test_get_all_with_on(self):

        datestr = '2014-01-01'

        dt = datetime.datetime.strptime(datestr, '%Y-%m-%d')

        rv = self.app.get('/events?on=' + datestr)

        self.verify_response(rv, pagination={})

        store.get_events_by_date.assert_called_with(
            dt,
            feeds=self._all_feeds_names,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

        self._event_set.page.assert_called_with(cursor=None)

    def test_get_all_with_invalid_on(self):

        datestr = 'abcd'

        rv = self.app.get('/events?on=' + datestr)

        self.verify_response(rv, code=400)

    def test_get_all_with_malformed_feeds(self):

        rv = self.app.get('/events?feeds=')

        self.verify_response(rv, code=400)

    def test_get_all_with_feeds(self):

        rv = self.app.get('/events?feeds=foo,bar')

        self.verify_response(rv, pagination={})

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=None,
            feeds=['foo', 'bar'],
            pagesize=10,
            embed_related=True,
            timezone=None
        )

    def test_get_all_with_feeds_and_next(self):
        feeds = ['foo', 'bar']

        self._page.next = ByTimeRangeCursor(
            datetime.datetime.utcnow(),
            str(uuid.uuid4())
        )

        expected_next = (
            "/events?" +
            "limit=10&embed_related=full&cursor=%s&feeds=%s" % (
                eventlog.service.core.cursor.serialize(self._page.next),
                ','.join(feeds)
            )
        )

        rv = self.app.get('/events?feeds=foo,bar')

        self.verify_response(rv, pagination={"next": expected_next})

        store.get_events_by_timerange.assert_called_with(
            after=None,
            before=None,
            feeds=feeds,
            pagesize=10,
            embed_related=True,
            timezone=None
        )

    def test_get_all_with_invalid_feeds(self):

        rv = self.app.get('/events?feeds=blu')

        self.verify_response(rv, code=400)

    def test_get_all_with_search(self):

        query = 'bar'

        rv = self.app.get('/events?q=' + query)

        self.verify_response(rv, pagination={})

        store.get_events_by_search.assert_called_with(
            query,
            to_mask=None,
            before=None,
            after=None,
            to_filter=[],
            pagesize=10,
            timezone=None
        )

    def test_get_all_with_search_with_unsearchable_feeds(self):

        new_feed = {
            'bazz': self._bazz_feed
        }

        self._all_feeds.update(new_feed)

        store.get_feeds.return_value.update(new_feed)

        self._bazz_feed.is_searchable = True
        self._jazz_feed.is_searchable = True

        query = 'bar'

        rv = self.app.get('/events?feeds=jazz,bazz&q=' + query)

        self.verify_response(rv, pagination={})

        store.get_events_by_search.assert_called_with(
            query,
            to_mask=['bar', 'foo'],
            before=None,
            after=None,
            to_filter=None,
            pagesize=10,
            timezone=None
        )

    def test_get_single(self):

        def iterable(obj):
            event_attrs = {'dict.return_value': {}}

            yield unittest.mock.Mock(feed=self._bar_feed, **event_attrs)

        self._event_set.count = 1
        self._event_set.__iter__ = iterable

        rv = self.app.get('/events/1')

        self.verify_response(rv)

        store.get_events_by_ids.assert_called_with(
            ['1'],
            timezone=None
        )

    def test_get_single_invalid_id(self):
        self._event_set.count = 0

        rv = self.app.get('/events/1')

        self.verify_response(rv, code=404)

    def test_get_single_with_timezone(self):

        def iterable(obj):
            event_attrs = {'dict.return_value': {}}

            yield unittest.mock.Mock(feed=self._bar_feed, **event_attrs)

        self._event_set.count = 1
        self._event_set.__iter__ = iterable

        rv = self.app.get('/events/1?tz=America/Toronto')

        self.verify_response(rv)

        store.get_events_by_ids.assert_called_with(
            ['1'],
            timezone="America/Toronto"
        )

    def test_get_all_unexpected_exception(self):

        def side_effect(*args, **kwargs):
            raise Exception("uh oh!")

        store.get_feeds.side_effect = side_effect

        rv = self.app.get('/events')

        self.verify_response(rv, code=500)

    def test_delete_not_allowed(self):
        rv = self.app.delete('/events')

        self.verify_response(rv, code=405)
