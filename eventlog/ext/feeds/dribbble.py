import datetime
import re

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, Fields


class Dribbble(Feed):

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = 'https://api.dribbble.com/v1/users/%s/likes' % (
            self.config['username']
        )

        # OAuth
        self._CLIENT_ID = self.config['oauth2_client_id']
        self._CLIENT_SECRET = self.config['oauth2_client_secret']
        self._ACCESS_TOKEN = self.config['oauth2_access_token']

        self._headers = {
            'Authorization': 'Bearer %s' % (self._ACCESS_TOKEN)
        }

        self._next_page = 1

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = raw['shot']['title']
        e.link = raw['shot']['html_url']
        e.occurred = datetime.datetime.strptime(
            raw['created_at'], '%Y-%m-%dT%H:%M:%SZ'
        )
        e.thumbnail_url = raw['shot']['html_url']
        e.original_url = raw['shot']['images'].get('hidpi')

        # if no hidpi image, use normal
        if e.original_url is None:
            e.original_url = raw['shot']['images'].get('normal')

        e.raw = raw

        return e

    def init_parse_params(self, **kwargs):
        return self.url, self._headers

    def parse(self, data):
        events = [self.to_event(shot) for shot in data]

        num_shots_returned = len(data)

        self._next_page += 1

        next_url = None
        next_headers = None

        if num_shots_returned > 0:
            next_url = self.url + ("?page=%d" % (self._next_page))

        return events, next_url, self._headers

    def deep_search(self, e, existing):

        post_id = re.search("(.*?)-", e.link).group(1)

        for key in existing:
            if post_id in key:
                return key

        return None
