import unittest
import json
import datetime
import os
import shutil

import eventlog.lib.archiver

from mock import patch, Mock

TEMP_DIR = '../testarchiver'


class TestArchiver(unittest.TestCase):

    def setUp(self):
        # make tempdir
        os.makedirs(TEMP_DIR)

    def tearDown(self):
        shutil.rmtree(TEMP_DIR)

    def test_archiver_url_simple(self):
        url = "https://www.google.ca/?gws_rd=cr&ei=bbiWUo-PLM78oATPxYKgCA"
        expected = (
            "testarchiver/"
            "www.google.ca/index.html?gws_rd=cr&ei=bbiWUo-PLM78oATPxYKgCA.html"
        )

        res = eventlog.lib.archiver.archive_url(
            url, '../', 'testarchiver'
        )

        self.assertEqual(
            res,
            expected
        )

    def test_archiver_url_simple_dry(self):
        url = "https://www.google.ca/?gws_rd=cr&ei=bbiWUo-PLM78oATPxYKgCA"
        expected = (
            "testarchiver/index.html?gws_rd=cr&ei=bbiWUo-PLM78oATPxYKgCA.html"
        )

        res = eventlog.lib.archiver.archive_url(
            url, '../', 'testarchiver', dry=True
        )

        self.assertEqual(
            res,
            expected
        )

        self.assertEqual(os.path.exists('../' + expected), False)

    @patch('eventlog.lib.archiver.parse_localized_path')
    @patch('os.makedirs')
    @patch('subprocess.Popen')
    def test_archiver_directory_missing(
        self,
        mock_popen,
        mock_makedirs,
        mock_parse_localized_path
    ):

        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = Mock(), Mock()
        mock_process.returncode = 0

        url = 'http://test.local/thingy.html'

        res = eventlog.lib.archiver.archive_url(
            url, '../', 'doesntexist'
        )

        mock_makedirs.assert_called_with('../doesntexist')

    @patch('eventlog.lib.archiver.parse_localized_path')
    @patch('os.makedirs')
    @patch('subprocess.Popen')
    def test_archiver_directory_missing_makedirs_fail(
        self,
        mock_popen,
        mock_makedirs,
        mock_parse_localized_path
    ):

        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = Mock(), Mock()
        mock_process.returncode = 0

        mock_makedirs.side_effect = Exception

        url = 'http://test.local/thingy.html'

        res = eventlog.lib.archiver.archive_url(
            url, '../', 'doesntexist'
        )

        mock_makedirs.assert_called_with('../doesntexist')

        self.assertIsNone(res)

    @patch('eventlog.lib.archiver.parse_localized_path')
    @patch('os.makedirs')
    @patch('subprocess.Popen')
    def test_archiver_bad_returncode(
        self,
        mock_popen,
        mock_makedirs,
        mock_parse_localized_path
    ):

        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = Mock(), Mock()
        mock_process.returncode = 1

        url = 'http://test.local/thingy.html'

        res = eventlog.lib.archiver.archive_url(
            url, '../', 'doesntexist'
        )

        self.assertIsNone(res)

    @patch('eventlog.lib.archiver.parse_localized_path')
    @patch('os.makedirs')
    @patch('subprocess.Popen')
    def test_archiver_unable_to_determine_localized_path(
        self,
        mock_popen,
        mock_makedirs,
        mock_parse_localized_path
    ):

        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = Mock(), Mock()
        mock_process.returncode = 0

        mock_parse_localized_path.return_value = None

        url = 'http://test.local/thingy.html'

        res = eventlog.lib.archiver.archive_url(
            url, '../', 'doesntexist'
        )

        self.assertIsNone(res)

    def test_parse_localized_path_failure(self):
        res = eventlog.lib.archiver.parse_localized_path(b'')

        self.assertIsNone(res)


if __name__ == '__main__':
    unittest.main()
