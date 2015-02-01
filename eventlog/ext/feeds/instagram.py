import datetime

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, fields


class Instagram(Feed):

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = 'https://api.instagram.com/v1/users/self/media/recent'

        # OAuth
        self._CLIENT_ID = self.config['oauth2_client_id']
        self._CLIENT_SECRET = self.config['oauth2_client_secret']
        self._ACCESS_TOKEN = self.config['oauth2_access_token']

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()

        if raw['caption']:
            e.title = raw['caption']['text']

        e.link = raw["images"]["standard_resolution"]["url"]
        e.occurred = datetime.datetime.utcfromtimestamp(
            float(raw['created_time'])
        )
        e.thumbnail_url = e.link
        e.original_url = e.link
        e.raw = raw

        return e

    def _make_url(self, next_max_id=None):
        url = self.url + ("?access_token=%s" % (self._ACCESS_TOKEN))

        if next_max_id:
            url += ("&max_id=%s" % (str(next_max_id)))

        return url

    def init_parse_params(self, **kwargs):
        return self._make_url(), None

    def parse(self, data):
        events = [self.to_event(photo) for photo in data['data']]

        next_max_id = data['pagination'].get('next_max_id')
        next_url = None
        next_headers = None

        if next_max_id:
            next_url = self._make_url(next_max_id)

        return events, next_url, next_headers
