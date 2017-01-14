import json
import datetime
import httplib2
import urllib.parse
import logging
import time
import re

from eventlog.lib.feeds import Feed, HTTPRequestFailure
from eventlog.lib.events import Event, Fields

_LOG = logging.getLogger(__name__)


def _get_id(link):

    m = re.search("/comments/([A-Za-z0-9]+)/", link)

    if m is None:
        m = re.search("/info/([A-Za-z0-9]+)/", link)

    return m.group(1)


class Reddit(Feed):

    key_field = Fields.TITLE

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = (
            "https://www.reddit.com/user/%s/liked.json?feed=%s&nocache=%d" % (
                self.config['username'],
                self.config['feed_key'],
                int(time.time())
            )
        )

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.link = urllib.parse.urljoin(
            'http://www.reddit.com', raw['data']['permalink']
        )
        e.title = raw['data']['title']
        e.occurred = datetime.datetime.utcnow()
        e.thumbnail_url = raw['data']['url']
        e.archive_url = raw['data']['url']
        e.raw = raw

        return e

    def init_parse_params(self, **kwargs):
        return self.url, None

    def parse(self, data):
        events = [self.to_event(link) for link in data["data"]["children"]]

        after_id = data['data']['after']
        next_url = None
        next_headers = None

        if after_id is not None:
            next_url = self.url + ("&after=%s" % (after_id))

        return events, next_url, next_headers
