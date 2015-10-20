import unittest
import datetime
import pytz
import simplejson as json

from eventlog.lib.events import (Event, _Field, _Fields, fields, DATEFMT,
                                 UnableToRetrieveImageException)
from eventlog.lib.util import pg_strptime, tz_unaware_utc_dt_to_local
from eventlog.lib.store.search import _SCHEMA

from util import feeds_create_fake, events_create_fake, events_compare
from util import events_create_single

from mock import patch, Mock

import feed_generator


class TestEvents(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._feeds = [
            feeds_create_fake(i, 'feed_generator')
            for i in range(feed_generator.MAX_NUM)
        ]

    def test_init_empty_fields(self):
        empty = _Fields()

    def test_in_fields(self):
        f = _Field('foo')
        link = _Field('link')

        self.assertFalse(f in fields)
        self.assertTrue(link in fields)

    def test_from_dict(self):
        distribution = [(json.dumps(feed), 1) for feed in self._feeds]

        event_dicts = events_create_fake(
            distribution,
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
            datetime.datetime(2012, 3, 24, 0, 0, 0, 0)
        )

        events = [Event.from_dict(d) for d in event_dicts]

        for e in events:
            if e.related is not None:
                for r in e.related:
                    r.feed = None

        events_compare(self, event_dicts, events)

    def test_get_latest_occurred_with_related(self):

        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
            num_related=10
        )

        expected = event_dict['related'][-1]['occurred']
        expected = pg_strptime(expected)

        e = Event.from_dict(event_dict)

        self.assertEqual(
            expected,
            e.latest_occurred
        )

    def test_get_latest_occurred_without_related(self):

        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        expected = event_dict['occurred']
        expected = pg_strptime(expected)

        e = Event.from_dict(event_dict)

        self.assertEqual(
            expected,
            e.latest_occurred
        )

    @patch('eventlog.lib.events.save_img_to_dir')
    @patch('eventlog.lib.events.get_thumbnail_from_url')
    def test_add_thumbnail(self, mock_get_thumb, mock_save_thumb):

        thumb = {
            'path': 'img/test.png',
            'size': {
                'width': 200,
                'height': 200
            }
        }

        mock_get_thumb.return_value = 1  # just needs to be not None
        mock_save_thumb.return_value = thumb

        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        e = Event.from_dict(event_dict)
        e.thumbnail_url = 'http://localhost/test/'

        e.add_thumbnail(
            200,
            200,
            '/path/to/test/',
            'img'
        )

        self.assertIsNotNone(e.thumbnail)

        self.assertDictEqual(
            e.thumbnail,
            thumb
        )

        mock_get_thumb.return_value = None

        e.thumbnail = None

        e.add_thumbnail(
            200,
            200,
            '/path/to/test/',
            'img'
        )

        self.assertIsNone(e.thumbnail)

    def test_add_thumbnail_no_url(self):
        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        e = Event.from_dict(event_dict)

        e.add_thumbnail(200, 200, '/tmp/doesntexist', 'notthere')

        self.assertIsNone(e.thumbnail)

    @patch('eventlog.lib.events.image_url_to_file')
    def test_add_original(self, mock_image_url_to_file):

        orig = {
            'path': 'img/test.png',
            'size': {
                'width': 1200,
                'height': 600
            }
        }

        mock_image_url_to_file.return_value = orig

        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        e = Event.from_dict(event_dict)
        e.original_url = 'http://localhost/test/'

        e.add_original(
            '/path/to/test/',
            'img'
        )

        self.assertIsNotNone(e.original)

        self.assertDictEqual(
            e.original,
            orig
        )

        # if image download fails, should raise exception
        mock_image_url_to_file.return_value = None

        e.original = None

        self.assertRaises(
            UnableToRetrieveImageException,
            e.add_original,
            '/path/to/test/',
            'img'
        )

    def test_add_original_no_url(self):
        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        e = Event.from_dict(event_dict)

        e.add_original('/tmp/doesntexist', 'notthere')

        self.assertIsNone(e.original)

    @patch('eventlog.lib.events.archive_url')
    def test_add_archive(self, mock_archive):
        arch = 'arch/path/to/index.html'

        mock_archive.return_value = arch

        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        e = Event.from_dict(event_dict)
        e.archive_url = 'http://localhost/test/'

        e.add_archive(
            '/path/to/test/',
            'arch'
        )

        self.assertIsNotNone(e.archived)

        self.assertDictEqual(
            e.archived,
            {
                'path': arch
            }
        )

        mock_archive.return_value = None
        e.archived = None

        e.add_archive(
            '/path/to/test/',
            'arch'
        )

        self.assertIsNone(e.archived)

    def test_add_archive_no_url(self):
        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        e = Event.from_dict(event_dict)

        e.add_archive('/tmp/doesntexist', 'notthere')

        self.assertIsNone(e.archived)

    def test_add_related(self):
        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        e = Event.from_dict(event_dict)

        related_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 10, 0, 0),
        )

        r = Event.from_dict(related_dict)

        e.add_related(r)

        self.assertIsNotNone(e.related)
        self.assertEqual(len(e.related), 1)
        self.assertDictEqual(
            e.related[0].dict(),
            r.dict()
        )

    def test_compare_two_fields(self):
        foo = _Field('foo')
        bar = _Field('bar')
        jazz = _Field('foo')

        self.assertTrue(foo != bar)
        self.assertFalse(foo == bar)
        self.assertTrue(foo == jazz)

    def test_get_field_str(self):
        foo = _Field('foo')

        self.assertEqual('foo', str(foo))

    def test_field_get_from(self):
        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
        )

        e = Event.from_dict(event_dict)

        link = _Field('link')

        self.assertEqual(
            link.get_from(e),
            e.link
        )

    def test_to_dict(self):

        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
            has_original=True,
            has_archived=True,
            has_thumbnail=True,
            num_related=5,
            text=True,
            title=True
        )

        e = Event.from_dict(event_dict)

        def compare_dict_to_event(d, e, is_related=False):
            # verify keys valid for both parent and children events
            keys = [
                'title', 'text', 'link',
                'archived', 'original', 'thumbnail', 'raw'
            ]

            if not is_related:
                keys.append('feed')

            for key in keys:
                self.assertEqual(
                    getattr(e, key),
                    d[key]
                )

            if is_related:
                self.assertIsNone(d['feed'])

            self.assertEqual(
                e.occurred.strftime(DATEFMT),
                d['occurred']
            )

            self.assertEqual(
                len(list(d.keys())),
                11
            )

        d = e.dict()

        compare_dict_to_event(d, e)

        for index, r in enumerate(e.related):
            compare_dict_to_event(d['related'][index], r)

        # test urlized dict

        d = e.dict(base_uri='/foo/')

        # the same, but just make sure paths are correct
        self.assertTrue(e.feed['favicon'].startswith('/foo/'))

        for e in [e] + e.related:
            self.assertTrue(e.thumbnail['path'].startswith('/foo/'))
            self.assertTrue(e.original['path'].startswith('/foo/'))
            self.assertTrue(e.archived['path'].startswith('/foo/'))

    def test_to_dict_related_count(self):
        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
            has_original=True,
            has_archived=True,
            has_thumbnail=True,
            num_related=5,
            text=True,
            title=True
        )

        e = Event.from_dict(event_dict)

        d = e.dict(related_count_only=True)

        self.assertEqual(d['related'], 5)

    def test_documents(self):
        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
            num_related=5
        )

        e = Event.from_dict(event_dict)

        docs = e.documents

        self.assertEqual(len(docs), 6)

        for d in e.documents:
            for f in _SCHEMA.names():
                self.assertTrue(f in d)

    def test_localize_from_naive(self):
        naive_utc_dt = datetime.datetime(2012, 1, 12, 0, 0, 0, 0)

        event_dict = events_create_single(
            self._feeds[0],
            naive_utc_dt,
            num_related=5
        )

        tz_name = 'America/Toronto'
        tz = pytz.timezone('America/Toronto')

        e = Event.from_dict(event_dict)

        related_naive_utc_dts = [r.occurred for r in e.related]
        local_related_dts = [
            tz_unaware_utc_dt_to_local(dt, tz) for dt in related_naive_utc_dts
        ]

        e.localize(tz_name)

        aware_local_dt = e.occurred

        self.assertEqual(
            tz_unaware_utc_dt_to_local(naive_utc_dt, tz),
            aware_local_dt
        )

        self.assertListEqual(
            local_related_dts,
            [r.occurred for r in e.related]
        )

    def test_to_str(self):
        event_dict = events_create_single(
            self._feeds[0],
            datetime.datetime(2012, 1, 12, 0, 0, 0, 0),
            num_related=5
        )

        e = Event.from_dict(event_dict)

        s = str(e)

        if e.link is not None:
            self.assertTrue('link' in s)

        if e.title is not None:
            self.assertTrue('title' in s)

        if e.text is not None:
            self.assertTrue('text' in s)

if __name__ == '__main__':
    unittest.main()
