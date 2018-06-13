#!/usr/bin/env python3

import json
import re
import urllib
import ssl

class GithubEventHandler:
    def __init__(self, app, event, data):
        self.app = app
        self.event = event
        self.data = data

    def set_config(self, global_config, repos_config):
        self.global_config = global_config
        self.repos_config = repos_config
    
    def handle(self):
        """
        github hook event handle goes here
        """
        self.app.logger.info('==== handle github event: %s', self.event)
        # self.app.logger.info('data send: %s', json.dumps(self.data, indent=2))
        if self.event == 'ping':
            return {'msg': 'Hi!'}
        else:
            task_match = []
            repo_config = self.get_repo_config()
            if repo_config:
                for task_config in repo_config['tasks']:
                    event_hit = False
                    if self.event == 'push':
                        event_hit = self._is_task_push(task_config)
                    elif self.event == 'pull_request':
                        event_hit = self._is_task_pull_request(task_config)
                    if event_hit:
                        task_match.append(task_config)
            # work start execute here...
            for task in task_match:
                self.app.logger.debug("event hit, start tasks under %s/%s...", self.repo_meta['owner'], self.repo_meta['name'])
                self._jenkins_build(task)
                pass
            return "OK"

    def get_repo_config(self):
        if self.data and 'repository' in self.data:
            self.repo_meta = {
                'name': self.data['repository']['name'],
                'owner': self.data['repository']['owner']['login'],
            }
            if 'sender' in self.data:
                self.repo_meta['sender'] = self.data['sender']['login']
            return self.repos_config.get('{owner}/{name}'.format(**self.repo_meta), None)
        return None

    def _is_task_push(self, task_config):
        '''
        determine whether this event hits the corresponding repos
        '''
        # Try to match on branch as configured in repos.json
        match = re.match(r"refs/heads/(?P<branch>.*)", self.data['ref'])
        if match:
            self.repo_meta['branch'] = match.groupdict()['branch']
            # for task in repo_config['tasks']:
            if not ('branch' in task_config and self.repo_meta['branch'] not in task_config['branch'] or 'push' not in task_config['event']):
                hit_flag = False
                self.repo_meta['commit_ids'] = []
                for commit in self.data['commits']:
                    if not ('message_pattern' in task_config and not re.match(task_config['message_pattern'], commit['message'])):
                        hit_flag = True
                    self.repo_meta['commit_ids'].append(commit['id'])
                if hit_flag:
                    self.app.logger.info('push commit: [%s] to %s/%s:%s', ','.join(self.repo_meta['commit_ids']),
                                self.repo_meta['owner'], self.repo_meta['name'], self.repo_meta['branch'])
                    return True
        return False

    def _is_task_pull_request(self, task_config):
        self.repo_meta['action'] = self.data['action']
        self.repo_meta['branch'] = self.data['pull_request']['base']['ref']
        self.repo_meta['pull_request'] = {
            'number': self.data['number'],
            'branch': self.data['pull_request']['head']['ref'],
            'name': self.data['pull_request']['head']['repo']['name'],
            'owner': self.data['pull_request']['head']['repo']['owner']['login'],
            'created_by': self.data['pull_request']['user']['login'],
        }
        self.repo_meta['pull_request']['author'] = {'email': self._get_pull_author()}
        if not ('branch' in task_config and self.repo_meta['branch'] not in task_config['branch'] or 'pull_request' not in task_config['event']):
            if not ('action' in task_config and self.data['action'] not in task_config['action']):
                if not ('merged' in task_config and task_config['merged'] != self.data['pull_request']['merged']):
                    # task hit
                    if self.data['pull_request']['merged']:
                        self.repo_meta['pull_request']['merged_by'] = self.data['pull_request']['merged_by']['login']
                    self.app.logger.info('%s %s\'s %s pull request (%s/%s:%s => %s/%s:%s), number:%d',
                                self.repo_meta['action'], self.repo_meta['pull_request']['created_by'],
                                'merged' if self.data['pull_request']['merged'] else 'unmerged',
                                self.repo_meta['pull_request']['owner'], self.repo_meta['pull_request']['name'],
                                self.repo_meta['pull_request']['branch'], self.repo_meta['owner'],
                                self.repo_meta['name'], self.repo_meta['branch'], self.repo_meta['pull_request']['number'])
                    return True
        return False

    def _get_pull_author(self):
        opener = self._get_auth_opener('https://api.github.com',
                                       self.global_config['github']['user'],
                                       self.global_config['github']['token'])
        github_api_url = 'https://api.github.com/repos/{owner}/{name}/pulls/{number}/commits'.format(**self.repo_meta['pull_request'])
        req = urllib.request.Request(url=github_api_url, method='GET')
        res = opener.open(req)
        json_result = json.loads(res.read().decode('utf-8'))
        res.close()
        email = json_result[-1]['commit']['author']['email'] if json_result and len(json_result) > 0 else None
        return email

    def _get_auth_opener(self, host, user, token):
        passman = urllib.request.HTTPPasswordMgrWithPriorAuth()
        passman.add_password(None, host, user, token, is_authenticated=True)
        auth_handler = urllib.request.HTTPBasicAuthHandler(passman)
        ssl._create_default_https_context = ssl._create_unverified_context
        opener = urllib.request.build_opener(auth_handler)
        # opener.add_handler(urllib.request.ProxyHandler(dict(http='http://127.0.0.1:5555')))
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        return opener

    def _jenkins_build(self, task_config):
        opener = self._get_auth_opener(self.global_config['jenkins']['host'],
                                       self.global_config['jenkins']['user'],
                                       self.global_config['jenkins']['token'])
        for build_config in task_config['jenkins_build']:
            self.app.logger.info('>> execute jenkins build job: %s...', build_config['job'])
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
