import unittest
import json

# NOTE: this mocks out Store, so import needs to before app
import util

from eventlog.service.application import app


class TestToken(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()

    def test_get(self):
        rv = self.app.get('/token')

        self.assertEqual(rv.status_code, 200)

        util.verify_headers(rv)

        resp_data = json.loads(rv.data.decode('utf-8'))

        self.assertIn("data", resp_data)
        self.assertIn("token", resp_data["data"])

if __name__ == '__main__':
    unittest.main()
