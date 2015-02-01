import unittest

from eventlog.lib.util import urlize


class TestUtil(unittest.TestCase):

    def test_target_is_none(self):
        self.assertIsNone(urlize(None, '/foo/'))

    def test_key_doesnt_exist(self):
        self.assertIsNone(urlize({}, '/foo/', key='foo'))

if __name__ == '__main__':
    unittest.main()
