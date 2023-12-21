import datetime

import oauth2 as oauth

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, Fields

PLACEHOLDER_HEIGHT = '683'
PLACEHOLDER_WIDTH = '1024'


class FlickrImageNotReady(Exception):
    pass


class Flickr(Feed):

    grouped = True
    grouped_window = 60 * 60

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        baseurl = (
            "https://api.flickr.com/services/rest/"
            "?method=flickr.people.getPhotos"
        )

        extras = [
            'description', 'license', 'date_upload',
            'date_taken', 'owner_name', 'icon_server',
            'original_format', 'last_update', 'geo', 'tags',
            'machine_tags', 'o_dims', 'views', 'media', 'path_alias',
            'url_sq', 'url_t', 'url_s', 'url_q', 'url_m', 'url_n',
            'url_z', 'url_c', 'url_l', 'url_o'
        ]

        args = '&' + '&'.join([
            'user_id=me',
            'per_page=100',
            'format=json',
            'nojsoncallback=1',
            'extras=' + ','.join(extras)
        ])

        self.url = baseurl + args

        # OAuth
        self._CONSUMER_KEY = self.config['oauth1_consumer_key']
        self._CONSUMER_SECRET = self.config['oauth1_consumer_secret']
        self._USER_KEY = self.config['oauth1_user_key']
        self._USER_SECRET = self.config['oauth1_user_secret']

        self.consumer = oauth.Consumer(
            self._CONSUMER_KEY,
            self._CONSUMER_SECRET
        )

        self.signature_method = oauth.SignatureMethod_HMAC_SHA1()

        self.token = oauth.Token(key=self._USER_KEY, secret=self._USER_SECRET)

    def _make_url(self, page=1):
        url = self.url + ("&page=%d" % (page))

        oauth_request = oauth.Request.from_consumer_and_token(
            self.consumer, token=self.token, http_url=url
        )
        oauth_request.sign_request(
            self.signature_method, self.consumer, self.token
        )

        url = oauth_request.to_url()

        return url

    def init_parse_params(self, **kwargs):
        return self._make_url(), None

    def parse(self, data):

        events = [self.to_event(photo) for photo in data['photos']['photo']]

        total_pages = int(data['photos']['pages'])
        next_page = int(data['photos']['page']) + 1
        next_url = None
        next_headers = None

        if next_page <= total_pages:
            next_url = self._make_url(next_page)

        return events, next_url, next_headers

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = raw['title']
        e.link = "https://www.flickr.com/photos/%s/%s" % (
            raw['owner'], raw['id']
        )
        e.occurred = datetime.datetime.utcfromtimestamp(
            float(raw['dateupload'])
        )

        e.thumbnail_url = raw['url_l']
        e.original_url = raw['url_o']
        e.raw = raw

        # crude check for placeholder image
        if (raw['height_o'], raw['width_o']) == (PLACEHOLDER_HEIGHT,
                                                 PLACEHOLDER_WIDTH):
            raise FlickrImageNotReady(
                'Upstream full size image is not ready for processing.'
            )

        return e
