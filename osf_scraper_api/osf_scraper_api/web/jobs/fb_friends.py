from osf_scraper_api.utilities.log_helper import _log, _log_image
from osf.scrapers.facebook import FbScraper
from osf_scraper_api.settings import SELENIUM_URL
from osf_scraper_api.utilities.fs_helper import save_dict, file_exists


def scrape_fb_friends(users, fb_username, fb_password, no_skip=False):
    _log('++ starting fb_friends job')
    fb_scraper = FbScraper(
                    fb_username=fb_username,
                    fb_password=fb_password,
                    command_executor=SELENIUM_URL,
                    log=_log,
                    log_image=_log_image
                )
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