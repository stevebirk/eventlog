#!/usr/bin/env python

"""
Update event data for configured feeds.

Usage: updater.py [-hjvd --added]

-h, --help      Show this screen.
-j, --dry-run   Enable readonly mode, i.e. db changes and thumbnail
                files are not saved.
-v, --verbose   Log to stderr instead of file.
-d, --debug     Enable DEBUG level logging. Implies --verbose.
    --added     Print number of added events to stdout at script completion.
"""

# monkey patch away!
import gevent
import gevent.monkey
gevent.monkey.patch_all()  # noqa

# psycopg2 monkey patch!
import psycogreen.gevent
psycogreen.gevent.patch_psycopg()  # noqa

import sys
import os
import os.path
import logging
import socket
import traceback
import time
import datetime
import docopt
import threading

from flask import Flask
from eventlog.lib.store import Store
from eventlog.service.util import init_config

_LOG = logging.getLogger(__name__)

# give all network communication a default
# timeout of 2 minutes
socket.setdefaulttimeout(60 * 2)

app = Flask(__name__)

store = Store()


def init_options():
    global args
    args = docopt.docopt(__doc__)


def init_logging():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
    logdir = app.config['LOG_ROOT']

    if not os.path.exists(logdir):
        try:
            os.makedirs(logdir, 0o755)
        except Exception:
            errmsg = "ERROR: unable to create LOG_ROOT directory: '%s'" % (
                logdir
            )
            print(errmsg, file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            sys.exit(1)

    if args["--debug"]:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logfile = os.path.join(logdir, 'updater.' + timestamp + '.log')

    if args["--debug"] or args["--verbose"]:
        handler = logging.StreamHandler()
    else:
        handler = logging.FileHandler(logfile)

    handler.setLevel(level)

    fmt = ('[%(asctime)s.%(msecs)03d]: %(levelname)10s | ' +
           '%(threadName)15s | %(name)20s | %(message)s')

    handler.setFormatter(logging.Formatter(fmt, '%H:%M:%S'))

    l = logging.getLogger()  # noqa: E741
    l.addHandler(handler)
    l.setLevel(level)

    t = threading.current_thread()
    t.name = ''


def wrapped_update(f, dry=False):
    # wrapper to make logging clearer
    t = threading.current_thread()
    t.name = f.short_name

    return f.update(dry)


def update_feeds(feeds):

    greenlets = []

    for f in feeds.values():
        g = gevent.spawn(wrapped_update, f, args["--dry-run"])
        greenlets.append(g)
        gevent.sleep(0)

    finished = gevent.joinall(greenlets)

    if args["--added"]:
        print(sum([g.value for g in finished if g.value is not None]))

    return


def main():
    init_config(app)

    init_options()
    init_logging()

    _LOG.info('starting processing')
    start = time.time()

    try:
        _LOG.debug('initializing store')
        store.init_app(app)
        _LOG.debug('store initialized')

        feeds = store.get_feeds(is_updating=True)

        update_feeds(feeds)

    except Exception:
        _LOG.critical('uncaught exception', exc_info=1)

    end = time.time()
    _LOG.info('finished processing (elapsed: %.6fs)', end - start)


if __name__ == "__main__":
    main()
