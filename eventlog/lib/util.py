import pytz
import datetime
import urllib.parse


def is_aware(dt):
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def local_datetime_to_utc(dt, tz):

    # do nothing if tz is None (implies already UTC)
    if tz is None:
        return dt

    # auto convert string to proper pytz timezone instance
    if isinstance(tz, str):
        tz = pytz.timezone(tz)

    local_dt = dt

    if not is_aware(dt):
        local_dt = tz.localize(dt)

    return pytz.utc.normalize(local_dt.astimezone(pytz.utc))


def utc_datetime_to_local(dt, tz):

    # do nothing if tz is None (implies desired timezone is UTC)
    if tz is None:
        return dt

    # auto convert string to proper pytz timezone instance
    if isinstance(tz, str):
        tz = pytz.timezone(tz)

    utc_dt = dt

    if not is_aware(dt):
        utc_dt = pytz.utc.localize(dt)

    return tz.normalize(utc_dt.astimezone(tz))


def pg_strptime(s):
    if '.' in s:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f+00:00")
    else:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S+00:00")


def urlize(target, base_uri, key=None):
    if target is None:
        return

    if target.get(key) is None:
        return

    target[key] = urllib.parse.urljoin(base_uri, target[key])
