import unittest
import datetime
import math
import copy

import pytz
import json

from eventlog.lib.events import Event, Fields, InvalidField
from eventlog.lib.util import utc_datetime_to_local

from ..util import events_create_fake, to_pg_datetime_str

from .common import TestStoreWithDBBase, store, feed_generator


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

        p = es.page()

        self.assertEqual(len(p), 0)

    def test_get_events_by_ids_single_missing_id(self):

        ids = ['eb2e5989-113b-419b-90ad-6914f555b299']

        es = store.get_events_by_ids(ids)

        self.assertEqual(es.count, 0)
        self.assertEqual(list(es), [])

    def test_get_events_by_ids_single_invalid_id(self):

        ids = ['7']

        es = store.get_events_by_ids(ids)

        self.assertEqual(es.count, 0)
        self.assertEqual(list(es), [])

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

        es = store.get_events_by_timerange(embed_related=False)

        self.assertEqual(es.count, len(self._events))
        self.assertEqual(
            es.num_pages,
            int(math.ceil(len(self._events) / 10.0)) + 1
        )

        p = es.page()

        for e in p:
            self.assertEqual(e.related, None)

        p = es.page()

        for e in p:
            self.assertEqual(e.related, None)

        self.assertEqual(len(p), 10)

    def test_get_events_no_args_page_1_pagesize_5(self):

        es = store.get_events_by_timerange(pagesize=5)

        self.assertEqual(es.count, len(self._events))
        self.assertEqual(
            es.num_pages,
            int(math.ceil(len(self._events) / 5.0)) + 1
        )

        p = es.page()

        self.assertEqual(len(p), 5)

    def test_get_events_no_args_page_1(self):
        es = store.get_events_by_timerange()

        self.assertEqual(es.count, len(self._events))
        self.assertEqual(
            es.num_pages,
            int(math.ceil(len(self._events) / 10.0)) + 1
        )

        p = es.page()

        self.assertEqual(len(p), 10)

        from_store = [e.dict() for e in p]
        expected = [e.dict() for e in self._events[:10]]

        for i in range(10):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_no_args_page_past_end(self):
        es = store.get_events_by_timerange()

        first_page = es.page()

        for _ in range(2, es.num_pages + 1):
            es.page()

        # next page will be first page
        too_far = es.page()

        self.assertEqual(
            [e.dict() for e in too_far],
            [e.dict() for e in first_page]
        )

    def test_get_events_no_args_single_feed_page_1(self):

        feeds = ['testfeed3']
        es = store.get_events_by_timerange(feeds=feeds)

        p = es.page()

        expected = [
            e.dict() for e in self._events
            if e.feed['short_name'] == 'testfeed3'
        ][:10]

        from_store = [e.dict() for e in p]

        for i in range(10):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_no_args_multiple_feeds_page_1(self):

        feeds = ['testfeed1', 'testfeed7']

        es = store.get_events_by_timerange(feeds=feeds)

        p = es.page()

        expected = [
            e.dict() for e in self._events
            if e.feed['short_name'] in feeds
        ]

        self.assertEqual(es.count, len(expected))

        expected = expected[:10]

        from_store = [e.dict() for e in p]

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

        ids = [e.id for e in self._events][:3]

        es = store.get_events_by_ids(ids)

        from_store = [e.dict() for e in es]

        expected = [e.dict() for e in self._events if e.id in ids]

        for i in range(3):
            self.assertDictEqual(from_store[i], expected[i])

        self.assertEqual(es.count, len(expected))

    def test_get_events_by_ids_single(self):

        expected = self._events[15]

        es = store.get_events_by_ids([expected.id])

        from_store = list(es)[0]

        self.assertEqual(es.count, 1)
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

        self.assertEqual(es.count, 1)
        self.assertEqual(from_store.dict(), expected.dict())

    def test_get_events_by_latest(self):
        events = {
            k: v.dict()
            for k, v in store.get_events_by_latest().items()
        }

        self.assertEqual(len(events), feed_generator.MAX_NUM)

        expected = {
            feed['short_name']: [
                e for e in self._events
                if e.feed['short_name'] == feed['short_name']
            ][0].dict()
            for feed in self._feeds
        }

        self.assertEqual(events, expected)

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
            new_time = utc_datetime_to_local(e.occurred, pytz.timezone(tz))

            if new_time.date() == d.date():

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

        p = es.page()

        self.assertTrue(len(p) > 0)

        from_store = [e.dict() for e in p]

        expected = []

        for e in self._events:
            new_time = utc_datetime_to_local(
                e.occurred,
                pytz.timezone(tz)
            )

            if new_time.date() == d.date():

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

        es = store.get_events_by_date(d, feeds=feeds, timezone=tz)

        self.assertTrue(es.count > 0)

        from_store = [e.dict() for e in es]

        expected = []

        for e in self._events:
            new_time = utc_datetime_to_local(e.occurred, pytz.timezone(tz))

            if new_time.date() == d.date():

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

    def test_get_events_by_timerange_after_only(self):

        dt = datetime.datetime(2012, 4, 1, 0, 0, 0, 0)
        es = store.get_events_by_timerange(after=dt)

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

    def test_get_events_by_timerange_before_only(self):

        dt = datetime.datetime(2012, 4, 1, 0, 0, 0, 0)
        es = store.get_events_by_timerange(before=dt)

        self.assertTrue(es.count > 0)

        from_store = [e.dict() for e in es]

        expected = []

        for e in self._events:
            if e.occurred < dt:
                expected.append(e)

        expected.sort(key=lambda x: x.occurred)
        expected.reverse()
        expected = [e.dict() for e in expected]

        self.assertEqual(es.count, len(expected))

        for i in range(len(expected)):
            self.assertDictEqual(from_store[i], expected[i])

    def test_get_events_by_timerange_before_and_after(self):
        before = datetime.datetime(2013, 1, 1, 0, 0, 0, 0)
        after = datetime.datetime(2012, 6, 12, 0, 0, 0, 0)

        es = store.get_events_by_timerange(
            before=before,
            after=after,
            pagesize=5
        )

        self.assertTrue(es.count > 0)

        expected = []

        for e in self._events:
            if after < e.occurred < before:
                expected.append(e)

        expected.sort(key=lambda x: x.occurred)
        expected.reverse()
        expected = [e.dict() for e in expected]

        self.assertEqual(es.count, len(expected))

        from_store = []

        for _ in range(1, es.num_pages + 1):
            p = es.page()
            from_store += [e.dict() for e in p]

        self.assertEqual(from_store, expected)

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

        es = store.get_events_by_timerange(flattened=True)

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

        es = store.get_events_by_timerange(flattened=True, feeds=[feed])

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

        es = store.get_events_by_timerange(flattened=True, feeds=[feed])

        self.assertEqual(es.count, total)


if __name__ == '__main__':
    unittest.main()
