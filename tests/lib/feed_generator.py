import sys

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, Fields

MAX_NUM = 25


class FakeFeedModule:
    pass

holder = {}

for i in range(MAX_NUM):

    def init_func(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

    def init_parse_params_func(self, **kwargs):
        raise Exception("TESTFEED: Not implemented")

    def parse_func(self, data):
        raise Exception("TESTFEED: Not implemented")

    def to_event(self, raw):
        raise Exception("TESTFEED: Not implemented")

    holder['TestFeed%d' % i] = type(
        'TestFeed%d' % i, (Feed, ), {
            'key_field': Fields.TITLE,
            '__module__': __name__ + '.testfeed%d' % i,
            '__init__': init_func,
            'init_parse_params': init_parse_params_func,
            'parse': parse_func,
            'to_event': to_event
        }
    )

    sys.modules[__name__ + '.testfeed%d' % i] = FakeFeedModule
