import re
import hashlib
import datetime

from flask import make_response, jsonify, Blueprint, request

from osf_scraper_api.utilities.fb_helper import fetch_friends_of_user
from osf_scraper_api.web.jobs.fb_posts import scrape_fb_posts
from osf_scraper_api.web.jobs.fb_friends import scrape_fb_friends
from osf_scraper_api.web.jobs.screenshot import screenshot_user_job, screenshot_multi_user_job
from osf_scraper_api.web.jobs.test_rq import test_rq
from osf_scraper_api.utilities.log_helper import _log
from osf_scraper_api.utilities.fs_helper import file_exists, list_files_in_folder
from osf_scraper_api.settings import TEMPLATE_DIR


def get_facebook_blueprint(osf_queue):
    facebook_blueprint = Blueprint('facebook_blueprint', __name__, template_folder=TEMPLATE_DIR)

    @facebook_blueprint.route('/api/test_rq/<test_id>/', methods=['GET'])
    def test_rq_endpoint(test_id):
        osf_queue.enqueue(test_rq, test_id)
        return make_response(jsonify({
            'message': 'Job enqueued for scraping.'
        }), 200)

    @facebook_blueprint.route('/api/fb_friends/', methods=['POST'])
    def fb_friends_endpoint():
        params = request.get_json()
        users = params.get('users')
        if users != 'all_friends':
            _log('++ enqueing fb_friends job')
            osf_queue.enqueue(scrape_fb_friends,
                users=params['users'],
                fb_username=params['fb_username'],
                fb_password=params['fb_password'],
                no_skip=params.get('no_skip')
            )
        else:
            central_user = params.get('central_user')
            friends = fetch_friends_of_user(central_user)
            for friend in friends:
                _log('++ enqueing fb_friends job for: {}'.format(friend))
                osf_queue.enqueue(scrape_fb_friends,
                  users=[friend],
                  fb_username=params['fb_username'],
                  fb_password=params['fb_password'],
                  no_skip=params.get('no_skip')
                )
        return make_response(jsonify({
            'message': 'fb_friend job enqueued'
        }), 200)

    @facebook_blueprint.route('/api/fb_posts/', methods=['POST'])
    def fb_posts_endpoint():
        params = request.get_json()
        job_name = params.get('job_name')
        # if a job_name is provided, then create a separate queue job for each user
        if job_name:
            _log('++ enqueing fb_posts job for each user provided')
            users = params.get('users')
            if users == 'all_friends':
                central_user = params.get('central_user')
                _log('++ looking up users from friends of central_user: {}'.format(central_user))
                users = fetch_friends_of_user(central_user)
            for user in users:
                key_name = 'jobs/{}/{}.json'.format(job_name, user)
                # if already exists then skip
                if params.get('no_skip') is not True:
                    if file_exists(key_name):
                        _log('++ skipping {}'.format(key_name))
                        continue
                # otherwise scrape and then save this user
                params['users'] = [user]
                params['output_path'] = key_name
                params['replace'] = True
                if params.get('job_name'):
                    del params['job_name']
                _log('++ enqueing fb_posts job for user {}'.format(user))
                osf_queue.enqueue(scrape_fb_posts, params)
        else:
            _log('++ enqueing fb_posts job')
            osf_queue.enqueue(scrape_fb_posts, params)
        # finally return 'OK' response
        return make_response(jsonify({
            'message': 'fb_post job enqueued'
        }), 200)

    @facebook_blueprint.route('/api/fb_screenshots/', methods=['POST'])
    def fb_screenshots_endpoint():
        params = request.get_json()
        input_folder = params['input_folder']
        user_files = list_files_in_folder(input_folder)
        no_skip = params.get('no_skip') is not True
        fb_username = params['fb_username']
        fb_password = params['fb_password']
        _log('++ enqueuing screenshot jobs for {} users'.format(len(user_files)))
        job_per_user = params.get('job_per_user')
        # if job_per_user, then make one job for each user
        if job_per_user:
            for user_file in user_files:
                osf_queue.enqueue(screenshot_user_job,
                                  user_file=user_file,
                                  input_folder=input_folder,
                                  fb_username=fb_username,
                                  fb_password=fb_password,
                                  no_skip=no_skip,
                                  timeout=600
                                  )
            _log('++ enqueued screenshot jobs for all {} users'.format(len(user_files)))
        # otherwise make a single job for all the posts
        else:
            osf_queue.enqueue(screenshot_multi_user_job,
                              user_files=user_files,
                              input_folder=input_folder,
                              fb_username=fb_username,
                              fb_password=fb_password,
                              no_skip=no_skip,
                              timeout=129600
                              )
            _log('++ enqueued 1 job for {} users'.format(len(user_files)))
        return make_response(jsonify({
            'message': 'fb_screenshot job enqueued'
        }), 200)

    return facebook_blueprint
