import uuid

from eventlog.lib.store.pagination import BySearchCursor, ByTimeRangeCursor

from .inputs import datetime_format, DATETIME_FMT


def parse(value, timezone):

    values = value.split(',')

    if len(values) == 1:
        return BySearchCursor(int(values[0]))
    elif len(values) == 2:
        return ByTimeRangeCursor(
            datetime_format(values[0]),
            str(uuid.UUID(values[1])),
            timezone=timezone
        )
    else:
        raise ValueError("unrecognized cursor format")


def serialize(cursor):
    if isinstance(cursor, BySearchCursor):
        return str(cursor.page)
    else:
        return '%s,%s' % (cursor.occurred.strftime(DATETIME_FMT), cursor.id)
