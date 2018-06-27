#!/usr/bin/env python3
from queue import Queue, Empty
from urllib import parse
import json
import time
import http_helper

class JenkinsBuild(object):
    
    buildQueue = Queue()

    @staticmethod
    def addTask(build_config, repo_meta):
        buildTask = dict(build_config=build_config, repo_meta=repo_meta)
        JenkinsBuild.buildQueue.put(buildTask)

    @staticmethod
    def start(logger, global_config):
        while True:
            buildTask = JenkinsBuild.buildQueue.get()
            # if buildTask is None:
            #     time.sleep(3)
            #     continue
            jobName = buildTask['build_config']['job']
            logger.debug("get one jenkins build task: %s from build queue", jobName)
            # check until the jenkins job having no build task remains unfinished
            instance = JenkinsBuild(logger, global_config['jenkins']['host'], 
                                        global_config['jenkins']['user'], 
                                        global_config['jenkins']['token'])
            while instance.get_job_building_status(jobName):
                logger.debug("jenkins job: %s have running task now, wait util free...", jobName)
                time.sleep(5)
            # no build job in progress, do jenkins build
            logger.info("execute jenkins build job: %s...", jobName)
            instance.do_build(jobName, buildTask['build_config']['params'], buildTask['repo_meta'])

    def __init__(self, logger, hostname, username, token):
        self.logger = logger
        self.hostname = hostname
        self.username = username
        self.token = token

    def do_build(self, jobName, buildTriggers, repo_meta):
        opener = http_helper.get_auth_opener(host=self.hostname, user=self.username, token=self.token)
        # get build api url
        api_url = self.hostname
        for project_name in jobName.split('/'):
            api_url += '/job/' + project_name
        api_url += '/build?delay=0sec'
        # request param
        json_param = { "parameter": [] }
        for param_key, param_value in buildTriggers.items():
            param_value = param_value.format(**repo_meta) if isinstance(param_value, str) else param_value
            json_param['parameter'].append({ 'name': param_key, 'value': param_value })
        form_data = { 'json': json.dumps(json_param) }
        http_helper.request_api(self.logger, opener, url=api_url, method='POST', 
                                data=parse.urlencode(form_data).encode(encoding='utf-8'),
                                headers = {'Content-Type': 'application/x-www-form-urlencoded'})

    def get_job_building_status(self, jobName):
        opener = http_helper.get_auth_opener(host=self.hostname, user=self.username, token=self.token)
        # get build api url
        api_url = self.hostname
        for project_name in jobName.split('/'):
            api_url += '/job/' + project_name
        api_url += '/lastBuild/api/json?tree=building'
        json_result = http_helper.request_json_api(self.logger, opener, url=api_url)
        return json_result['building']
