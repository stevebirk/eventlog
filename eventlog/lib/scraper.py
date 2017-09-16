import sys
import os
import os.path
import pprint
import math
import logging
import urllib.parse
import mimetypes
import hashlib
import urllib.request
import urllib.parse
import urllib.error
import httplib2

from bs4 import BeautifulSoup, SoupStrainer

from PIL import Image
from io import BytesIO

SLICE_WIDTH = 5

_LOG = logging.getLogger(__name__)

# prevent memory issues with very large images
Image.warnings.simplefilter('error', Image.DecompressionBombWarning)


def fetch_url(url):

    try:
        h = httplib2.Http()
        resp, content = h.request(url, "GET")
    except Exception:
        _LOG.exception("unable to fetch url: %s", repr(url))
        return None, None

    # need to check content type for either
    # a) html -> parse page and get imgs
    # b) image -> return raw image

    # retrieve and require a content type
    content_type = resp.get('content-type')
    if not content_type:

        # try and determine it from url
        content_type, _ = mimetypes.guess_type(url)

    return content_type, content


def image_url_to_file(url, rootdir, subdir, fileprefix, dry=False):

    # download file to temporary location
    try:
        tmpfile, headers = urllib.request.urlretrieve(url)
    except Exception:
        _LOG.exception("unable to fetch url: %s", repr(url))
        return None

    # verify file is an image, and get its size
    try:
        img = Image.open(tmpfile)

        size = img.size

        # is it valid?
        img.verify()

        img.close()
    except Exception:
        _LOG.exception("unable to verify image from url: %s", repr(url))
        return None

    # change ownerships (urlretrieve seems to set funny ones)
    try:
        os.chmod(tmpfile, 0o664)
    except Exception:
        _LOG.exception("unable to set reasonable file permissions")
        return None

    target_dir = os.path.join(rootdir, subdir)

    # create filepath if it doesn't exist
    if (not dry) and (not os.path.exists(target_dir)):
        try:
            os.makedirs(target_dir)
        except Exception:
            _LOG.exception(
                'unable to create target directory for file: %s', target_dir
            )
            return None

    # use urlparse here to avoid issues with possible query parameters and/or
    # fragment
    filesuffix = os.path.splitext(urllib.parse.urlparse(url).path)[-1]

    destination = os.path.join(target_dir, fileprefix + filesuffix)

    # move file to destination
    _LOG.info("saving image '%s'", destination)
    if not dry:
        try:
            os.rename(tmpfile, destination)
        except Exception:
            _LOG.exception(
                'unable to move file to destination: %s', destination
            )
            return None

    staticpath = os.path.join(subdir, fileprefix + filesuffix)

    # if dry=True the tmpfile will be cleaned up automatically

    return {
        'path': staticpath,
        'size': dict(zip(('width', 'height'), size))
    }


def url_to_image(url):
    content_type, content = fetch_url(url)

    if content_type is None or content is None:
        return None

    if 'image' in content_type:
        return content_to_image_obj(content, url)
    else:
        return None


def content_to_image_obj(content, url):

    try:
        im = Image.open(BytesIO(content))

        # is it valid?
        im.verify()

        # reset file
        im = Image.open(BytesIO(content))
    except Exception:
        _LOG.exception("unable to verify image from url: %s", repr(url))
        im = None

    return im


def get_images_from_html(content, url):

    try:
        soup = BeautifulSoup(content, 'lxml', parse_only=SoupStrainer("img"))

        # grab img tags
        image_tags = soup.find_all('img', src=True)

        # NOTE: special case for imgur (so far)
        image_datasrc_tags = soup.find_all('img', attrs={'data-src': True})

        uris = []
        uris += [t['src'] for t in image_tags]
        uris += [t['data-src'] for t in image_datasrc_tags]

        images = []
        for uri in uris:
            if uri.startswith('data:'):  # ignore binary encoded data uri's
                continue

            image_url = urllib.parse.urljoin(url, uri)

            image = url_to_image(image_url)

            if image:
                images.append(image)

        return images

    except Exception:
        _LOG.exception(
            "unable to parse images from html from url: %s", repr(url)
        )
        return []


def get_images(url):

    images = []

    content_type, content = fetch_url(url)

    if content_type is None or content is None:
        return images

    if 'html' in content_type:
        # use beautiful soup to find images on the page
        images = get_images_from_html(content, url)

    elif 'image' in content_type:
        # parse content as image, use it
        image = content_to_image_obj(content, url)

        if image is not None:
            images = [image]

    return images


def get_largest_image(url, min_width, min_height):

    images = get_images(url)

    if not len(images):
        return None

    max_area = 0
    max_im = None

    for image in images:
        width, height = image.size
        area = width * height

        if width < min_width or height < min_height:
            continue

        if area > max_area:
            max_area = area
            max_im = image

    return max_im


def get_thumbnail_from_url(url, width, height):

    image = get_largest_image(url, width, height)

    if image is not None:

        image_width, image_height = image.size

        if image_width > width or image_height > height:
            image = crop_image(image, width, height)

    return image


def image_entropy(img):
    # calculate the entropy of an image
    hist = img.histogram()
    hist_size = sum(hist)
    hist = [float(h) / hist_size for h in hist]

    return -sum([p * math.log(p, 2) for p in hist if p != 0])


def crop_image(img, width, height):

    # crop vertically
    x, y = img.size

    while y > height:
        slice_height = min(y - height, SLICE_WIDTH)

        bottom = img.crop((0, y - slice_height, x, y))
        top = img.crop((0, 0, x, slice_height))

        top_entr = image_entropy(top)
        bottom_entr = image_entropy(bottom)

        # remove the slice with the least entropy
        if bottom_entr and abs(top_entr / bottom_entr - 1) < 0.01:
            # less than 1% difference between the two,
            # chop off slice_height/2 from both
            half_slice = slice_height // 2

            if half_slice * 2 == slice_height:
                img = img.crop((0, half_slice, x, y - half_slice))
            else:
                extra = slice_height % 2
                img = img.crop((0, half_slice + extra, x, y - half_slice))

        elif bottom_entr < top_entr:
            img = img.crop((0, 0, x, y - slice_height))
        else:
            img = img.crop((0, slice_height, x, y))

        x, y = img.size

    # crop horizontally
    while x > width:
        slice_width = min(x - width, SLICE_WIDTH)

        # L, T, R, B
        left = img.crop((0, 0, slice_width, y))
        right = img.crop((x - slice_width, 0, x, y))

        left_entr = image_entropy(left)
        right_entr = image_entropy(right)

        # remove the slice with the least entropy
        if right_entr and abs(left_entr / right_entr - 1) < 0.01:
            # less than 1% difference between the two,
            # chop off slice_height/2 from both
            half_slice = slice_width // 2

            if half_slice * 2 == slice_width:
                img = img.crop((half_slice, 0, x - half_slice, y))
            else:
                extra = slice_width % 2
                img = img.crop((half_slice + extra, 0, x - half_slice, y))

        elif left_entr < right_entr:
            img = img.crop((slice_width, 0, x, y))
        else:
            img = img.crop((0, 0, x - slice_width, y))

        x, y = img.size

    return img


def save_img_to_dir(img, rootdir, subdir, dry=False,
                    file_suffix=None, use_original_format=False):

    # determine format to save image as
    img_format = "PNG"

    # use original format if specified and possible
    if use_original_format and img.format is not None:
        img_format = img.format

    # generate MD5 hash from image
    md5 = hashlib.md5(img.tobytes()).hexdigest()

    # create filepath from hash
    filepath = os.path.join(rootdir, subdir, md5[:2])

    # create filepath if it doesn't exist
    if (not dry) and (not os.path.exists(filepath)):
        os.makedirs(filepath)

    # determine file name suffix
    suffix = file_suffix
    if suffix is None:
        suffix = '.' + img_format.lower()

    # generate full filename (including path)
    filename = os.path.join(filepath, md5 + suffix)

    # thumbnail path
    staticpath = os.path.join(subdir, md5[:2], md5 + suffix)

    if not os.path.exists(filename):
        _LOG.info("saving image '%s'", filename)
        if not dry:
            img.save(filename, img_format, quality=95)
    else:
        _LOG.info("image file matching MD5 '%s' already exists", md5)

    if dry:
        metadata = None
    else:
        metadata = {
            'path': staticpath,
            'size': dict(zip(('width', 'height'), img.size))
        }

    return metadata
