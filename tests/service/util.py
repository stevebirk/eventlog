import unittest.mock

import eventlog.lib.store

eventlog.lib.store.Store = unittest.mock.Mock


def check_content_type(resp):
    if resp.headers['Content-Type'] != 'application/json':
        raise Exception('Response Content-Type is not "application/json"')


def check_has_allow_origin(resp):
    if resp.headers['Access-Control-Allow-Origin'] != '*':
        raise Exception(
            'Response missing "Access-Control-Allow-Origin" header'
        )


def check_has_cors(resp):

    if 'Access-Control-Allow-Methods' not in resp.headers:
        raise Exception(
            'Response missing "Access-Control-Allow-Methods" header'
        )

    if 'Access-Control-Max-Age' not in resp.headers:
        raise Exception(
            'Response missing "Access-Control-Max-Age" header'
        )


def verify_response(resp):
    check_content_type(resp)
    check_has_allow_origin(resp)

    if resp.status_code / 200 == 1:
        check_has_cors(resp)
