import logging

_LOG = logging.getLogger(__name__)


def load(resource, config, **kwargs):

    result = []

    # import necessary modules
    for name, options in config.items():
        # import module
        try:
            __import__(name)
        except Exception:
            _LOG.exception("unable to load module '%s', skipping.", name)
        else:
            _LOG.debug("loaded %s '%s'." % (resource.__name__, name))

    # find desired resources
    for r in resource.__subclasses__():

        if r.__module__ in config:
            options = config[r.__module__]
        else:  # pragma: no cover
            continue

        try:
            obj = r(options, **kwargs)

            result.append(obj)
        except Exception:
            _LOG.exception(
                "unable to instantiate %s '%s'", resource.__name__, r.__name__
            )

    return result
