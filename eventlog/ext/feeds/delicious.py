import datetime
import codecs
import re

from eventlog.lib.feeds import Feed
from eventlog.lib.events import Event, fields


class Delicious(Feed):

    key_field = fields.LINK

    def __init__(self, config, **kwargs):
        Feed.__init__(self, config, **kwargs)

        self.url = "http://feeds.delicious.com/v2/json/%s" % (
            self.config['username']
        )

    def parse(self, data):
        return [self.to_event(entry) for entry in data], None, None

    def to_event(self, raw):
        e = Event()
        e.feed = self.dict()
        e.title = raw['d']
        e.link = raw['u']
        e.occurred = datetime.datetime.strptime(raw['dt'],
                                                '%Y-%m-%dT%H:%M:%SZ')
        e.thumbnail_url = raw['u']
        e.archive_url = raw['u']
        e.raw = raw

        return e

    def init_parse_params(self, **kwargs):
        return self.url, None

    def load(self, loadfile=None, dumpfile=None):

        if loadfile is None:
            raise Exception(
                'import of delicious data requires HTML dump file.'
            )

        fh = codecs.open(loadfile, "r", "utf-8")

        try:
            events = []

            for line in fh:
                if 'HREF' in line:

                    title = re.search("TAGS=\".*?\">(.*?)</A>", line).group(1)
                    link = re.search("HREF=\"(.*?)\"", line).group(1)
                    tags = re.search("TAGS=\"(.*?)\"", line).group(1)
                    tags = tags.split(',')

                    dt = int(re.search("ADD_DATE=\"(.*?)\"", line).group(1))
                    dt = datetime.datetime.utcfromtimestamp(dt)
                    dt = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                    data = {
                        u"a": u"ruuk",
                        u"d": unicode(title),
                        u"n": u"",
                        u"u": unicode(link),
                        u"t": unicode(tags),
                        u"dt": unicode(dt)

                    }

                    events.append(self.to_event(data))
        finally:
            fh.close()

        return events
