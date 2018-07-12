#!/usr/bin/env python3
import io
import os
import sys
import json
from logging.config import dictConfig
from flask import Flask, request, abort
from event_handler import GithubEventHandler
from jenkins_build import JenkinsBuild
from validation import Validation
from threading import Thread

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
logging_config = json.loads(io.open(BASE_APP_PATH + '/config/logging.json', 'r').read())

if 'use_proxyfix' in global_config and global_config['use_proxyfix']:
    from werkzeug.contrib.fixers import ProxyFix

dictConfig(logging_config)
app = Flask(__name__)
validation = Validation(global_config)


@app.route("/", methods=['GET', 'POST'])
def index():
    if not validation.validate_ip():
        abort(403)
    if request.method == 'GET':
        return 'OK'
    elif request.method == 'POST':
        event = request.headers.get('X-GitHub-Event')
        payload = json.loads(request.data.decode('utf8')) if request.data else None
        handler = GithubEventHandler(app, event, payload)
        handler.set_config(global_config, repos_config)
        repo_config = handler.get_repo_config()
        secretkey = repo_config['secretkey'] if repo_config else None
        if not validation.validate_secret(secretkey):
            abort(403)
        result = handler.handle()
        return json.dumps(result) if type(result) == dict else result


if __name__ == "__main__":
    try:
        port_number = int(sys.argv[1])
    except:
        port_number = 80
    if global_config['use_proxyfix']:
        app.wsgi_app = ProxyFix(app.wsgi_app)
    Thread(target=JenkinsBuild.start, args=[app.logger, global_config]).start()
    app.run(host='0.0.0.0', port=port_number, threaded=True)
