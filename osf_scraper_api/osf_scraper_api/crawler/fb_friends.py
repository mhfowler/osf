import requests
import json

from osf_scraper_api.settings import ENV_DICT
from osf_scraper_api.utilities.log_helper import _log, _log_image
from osf_scraper_api.utilities.osf_helper import get_fb_scraper
from osf_scraper_api.utilities.fs_helper import save_dict, file_exists


def crawler_scrape_fb_friends(users, fb_username, fb_password, no_skip=False, post_process=False):
    _log('++ starting fb_friends job')
    fb_scraper = get_fb_scraper(fb_username=fb_username, fb_password=fb_password)
    fb_scraper.fb_login()

    for user in users:
        key_name = 'friends/{}.json'.format(user)
        if no_skip is not True:
            if file_exists(key_name):
                _log('++ skipping {}'.format(key_name))
                continue
        # otherwise scrape and then save to s3
        output_dict = fb_scraper.get_friends(users=[user])
        save_dict(output_dict, key_name)
        _log('++ data saved to {}'.format(key_name))
    _log('++ request complete')

    if post_process:
        _log('++ initiating post_process job')
        for user in users:
            job_params = {
                'fb_username': fb_username,
                'fb_password': fb_password,
                "users": "all_friends",
                "central_user": user,
                "no_skip": False,
                "jump_to_timestamp": 1480482000,
                "before_timestamp": 1479358800,
                "after_timestamp": 1478494800,
                "post_process": True
            }
            url = '{API_DOMAIN}/api/crawler/fb_posts/'.format(API_DOMAIN=ENV_DICT['API_DOMAIN'])
            headers = {'content-type': 'application/json'}
            requests.post(url, data=json.dumps(job_params), headers=headers)
            _log('++ curled job to scrape posts of all friends of {}'.format(user))