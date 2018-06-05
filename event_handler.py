#!/usr/bin/env python3

import json
import os
import re
import urllib
from requests.auth import HTTPBasicAuth
import ssl
import hmac
from hashlib import sha1

class GithubEventHandler:
    def __init__(self, event, data):
        self.event = event
        self.data = data

    def set_config(self, global_config, repos_config):
        self.global_config = global_config
        self.repos_config = repos_config
    
    def handle(self, signature=None):
        """
        github hook event handle goes here
        """
        print('handle github event: %s' % self.event)
        events_allowed = ['push', 'pull_request_review']
        if self.event == 'ping':
            return {'msg': 'Hi!'}
        elif self.event in events_allowed:
            event_hit = False
            repo_config = self.get_repo_config()
            if self.event == 'push':
                event_hit = self._is_push_hit(repo_config)
            elif self.event == 'pull_request_review':
                event_hit = self._is_pull_request_review_hit(repo_config)
            # work start execute here...
            if repo_config and event_hit:
                print("==========================")
                self._jenkins_build(repo_config)
                pass
            return "OK"
        else:
            return {'msg': 'wrong event type:%s' % self.event}

    def get_repo_config(self):
        if self.data and 'repository' in self.data:
            self.repo_meta = {
                'name': self.data['repository']['name'],
                'owner': self.data['repository']['owner']['name'],
            }
            return self.repos_config.get('{owner}/{name}'.format(**self.repo_meta), None)
        return None

    def _is_push_hit(self, repo_config):
        '''
        determine whether this event hits the corresponding repos
        '''
        # Try to match on branch as configured in repos.json
        match = re.match(r"refs/heads/(?P<branch>.*)", self.data['ref'])
        if match:
            self.repo_meta['branch'] = match.groupdict()['branch']
            if repo_config and (not repo_config['branch'] or self.repo_meta['branch'] in repo_config['branch']):
                return True
        return False

    def _is_pull_request_review_hit(self, repo_config):
        print(">> pull_request_review event with action: %s..." % self.data['action'])
        print(json.dumps(self.data, indent=2))
        # todo here...
        return False

    def _jenkins_build(self, repo_config):
        passman = urllib.request.HTTPPasswordMgrWithPriorAuth()
        passman.add_password(None,
                             self.global_config['jenkins']['host'],
                             self.global_config['jenkins']['user'],
                             self.global_config['jenkins']['token'],
                             is_authenticated=True)
        auth_handler = urllib.request.HTTPBasicAuthHandler(passman)
        ssl._create_default_https_context = ssl._create_unverified_context
        opener = urllib.request.build_opener(auth_handler)
        # opener.add_handler(urllib.request.ProxyHandler(dict(http='http://127.0.0.1:5555')))
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        for build_config in repo_config['jenkins_build']:
            # get build api url
            build_api_url = self.global_config['jenkins']['host']
            for project_name in build_config['job'].split('/'):
                build_api_url += '/job/' + project_name
            build_api_url += '/build?delay=0sec'
            # request param
            json_param = { "parameter": [] }
            for param_key, param_value in build_config['params'].items():
                param_value = param_value.format(**self.repo_meta) if isinstance(param_value, str) else param_value
                json_param['parameter'].append({ 'name': param_key, 'value': param_value })
            form_data = { 'json': json.dumps(json_param) }
            req = urllib.request.Request(url = build_api_url,
                                data = urllib.parse.urlencode(form_data).encode(encoding='utf-8'), 
                                headers = {'Content-Type': 'application/x-www-form-urlencoded'},
                                method = 'POST')
            opener.open(req)
