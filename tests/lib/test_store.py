import unittest
import json
import datetime
import os.path
import shutil
import math
import time
import copy
import pkg_resources

import pytz
import psycopg2

from flask import Flask

from eventlog.lib.store import Store, InvalidTimeRangeException
from eventlog.lib.store.eventquery import EventQuery
from eventlog.lib.store.search import open_index, Index
from eventlog.lib.events import (Event, Fields,
                                 InvalidField, MissingEventIDException)
from eventlog.lib.feeds import MissingFeedIDException
from eventlog.lib.util import tz_unaware_utc_dt_to_local

from util import db_drop_all_data, db_init_schema, db_drop_all_events
from util import db_insert_feeds, feeds_create_fake
from util import events_create_fake, events_compare, events_create_single
from util import index_check_documents, to_pg_datetime_str

import feed_generator

SCHEMA_PATH = pkg_resources.resource_filename(
    'eventlog.lib', 'store/sql/eventlog.sql'
)

app = Flask(__name__)
store = Store()


class TestStoreNoDB(unittest.TestCase):
    def test_eventquery_add_first_clause(self):
        eq = EventQuery(
            "select * from events",
            embed_feeds=False,
            embed_related=False
        )
        eq.add_clause("is_related=%s", (False,))

        self.assertIn("where is_related", eq.query)


class TestStoreWithDBBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):

        cls._config = {
            'DB_USER': 'test',
            'DB_PASS': 'test',
            'DB_NAME': 'test',
            'INDEX_DIR': '../testindex',
            'TIME_ZONE': 'America/Toronto'
        }

        # create connection
        cls._conn = psycopg2.connect(
            database=cls._config['DB_NAME'],
            user=cls._config['DB_USER'],
            password=cls._config['DB_PASS']
        )

        # create test feeds
        cls._feeds = [
            feeds_create_fake(i, 'feed_generator')
            for i in range(feed_generator.MAX_NUM)
        ]

        # prep database
        db_drop_all_data(cls._conn)
        db_init_schema(cls._conn, SCHEMA_PATH)

        # prep database data
        db_insert_feeds(cls._conn, cls._feeds)

        # remove any existing index
        if os.path.exists(cls._config['INDEX_DIR']):
            shutil.rmtree(cls._config['INDEX_DIR'])

        # init our store
        app.config['STORE'] = cls._config
        store.init_app(app)

    @classmethod
    def tearDownClass(cls):
        # remove any existing index
        if os.path.exists(cls._config['INDEX_DIR']):
            shutil.rmtree(cls._config['INDEX_DIR'])


class TestStoreModify(TestStoreWithDBBase):

    def tearDown(self):
        # empty events table
        db_drop_all_events(self._conn)

        # clear index
        store._index.clear()

    def _add_events(self, dry=False):
        distribution = [(json.dumps(feed), 3) for feed in self._feeds]

        event_dicts = events_create_fake(
            distribution,
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
            datetime.datetime(2012, 3, 24, 0, 0, 0, 0)
        )
        event_dicts.reverse()

        events = [Event.from_dict(d) for d in event_dicts]

        store.add_events(events, dry=dry)

        return event_dicts, events

    def test_init_store_no_index_path(self):
        config = copy.deepcopy(self._config)
        config['INDEX_DIR'] = None

        test_app = Flask('TestApp')
        test_app.config['STORE'] = config

        test_store = Store()
        test_store.init_app(test_app)

        self.assertIsNone(test_store._index)

    def test_get_events_empty_db(self):
        es = store.get_events()

        self.assertEqual(es.count, 0)

        p = es.get_page(1)

        self.assertIsNotNone(p)
        self.assertEqual(len(p.events), 0)

    def test_get_events_by_latest_empty_db(self):
        es = store.get_events_by_latest()

        self.assertEqual(es.count, 0)

    def test_get_events_by_latest_single_feed_empty_db(self):
        latest = store.get_events_by_latest(feed=self._feeds[0]['short_name'])
        self.assertIsNone(latest)

    def test_add_events(self):

        event_dicts, events = self._add_events()

        es = store.get_events()

        from_store = list(es)

        events_compare(self, event_dicts, from_store)

        index_check_documents(self, store, from_store)

    def test_add_events_dry(self):
        event_dicts, events = self._add_events(dry=True)

        es = store.get_events()

        self.assertEqual(es.count, 0)

        index_check_documents(self, store, events, should_exist=False)

    def test_add_event_bad_object(self):
        self.assertRaises(
            Exception,
            store.add_events,
            [{}]
        )

    def test_add_event_bad_id_value(self):
        e = Event.from_dict(
            events_create_single(
                self._feeds[0],
                datetime.datetime(2012, 1, 12, 0, 0, 0, 0)
            )
        )
        e.id = 7

        self.assertRaises(
            psycopg2.Error,
            store.add_events,
            [e]
        )

    def test_add_event_with_existing_related_event(self):
        related = Event.from_dict(
            events_create_single(
                self._feeds[0],
                datetime.datetime(2012, 1, 12, 0, 0, 0, 0)
            )
        )

        store.add_events([related])

        # remove feed data on related event to match what is retrieved from the
        # store
        related.feed = None

        e = Event.from_dict(
            events_create_single(
                self._feeds[0],
                datetime.datetime(2012, 1, 11, 0, 0, 0, 0)
            )
        )
        e.add_related(related)

        store.add_events([e])

        es = store.get_events_by_ids([e.id])

        self.assertEqual(es.count, 1)

        from_store = es.get_page(1).events[0]

        self.assertEqual(len(from_store.related), 1)

        related_dict = related.dict()
        related_dict['feed'] = None

        self.assertEqual(from_store.related[0].dict(), related_dict)

        es = store.get_events_by_ids([related.id])

        related_from_store = es.get_page(1).events[0]

        self.assertIsNotNone(related_from_store.feed)

    def test_add_existing_event(self):
        event_dicts, events = self._add_events()

        existing = events[3]

        store.add_events([existing])

        es = store.get_events()

        self.assertEqual(es.count, len(event_dicts))

    def test_update_feeds_with_nonexistent(self):
        feeds = store.get_feeds()

        # grab the first feed
        f = next(iter(feeds.values()))

        # increment ID to one that doesn't exist
        f.id = feed_generator.MAX_NUM + 1

        self.assertRaises(
            MissingFeedIDException,
            store.update_feeds,
            [f]
        )

    def test_update_feeds_change_config(self):
        new_key = 'test_update_feeds_change_config'
        new_value = "OMGVALUE"

        feeds = store.get_feeds()

        # grab the first feed
        f = next(iter(feeds.values()))
        f.overrides[new_key] = new_value

        store.update_feeds([f])

        # regrab the feed
        feeds = store.get_feeds()

        new_f = next(iter(feeds.values()))

        self.assertIn(new_key, new_f.overrides)
        self.assertEqual(new_value, new_f.overrides[new_key])
        self.assertDictEqual(f.dict(admin=True), new_f.dict(admin=True))

    def test_update_feeds_change_config_dry(self):
        new_key = 'test_update_feeds_change_config_dry'
        new_value = "OMGVALUE"

        feeds = store.get_feeds()

        # grab the first feed
        f = next(iter(feeds.values()))
        f.overrides[new_key] = new_value

        store.update_feeds([f], dry=True)

        # regrab the feed
        feeds = store.get_feeds()

        new_f = next(iter(feeds.values()))

        self.assertNotIn(new_key, new_f.overrides)

    def test_update_events_change_title(self):

        event_dicts, events = self._add_events()

        num = 1
        for d in event_dicts:
            d['title'] = 'changed to %d' % (num)
            num += 1

        events = [Event.from_dict(d) for d in event_dicts]

        store.update_events(events)

        es = store.get_events()

        from_store = list(es)

        events_compare(self, event_dicts, from_store)

        es = store.get_events_by_search("changed")

        self.assertEqual(es.count, len(event_dicts))

    def test_update_events_change_title_dry(self):

        event_dicts, events = self._add_events()

        for i, d in enumerate(event_dicts):
            d['title'] = 'changed to %d' % (i)

        events = [Event.from_dict(d) for d in event_dicts]

        store.update_events(events, dry=True)

        es = store.get_events()

        from_store = list(es)

        for e in from_store:
            if e.title is not None:
                self.assertNotIn('changed', e.title)

        es = store.get_events_by_search("changed")

        self.assertEqual(es.count, 0)

    def test_update_events_with_nonexistent(self):
        e = Event.from_dict(
            events_create_single(
                self._feeds[0],
                datetime.datetime(2012, 1, 12, 0, 0, 0, 0)
            )
        )

        self.assertRaises(
            MissingEventIDException,
            store.update_events,
            [e]
        )

    def test_delete_events_with_bad_arguments(self):
        event_dicts, events = self._add_events()

        store.remove_events(events=None, feed=None)

        es = store.get_events()

        self.assertEqual(es.count, len(events))

    def test_delete_events_by_list(self):
        event_dicts, events = self._add_events()

        to_remove = events[3:5]

        store.remove_events(events=to_remove)

        es = store.get_events_by_ids([e.id for e in to_remove])

        self.assertEqual(es.count, 0)

        index_check_documents(self, store, to_remove, should_exist=False)

    def test_delete_events_by_feed(self):
        event_dicts, events = self._add_events()

        to_remove = 'testfeed3'
        removed = [e for e in events if e.feed['short_name'] == to_remove]

        self.assertTrue(len(removed) > 0)

        store.remove_events(feed=to_remove)

        es = store.get_events(feeds=[to_remove])

        self.assertEqual(es.count, 0)

        es = store.get_events()
        self.assertEqual(es.count, len(events) - len(removed))

        index_check_documents(self, store, removed, should_exist=False)

    def test_delete_events_by_list_dry(self):
        event_dicts, events = self._add_events()

        to_remove = events[3:5]

        store.remove_events(events=to_remove, dry=True)

        es = store.get_events_by_ids([e.id for e in to_remove])

        self.assertEqual(es.count, len(to_remove))

        es = store.get_events()

        from_store = list(es)

        index_check_documents(self, store, from_store)

    def test_delete_non_existent_events(self):
        e = Event.from_dict(
            events_create_single(
                self._feeds[0],
                datetime.datetime(2012, 1, 12, 0, 0, 0, 0)
            )
        )

        # should be a no-op
        store.remove_events(events=[e])

    def test_delete_event_with_bad_id(self):
        e = Event.from_dict(
            events_create_single(
                self._feeds[0],
                datetime.datetime(2012, 1, 12, 0, 0, 0, 0)
            )
        )

        e.id = 7

        self.assertRaises(
            Exception,
            store.remove_events,
            [e]
        )

    def test_delete_events_with_related(self):
        event_dicts, events = self._add_events()

        has_related = False
        for e in events:
            if e.related is not None:
                has_related = True

        self.assertTrue(has_related)

        es = store.get_events(flattened=True)

        self.assertGreater(es.count, len(events))

        store.remove_events(events=events)

        es = store.get_events(flattened=True)

        self.assertEqual(es.count, 0)

    def test_search_with_timezone(self):
        event_dicts, events = self._add_events()

        num = 1
        for d in event_dicts:
            d['title'] = 'changed to %d' % (num)
            num += 1

        events = [Event.from_dict(d) for d in event_dicts]

        store.update_events(events)

        tz = 'America/Toronto'

        es = store.get_events_by_search("changed", timezone=tz)

        from_store = []

        for i in range(es.num_pages):
            p = es.get_page(i + 1)
            from_store += p.events

        from_store.sort(key=lambda x: x.occurred)
        from_store = [e.dict() for e in from_store]

        expected = []

        for e in events:
            new_time = tz_unaware_utc_dt_to_local(e.occurred,
                                                  pytz.timezone(tz))

            new_event_dict = e.dict()
            to_pg_datetime_str(new_event_dict, 'occurred')
            new_event_dict['related'] = None

            new_event = Event.from_dict(new_event_dict)  # need a copy
            new_event.localize(tz)
            expected.append(new_event)

        expected.sort(key=lambda x: x.occurred)
        expected = [e.dict() for e in expected]

        self.assertEqual(len(expected), len(from_store))

        for i in range(len(expected)):
            self.assertDictEqual(from_store[i], expected[i])

    def test_search_with_filter(self):
        event_dicts, events = self._add_events()

        num = 1
        for d in event_dicts:
            d['title'] = 'changed to %d' % (num)
            num += 1

        events = [Event.from_dict(d) for d in event_dicts]

        store.update_events(events)

        to_filter = ['testfeed2']
        unfiltered = [f for f in self._feeds if f not in to_filter]

        num_filtered = len(
            [e for e in events if e.feed['short_name'] in to_filter]
        )

        self.assertTrue(num_filtered > 0)

        es = store.get_events_by_search("changed", to_filter=to_filter)

        self.assertEqual(es.count, num_filtered)
        self.assertEqual(len(es), num_filtered)

        for page_num in range(es.num_pages):
            for e in es.get_page(page_num + 1).events:
                self.assertNotIn(e.feed['short_name'], unfiltered)

    def test_search_with_mask(self):
        event_dicts, events = self._add_events()

        num = 1
        for d in event_dicts:
            d['title'] = 'changed to %d' % (num)
            num += 1

        events = [Event.from_dict(d) for d in event_dicts]

        store.update_events(events)

        to_mask = ['testfeed3', 'testfeed5']

        num_masked = len(
            [e for e in events if e.feed['short_name'] in to_mask]
        )
        num_un_masked = len(events) - num_masked

        self.assertTrue(num_masked > 0)
        self.assertTrue(num_un_masked > 0)

        es = store.get_events_by_search("changed", to_mask=to_mask)

        self.assertEqual(es.count, num_un_masked)

        for page_num in range(es.num_pages):
            for e in es.get_page(page_num + 1).events:
                self.assertNotIn(e.feed['short_name'], to_mask)

    def test_search_invalid_page_number_past_first(self):
        es = store.get_events_by_search("changed")

        p = es.get_page(3)

        self.assertIsNone(p)

    def test_reopen_existing_index(self):
        self._add_events()

        index = open_index(self._config['INDEX_DIR'])

        self.assertIsNotNone(index)

        with index.searcher() as searcher:
            documents = list(searcher.documents())

            self.assertTrue(len(documents) > 0)

    def test_open_index_invalid_path(self):
        index = open_index(1)
        self.assertIsNone(index)

    def test_operations_on_uninitialized_index(self):
        index = Index(1)
        self.assertIsNone(index._index)
        index.remove([1, 2, 3])
        index.index([1, 2, 3])
        index.search("foo", None, None, None)

    def test_index_remove_without_args(self):
        self._add_events()

        store._index.remove()

        with store._index._index.searcher() as searcher:
            documents = list(searcher.documents())

            self.assertTrue(len(documents) > 0)


class TestStoreReadOnly(TestStoreWithDBBase):
    @classmethod
    def setUpClass(cls):
        TestStoreWithDBBase.setUpClass()

        # add our events
        distribution = [(json.dumps(feed), 30) for feed in cls._feeds]

        event_dicts = events_create_fake(
            distribution,
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
            datetime.datetime(2013, 3, 24, 0, 0, 0, 0)
        )

        cls._events = [Event.from_dict(d) for d in event_dicts]
        cls._events.sort(key=lambda x: x.occurred)
        cls._events.reverse()

        store.add_events(cls._events)

        # need to stub out feeds in related events
        for e in cls._events:
            if e.related is not None:
                for r in e.related:
                    r.feed = None

    def setUp(self):
        self.maxDiff = None

    def test_get_feeds_no_args(self):
        feeds = store.get_feeds()

        self.assertEqual(len(feeds), feed_generator.MAX_NUM)

        for f in self._feeds:
            short_name = f['short_name']

            loaded_feed = feeds[short_name]

            check_fields = ['short_name', 'full_name', 'color', 'favicon']

            for field in check_fields:
                self.assertEqual(f[field], getattr(loaded_feed, field))

    def test_exists_return_false(self):
        self.assertFalse(store.exists(Fields.TITLE, 'oijweoiur319831_'))

    def test_exists_invalid_field(self):
        self.assertRaises(
            InvalidField,
            store.exists,
            'noexist',
            'blarg'
        )

    def test_events_by_search_no_results(self):
        es = store.get_events_by_search('omoiwe')

        self.assertEqual(es.count, 0)

        p = es.get_page(1)

        self.assertEqual(len(p.events), 0)

    def test_get_events_by_ids_single_missing_id(self):

        ids = [
            'eb2e5989-113b-419b-90ad-6914f555b299',
        ]

        es = store.get_events_by_ids(ids)

        self.assertEqual(es.count, 0)

    def test_get_events_by_ids_single_invalid_id(self):

        ids = [
            '7',
        ]

        es = store.get_events_by_ids(ids)

        self.assertEqual(es.count, 0)

    def test_get_events_no_args_invalid_page(self):
        es = store.get_events()

        self.assertIsNone(es.get_page(900))

    def test_get_events_by_latest_single_feed_doesnt_exist(self):
        e = store.get_events_by_latest(feed='oijwef')

        self.assertIsNone(e)

    def test_get_feeds_single_filter(self):
        feeds = store.get_feeds(is_updating=True)

        expected = [f['short_name'] for f in self._feeds if f['is_updating']]

        self.assertEqual(len(expected), 12)

        from_store = list(feeds.keys())

        expected.sort()
        from_store.sort()

        self.assertEqual(expected, from_store)

    def test_get_feeds_multiple_filter(self):
        feeds = store.get_feeds(is_updating=False, is_searchable=True)

        expected = [
            f['short_name']
            for f in self._feeds
            if (not f['is_updating'] and f['is_searchable'])
        ]
        self.assertEqual(len(expected), 5)

        from_store = list(feeds.keys())

        expected.sort()
        from_store.sort()

        self.assertEqual(expected, from_store)

    def test_get_events_no_embed_page_1_2(self):

        es = store.get_events(embed_related=False)

        self.assertEqual(es.count, len(self._events))
        self.assertEqual(
            es.num_pages,
            int(math.ceil(len(self._events)/10.0))
        )

        p = es.get_page(1)

        for e in p.events:
            self.assertEqual(e.related, None)

        p = es.get_page(2)

        for e in p.events:
            self.assertEqual(e.related, None)

        self.assertEqual(len(p.events), 10)

    def test_get_events_no_args_page_1_pagesize_5(self):

        es = store.get_events(pagesize=5)

        self.assertEqual(es.count, len(self._events))
        self.assertEqual(
            es.num_pages,
            int(math.ceil(len(self._events)/5.0))
        )

        p = es.get_page(1)

        self.assertEqual(len(p.events), 5)

    def test_get_events_no_args_page_1(self):
        es = store.get_events()

        self.assertEqual(es.count, len(self._events))
        self.assertEqual(
            es.num_pages,
            int(math.ceil(len(self._events)/10.0))
        )

        p = es.get_page(1)

        self.assertEqual(len(p.events), 10)

        from_store = [e.dict() for e in p.events]
        expected = [e.dict() for e in self._events[:10]]

        for i in range(10):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_no_args_single_feed_page_1(self):

        feeds = ['testfeed3']
        es = store.get_events(feeds=feeds)

        p = es.get_page(1)

        expected = [
            e.dict() for e in self._events
            if e.feed['short_name'] == 'testfeed3'
        ][:10]

        from_store = [e.dict() for e in p.events]

        for i in range(10):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_no_args_multiple_feeds_page_1(self):

        feeds = ['testfeed1', 'testfeed7']

        es = store.get_events(feeds=feeds)

        p = es.get_page(1)

        expected = [
            e.dict() for e in self._events
            if e.feed['short_name'] in feeds
        ]
        self.assertEqual(es.count, len(expected))
        expected = expected[:10]

        from_store = [e.dict() for e in p.events]

        for i in range(10):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_by_latest_single_feed_exists(self):

        from_store = store.get_events_by_latest(feed='testfeed11')

        self.assertIsNotNone(from_store)

        expected = [
            e.dict() for e in self._events
            if e.feed['short_name'] == 'testfeed11'
        ][0]

        self.assertEqual(from_store.dict(), expected)

    def test_get_events_by_ids_multiple(self):

        ids = [
            e.id for e in self._events
        ][:3]

        es = store.get_events_by_ids(ids)

        from_store = [e.dict() for e in es]

        expected = [
            e.dict() for e in self._events
            if e.id in ids
        ]

        for i in range(3):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_by_ids_single(self):

        expected = self._events[15]

        es = store.get_events_by_ids([expected.id])

        from_store = list(es)[0]

        self.assertEqual(from_store.dict(), expected.dict())

    def test_get_events_by_ids_single_is_related(self):
        parent = None

        for e in self._events:
            if e.related is not None:
                parent = e
                break

        self.assertIsNotNone(parent)

        # HACK: testing infrastructure strips feeds from related items
        #       to match DB result for other tests, need to correct here
        expected = copy.deepcopy(e.related[-1])
        expected.feed = parent.feed

        es = store.get_events_by_ids([expected.id])

        from_store = list(es)[0]

        self.assertEqual(from_store.dict(), expected.dict())

    def test_get_events_by_latest(self):
        es = store.get_events_by_latest()

        self.assertEqual(es.count, feed_generator.MAX_NUM)

        from_store = [e.dict() for e in es]

        expected = []

        for feed in self._feeds:
            latest = [
                e for e in self._events
                if e.feed['short_name'] == feed['short_name']
            ][0]
            expected.append(latest)
        expected.sort(key=lambda x: x.occurred)
        expected.reverse()
        expected = [e.dict() for e in expected]

        for i in range(feed_generator.MAX_NUM):
            self.assertDictEqual(from_store[i], expected[i])

    def test_exists_return_true(self):

        for field in [Fields.TITLE, Fields.TEXT, Fields.LINK]:
            value = None

            for e in self._events:
                candidate = getattr(e, str(field), None)

                if candidate is not None:
                    value = candidate
                    break

            self.assertIsNotNone(value)
            self.assertTrue(store.exists(field, value))

    def test_get_events_by_date_local(self):
        d = datetime.datetime(2012, 11, 24, 0, 0, 0, 0)

        tz = 'America/Toronto'

        es = store.get_events_by_date(d, timezone=tz)

        self.assertTrue(es.count > 0)

        from_store = [e.dict() for e in es]

        expected = []

        for e in self._events:
            new_time = tz_unaware_utc_dt_to_local(e.occurred,
                                                  pytz.timezone(tz))

            if (new_time.date() == d.date()):

                new_event_dict = e.dict()
                to_pg_datetime_str(new_event_dict, 'occurred')

                if new_event_dict['related'] is not None:
                    for r in new_event_dict['related']:
                        to_pg_datetime_str(r, 'occurred')

                new_event = Event.from_dict(new_event_dict)  # need a copy
                new_event.localize(tz)
                expected.append(new_event)

        expected.sort(key=lambda x: x.occurred)
        expected.reverse()
        expected = [e.dict() for e in expected]

        for i in range(len(expected)):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_by_date_local_page_1(self):
        d = datetime.datetime(2012, 11, 24, 0, 0, 0, 0)

        tz = 'America/Toronto'

        es = store.get_events_by_date(d, timezone=tz)

        p = es.get_page(1)

        self.assertTrue(len(p.events) > 0)

        from_store = [e.dict() for e in p.events]

        expected = []

        for e in self._events:
            new_time = tz_unaware_utc_dt_to_local(e.occurred,
                                                  pytz.timezone(tz))

            if (new_time.date() == d.date()):

                new_event_dict = e.dict()
                to_pg_datetime_str(new_event_dict, 'occurred')

                if new_event_dict['related'] is not None:
                    for r in new_event_dict['related']:
                        to_pg_datetime_str(r, 'occurred')

                new_event = Event.from_dict(new_event_dict)  # need a copy
                new_event.localize(tz)
                expected.append(new_event)

        expected.sort(key=lambda x: x.occurred)
        expected.reverse()
        expected = [e.dict() for e in expected]
        expected = expected[0:es.pagesize]

        for i in range(len(expected)):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_by_date_local_specific_feeds(self):
        d = datetime.datetime(2012, 12, 1, 0, 0, 0, 0)

        tz = 'America/Toronto'

        feeds = ['testfeed17', 'testfeed18']

        es = store.get_events_by_date(
            d, feeds=feeds, timezone=tz
        )

        self.assertTrue(es.count > 0)

        from_store = [e.dict() for e in es]

        expected = []

        for e in self._events:
            new_time = tz_unaware_utc_dt_to_local(e.occurred,
                                                  pytz.timezone(tz))

            if (new_time.date() == d.date()):

                new_event_dict = e.dict()
                to_pg_datetime_str(new_event_dict, 'occurred')

                if new_event_dict['related'] is not None:
                    for r in new_event_dict['related']:
                        to_pg_datetime_str(r, 'occurred')

                new_event = Event.from_dict(new_event_dict)  # need a copy
                new_event.localize(tz)
                expected.append(new_event)

        expected.sort(key=lambda x: x.occurred)
        expected.reverse()
        expected = [e.dict() for e in expected]

        for i in range(len(expected)):
            self.assertIn(from_store[i]['feed']['short_name'], feeds)
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_by_timerange_start_only(self):

        dt = datetime.datetime(2012, 4, 1, 0, 0, 0, 0)
        es = store.get_events_by_timerange(dt)

        self.assertTrue(es.count > 0)

        from_store = [e.dict() for e in es]

        expected = []

        for e in self._events:
            if e.occurred > dt:
                expected.append(e)

        expected.sort(key=lambda x: x.occurred)
        expected.reverse()
        expected = [e.dict() for e in expected]

        self.assertEqual(es.count, len(expected))

        for i in range(len(expected)):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_by_timerange_end_only(self):

        dt = datetime.datetime(2012, 4, 1, 0, 0, 0, 0)
        es = store.get_events_by_timerange(end=dt)

        self.assertTrue(es.count > 0)

        from_store = [e.dict() for e in es]

        expected = []

        for e in self._events:
            if e.occurred <= dt:
                expected.append(e)

        expected.sort(key=lambda x: x.occurred)
        expected.reverse()
        expected = [e.dict() for e in expected]

        self.assertEqual(es.count, len(expected))

        for i in range(len(expected)):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_by_timerange_no_args(self):

        self.assertRaises(
            InvalidTimeRangeException,
            store.get_events_by_timerange
        )

    def test_embeded_related_ordering(self):
        expected = None

        for e in self._events:
            if e.related is not None and len(e.related) > 3:
                expected = e
                break

        self.assertIsNotNone(expected)

        es = store.get_events_by_ids([expected.id])

        from_store = list(es)[0]

        prev = expected.occurred
        for r in expected.related:
            self.assertTrue(r.occurred > prev)
            prev = r.occurred

        self.assertDictEqual(expected.dict(), from_store.dict())

    def test_get_events_flattened(self):
        expected = 0
        for e in self._events:
            expected += 1
            if e.related is not None:
                expected += len(e.related)

        es = store.get_events(flattened=True)

        self.assertEqual(es.count, expected)

    def test_get_events_flattened_by_feed_with_related(self):
        expected = None

        for e in self._events:
            if e.related is not None:
                expected = e
                break

        self.assertIsNotNone(expected)

        feed = expected.feed['short_name']

        without_related = 0
        num_related = 0
        for e in self._events:
            if e.feed['short_name'] != feed:
                continue

            without_related += 1
            if e.related is not None:
                num_related += len(e.related)

        total = without_related + num_related

        self.assertTrue(without_related < total)

        es = store.get_events(flattened=True, feeds=[feed])

        self.assertEqual(es.count, total)

    def test_get_events_flattened_by_feed_without_related(self):
        expected = None

        for e in self._events:
            if e.related is None:
                expected = e
                break

        self.assertIsNotNone(expected)

        feed = expected.feed['short_name']

        without_related = 0
        num_related = 0
        for e in self._events:
            if e.feed['short_name'] != feed:
                continue

            without_related += 1
            if e.related is not None:
                num_related += len(e.related)

        total = without_related + num_related

        self.assertTrue(without_related == total)

        es = store.get_events(flattened=True, feeds=[feed])

        self.assertEqual(es.count, total)

if __name__ == '__main__':
    unittest.main()
