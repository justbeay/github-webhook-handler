#!/usr/bin/env python3

import json
import re
import urllib
import http_helper
from jenkins_build import JenkinsBuild

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
                self.app.logger.info("event hit, start tasks under %s/%s...", self.repo_meta['owner'], self.repo_meta['name'])
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
        if not ('branch' in task_config and self.repo_meta['branch'] not in task_config['branch'] or 'pull_request' not in task_config['event']):
            if not ('action' in task_config and self.data['action'] not in task_config['action']):
                if not ('merged' in task_config and task_config['merged'] != self.data['pull_request']['merged']):
                    # task hit
                    self.repo_meta['pull_request']['author'] = {'email': self._get_pull_author()}
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
        opener = http_helper.get_auth_opener(host='https://api.github.com',
                                       user=self.global_config['github']['user'],
                                       token=self.global_config['github']['token'])
        github_api_url = 'https://api.github.com/repos/{owner}/{name}/pulls/{pull_request[number]}/commits'.format(**self.repo_meta)
        json_result = http_helper.request_json_api(self.app.logger, opener, github_api_url)
        email = json_result[-1]['commit']['author']['email'] if json_result and len(json_result) > 0 else None
        return email

    def _jenkins_build(self, task_config):
        opener = http_helper.get_auth_opener(host=self.global_config['jenkins']['host'],
                                       user=self.global_config['jenkins']['user'],
                                       token=self.global_config['jenkins']['token'])
        for build_config in task_config['jenkins_build']:
            self.app.logger.info('>> add jenkins build job: %s to build queue...', build_config['job'])
            JenkinsBuild.addTask(build_config, self.repo_meta)
