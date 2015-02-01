import json
import datetime
import httplib2
import urlparse
import logging
import time
import re

from eventlog.lib.feeds import Feed, HTTPRequestFailure
from eventlog.lib.events import Event, fields

_LOG = logging.getLogger(__name__)


def _get_id(link):

    m = re.search("/comments/([A-Za-z0-9]+)/", link)

    if m is None:
        m = re.search("/info/([A-Za-z0-9]+)/", link)

    return m.group(1)


class Reddit(Feed):

    key_field = fields.TITLE

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = (
            "http://www.reddit.com/user/%s/liked.json?feed=%s&nocache=%d" % (
                self.config['username'],
                self.config['feed_key'],
                int(time.time())
            )
        )

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.link = urlparse.urljoin(
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

    def deep_search(self, e, existing):

        trimmed = e.title[:200]

        if trimmed in existing:
            return trimmed
        else:

            for key, val in existing.items():
                if e.link == val.link:
                    return key

        return None

    def find_missing(self, missing):

        h = httplib2.Http()

        url = missing.link + '.json'

        entry = None

        # try loading from URL if we have no match
        if entry is None:

            try:
                resp, content = h.request(url, "GET")

                if resp.status != 200:
                    raise HTTPRequestFailure(
                        'received non-200 status %s:\n%s' % (
                            str(resp.status),
                            content
                        )
                    )

                parsed = json.loads(content)

                entry = parsed[0]['data']['children'][0]

                time.sleep(1)

            except Exception:
                _LOG.exception('unable to fetch %s', missing.link)
                entry = None

        if entry is not None:
            e = self.to_event(entry)

            _LOG.debug('found missing event %s', missing.link)
            return e

        return None
