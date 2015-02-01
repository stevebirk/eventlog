import datetime
import re

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, fields


class Dribbble(Feed):

    key_field = fields.LINK

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = 'http://api.dribbble.com/players/%s/shots/likes' % (
            self.config['username']
        )

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = raw['title']
        e.link = raw['url']
        e.occurred = datetime.datetime.utcnow()
        e.thumbnail_url = raw['url']
        e.original_url = raw.get('image_url')
        e.raw = raw

        return e

    def init_parse_params(self, **kwargs):
        return self.url, None

    def parse(self, data):
        events = [self.to_event(shot) for shot in data['shots']]

        num_shots_returned = len(data['shots'])
        next_page = int(data['page']) + 1
        next_url = None
        next_headers = None

        if num_shots_returned > 0:
            next_url = self.url + ("?page=%d" % (next_page))

        return events, next_url, next_headers

    def deep_search(self, e, existing):

        post_id = re.search("(.*?)-", e.link).group(1)

        for key in existing:
            if post_id in key:
                return key

        return None
