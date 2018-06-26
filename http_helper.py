#!/usr/bin/env python3

import json
import urllib
from urllib.error import HTTPError
import ssl

def get_auth_opener(host, user, token):
    passman = urllib.request.HTTPPasswordMgrWithPriorAuth()
    passman.add_password(None, host, user, token, is_authenticated=True)
    auth_handler = urllib.request.HTTPBasicAuthHandler(passman)
    ssl._create_default_https_context = ssl._create_unverified_context
    opener = urllib.request.build_opener(auth_handler)
    # opener.add_handler(urllib.request.ProxyHandler(dict(https='http://127.0.0.1:5555')))
    opener.addheaders = [('User-agent', 'Mozilla/5.0')]
    urllib.request.install_opener(opener)
    return opener

def request_json_api(logger, opener, url, method='GET', json_data=None, form_data=None):
    data_req = None
    headers_req = {}
    if json_data:
        data_req = json.dumps(json_data).encode(encoding='utf-8')
        headers_req['Content-Type'] = 'application/json'
    elif form_data:
        data_req = urllib.parse.urlencode(form_data).encode(encoding='utf-8')
        headers_req['Content-Type'] = 'application/x-www-form-urlencoded'
    res = request_api(logger, opener, url, method, data_req, headers_req)
    json_result = json.loads(res.read().decode('utf-8'))
    res.close()
    return json_result

def request_api(logger, opener, url, method='GET', data=None, headers={}):
    logger.debug("request api: %s with method: %s...", url, method)
    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
    try:
        return opener.open(req)
    except HTTPError as ex:
        result = ex.read().decode('utf-8')
        logger.error("%s url: %s return httpError with code: %s and body: %s", method, url, ex.code, 
                result)
        raise ex