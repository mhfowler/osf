import json
import requests
import threading

from slackclient import SlackClient

from osf_scraper_api.settings import ENV_DICT


def list_channels():
    """
    helper method for listing all slack channels
    :return: None
    """
    bot_token = ENV_DICT.get('SLACKBOT_TOKEN')
    if not bot_token:
        return []
    sc = SlackClient(bot_token)
    channels = sc.api_call('channels.list')
    # this is to make this function backwards-compatible with older version of SlackClient which returns a string
    if isinstance(channels, basestring):
        channels = json.loads(channels)
    return channels

# construct a map from slack channel name to slack channel id (the format that the API expects)
print '++ constructing slack channel map'
if ENV_DICT.get('LOG_TO_SLACK'):
    channels = list_channels()
    channel_map = {}
    if channels:
        for channel in channels['channels']:
            channel_map[channel['name']] = channel['id']
else:
    channels = []
    channel_map = {}


def slack_notify_message(message, channel_name=None):
    """
    sends a slack message (for logging, and error notification)
    :param message: string of message to send
    :param channel_name: string name of slack channel to log message to (this channel must exist)
    -- note that a suffix may be appended to this channel name automatically SLACK_CHANNEL_SUFFIX is in env.json
    :return: None
    """
    if ENV_DICT.get('SLACK_WEBHOOK_URL'):
        webhook_url = ENV_DICT['SLACK_WEBHOOK_URL']
        slack_data = {'text': message}
        try:
            requests.post(
                webhook_url, data=json.dumps(slack_data),
                headers={'Content-Type': 'application/json'}
            )
        except:
            pass
        # def webhook_post():
        #     requests.post(
        #         webhook_url, data=json.dumps(slack_data),
        #         headers={'Content-Type': 'application/json'}
        #     )
        # t = threading.Thread(target=webhook_post)
        # t.start()

    else:
        # get slack token
        bot_token = ENV_DICT.get('SLACKBOT_TOKEN')
        sc = SlackClient(bot_token)

        # if a suffix is specified for this environment, add suffix to channel_name
        cname = channel_name or '_osf_scraper_api'
        slack_suffix = ENV_DICT.get('SLACK_CHANNEL_SUFFIX')
        if slack_suffix:
            cname += slack_suffix

        # lookup channel_id associated with channel name
        # (will throw an error if channel name doesn't exist which is what we want)
        channel_id = channel_map[cname]

        # make a request to API to log message to slack
        sc.api_call('chat.postMessage', channel=channel_id,
                    text='{message}'.format(message=message), link_names=1,
                    as_user=True)
