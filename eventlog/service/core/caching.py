from flask import request

from flask_caching import Cache

from eventlog.service.core.auth import is_authorized

cache = Cache()


def make_cache_key():
    key = request.path + '?' + request.query_string.decode('utf-8')
    key += 'authenticated' if is_authorized() else ''
    return key
