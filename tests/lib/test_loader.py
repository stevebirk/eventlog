import unittest

from eventlog.lib.loader import load
from eventlog.lib.feeds import Feed

from unittest.mock import patch, Mock

from util import feeds_create_fake

import feed_generator


class TestLoader(unittest.TestCase):

    def test_load_feeds(self):
        num_to_create = feed_generator.MAX_NUM

        fake_feeds = [
            feeds_create_fake(i, 'feed_generator')
            for i in range(num_to_create)
        ]
        config = {
            f['module']: {} for f in fake_feeds
        }

        loaded_feeds = load(Feed, config, store=None, timezone='UTC')

        self.assertEqual(len(loaded_feeds), num_to_create)

    def test_load_feeds_exclude_via_config(self):
        num_to_create = feed_generator.MAX_NUM

        fake_feeds = [
            feeds_create_fake(i, 'feed_generator')
            for i in range(num_to_create)
        ]
        config = {
            f['module']: {} for f in fake_feeds
        }

        to_exclude = 3

        for key in list(config.keys())[:to_exclude]:
            del config[key]

        loaded_feeds = load(Feed, config, store=None, timezone='UTC')

        self.assertEqual(len(loaded_feeds), num_to_create - to_exclude)

    @patch('builtins.__import__')
    def test_load_with_import_error(self, mock_import):
        class Test(object):
            pass

        mock_import.side_effect = Exception

        loaded = load(Test, {'test_name': {}})

        self.assertEqual(len(loaded), 0)

    @patch('builtins.__import__')
    def test_load_with_instantiation_error(self, mock_import):
        class Test(object):
            pass

        class Subclass(Test):
            def __init__(self, *args, **kwargs):
                raise Exception

        loaded = load(Test, {'test_loader': {}})

        self.assertEqual(len(loaded), 0)

    @patch('builtins.__import__')
    def test_load_with_subclass_not_in_config(self, mock_import):
        class Test(object):
            pass

        class Subclass(Test):
            def __init__(self, *args, **kwargs):
                raise Exception

        loaded = load(Test, {'abcd': {}})

        self.assertEqual(len(loaded), 0)


if __name__ == '__main__':
    unittest.main()
