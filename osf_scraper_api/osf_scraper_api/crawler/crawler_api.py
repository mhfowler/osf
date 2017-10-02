import requests
import json
import  time
import random

from flask import make_response, jsonify, Blueprint, request, abort

from osf_scraper_api.crawler.fb_posts import scrape_fb_posts_job, fb_posts_post_process
from osf_scraper_api.crawler.screenshot import screenshot_user_job, screenshot_multi_user_job
from osf_scraper_api.crawler.utils import fetch_friends_of_user
from osf_scraper_api.crawler.utils import get_unprocessed_friends
from osf_scraper_api.crawler.utils import get_user_posts_file
from osf_scraper_api.crawler.make_pdf import make_pdf_job
from osf_scraper_api.crawler.whats_on_your_mind import whats_on_your_mind_job
from osf_scraper_api.crawler.fb_friends import crawler_scrape_fb_friends
from osf_scraper_api.settings import TEMPLATE_DIR
from osf_scraper_api.utilities.fs_helper import file_exists, list_files_in_folder
from osf_scraper_api.utilities.log_helper import _log, _capture_exception
from osf_scraper_api.utilities.osf_helper import paginate_list, get_fb_scraper
from osf_scraper_api.utilities.rq_helper import enqueue_job
from osf_scraper_api.settings import ENV_DICT


def get_crawler_blueprint(osf_queue):
    crawler_blueprint = Blueprint('crawler_blueprint', __name__, template_folder=TEMPLATE_DIR)

    @crawler_blueprint.route('/api/whats_on_your_mind/', methods=['POST'])
    def whats_on_your_mind_endpoint():
        _log('++ new request to /api/whats_on_your_mind/')
        params = request.get_json()
        required_fields = [
            'fb_username',
            'fb_password',
        ]
        for req_field in required_fields:
            if req_field not in params.keys():
                abort(make_response(jsonify({'message': '{} field is required.'.format(req_field)}), 422))

        fb_username = params['fb_username']
        fb_password = params['fb_password']
        enqueue_job(whats_on_your_mind_job, fb_username=fb_username, fb_password=fb_password)
        return make_response(jsonify({
            'message': "Thanks, we'll send an email to {} in 1-2 days when your PDF is finished.".format(fb_username)
        }), 200)

    @crawler_blueprint.route('/api/crawler/fb_friends/', methods=['POST'])
    def fb_friends_endpoint():
        params = request.get_json()
        users = params.get('users')
        post_process = params.get('post_process')
        if users != 'all_friends':
            _log('++ enqueing fb_friends job')
            enqueue_job(crawler_scrape_fb_friends,
                users=params['users'],
                fb_username=params['fb_username'],
                fb_password=params['fb_password'],
                no_skip=params.get('no_skip'),
                post_process=post_process
            )
        else:
            central_user = params.get('central_user')
            friends = fetch_friends_of_user(central_user)
            for friend in friends:
                _log('++ enqueing fb_friends job for: {}'.format(friend))
                enqueue_job(crawler_scrape_fb_friends,
                  users=[friend],
                  fb_username=params['fb_username'],
                  fb_password=params['fb_password'],
                  no_skip=params.get('no_skip'),
                  post_process=params.get('post_process')
                )
        return make_response(jsonify({
            'message': 'fb_friend job enqueued'
        }), 200)

    @crawler_blueprint.route('/api/crawler/fb_posts/', methods=['POST'])
    def fb_posts_endpoint():
        params = request.get_json()
        users = params.get('users')
        if users == 'all_friends':
            central_user = params.get('central_user')
            _log('++ looking up users from friends of central_user: {}'.format(central_user))
            users = fetch_friends_of_user(central_user)
            users_to_scrape = get_unprocessed_friends(central_user)
        else:
            users_to_scrape = []
            num_skipped = 0
            num_users = len(users)
            for index, user in enumerate(users):
                if not index % 10:
                    _log('++ {}/{}'.format(index, num_users))
                key_name = get_user_posts_file(user)
                # if already exists then skip
                if params.get('no_skip') is not True:
                    if file_exists(key_name):
                        num_skipped +=1
                        continue
                users_to_scrape.append(user)
            _log('++ skipped {} users'.format(num_skipped))

        # for testing, reduce sample size
        if ENV_DICT.get('TEST_SAMPLE_SIZE'):
            sample_size = ENV_DICT.get('TEST_SAMPLE_SIZE')
            _log('++ truncating users_to_scrape for testing: {}'.format(sample_size))
            users_to_scrape = random.sample(users_to_scrape, min(sample_size, len(users_to_scrape)))

        # now paginate and scrape
        num_to_scrape = len(users_to_scrape)
        num_total = len(users)
        _log('++ preparing to scrape {} users ({} total)'.format(num_to_scrape, num_total))
        if ENV_DICT.get("TEST_SAMPLE_SIZE"):
            page_size = 2
        else:
            page_size = 50
        pages = paginate_list(mylist=users_to_scrape, page_size=page_size)
        _log('++ enqueing {} users in {} jobs'.format(len(users_to_scrape), len(pages)))
        for index, page in enumerate(pages):
            _log('++ enqueing {} job'.format(index))
            enqueue_job(scrape_fb_posts_job,
                users=page,
                params=params,
                fb_username=params['fb_username'],
                fb_password=params['fb_password'],
                post_process=params.get('post_process'),
                central_user=params.get('central_user'),
                timeout=5000
            )
        if not pages:
            if params.get('post_process'):
                _log('++ enqueued 0 jobs, so starting post process function directly')
                fb_posts_post_process(
                    central_user=params.get('central_user'),
                    fb_username=params['fb_username'],
                    fb_password=params['fb_password']
                )
        # finally return 'OK' response
        return make_response(jsonify({
            'message': 'fb_post job enqueued'
        }), 200)

    @crawler_blueprint.route('/api/crawler/fb_screenshots/', methods=['POST'])
    def fb_screenshots_endpoint():
        params = request.get_json()
        input_folder = params['input_folder']
        no_skip = params.get('no_skip') is not True
        fb_username = params['fb_username']
        fb_password = params['fb_password']
        post_process = params.get('post_process')
        central_user = params.get('central_user')
        # if central_user is provided, then create a list of all of their friends which have a posts file
        if central_user:
            user_files = []
        else:
            user_files = list_files_in_folder(input_folder)
        job_per_user = params.get('job_per_user')
        # if job_per_user, then make one job for each user
        if job_per_user:
            _log('++ enqueuing screenshot jobs for {} users'.format(len(user_files)))
            for user_file in user_files:
                enqueue_job(screenshot_user_job,
                                  user_file=user_file,
                                  input_folder=input_folder,
                                  fb_username=fb_username,
                                  fb_password=fb_password,
                                  no_skip=no_skip,
                                  timeout=600
                                  )
            _log('++ enqueued screenshot jobs for all {} users'.format(len(user_files)))
        # otherwise make a single job for all the posts, which makes other jobs
        else:
            enqueue_job(screenshot_multi_user_job,
                user_files=user_files,
                central_user=central_user,
                input_folder=input_folder,
                fb_username=fb_username,
                fb_password=fb_password,
                no_skip=no_skip,
                post_process=post_process,
                timeout = 600
            )
        return make_response(jsonify({
            'message': 'fb_screenshot job enqueued'
        }), 200)

    @crawler_blueprint.route('/api/crawler/pdf/', methods=['POST'])
    def make_pdf_endpoint():
        params = request.get_json()
        fb_username = params['fb_username']
        fb_password = params['fb_password']
        enqueue_job(make_pdf_job, fb_username=fb_username, fb_password=fb_password, timeout=1800)
        return make_response(jsonify({
            'message': 'pdf job enqueued'
        }), 200)

    @crawler_blueprint.route('/api/my_ip/', methods=['GET'])
    def get_ip_endpoint():
        fb_scraper = get_fb_scraper(fb_username='', fb_password='')
        fb_scraper.driver.get('https://whatismyipaddress.com/')
        time.sleep(4)
        fb_scraper.log_screenshot()
        time.sleep(2)
        return make_response(jsonify({
                'message': 'ip address found'
        }), 200)

    return crawler_blueprint
