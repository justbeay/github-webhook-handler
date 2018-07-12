#!/usr/bin/env python3

import ipaddress
import hmac
import hashlib
import requests
import time
from flask import request

class Validation(object):

    def __init__(self, global_config):
        self.hook_address_allows = global_config['github']['hooks_address'] if 'hooks_address' in global_config['github'] else None
        self.last_refresh_time = -1
        self.validate_sourceip = global_config['validate_sourceip'] if 'validate_sourceip' in global_config else False

    def validate_ip(self):
        if request.method != 'GET':
            if self.validate_sourceip:
                request_ip = request.headers['X-Forwarded-For'] if 'X-Forwarded-For' in request.headers else request.remote_addr
                if not self.hook_address_allows or self.last_refresh_time != -1 and time.time() - self.last_refresh_time > 300:
                    # hooks_address not set in global config or it expires (> 5min)
                    self.hook_address_allows = requests.get('https://api.github.com/meta').json()['hooks']
                    self.last_refresh_time = time.time()
                for block in self.hook_address_allows:
                    if ipaddress.ip_address(request_ip) in ipaddress.ip_network(block):
                        break  # the remote_addr is within the network range of github.
                else:
                    if request_ip != '127.0.0.1':
                        return False
        return True

    def validate_secret(self, secret_key):
        if secret_key:
            algo, signature = request.headers.get('X-Hub-Signature').split('=') \
                if request.headers.get('X-Hub-Signature') and request.headers.get('X-Hub-Signature').find('=') > 0 \
                else [None, None]
            signature_valid = algo and signature
            if signature_valid:
                mac = hmac.new(secret_key.encode('utf-8'), msg=request.data, digestmod=getattr(hashlib, algo))
                signature_valid = hmac.compare_digest(mac.hexdigest(), signature)
            return not (not signature_valid)
        return True
