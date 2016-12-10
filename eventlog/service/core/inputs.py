import datetime
import pytz

from flask import current_app

from eventlog.lib.events import DATEFMT


DATETIME_FMT = DATEFMT.replace('%z', '')
DATE_FMT = "%Y-%m-%d"


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
        return datetime.datetime.strptime(value, DATETIME_FMT)
    except Exception as e:
        raise ValueError(
            "expected datetime format is '%s'" % (DATETIME_FMT)
        )


def date_format(value):
    try:
        return datetime.datetime.strptime(value, DATE_FMT)
    except Exception:
        raise ValueError("expected date format is '%s'" % (DATE_FMT))


def tz(value):
    try:
        pytz.timezone(value)
        return value
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError("unrecognized timezone '%s'" % (value))
