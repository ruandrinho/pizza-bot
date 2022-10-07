import redis
from environs import Env
from flask import Flask, request

from fb_handlers import handle_users_reply
from moltin import MoltinClient

app = Flask(__name__)


@app.route('/', methods=['GET'])
def verify():
    if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.challenge'):
        if not request.args.get('hub.verify_token') == app.config['facebook_verify_token']:
            return 'Verification token mismatch', 403
        return request.args['hub.challenge'], 200
    return 'Hello world', 200


@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if data['object'] == 'page':
        for entry in data['entry']:
            for messaging_event in entry['messaging']:
                sender_id = messaging_event['sender']['id']
                message_text, postback_payload = '', ''
                if messaging_event.get('message'):
                    message_text = messaging_event['message']['text']
                if messaging_event.get('postback'):
                    postback_payload = messaging_event['postback']['payload']
                handle_users_reply(sender_id, message_text, postback_payload, app.config)
    return 'ok', 200


if __name__ == '__main__':
    env = Env()
    env.read_env()

    app.config.update(
        facebook_access_token=env('FACEBOOK_ACCESS_TOKEN'),
        facebook_verify_token=env('FACEBOOK_VERIFY_TOKEN'),
        redis_client=redis.Redis(
            'redis-12339.c293.eu-central-1-1.ec2.cloud.redislabs.com',
            port=12339, username='default', password=env('REDIS_PASSWORD'), decode_responses=True
        ),
        moltin_client=MoltinClient(env('MOLTIN_CLIENT_ID'), env('MOLTIN_CLIENT_SECRET'))
    )

    app.run(debug=True)
