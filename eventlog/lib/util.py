import pytz
import datetime
import urlparse


def tz_unaware_local_dt_to_utc(dt, tz):
    return pytz.utc.normalize(
        tz.localize(dt).astimezone(pytz.utc)
    )


def tz_unaware_utc_dt_to_local(dt, tz):
    return tz.normalize(
        pytz.utc.localize(dt).astimezone(tz)
    )


def pg_strptime(s):
    if '.' in s:
        return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f+00")
    else:
        return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S+00")


def urlize(target, base_uri, key=None):
    if target is None:
        return

    if target.get(key) is None:
        return

    target[key] = urlparse.urljoin(base_uri, target[key])
