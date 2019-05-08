import unittest
import datetime
import copy

import psycopg2
import json

from flask import Flask

from eventlog.lib.store import Store
from eventlog.lib.store.search import open_index, Index
from eventlog.lib.store.pagination import (InvalidPage, ByTimeRangeCursor,
                                           BySearchCursor)
from eventlog.lib.events import Event, InvalidField, MissingEventIDException
from eventlog.lib.feeds import MissingFeedIDException

from ..util import db_drop_all_events
from ..util import events_create_fake, events_compare, events_create_single
from ..util import index_check_documents, to_pg_datetime_str

from .common import TestStoreWithDBBase, store, feed_generator


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
        es = store.get_events_by_timerange()

        self.assertEqual(es.count, 0)

        p = es.page()

        self.assertIsNotNone(p)
        self.assertEqual(len(p), 0)

    def test_get_events_by_latest_empty_db(self):
        events = store.get_events_by_latest()

        self.assertEqual(events, {})

    def test_get_events_by_latest_single_feed_empty_db(self):
        latest = store.get_events_by_latest(feed=self._feeds[0]['short_name'])
        self.assertIsNone(latest)

    def test_get_events_by_timerange_cursor_all_same_occurred(self):
        event_dicts, events = self._add_events()

        timestamp = datetime.datetime(2012, 1, 12, 0, 0, 0, 0)
        before = timestamp + datetime.timedelta(microseconds=1)

        for e in events:
            e.occurred = timestamp

        store.update_events(events)

        es = store.get_events_by_timerange(before=before)

        self.assertEqual(es.count, len(events))

        last_id = None

        from_store = list(es)

        for e in from_store:
            self.assertEqual(e.occurred, timestamp)

            if last_id is None:
                last_id = e.id
            else:
                self.assertTrue(e.id < last_id)

        # pagination should also work
        es = store.get_events_by_timerange()

        expected = []

        # need to sort by ID
        for e in sorted(events, key=lambda x: x.id, reverse=True):

            d = e.dict()

            if e.related is not None:
                for r in d['related']:
                    r['feed'] = None

            expected.append(d)

        from_store = []

        for p in es.pages():

            from_store += [e.dict() for e in p]

        self.assertEqual(expected, from_store)

    def test_get_events_by_timerange_cursor(self):
        event_dicts, events = self._add_events()

        es = store.get_events_by_timerange()

        self.assertEqual(es.count, len(events))

        from_store = list(es)

        cursor = ByTimeRangeCursor(
            from_store[2].occurred,
            from_store[2].id
        )

        omitted = [e.id for e in from_store[:2]]

        es = store.get_events_by_timerange()

        count = 0

        for p in list(es.pages(cursor=cursor)):
            count += p.count

            for e in p:
                self.assertTrue(
                    (e.occurred, e.id) < (cursor.occurred, cursor.id)
                )
                self.assertTrue(e.id not in omitted)

        self.assertEqual(es.count - 3, count)

    def test_add_events(self):

        event_dicts, events = self._add_events()

        es = store.get_events_by_timerange()

        from_store = list(es)

        events_compare(self, event_dicts, from_store)

        index_check_documents(self, store, from_store)

    def test_add_events_dry(self):
        event_dicts, events = self._add_events(dry=True)

        es = store.get_events_by_timerange()

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

        from_store = es.page().events[0]

        self.assertEqual(len(from_store.related), 1)

        related_dict = related.dict()
        related_dict['feed'] = None

        self.assertEqual(from_store.related[0].dict(), related_dict)

        es = store.get_events_by_ids([related.id])

        related_from_store = es.page().events[0]

        self.assertIsNotNone(related_from_store.feed)

    def test_add_existing_event(self):
        event_dicts, events = self._add_events()

        existing = events[3]

        store.add_events([existing])

        es = store.get_events_by_timerange()

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

        es = store.get_events_by_timerange()

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

        es = store.get_events_by_timerange()

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

        es = store.get_events_by_timerange()

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

        es = store.get_events_by_timerange(feeds=[to_remove])

        self.assertEqual(es.count, 0)

        es = store.get_events_by_timerange()
        self.assertEqual(es.count, len(events) - len(removed))

        index_check_documents(self, store, removed, should_exist=False)

    def test_delete_events_by_list_dry(self):
        event_dicts, events = self._add_events()

        to_remove = events[3:5]

        store.remove_events(events=to_remove, dry=True)

        es = store.get_events_by_ids([e.id for e in to_remove])

        self.assertEqual(es.count, len(to_remove))

        es = store.get_events_by_timerange()

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

        es = store.get_events_by_timerange(flattened=True)

        self.assertGreater(es.count, len(events))

        store.remove_events(events=events)

        es = store.get_events_by_timerange(flattened=True)

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

        from_store = list(es)
        from_store.sort(key=lambda x: x.occurred)
        from_store = [e.dict() for e in from_store]

        expected = []

        for e in events:
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

    def test_get_all_with_timezone(self):
        event_dicts, events = self._add_events()

        tz = 'America/Toronto'

        es = store.get_events_by_timerange(timezone=tz)

        from_store = []

        # use pages to iterate
        for i in range(1, es.num_pages + 1):
            p = es.page()
            data = list(p)

            if i < es.num_pages:
                self.assertEqual(data[-1].occurred, p.next.occurred)

            from_store += [e.dict() for e in data]

        expected = []

        for e in events:
            new_event_dict = e.dict()
            to_pg_datetime_str(new_event_dict, 'occurred')

            # need to convert related as well
            if new_event_dict['related'] is not None:
                for r in new_event_dict['related']:
                    r['feed'] = None
                    to_pg_datetime_str(r, 'occurred')

            new_event = Event.from_dict(new_event_dict)  # need a copy
            new_event.localize(tz)
            expected.append(new_event)

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

        for _ in range(es.num_pages):
            for e in es.page():
                self.assertNotIn(e.feed['short_name'], unfiltered)

    def test_search_with_after(self):
        event_dicts, events = self._add_events()

        num = 1
        for d in event_dicts:
            d['title'] = 'changed to %d' % (num)
            num += 1

        events = [Event.from_dict(d) for d in event_dicts]

        store.update_events(events)

        es = store.get_events_by_search("changed")

        initial_count = len(events)

        self.assertEqual(es.count, initial_count)
        self.assertEqual(len(es), initial_count)

        after = datetime.datetime(2012, 2, 1, 0, 0, 0, 0)

        expected_num = 0

        for e in events:
            if e.occurred > after:
                expected_num += 1

        self.assertTrue(expected_num > 0)

        es = store.get_events_by_search("changed", after=after)

        # start using results to trigger reading of metadata, first page
        p = es.page()

        # add new event
        new_time = datetime.datetime(2012, 4, 24, 0, 0, 0, 0)

        event_dict = events_create_single(self._feeds[0], new_time)
        event_dict['title'] = 'changed to %d' % (num)

        e = Event.from_dict(event_dict)

        store.add_events([e])

        # original search should not contain the new event
        self.assertEqual(len(es), expected_num)

        for _ in range(es.num_pages):
            for e in es.page():
                self.assertTrue(e.occurred > after)

        # new search should include new event
        self.assertEqual(
            len(store.get_events_by_search("changed", after=after)),
            expected_num + 1
        )

    def test_search_with_before(self):
        event_dicts, events = self._add_events()

        num = 1
        for d in event_dicts:
            d['title'] = 'changed to %d' % (num)
            num += 1

        events = [Event.from_dict(d) for d in event_dicts]

        store.update_events(events)

        es = store.get_events_by_search("changed")

        initial_count = len(events)

        self.assertEqual(es.count, initial_count)
        self.assertEqual(len(es), initial_count)

        before = es.latest + datetime.timedelta(microseconds=1)

        # add new event

        new_time = datetime.datetime(2012, 4, 24, 0, 0, 0, 0)

        event_dict = events_create_single(self._feeds[0], new_time)
        event_dict['title'] = 'changed to %d' % (num)

        e = Event.from_dict(event_dict)

        store.add_events([e])

        # the same search would now also return the new entry
        es = store.get_events_by_search("changed")

        self.assertEqual(es.count, initial_count + 1)

        # with time limit it shouldn't
        es = store.get_events_by_search("changed", before=before)

        self.assertEqual(es.count, initial_count)
        self.assertEqual(len(es), initial_count)

        for _ in range(es.num_pages):
            for e in es.page():
                self.assertTrue(e.occurred != new_time)
                self.assertTrue(e.occurred < before)

    def test_search_with_before_and_filter(self):
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

        before = es.latest + datetime.timedelta(microseconds=1)

        # add new event

        new_time = datetime.datetime(2012, 4, 24, 0, 0, 0, 0)

        event_dict = events_create_single(self._feeds[2], new_time)
        event_dict['title'] = 'changed to %d' % (num)

        e = Event.from_dict(event_dict)

        store.add_events([e])

        # the same search would now also return the new entry
        es = store.get_events_by_search("changed", to_filter=to_filter)

        self.assertEqual(es.count, num_filtered + 1)

        # with time limit it shouldn't
        es = store.get_events_by_search(
            "changed",
            before=before,
            to_filter=to_filter
        )

        self.assertEqual(es.count, num_filtered)
        self.assertEqual(len(es), num_filtered)

        for _ in range(es.num_pages):
            for e in es.page():
                self.assertTrue(e.occurred != new_time)
                self.assertTrue(e.occurred < before)
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

        for _ in range(es.num_pages):
            for e in es.page():
                self.assertNotIn(e.feed['short_name'], to_mask)

    def test_search_invalid_page_number_past_first(self):
        es = store.get_events_by_search("changed")

        with self.assertRaises(InvalidPage):
            p = es.page(BySearchCursor(es.num_pages + 6))

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


if __name__ == '__main__':
    unittest.main()
