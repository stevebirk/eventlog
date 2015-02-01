import datetime
import logging

import oauth2 as oauth

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, fields


class Twitter(Feed):

    rate_limit = 180.0 / (60 * 15)  # 180 per 15 min

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        base = 'https://api.twitter.com/1.1/statuses/user_timeline.json'
        self.url = base + '?include_rts=1'

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

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.text = raw['text']
        e.occurred = datetime.datetime.strptime(
            raw['created_at'],
            '%a %b %d %H:%M:%S +0000 %Y'
        )
        e.raw = raw

        return e

    def _make_url(self):
        url = self.url

        oauth_request = oauth.Request.from_consumer_and_token(
            self.consumer,
            token=self.token,
            http_url=url
        )
        oauth_request.sign_request(
            self.signature_method, self.consumer, self.token
        )

        url = oauth_request.to_url()

        return url

    def init_parse_params(self, **kwargs):
        return self._make_url(), None

    def parse(self, data):
        return [self.to_event(entry) for entry in data], None, None

    def load(self, loadfile=None, dumpfile=None):
        raise Exception('Not implemented.')
