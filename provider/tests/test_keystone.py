# Copyright 2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
from __future__ import absolute_import

import json
from mock import MagicMock, ANY
import mock
import pytest

from handlers.keystone import TokenHandler

from handlers.selecting_handler import rest

REST_RESPONSE_POST = 'REST_RESPONSE_POST'

response_handlers = {}


@rest('POST', 'tokens', response_handlers)
def tokens_handler(content, id):
    return {'value': REST_RESPONSE_POST + content['key']}


@rest('POST', 'domains', response_handlers)
def domains_handler(content, id):
    return {'value': id + content['key']}


@mock.patch('handlers.keystone.TokenHandler._run_server', lambda *args: None)
@mock.patch('handlers.keystone_responses._responses', response_handlers)
@mock.patch('handlers.keystone.TokenHandler.end_headers')
@mock.patch('handlers.keystone.TokenHandler.send_header')
@mock.patch('handlers.keystone.TokenHandler.send_response', autospec=True)
class TestKeystoneHandler(object):

    def _test_handle_post_request(self, mock_send_response, path,
                                  expected_string):

        handler = TokenHandler(None, None, None)
        handler.wfile = MagicMock()
        handler.rfile = MagicMock()
        input_data = json.dumps({'key': 'value'})
        handler.rfile.read.return_value = input_data
        handler.headers = {'Content-Length': len(input_data)}

        handler.path = path

        handler.do_POST()

        mock_send_response.assert_called_once_with(handler, 200)
        handler.wfile.write.assert_called_once_with(json.dumps(
            {'value': expected_string + 'value'}))

    def test_handle_post_request(self, mock_send_response, mock_send_header,
                                 mock_end_headers):
        self._test_handle_post_request(mock_send_response, '/v2.0/tokens',
                                       REST_RESPONSE_POST)

    def test_handle_post_request_double_slashes(self, mock_send_response,
                                                mock_send_header,
                                                mock_end_headers):

        self._test_handle_post_request(mock_send_response, '/v2.0//tokens',
                                       REST_RESPONSE_POST)

    def test_handle_post_request_long(self, mock_send_response,
                                      mock_send_header, mock_end_headers):
        key = 'domains'
        id = 'domain_id/config/group/option'
        path = '/v3/{}/{}'.format(key, id)

        self._test_handle_post_request(mock_send_response, path, id)

    @mock.patch('handlers.keystone.TokenHandler.send_error', autospec=True)
    def test_handle_post_request_invalid(self, mock_send_error,
                                         mock_send_response,
                                         mock_send_header,
                                         mock_end_headers):
        with pytest.raises(Exception):
            self._test_handle_post_request(mock_send_response, '/v2/garbage',
                                           REST_RESPONSE_POST)
        mock_send_error.assert_called_once_with(ANY, 404)
