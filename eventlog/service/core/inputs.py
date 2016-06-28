import datetime
import pytz

from flask import current_app

from eventlog.lib.events import DATEFMT


def limit(value):
    max_allowed = current_app.config['PAGE_SIZE_MAX']
    value = int(value)
    if not (0 < value <= max_allowed):
        raise ValueError("valid range is 0 < limit <= %d" % (max_allowed))

    return value


def comma_separated(value):
    comma_separated = [v.strip() for v in value.split(',') if v.strip()]

    if not comma_separated:
        raise ValueError("must contain one or more comma separated values")

    return comma_separated


def datetime_format(value):
    try:
        return datetime.datetime.strptime(value, DATEFMT.replace('%z', ''))
    except Exception:
        raise ValueError(
            "expected datetime format is '%s'" % (DATEFMT.replace('%z', ''))
        )


def date_format(value):
    fmt = "%Y-%m-%d"
    try:
        return datetime.datetime.strptime(value, fmt)
    except Exception:
        raise ValueError("expected date format is '%s'" % (fmt))


def tz(value):
    try:
        pytz.timezone(value)
        return value
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError("unrecognized timezone '%s'" % (value))
