#!/usr/bin/env python3
import io
import os
import sys
import json
import requests
import ipaddress
import hmac
import hashlib
from flask import Flask, request, abort
from event_handler import GithubEventHandler

"""
Conditionally import ProxyFix from werkzeug if the USE_PROXYFIX environment
variable is set to true.  If you intend to import this as a module in your own
code, use os.environ to set the environment variable before importing this as a
module.

.. code:: python

    os.environ['USE_PROXYFIX'] = 'true'
    import flask-github-webhook-handler.index as handler

"""
# The repos.json file should be readable by the user running the Flask app,
# and the absolute path should be given by this environment variable.
BASE_APP_PATH = os.path.dirname(os.path.realpath(__file__))
repos_config = json.loads(io.open(BASE_APP_PATH + '/config/repos.json', 'r').read())
global_config = json.loads(io.open(BASE_APP_PATH + '/config/global.json', 'r').read())

if global_config['use_proxyfix']:
    from werkzeug.contrib.fixers import ProxyFix

app = Flask(__name__)
app.debug = global_config['debug']


@app.route("/", methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return 'OK'
    elif request.method == 'POST':
        # Store the IP address of the requester
        request_ip = ipaddress.ip_address(u'{0}'.format(request.remote_addr))

        # If VALIDATE_SOURCEIP is set to false, do not validate source IP
        if not (global_config['validate_sourceip'] == False):

            # If GHE_ADDRESS is specified, use it as the hook_blocks.
            if global_config['ghe_address']:
                hook_blocks = [global_config['ghe_address']]
            # Otherwise get the hook address blocks from the API.
            else:
                hook_blocks = requests.get('https://api.github.com/meta').json()[
                    'hooks']

            # Check if the POST request is from github.com or GHE
            for block in hook_blocks:
                if ipaddress.ip_address(request_ip) in ipaddress.ip_network(block):
                    break  # the remote_addr is within the network range of github.
            else:
                if str(request_ip) != '127.0.0.1':
                    abort(403)

        event = request.headers.get('X-GitHub-Event')
        payload = json.loads(request.data.decode('utf8'))
        handler = GithubEventHandler(event, payload)
        handler.set_config(global_config, repos_config)
        repo_config = handler.get_repo_config()
        secretkey = repo_config['secretkey'] if repo_config else None
        if secretkey:
            algo, signature = request.headers.get('X-Hub-Signature').split('=') \
                if request.headers.get('X-Hub-Signature') and request.headers.get('X-Hub-Signature').find('=') > 0 \
                else [None, None]
            signature_valid = algo and signature
            if signature_valid:
                mac = hmac.new(secretkey.encode('utf-8'), msg=request.data, digestmod=getattr(hashlib, algo))
                signature_valid = compare_digest(mac.hexdigest(), signature)
            if not signature_valid:
                abort(403)
        result = handler.handle()
        return json.dumps(result) if type(result) == dict else result

# Check if python version is less than 2.7.7
if sys.version_info < (2, 7, 7):
    # http://blog.turret.io/hmac-in-go-python-ruby-php-and-nodejs/
    def compare_digest(a, b):
        """
        ** From Django source **

        Run a constant time comparison against two strings

        Returns true if a and b are equal.

        a and b must both be the same length, or False is
        returned immediately
        """
        if len(a) != len(b):
            return False

        result = 0
        for ch_a, ch_b in zip(a, b):
            result |= ord(ch_a) ^ ord(ch_b)
        return result == 0
else:
    compare_digest = hmac.compare_digest

if __name__ == "__main__":
    try:
        port_number = int(sys.argv[1])
    except:
        port_number = 80
    if global_config['use_proxyfix']:
        app.wsgi_app = ProxyFix(app.wsgi_app)
    app.run(host='0.0.0.0', port=port_number)
