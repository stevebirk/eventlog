import sys
import re
import copy
import difflib

from flask import request, current_app
from flask.signals import got_request_exception

from werkzeug.exceptions import abort, BadRequest

from werkzeug.http import HTTP_STATUS_CODES

from flask.ext.restful import Api as _Api
from flask.ext.restful import abort as _abort
from flask.ext.restful.reqparse import Argument as _Argument
from flask.ext.restful.utils import error_data, cors

envelope = {
    "meta": {
        "code": None
    },
    "data": {},
}

error_meta = {
    "meta": {
        "error_type": "Unknown",
        "error_message": ""
    }
}

pagination = {
    "pagination": {}
}

# WARNING: this fixes an issue where 400 errors are raised as
#          ClientDisconnected instead of BadRequest
abort.mapping[BadRequest.code] = BadRequest


class Api(_Api):

    def handle_error(self, e):
        """Error handler for the API transforms a raised exception into a
        Flask response, with the appropriate HTTP status code and body.

        :param e: the raised Exception object
        :type e: Exception

        """
        got_request_exception.send(
            current_app._get_current_object(), exception=e
        )

        if not hasattr(e, 'code') and current_app.propagate_exceptions:
            exc_type, exc_value, tb = sys.exc_info()
            if exc_value is e:
                raise
            else:  # pragma: no cover
                raise e

        code = getattr(e, 'code', 500)
        data = getattr(e, 'data', error_data(code))
        headers = {
            'Access-Control-Allow-Origin': '*'
        }

        if code >= 500:

            # There's currently a bug in Python3 that disallows calling
            # logging.exception() when an exception hasn't actually be raised
            if sys.exc_info() == (None, None, None):  # pragma: no cover
                current_app.logger.error("Internal Error")
            else:
                current_app.logger.exception("Internal Error")

        help_on_404 = current_app.config.get("ERROR_404_HELP", True)
        if (code == 404 and help_on_404 and
            ('message' not in data or
             data['message'] == HTTP_STATUS_CODES[404])):

            rules = dict([(re.sub('(<.*>)', '', rule.rule), rule.rule)
                          for rule in current_app.url_map.iter_rules()])
            close_matches = difflib.get_close_matches(request.path,
                                                      rules.keys())
            if close_matches:
                # If we already have a message, add punctuation and
                # continue it.
                if "message" in data:
                    data["message"] += ". "
                else:  # pragma: no cover
                    data["message"] = ""

                data['message'] += ('You have requested this URI [' +
                                    request.path + '] but did you mean ' +
                                    ' or '.join((rules[match]
                                                for match in close_matches)) +
                                    ' ?')

        if code == 405:
            headers['Allow'] = e.valid_methods

        enhanced_data = copy.deepcopy(envelope)
        enhanced_data.update(copy.deepcopy(error_meta))
        enhanced_data["meta"]["error_type"] = e.__class__.__name__
        enhanced_data["meta"]["code"] = code
        enhanced_data["meta"]["error_message"] = data['message']

        resp = self.make_response(enhanced_data, code, headers)

        if code == 401:  # pragma: no cover
            resp = self.unauthorized(resp)

        return resp


class Argument(_Argument):
    def convert(self, value, op):
        try:
            return super(Argument, self).convert(value, op)
        except Exception as e:
            old_message = e.message
            message = "Invalid value for '%s': %s" % (self.name, old_message)
            raise type(e)(message)

    def handle_validation_error(self, error):
        _abort(400, message=str(error))


api = Api(catch_all_404s=True, decorators=[cors.crossdomain(origin='*')])
