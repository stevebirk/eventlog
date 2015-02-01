import unittest
import os.path
import shutil
import hashlib

from eventlog.lib.scraper import (fetch_url, get_largest_image, crop_image,
                                  image_url_to_file, save_img_to_dir,
                                  url_to_image, get_images_from_html,
                                  get_images, content_to_image_obj,
                                  get_thumbnail_from_url)

from mock import patch, Mock

from PIL import Image

TEMP_DIR = '2f'


class TestScraper(unittest.TestCase):

    def setUp(self):
        self.files_to_cleanup = []

    def tearDown(self):
        for filename in self.files_to_cleanup:
            if os.path.exists(filename):
                os.unlink(filename)

        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)

    @patch('httplib2.Http')
    def test_fetch_url(self, mock_http):

        resp = Mock()
        resp.get.return_value = 'image/png'

        instance = mock_http.return_value

        instance.request.return_value = (resp, '1234567')

        url = 'http://test.local/image.png'

        content_type, content = fetch_url(url)

        self.assertEqual(content_type, 'image/png')

    @patch('httplib2.Http')
    def test_fetch_url_missing_content_type(self, mock_http):

        resp = Mock()
        resp.get.return_value = None

        instance = mock_http.return_value

        instance.request.return_value = (resp, '1234567')

        url = 'http://test.local/image.png'

        content_type, content = fetch_url(url)

        self.assertEqual(content_type, 'image/png')

    @patch('httplib2.Http')
    def test_fetch_url_request_fail(self, mock_http):

        resp = Mock()
        resp.get.return_value = 'image/png'

        instance = mock_http.return_value

        instance.request.side_effect = Exception

        url = 'http://test.local/image.png'

        content_type, content = fetch_url(url)

        self.assertEqual(content_type, None)
        self.assertEqual(content, None)

    @patch('eventlog.lib.scraper.get_images')
    def test_get_largest_image(self, mock_get_images):
        image1 = Mock()
        image1.size = (100, 200)
        image1.tag = 'image1'

        image2 = Mock()
        image2.size = (200, 50)
        image2.tag = 'image2'

        image3 = Mock()
        image3.size = (200, 300)
        image3.tag = 'image3'

        images = [image1, image2, image3]

        mock_get_images.return_value = images

        largest = get_largest_image('foo', 50, 50)

        self.assertIsNotNone(largest)
        self.assertEqual(largest.tag, image3.tag)

        # getting largest from empty list
        mock_get_images.return_value = []

        largest = get_largest_image('foo', 50, 50)

        self.assertIsNone(largest)

        # ignoring too small images
        mock_get_images.return_value = [image1, image2]

        largest = get_largest_image('foo', 200, 200)

        self.assertIsNone(largest)

    def test_crop_image(self):

        test_image_path = os.path.join(
            os.path.dirname(__file__),
            '../data/image1.JPG'
        )
        image = Image.open(test_image_path)

        cropped = crop_image(image, 200, 200)

        self.assertEqual(cropped.size, (200, 200))

    @patch('eventlog.lib.scraper.SLICE_WIDTH', 10)
    def test_crop_image_even_slice_width(self):

        test_image_path = os.path.join(
            os.path.dirname(__file__),
            '../data/image1.JPG'
        )
        image = Image.open(test_image_path)

        cropped = crop_image(image, 200, 200)

        self.assertEqual(cropped.size, (200, 200))

    def test_image_url_to_file(self):
        url = "http://httpbin.org/image/jpeg"

        res = image_url_to_file(url, '.', '', 'testimg')

        self.assertIsNotNone(res)

        filename = res['path']

        self.files_to_cleanup.append(filename)

    @patch('urllib.urlretrieve')
    def test_image_url_to_file_bad_retrieve(self, mock_url_retrieve):
        def side_effect(url):
            raise Exception

        mock_url_retrieve.side_effect = side_effect

        url = "http://httpbin.org/image/jpeg"

        res = image_url_to_file(url, '.', '', 'testimg')

        self.assertIsNone(res)

    @patch('os.chmod')
    def test_image_url_to_file_change_permissions_error(self, mock_chmod):
        def side_effect(url):
            raise Exception

        mock_chmod.side_effect = side_effect

        url = "http://httpbin.org/image/jpeg"

        res = image_url_to_file(url, '.', '', 'testimg')

        self.assertIsNone(res)

    @patch('os.makedirs')
    def test_image_url_to_file_makedirs_error(self, mock_makedirs):
        def side_effect(url):
            raise Exception

        mock_makedirs.side_effect = side_effect

        url = "http://httpbin.org/image/jpeg"

        res = image_url_to_file(url, './blargh', '', 'testimg')

        self.assertIsNone(res)

    @patch('os.rename')
    def test_image_url_to_file_rename_error(self, mock_rename):
        def side_effect(url):
            raise Exception

        mock_rename.side_effect = side_effect

        url = "http://httpbin.org/image/jpeg"

        res = image_url_to_file(url, '.', '', 'testimg')

        self.assertIsNone(res)

    @patch('os.rename')
    @patch('os.makedirs')
    @patch('urllib.urlretrieve')
    def test_image_url_to_file_invalid_img(self,
                                           mock_url_retrieve,
                                           mock_makedirs,
                                           mock_rename):

        filename = 'badimage.jpeg'

        def side_effect(url):
            with open(filename, 'w') as fh:
                fh.write('abcd')

            return filename, None

        mock_url_retrieve.side_effect = side_effect

        url = "http://test.local/image.jpeg"

        res = image_url_to_file(url, '.', '', 'testimg')

        self.assertIsNone(res)

        self.files_to_cleanup.append(filename)

    def test_save_img_to_dir(self):
        test_image_path = os.path.join(
            os.path.dirname(__file__),
            '../data/image1.JPG'
        )
        image = Image.open(test_image_path)

        res = save_img_to_dir(image, '.', '')

        self.assertIsNotNone(res)

        filename = res['path']

        self.assertTrue(filename.endswith('.png'))

        self.files_to_cleanup.append(filename)

    def test_save_img_to_dir_use_original_format(self):
        test_image_path = os.path.join(
            os.path.dirname(__file__),
            '../data/image1.JPG'
        )
        image = Image.open(test_image_path)

        res = save_img_to_dir(image, '.', '', use_original_format=True)

        self.assertIsNotNone(res)

        filename = res['path']

        self.assertTrue(filename.endswith('.jpeg'))

        self.files_to_cleanup.append(filename)

    @patch('os.path.exists')
    def test_save_img_to_dir_already_exists(self, mock_exists):
        test_image_path = os.path.join(
            os.path.dirname(__file__),
            '../data/image1.JPG'
        )
        image = Image.open(test_image_path)

        image.save = Mock()

        mock_exists.return_value = True

        res = save_img_to_dir(image, '.', '')

        self.assertIsNotNone(res)

        self.assertEqual(image.save.call_count, 0)

    def test_save_img_to_dir_dry(self):
        test_image_path = os.path.join(
            os.path.dirname(__file__),
            '../data/image1.JPG'
        )
        image = Image.open(test_image_path)

        res = save_img_to_dir(image, '.', '', dry=True)

        self.assertIsNone(res)

        md5 = hashlib.md5(image.tostring()).hexdigest()

        filepath = os.path.join('.', '', md5[:2], md5 + '.png')

        self.assertFalse(os.path.exists(filepath))

    @patch('eventlog.lib.scraper.fetch_url')
    def test_url_to_image(self, mock_fetch_url):
        test_image_path = os.path.join(
            os.path.dirname(__file__),
            '../data/image1.JPG'
        )

        url = 'http://test.local/image.png'

        test_content = open(test_image_path).read()

        mock_fetch_url.return_value = ('image/jpeg', test_content)

        res = url_to_image(url)

        self.assertIsNotNone(res)

    @patch('eventlog.lib.scraper.fetch_url')
    def test_url_to_image_bad_url(self, mock_fetch_url):
        url = 'http://test.local/image.png'

        mock_fetch_url.return_value = ('image/jpeg', None)

        res = url_to_image(url)

        self.assertIsNone(res)

        mock_fetch_url.return_value = (None, 'abcd')

        res = url_to_image(url)

        self.assertIsNone(res)

    @patch('eventlog.lib.scraper.fetch_url')
    def test_url_to_image_not_image(self, mock_fetch_url):
        test_image_path = os.path.join(
            os.path.dirname(__file__),
            '../data/image1.JPG'
        )

        url = 'http://test.local/image.png'

        test_content = "{}"

        mock_fetch_url.return_value = ('application/json', test_content)

        res = url_to_image(url)

        self.assertIsNone(res)

    @patch('eventlog.lib.scraper.url_to_image')
    def test_get_images_from_html(self, mock_url_to_image):
        test_html = os.path.join(
            os.path.dirname(__file__),
            '../data/images.html'
        )

        test_content = open(test_html).read()

        mock_url_to_image.return_value = True

        url = 'http://test.local/image.png'

        images = get_images_from_html(test_content, url)

        self.assertEqual(len(images), 64)

    @patch('eventlog.lib.scraper.url_to_image')
    def test_get_images_from_html_with_bad_request(self, mock_url_to_image):
        test_html = os.path.join(
            os.path.dirname(__file__),
            '../data/images.html'
        )

        test_content = open(test_html).read()

        mock_url_to_image.side_effect = Exception

        url = 'http://test.local/image.png'

        images = get_images_from_html(test_content, url)

        self.assertEqual(mock_url_to_image.call_count, 1)
        self.assertEqual(len(images), 0)

    @patch('eventlog.lib.scraper.get_images_from_html')
    @patch('eventlog.lib.scraper.fetch_url')
    def test_get_images_called_with_html(self,
                                         mock_fetch_url,
                                         mock_get_images_from_html):

        url = 'http://test.local/image.png'
        content = "abcd"

        mock_fetch_url.return_value = ("text/html", content)

        res = get_images(url)

        mock_get_images_from_html.assert_called_with(content, url)

    @patch('eventlog.lib.scraper.content_to_image_obj')
    @patch('eventlog.lib.scraper.fetch_url')
    def test_get_images_called_with_image_url(self,
                                              mock_fetch_url,
                                              mock_content_to_image_obj):

        url = 'http://test.local/image.png'
        content = "abcd"

        mock_fetch_url.return_value = ("image/jpeg", content)
        mock_content_to_image_obj.return_value = True

        res = get_images(url)

        mock_content_to_image_obj.assert_called_with(content, url)

    @patch('eventlog.lib.scraper.fetch_url')
    def test_get_images_with_failed_fetch(self,
                                          mock_fetch_url):

        url = 'http://test.local/image.png'
        content = "abcd"

        mock_fetch_url.return_value = (None, content)

        res = get_images(url)

        self.assertEqual(len(res), 0)

        mock_fetch_url.return_value = ("text/plain", None)

        res = get_images(url)

        self.assertEqual(len(res), 0)

    def test_content_to_image_obj_invalid_content(self):
        url = 'http://test.local/image.png'

        res = content_to_image_obj("oijfewaois", url)

        self.assertIsNone(res)

    @patch('eventlog.lib.scraper.crop_image')
    @patch('eventlog.lib.scraper.get_largest_image')
    def test_get_thumbnail_from_url_with_crop(self,
                                              mock_get_largest_image,
                                              mock_crop_image):

        url = 'http://test.local/image.png'
        width, height = 200, 300

        image = Mock()
        image.size = 500, 500

        mock_get_largest_image.return_value = image

        get_thumbnail_from_url(url, width, height)

        mock_get_largest_image.assert_called_with(url, width, height)
        mock_crop_image.assert_called_with(image, width, height)

if __name__ == '__main__':
    unittest.main()
