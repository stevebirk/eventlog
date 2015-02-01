#!/usr/bin/env python

"""
(Re-)Index event data.

Usage: indexer.py [-hj]

-h, --help          Show this screen.
-j, --dry-run       Enable dry run mode, i.e. index changes are not committed.
"""

import os
import sys
import time
import logging
import docopt

from flask import Flask

from eventlog.lib.store import Store
from eventlog.service.util import init_config

store = Store()


def init_logging():
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        ('[%(asctime)s.%(msecs)03d]: '
         '%(levelname)10s | %(name)20s | %(message)s'),
        '%H:%M:%S'
    ))

    l = logging.getLogger()
    l.addHandler(handler)
    l.setLevel(logging.INFO)

if __name__ == "__main__":
    init_logging()

    app = Flask(__name__)
    init_config(app)
    store.init_app(app)

    args = docopt.docopt(__doc__)

    # create index directory if necessary
    indexdir = app.config['STORE']['INDEX_DIR']

    # create new index in desired directory
    store._index.clear(indexdir)

    start = time.time()

    # get events
    es = store.get_events()

    # index events
    store._index.index(es, dry=args['--dry-run'])

    end = time.time()

    print 'indexing took %.3fs' % (end - start)
