import unittest
import json

import pytest

from dummyserver.server import HAS_IPV6
from dummyserver.testcase import (HTTPDummyServerTestCase,
                                  IPv6HTTPDummyServerTestCase)
from urllib3._collections import HTTPHeaderDict
from urllib3.poolmanager import PoolManager
from urllib3.connectionpool import port_by_scheme
from urllib3.exceptions import MaxRetryError
from urllib3.util.retry import Retry


class TestPoolManager(HTTPDummyServerTestCase):

    def setUp(self):
        self.base_url = 'http://%s:%d' % (self.host, self.port)
        self.base_url_alt = 'http://%s:%d' % (self.host_alt, self.port)

    def test_redirect(self):
        for pool_manager_kwargs in ({}, {'retries': None}, {'retries': 1},
                                    {'retries': Retry(1)}):
            with PoolManager(**pool_manager_kwargs) as http:
                r = http.request('GET', '%s/redirect' % self.base_url,
                                 fields={'target': '%s/' % self.base_url},
                                 redirect=False)

                self.assertEqual(r.status, 303)

                r = http.request('GET', '%s/redirect' % self.base_url,
                                 fields={'target': '%s/' % self.base_url})

                self.assertEqual(r.status, 200)
                self.assertEqual(r.data, b'Dummy server!')

    def test_redirect_twice(self):
        for pool_manager_kwargs in ({}, {'retries': None}, {'retries': 2},
                                    {'retries': Retry(2)}):
            with PoolManager(**pool_manager_kwargs) as http:
                r = http.request('GET', '%s/redirect' % self.base_url,
                                 fields={'target': '%s/redirect' % self.base_url},
                                 redirect=False)

                self.assertEqual(r.status, 303)

                r = http.request('GET', '%s/redirect' % self.base_url,
                                 fields={'target': '%s/redirect?target=%s/' % (
                                     self.base_url, self.base_url)})

                self.assertEqual(r.status, 200)
                self.assertEqual(r.data, b'Dummy server!')

    def test_redirect_to_relative_url(self):
        http = PoolManager()
        self.addCleanup(http.clear)

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '/redirect'},
                         redirect=False)

        self.assertEqual(r.status, 303)

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '/redirect'})

        self.assertEqual(r.status, 200)
        self.assertEqual(r.data, b'Dummy server!')

    def test_redirects_disabled_for_pool_manager_with_0(self):
        """
        Check handling redirects when retries is set to 0 on the pool
        manager.
        """
        for retries in (0, Retry(total=0), Retry(redirect=0), Retry(total=0, redirect=0)):
            with PoolManager(retries=retries) as http:
                with pytest.raises(MaxRetryError):
                    http.request('GET', '%s/redirect' % self.base_url)

                # Setting redirect=True should not change the behavior.
                with pytest.raises(MaxRetryError):
                    http.request('GET', '%s/redirect' % self.base_url, redirect=True)

                # Setting redirect=False should not make it follow the redirect,
                # but MaxRetryError should not be raised.
                response = http.request('GET', '%s/redirect' % self.base_url, redirect=False)
                self.assertEqual(response.status, 303)

    def test_redirects_disabled_for_pool_manager_with_false(self):
        """
        Check that setting retries set to False on the pool manager disables
        raising MaxRetryError and redirect=True does not change the
        behavior.
        """
        for retries in (False, Retry(total=False), Retry(redirect=False),
                        Retry(total=False, redirect=False)):
            with PoolManager(retries=retries) as http:
                response = http.request('GET', '%s/redirect' % self.base_url)
                self.assertEqual(response.status, 303)

                response = http.request('GET', '%s/redirect' % self.base_url, redirect=True)
                self.assertEqual(response.status, 303)

                response = http.request('GET', '%s/redirect' % self.base_url, redirect=False)
                self.assertEqual(response.status, 303)

    def test_redirects_disabled_for_individual_request(self):
        """
        Check handling redirects when they are meant to be disabled
        on the request level.
        """
        with PoolManager() as http:
            # Check when redirect is not passed.
            with pytest.raises(MaxRetryError):
                http.request('GET', '%s/redirect' % self.base_url, retries=0)
            response = http.request('GET', '%s/redirect' % self.base_url, retries=False)
            self.assertEqual(response.status, 303)

            # Check when redirect=True.
            with pytest.raises(MaxRetryError):
                http.request('GET', '%s/redirect' % self.base_url, retries=0, redirect=True)
            response = http.request('GET', '%s/redirect' % self.base_url, retries=False,
                                    redirect=True)
            self.assertEqual(response.status, 303)

            # Check when redirect=False.
            response = http.request('GET', '%s/redirect' % self.base_url, retries=0,
                                    redirect=False)
            self.assertEqual(response.status, 303)
            response = http.request('GET', '%s/redirect' % self.base_url, retries=False,
                                    redirect=False)
            self.assertEqual(response.status, 303)

    def test_cross_host_redirect(self):
        http = PoolManager()
        self.addCleanup(http.clear)

        cross_host_location = '%s/echo?a=b' % self.base_url_alt
        try:
            http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': cross_host_location},
                         timeout=1, retries=0)
            self.fail("Request succeeded instead of raising an exception like it should.")

        except MaxRetryError:
            pass

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '%s/echo?a=b' % self.base_url_alt},
                         timeout=1, retries=1)

        self.assertEqual(r._pool.host, self.host_alt)

    def test_too_many_redirects(self):
        http = PoolManager()
        self.addCleanup(http.clear)

        try:
            r = http.request('GET', '%s/redirect' % self.base_url,
                             fields={'target': '%s/redirect?target=%s/' % (self.base_url,
                                                                           self.base_url)},
                             retries=1)
            self.fail("Failed to raise MaxRetryError exception, returned %r" % r.status)
        except MaxRetryError:
            pass

        try:
            r = http.request('GET', '%s/redirect' % self.base_url,
                             fields={'target': '%s/redirect?target=%s/' % (self.base_url,
                                                                           self.base_url)},
                             retries=Retry(total=None, redirect=1))
            self.fail("Failed to raise MaxRetryError exception, returned %r" % r.status)
        except MaxRetryError:
            pass

        # Check when retries are configured for the pool manager.
        with PoolManager(retries=1) as http:
            with pytest.raises(MaxRetryError):
                http.request('GET', '%s/redirect' % self.base_url,
                             fields={'target': '%s/redirect?target=%s/' % (self.base_url,
                                                                           self.base_url)})

            # Here we allow more retries for the request.
            response = http.request('GET', '%s/redirect' % self.base_url,
                                    fields={'target': '%s/redirect?target=%s/' % (
                                        self.base_url, self.base_url)},
                                    retries=2)
            self.assertEqual(response.status, 200)

    def test_redirect_cross_host_remove_headers(self):
        http = PoolManager()
        self.addCleanup(http.clear)

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '%s/headers' % self.base_url_alt},
                         headers={'Authorization': 'foo', 'Cookie': 'foo=bar',
                                  'Proxy-Authorization': 'bar'})

        self.assertEqual(r.status, 200)

        data = json.loads(r.data.decode('utf-8'))

        self.assertNotIn('Authorization', data)
        self.assertNotIn('Proxy-Authorization', data)
        self.assertNotIn('Cookie', data)

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '%s/headers' % self.base_url_alt},
                         headers={'authorization': 'foo', 'cookie': 'foo=bar',
                                  'Proxy-Authorization': 'bar'})

        self.assertEqual(r.status, 200)

        data = json.loads(r.data.decode('utf-8'))

        self.assertNotIn('authorization', data)
        self.assertNotIn('Authorization', data)
        self.assertNotIn('cookie', data)
        self.assertNotIn('Cookie', data)
        self.assertNotIn('Proxy-Authorization', data)
        self.assertNotIn('proxy-authorization', data)

    def test_redirect_cross_host_no_remove_headers(self):
        http = PoolManager()
        self.addCleanup(http.clear)

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '%s/headers' % self.base_url_alt},
                         headers={'Authorization': 'foo', 'Cookie': 'foo=bar',
                                  'Proxy-Authorization': 'bar'},
                         retries=Retry(remove_headers_on_redirect=[]))

        self.assertEqual(r.status, 200)

        data = json.loads(r.data.decode('utf-8'))

        self.assertEqual(data['Authorization'], 'foo')
        self.assertEqual(data['Cookie'], 'foo=bar')
        self.assertEqual(data['Proxy-Authorization'], 'bar')

    def test_redirect_cross_host_set_removed_headers(self):
        http = PoolManager()
        self.addCleanup(http.clear)

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '%s/headers' % self.base_url_alt},
                         headers={'X-API-Secret': 'foo',
                                  'Authorization': 'bar',
                                  'Cookie': 'foo=bar',
                                  'Proxy-Authorization': 'bar'},
                         retries=Retry(remove_headers_on_redirect=['X-API-Secret']))

        self.assertEqual(r.status, 200)

        data = json.loads(r.data.decode('utf-8'))

        self.assertNotIn('X-API-Secret', data)
        self.assertEqual(data['Authorization'], 'bar')
        self.assertEqual(data['Cookie'], 'foo=bar')
        self.assertEqual(data['Proxy-Authorization'], 'bar')

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '%s/headers' % self.base_url_alt},
                         headers={'x-api-secret': 'foo',
                                  'authorization': 'bar',
                                  'cookie': 'foo=bar',
                                  'proxy-authorization': 'bar'},
                         retries=Retry(remove_headers_on_redirect=['X-API-Secret']))

        self.assertEqual(r.status, 200)

        data = json.loads(r.data.decode('utf-8'))

        self.assertNotIn('x-api-secret', data)
        self.assertNotIn('X-API-Secret', data)

        self.assertEqual(data['Authorization'], 'bar')
        self.assertEqual(data['Cookie'], 'foo=bar')
        self.assertEqual(data['Proxy-Authorization'], 'bar')

    def test_redirect_cross_host_remove_default_cookie_header(self):
        http = PoolManager(headers={'Cookie': 'foo=bar'})
        self.addCleanup(http.clear)

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '%s/headers' % self.base_url_alt})

        self.assertEqual(r.status, 200)

        data = json.loads(r.data.decode('utf-8'))

        self.assertNotIn('Cookie', data)

    def test_303_redirect_makes_request_lose_body(self):
        with PoolManager() as http:
            response = http.request(
                'POST',
                '%s/redirect' % self.base_url,
                fields={
                    'target': '%s/headers_and_params' % self.base_url,
                    'status': '303 See Other',
                },
            )
        data = json.loads(response.data.decode('utf-8'))
        assert data['params'] == {}
        assert 'Content-Type' not in HTTPHeaderDict(data['headers'])

    def test_raise_on_redirect(self):
        http = PoolManager()
        self.addCleanup(http.clear)

        r = http.request('GET', '%s/redirect' % self.base_url,
                         fields={'target': '%s/redirect?target=%s/' % (self.base_url,
                                                                       self.base_url)},
                         retries=Retry(total=None, redirect=1, raise_on_redirect=False))

        self.assertEqual(r.status, 303)

    def test_raise_on_status(self):
        http = PoolManager()
        self.addCleanup(http.clear)

        try:
            # the default is to raise
            r = http.request('GET', '%s/status' % self.base_url,
                             fields={'status': '500 Internal Server Error'},
                             retries=Retry(total=1, status_forcelist=range(500, 600)))
            self.fail("Failed to raise MaxRetryError exception, returned %r" % r.status)
        except MaxRetryError:
            pass

        try:
            # raise explicitly
            r = http.request('GET', '%s/status' % self.base_url,
                             fields={'status': '500 Internal Server Error'},
                             retries=Retry(total=1,
                                           status_forcelist=range(500, 600),
                                           raise_on_status=True))
            self.fail("Failed to raise MaxRetryError exception, returned %r" % r.status)
        except MaxRetryError:
            pass

        # don't raise
        r = http.request('GET', '%s/status' % self.base_url,
                         fields={'status': '500 Internal Server Error'},
                         retries=Retry(total=1,
                                       status_forcelist=range(500, 600),
                                       raise_on_status=False))

        self.assertEqual(r.status, 500)

    def test_missing_port(self):
        # Can a URL that lacks an explicit port like ':80' succeed, or
        # will all such URLs fail with an error?

        http = PoolManager()
        self.addCleanup(http.clear)

        # By globally adjusting `port_by_scheme` we pretend for a moment
        # that HTTP's default port is not 80, but is the port at which
        # our test server happens to be listening.
        port_by_scheme['http'] = self.port
        try:
            r = http.request('GET', 'http://%s/' % self.host, retries=0)
        finally:
            port_by_scheme['http'] = 80

        self.assertEqual(r.status, 200)
        self.assertEqual(r.data, b'Dummy server!')

    def test_headers(self):
        http = PoolManager(headers={'Foo': 'bar'})
        self.addCleanup(http.clear)

        r = http.request('GET', '%s/headers' % self.base_url)
        returned_headers = json.loads(r.data.decode())
        self.assertEqual(returned_headers.get('Foo'), 'bar')

        r = http.request('POST', '%s/headers' % self.base_url)
        returned_headers = json.loads(r.data.decode())
        self.assertEqual(returned_headers.get('Foo'), 'bar')

        r = http.request_encode_url('GET', '%s/headers' % self.base_url)
        returned_headers = json.loads(r.data.decode())
        self.assertEqual(returned_headers.get('Foo'), 'bar')

        r = http.request_encode_body('POST', '%s/headers' % self.base_url)
        returned_headers = json.loads(r.data.decode())
        self.assertEqual(returned_headers.get('Foo'), 'bar')

        r = http.request_encode_url('GET', '%s/headers' % self.base_url, headers={'Baz': 'quux'})
        returned_headers = json.loads(r.data.decode())
        self.assertIsNone(returned_headers.get('Foo'))
        self.assertEqual(returned_headers.get('Baz'), 'quux')

        r = http.request_encode_body('GET', '%s/headers' % self.base_url, headers={'Baz': 'quux'})
        returned_headers = json.loads(r.data.decode())
        self.assertIsNone(returned_headers.get('Foo'))
        self.assertEqual(returned_headers.get('Baz'), 'quux')

    def test_http_with_ssl_keywords(self):
        http = PoolManager(ca_certs='REQUIRED')
        self.addCleanup(http.clear)

        r = http.request('GET', 'http://%s:%s/' % (self.host, self.port))
        self.assertEqual(r.status, 200)

    def test_http_with_ca_cert_dir(self):
        http = PoolManager(ca_certs='REQUIRED', ca_cert_dir='/nosuchdir')
        self.addCleanup(http.clear)

        r = http.request('GET', 'http://%s:%s/' % (self.host, self.port))
        self.assertEqual(r.status, 200)


@pytest.mark.skipif(
    not HAS_IPV6,
    reason='IPv6 is not supported on this system'
)
class TestIPv6PoolManager(IPv6HTTPDummyServerTestCase):

    def setUp(self):
        self.base_url = 'http://[%s]:%d' % (self.host, self.port)

    def test_ipv6(self):
        http = PoolManager()
        self.addCleanup(http.clear)
        http.request('GET', self.base_url)


if __name__ == '__main__':
    unittest.main()
