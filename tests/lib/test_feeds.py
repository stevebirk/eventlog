import unittest
import datetime
import time
import json
import re
import copy
import tempfile
import shutil
import os.path

import httplib2

from eventlog.lib.feeds import Feed, HTTPRequestFailure
from eventlog.lib.events import Event, Fields, DATEFMT

from .util import events_create_single, events_create_fake, events_compare

from unittest.mock import patch, Mock

LATEST = time.time()
DELTA = 10*60
PAGES = 20
PER_PAGE = 10
STATUS = 200
LAST_URL = None
LAST_HEADERS = None


class MockHttpResponse:
    def __init__(self, status=200):
        self.status = status


class MockHttp:
    def __init__(self, *args, **kwargs):
        pass

    def request(self, url, method, **kwargs):
        global STATUS, LAST_URL, LAST_HEADERS

        LAST_URL = url
        LAST_HEADERS = kwargs.get('headers')

        if 'page' not in url:
            page = 1
        else:
            page = int(re.search('page=(\d+)', url).group(1))

        content = {
            'things': [
                {
                    'i': i,
                    't': 'title%d' % i,
                    'l': 'http://localhost/link%d' % i,
                    'time': LATEST - i*DELTA

                } for i in range((page-1)*PER_PAGE, page*PER_PAGE)
            ]
        }

        if (page + 1) <= PAGES:
            content.update({
                'pagination': {
                    'next': page + 1
                }
            })

        resp = MockHttpResponse(STATUS)

        return resp, json.dumps(content).encode('utf8')


class MockFeed(Feed):

    rate_limit = 100

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = "http://localhost/"

    def init_parse_params(self, **kwargs):
        return self.url, None

    def parse(self, data):

        events = [self.to_event(thing) for thing in data['things']]

        next_url = None
        if 'pagination' in data:
            page = data['pagination']['next']
            next_url = self.url + '?page=%d' % (page)

        return events, next_url, None

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = raw['t']
        e.link = raw['l']
        e.occurred = datetime.datetime.utcfromtimestamp(float(raw['time']))
        e.raw = raw

        return e


class MockFeedWithNonDateKey(MockFeed):
    key_field = Fields.TITLE


@patch('httplib2.Http', MockHttp)
class TestFeeds(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp_dir)

    def setUp(self):
        global STATUS

        self._feed = MockFeed({
            'overrides': {
                'media_dir': '/notreal/',
                'thumbnail_subdir': 'thumb',
                'thumbnail_height': 200,
                'thumbnail_width': 200,
                'original_subdir': 'orig',
                'archive_subdir': 'arch'
            },
            'flags': {
                'is_searchable': True,
                'is_public': True,
                'is_updating': True
            }
        })

        self._feed_non_date_key = MockFeedWithNonDateKey({
            'overrides': {
                'media_dir': '/notreal/',
                'thumbnail_subdir': 'thumb',
                'thumbnail_height': 200,
                'thumbnail_width': 200,
                'original_subdir': 'orig',
                'archive_subdir': 'arch'
            }
        })

        STATUS = 200

    def test_flag_attributes(self):
        self.assertTrue(self._feed.is_searchable)

        with self.assertRaises(AttributeError):
            self._feed.is_foo

    def test_date_key_iter_events_no_args(self):
        events = list(self._feed.iter_events())

        self.assertEqual(len(events), PER_PAGE*PAGES)

        # TODO: better verification

    def test_date_key_iter_events_rate_limited(self):
        # need to stub time.sleep, ensure that it is called
        # PAGES times with the correct argument

        with patch('time.sleep') as mock_sleep:
            events = list(self._feed.iter_events(rate_limit=True))

            self.assertEqual(mock_sleep.call_count, PAGES)
            self.assertEqual(len(events), PER_PAGE*PAGES)

    def test_date_key_fetch_no_args(self):
        events = self._feed.fetch()

        self.assertEqual(len(events), PER_PAGE*PAGES)

        # TODO: better verification

    def test_date_key_fetch_with_last_updated(self):
        last_updated = datetime.datetime.utcfromtimestamp(LATEST - 5 * DELTA)

        events = self._feed.fetch(last_updated=last_updated)

        self.assertEqual(len(events), 5)

    def test_non_date_key_with_last_key(self):

        self._feed.key_field = Fields.LINK

        last_key = "http://localhost/link5"

        self._feed.store = Mock()

        def mock_exists(key_name, key_value):
            if key_value == last_key and key_name == 'link':
                return True
            else:
                return False

        self._feed.store.exists = mock_exists

        events = self._feed.fetch(last_key=last_key)

        self.assertEqual(len(events), 5)

    def test_non_date_key_iter_events_no_args(self):
        # change feed key to non-DATE
        # iter_events should yield only the first page

        self._feed.key_field = Fields.LINK
        events = list(self._feed.iter_events())

        self.assertEqual(len(events), PER_PAGE)

    def test_non_date_key_iter_events_get_all(self):
        # change feed key to non-DATE
        self._feed.key_field = Fields.LINK

        events = list(self._feed.iter_events(all=True))
        self.assertEqual(len(events), PER_PAGE*PAGES)

    def test_group_events(self):

        self._feed.grouped = True
        self._feed.grouped_window = 60 * 60

        events = self._feed.fetch()

        self._feed.group(events)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].related), PER_PAGE*PAGES - 1)
        self.assertEqual(events[0].title, "title%d" % (PER_PAGE*PAGES - 1))

    def test_group_events_noop(self):

        events = self._feed.fetch()

        self._feed.group(events)

        self.assertEqual(len(events), PER_PAGE*PAGES)

    def test_group_events_with_latest_extra(self):
        extra_id = PER_PAGE*PAGES
        extra_raw = {
            'i': extra_id,
            't': 'title%d' % extra_id,
            'l': 'http://localhost/link%d' % extra_id,
            'time': LATEST - extra_id*DELTA
        }

        extra = self._feed.to_event(extra_raw)

        self._feed.grouped = True
        self._feed.grouped_window = 60 * 60

        events = self._feed.fetch()

        self._feed.group(events, latest_event=extra)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].related), PER_PAGE*PAGES)
        self.assertEqual(events[0].title, "title%d" % (extra_id))

    def test_group_events_multiple_groups(self):
        self._feed.grouped = True
        self._feed.grouped_window = 60 * 60

        events = self._feed.fetch()

        # spread out our events a bit, to generate
        # multiple groupings

        prev = None
        extra_days = 0
        unique_days = 0

        for e in events:
            day = e.occurred.strftime("%Y-%m-%d")

            if prev is None or day != prev:
                unique_days += 1
                extra_days += 60
                prev = day

            extra_delta = datetime.timedelta(days=extra_days)
            e.occurred -= extra_delta

        self._feed.group(events)

        # should be as many groups as there were unique days
        self.assertEqual(len(events), unique_days)

        # confirm all events are accounted for
        total = 0
        total += len(events)
        for e in events:
            total += len(e.related)

        self.assertEqual(total, PER_PAGE*PAGES)

    def test_load_no_files(self):
        events = self._feed.load()
        self.assertEqual(len(events), PER_PAGE*PAGES)

    def test_load_with_dumpfile(self):
        outpath = os.path.join(self._tmp_dir, 'testdump.json')

        events = self._feed.load(dumpfile=outpath)

        self.assertTrue(os.path.exists(outpath))

        # NOTE: during load event IDs are reset, so we need to remove them for
        #       the comparison

        from_file = []

        with open(outpath) as fh:
            for line in fh:
                data = json.loads(line)
                loaded = self._feed.to_event(data)
                loaded_dict = loaded.dict()
                del loaded_dict['id']
                from_file.append(loaded_dict)

        self.assertEqual(len(from_file), len(events))

        event_dicts = []
        for e in events:
            d = e.dict()
            del d['id']
            event_dicts.append(d)

        self.assertEqual(from_file, event_dicts)

    def test_load_with_loadfile(self):
        infile = os.path.join(self._tmp_dir, 'testload.json')

        conn = httplib2.Http()

        resp1, last_page = conn.request('page=' + str(PAGES), 'GET')
        resp2, second_last_page = conn.request('page=' + str(PAGES - 1), 'GET')

        with open(infile, 'w') as fh:
            fh.write(last_page.decode('utf-8') + '\n')
            fh.write(second_last_page.decode('utf-8') + '\n')

        events = self._feed.load(loadfile=infile)

        self.assertEqual(len(events), PER_PAGE*PAGES)

    def test_load_feed_with_non_date_key_with_loadfile(self):
        infile = os.path.join(self._tmp_dir, 'testload.json')

        conn = httplib2.Http()

        resp1, last_page = conn.request('page=' + str(PAGES), 'GET')
        resp2, second_last_page = conn.request('page=' + str(PAGES - 1), 'GET')

        with open(infile, 'w') as fh:
            fh.write(last_page.decode('utf-8') + '\n')
            fh.write(second_last_page.decode('utf-8') + '\n')

        self._feed_non_date_key.store = Mock()
        self._feed_non_date_key.store.exists.return_value = False

        events = self._feed_non_date_key.load(loadfile=infile)

        self.assertEqual(len(events), PER_PAGE*PAGES)

    def test_load_with_loadfile_and_dumpfile(self):
        # TODO: implement
        pass

    def test_to_dict(self):
        base_config = {
            'color': '012345',
            'favicon': 'img/source/testfeed.png',
            'short_name': 'testfeed',
            'full_name': 'TestFeed',
            'id': -1
        }

        config = copy.deepcopy(base_config)
        config['flags'] = {
            'flag1': True,
            'flag2': False,
            'flag3': True
        }
        config['overrides'] = {
            'key1': 'value1',
            'key2': 'value2'
        }
        config['module'] = 'testfeeds.testfeed'

        testfeed = MockFeed(config)

        base_dict = testfeed.dict()

        self.assertDictEqual(base_dict, base_config)

        urlized_dict = testfeed.dict(base_uri="/media/")
        urlized_config = copy.deepcopy(base_config)
        urlized_config['favicon'] = '/media/img/source/testfeed.png'

        self.assertDictEqual(urlized_dict, urlized_config)

        full_dict = testfeed.dict(admin=True)
        full_config = copy.deepcopy(base_config)
        full_config['config'] = {
            'key1': 'value1',
            'key2': 'value2'
        }
        full_config['flags'] = {
            'flag1': True,
            'flag2': False,
            'flag3': True
        }
        full_config['module'] = 'testfeeds.testfeed'

        self.assertDictEqual(full_dict, full_config)

    def test_get_key_func(self):
        e_raw = {
            't': 'title0',
            'l': 'http://localhost/link0',
            'time': time.time()
        }

        e = self._feed.to_event(e_raw)

        # test date keyed feed
        date_key_func = self._feed.get_key_func()

        self.assertEqual(date_key_func(e), e.occurred.strftime(DATEFMT))

        # test non-date keyed feed
        self._feed.key_field = Fields.LINK

        non_date_key_func = self._feed.get_key_func()

        self.assertEqual(non_date_key_func(e), 'http://localhost/link0')

    def test_update_no_latest_no_media(self):
        self._feed.store = Mock()
        self._feed.store.get_events_by_latest()
        self._feed.store.get_events_by_latest.return_value = None
        self._feed.store.add_events()

        added = self._feed.update()

        # confirm what is passed to add_events makes sense
        self.assertEqual(
            len(self._feed.store.add_events.call_args[0][0]),
            PER_PAGE*PAGES
        )

        self.assertFalse(
            self._feed.store.add_events.call_args[1]['dry']
        )

        self.assertEqual(added, PER_PAGE*PAGES)

    def test_update_with_latest_no_media(self):
        e_raw = {
            't': 'title5',
            'l': 'http://localhost/link5',
            'time': LATEST - 5*DELTA
        }

        e = self._feed.to_event(e_raw)

        self._feed.store = Mock()
        self._feed.store.get_events_by_latest()
        self._feed.store.get_events_by_latest.return_value = e
        self._feed.store.add_events()

        added = self._feed.update()

        # confirm what is passed to add_events makes sense
        self.assertEqual(
            len(self._feed.store.add_events.call_args[0][0]),
            5
        )

        self.assertFalse(
            self._feed.store.add_events.call_args[1]['dry']
        )

        self.assertEqual(added, 5)

    def test_update_with_exception(self):
        self._feed.store = Mock()
        self._feed.store.get_events_by_latest()
        self._feed.store.get_events_by_latest.return_value = None
        self._feed.store.add_events()

        def bad_fetch(*args, **kwargs):
            raise Exception('bad fetch!')

        self._feed.fetch = bad_fetch

        added = self._feed.update()

        self.assertEqual(added, 0)

    def test_iter_events_with_bad_http_status(self):
        global STATUS

        STATUS = 400

        with self.assertRaises(HTTPRequestFailure):
            list(self._feed.iter_events())

        STATUS = 500

        with self.assertRaises(HTTPRequestFailure):
            list(self._feed.iter_events())

    def test_iter_events_with_retry_url_and_headers(self):
        retry_url = "foo"
        retry_headers = {"foo": "bar"}

        with patch.object(self._feed, 'parse_status') as mock_parse_status:
            mock_parse_status.side_effect = [
                (True, retry_url, retry_headers), (False, None, None)
            ]

            # trigger first page load
            for i in self._feed.iter_events():
                break

            self.assertEqual(LAST_URL, retry_url)
            self.assertDictEqual(LAST_HEADERS, retry_headers)

    def test_to_str(self):
        self.assertEqual(str(self._feed), str(self._feed.dict(admin=True)))

if __name__ == '__main__':
    unittest.main()
