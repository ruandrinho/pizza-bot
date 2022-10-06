import requests

import redis
from environs import Env
from flask import Flask, request, g

from moltin import MoltinClient

app = Flask(__name__)

env = Env()
env.read_env()


@app.before_request
def config():
    g.facebook_token = env('FACEBOOK_ACCESS_TOKEN')
    g.moltin_client = MoltinClient(env('MOLTIN_CLIENT_ID'), env('MOLTIN_CLIENT_SECRET'))
    g.redis = redis.Redis(
        'redis-12339.c293.eu-central-1-1.ec2.cloud.redislabs.com',
        port=12339, username='default', password=env('REDIS_PASSWORD'), decode_responses=True
    )


@app.route('/', methods=['GET'])
def verify():
    if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.challenge'):
        if not request.args.get('hub.verify_token') == env('FACEBOOK_VERIFY_TOKEN'):
            return 'Verification token mismatch', 403
        return request.args['hub.challenge'], 200
    return 'Hello world', 200


@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if data['object'] == 'page':
        for entry in data['entry']:
            for messaging_event in entry['messaging']:
                if messaging_event.get('message'):
                    sender_id = messaging_event['sender']['id']
                    message_text = messaging_event['message']['text']
                    handle_users_reply(sender_id, message_text)
    return 'ok', 200


def handle_start(sender_id, message_text):
    send_menu(sender_id)
    return 'START'


def handle_users_reply(sender_id, message_text):
    states_functions = {
        'START': handle_start,
    }
    recorded_state = g.redis.get(f'facebookid_{sender_id}')
    if not recorded_state or recorded_state not in states_functions.keys():
        user_state = 'START'
    else:
        user_state = recorded_state
    if message_text == '/start':
        user_state = 'START'
    state_handler = states_functions[user_state]
    next_state = state_handler(sender_id, message_text)
    g.redis.set(f'facebookid_{sender_id}', next_state)


def get_menu_elements(recipient_id):
    elements = [
        {
            'title': 'Меню',
            'image_url': 'https://img.freepik.com/vektoren-premium/pizza-logo-design-vorlage_15146-192.jpg',
            'buttons': [
                {
                    'type': 'postback',
                    'title': '🍕 Корзина',
                    'payload': 'cart'
                },
                {
                    'type': 'postback',
                    'title': '🔥 Акции',
                    'payload': 'actions'
                }
            ]
        }
    ]
    for product in g.moltin_client.get_products_by_category('basic'):
        product = g.moltin_client.get_product(product['id'], recipient_id)
        elements.append({
            'title': f'{product["name"]} ({product["price"]})',
            'image_url': product['image_url'],
            'subtitle': product['description'],
            'buttons': [
                {
                    'type': 'postback',
                    'title': '➕ Добавить в корзину',
                    'payload': product['id']
                }
            ]
        })
    categories_buttons = []
    for category in g.moltin_client.get_categories():
        if category['slug'] == 'basic':
            continue
        categories_buttons.append({
            'type': 'postback',
            'title': category['name'],
            'payload': category['slug']
        })
    elements.append({
        'title': 'Не нашли нужную пиццу?',
        'image_url': 'https://primepizza.ru/uploads/position/large_0c07c6fd5c4dcadddaf4a2f1a2c218760b20c396.jpg',
        'subtitle': 'Выберите категорию',
        'buttons': categories_buttons
    })
    return elements


def send_menu(recipient_id):
    params = {'access_token': g.facebook_token}
    headers = {'Content-Type': 'application/json'}
    request_content = {
        'recipient': {
            'id': recipient_id
        },
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'elements': get_menu_elements(recipient_id)
                }
            }
        }
    }
    response = requests.post(
        'https://graph.facebook.com/v2.6/me/messages',
        params=params, headers=headers, json=request_content
    )
    print(response.json())
    response.raise_for_status()


def send_message(recipient_id, message_text):
    params = {'access_token': g.facebook_token}
    headers = {'Content-Type': 'application/json'}
    request_content = {
        'recipient': {
            'id': recipient_id
        },
        'message': {
            'text': message_text
        }
    }
    response = requests.post(
        'https://graph.facebook.com/v2.6/me/messages',
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


if __name__ == '__main__':
    app.run(debug=True)
