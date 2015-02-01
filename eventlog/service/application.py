from flask import Flask

from eventlog.service.core.api import api
from eventlog.service.core.caching import cache
from eventlog.service.core.store import store

from eventlog.service.util import init_config, init_logging

import eventlog.service.endpoints.events
import eventlog.service.endpoints.feeds
import eventlog.service.endpoints.token

app = Flask(__name__)

# initialize application
init_config(app)
init_logging(app)

# initialize cache
cache.init_app(app)

# initialize eventlog store
store.init_app(app)

# initialize api
api.init_app(app)

if __name__ == '__main__':  # pragma: no cover
    app.run('0.0.0.0', use_reloader=False)
