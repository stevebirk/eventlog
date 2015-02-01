import sys
import os
import os.path
import logging

DEFAULT_CONFIG_FILE = os.path.join(
    sys.prefix, 'etc', 'eventlog', 'eventlog.conf'
)


def init_config(app):

    config_file = os.getenv('EVENTLOG_SETTINGS')

    if not config_file:
        config_file = DEFAULT_CONFIG_FILE

    app.config.from_pyfile(config_file)


def init_logging(app):

    if not app.debug:  # pragma: no cover
        # initialize logging
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
