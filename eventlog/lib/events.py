import os.path
import logging
import pytz
import uuid
import datetime

from .scraper import (get_thumbnail_from_url, save_img_to_dir, url_to_image,
                      image_url_to_file)
from .archiver import archive_url
from .util import tz_unaware_utc_dt_to_local, pg_strptime, urlize

DATEFMT = '%Y-%m-%d %H:%M:%S.%f%z'

_LOG = logging.getLogger(__name__)


class InvalidField(Exception):
    pass


class MissingEventIdException(Exception):
    pass


class UnableToRetrieveImageException(Exception):
    pass


class _Field(object):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return str(self) != str(other)

    def get_from(self, e):
        return getattr(e, self.name)


class _Fields(object):
    def __init__(self, fields=None):
        if fields is None:
            fields = []

        for field in fields:
            setattr(self, field.upper(), _Field(field))

    def __contains__(self, item):
        return hasattr(self, str(item).upper())

fields = _Fields(fields=['occurred', 'title', 'text', 'link'])


class Event(object):
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.title = None
        self.text = None
        self.link = None
        self.occurred = None
        self.feed = None
        self.raw = None
        self.related = None

        self.thumbnail = None
        self.thumbnail_url = None

        self.original = None
        self.original_url = None

        self.archived = None
        self.archive_url = None

    @classmethod
    def from_dict(cls, d):
        e = cls()
        e.id = d.get('id')
        e.title = d.get('title')
        e.text = d.get('text')
        e.link = d.get('link')

        e.occurred = pg_strptime(d.get('occurred'))

        e.feed = d.get('feed')

        e.raw = d.get('raw')
        e.thumbnail = d.get('thumbnail')
        e.original = d.get('original')
        e.archived = d.get('archived')

        if d.get('related') is not None:
            e.related = []

            for r in d['related']:
                e.related.append(Event.from_dict(r))

        return e

    def dict(self, base_uri=None, related_count_only=False):
        d = {
            'id': self.id,
            'title': self.title,
            'text': self.text,
            'link': self.link,
            'occurred': self.occurred.strftime(DATEFMT),
            'feed': self.feed,
            'raw': self.raw,
            'thumbnail': self.thumbnail,
            'original': self.original,
            'archived': self.archived,
            'related': None
        }

        if base_uri is not None:
            urlize(d['feed'], base_uri, key='favicon')
            urlize(d['thumbnail'], base_uri, key='path')
            urlize(d['original'], base_uri, key='path')
            urlize(d['archived'], base_uri, key='path')

        if self.related is not None:
            if related_count_only:
                d['related'] = len(self.related)
            else:
                d['related'] = []
                for r in self.related:
                    d['related'].append(r.dict(base_uri=base_uri))

        return d

    @property
    def documents(self):

        docs = [{
            'id': unicode(self.id),
            'feed': unicode(self.feed['short_name']),
            'title': unicode(self.title),
            'text': unicode(self.text)
        }]

        # add any related documents
        if self.related is not None:
            for r in self.related:
                docs.append({
                    'id': unicode(r.id),
                    'feed': unicode(self.feed['short_name']),
                    'title': unicode(r.title),
                    'text': unicode(r.text),
                })

        return docs

    @property
    def latest_occurred(self):
        if self.related is None:
            return self.occurred
        else:
            return self.related[-1].occurred

    def localize(self, timezone):
        tz = pytz.timezone(timezone)

        # localize this event
        self.occurred = tz_unaware_utc_dt_to_local(self.occurred, tz)

        # localize any related events
        if self.related is not None:

            for child in self.related:
                child.localize(timezone)

    def add_thumbnail(self, width, height, staticroot, subdir, dry=False):

        if self.thumbnail_url is None:
            _LOG.debug('no image URL provided')
            return

        _LOG.debug('using image URL: %s', self.thumbnail_url)

        img = get_thumbnail_from_url(self.thumbnail_url, width, height)

        if img is not None:
            self.thumbnail = save_img_to_dir(img, staticroot, subdir, dry=dry)
        else:
            _LOG.info(
                'unable to find suitable thumbnail image from URL: %s',
                self.thumbnail_url
            )

    def add_original(self, staticroot, subdir, dry=False):

        if self.original_url is None:
            _LOG.debug('no original image URL provided')
            return

        _LOG.debug('using original image URL: %s', self.original_url)

        original = image_url_to_file(
            self.original_url,
            staticroot,
            os.path.join(subdir, str(self.id)[:2]),
            str(self.id),
            dry=dry
        )

        if original is not None:
            self.original = original
        else:
            raise UnableToRetrieveImageException(
                'unable to download original image from URL: %s' % (
                    self.original_url
                )
            )

    def add_archive(self, staticroot, subdir, dry=False):

        if self.archive_url is None:
            _LOG.debug('no archive URL provided')
            return

        _LOG.debug('using archive URL: %s', self.archive_url)

        archived_path = archive_url(
            self.archive_url,
            staticroot,
            os.path.join(subdir, str(self.id)[:2], str(self.id)),
            dry=dry
        )

        if archived_path is not None:
            self.archived = {
                'path': archived_path
            }

    def add_related(self, child):

        if self.related is None:
            self.related = []

        # children should have no related
        child.related = None

        # add new child to related
        self.related.append(child)

    def __str__(self):
        fields = ['title', 'link', 'text']
        values = [self.title, self.link, self.text]

        return ", ".join([
            "%s=%s..." % (field, val[:50])
            for field, val in zip(fields, values) if val is not None
        ])
