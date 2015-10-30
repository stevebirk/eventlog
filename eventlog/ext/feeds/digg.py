import logging

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, Fields

_LOG = logging.getLogger(__name__)


class Digg(Feed):

    key_field = Fields.TITLE

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = ("http://services.digg.com/2.0/user.getActivity"
                    "?type=json&username=%s") % (self.config['username'])

    def init_parse_params(self, **kwargs):
        raise Exception("Digg feed does not support parsing new data.")

    def parse(self, data):
        raise Exception("Digg feed does not support parsing new data.")

    def to_event(self, raw):
        raise Exception("Digg feed does not support parsing new data.")
