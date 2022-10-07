import requests
from contextlib import suppress

import redis
from environs import Env
from flask import Flask, request, g

from moltin import MoltinClient

env = Env()
env.read_env()

app = Flask(__name__)
redis_client = redis.Redis(
    'redis-12339.c293.eu-central-1-1.ec2.cloud.redislabs.com',
    port=12339, username='default', password=env('REDIS_PASSWORD'), decode_responses=True
)


@app.before_request
def config():
    g.facebook_token = env('FACEBOOK_ACCESS_TOKEN')
    g.moltin_client = MoltinClient(env('MOLTIN_CLIENT_ID'), env('MOLTIN_CLIENT_SECRET'))


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
                sender_id = messaging_event['sender']['id']
                message_text, postback_payload = '', ''
                if messaging_event.get('message'):
                    message_text = messaging_event['message']['text']
                if messaging_event.get('postback'):
                    postback_payload = messaging_event['postback']['payload']
                handle_users_reply(sender_id, message_text, postback_payload)
    return 'ok', 200


def handle_start(sender_id, message_text, postback_payload):
    if postback_payload not in ['basic', 'special', 'spicy', 'nourishing']:
        postback_payload = 'basic'
    send_menu(sender_id, postback_payload)
    return 'MENU'


def handle_menu(sender_id, message_text, postback_payload):
    if postback_payload == 'cart':
        send_cart(sender_id)
        return 'CART'
    if '+' in postback_payload:
        product_id = postback_payload.replace('+', '')
        with suppress(requests.exceptions.HTTPError):
            g.moltin_client.add_product_to_cart(product_id, 1, f'facebookid_{sender_id}')
        product = g.moltin_client.get_product(product_id, sender_id)
        send_message(sender_id, f'Пицца «{product["name"]}» добавлена в корзину')
    return 'MENU'


def handle_cart(sender_id, message_text, postback_payload):
    if postback_payload == 'back':
        send_menu(sender_id)
        return 'MENU'
    if '+' in postback_payload:
        product_id = postback_payload.replace('+', '')
        with suppress(requests.exceptions.HTTPError):
            g.moltin_client.add_product_to_cart(product_id, 1, f'facebookid_{sender_id}')
        product = g.moltin_client.get_product(product_id, sender_id)
        send_message(sender_id, f'Ещё одна пицца «{product["name"]}» добавлена в корзину')
        send_cart(sender_id)
    if '×' in postback_payload:
        product_id = postback_payload.replace('×', '')
        with suppress(requests.exceptions.HTTPError):
            g.moltin_client.remove_product_from_cart(product_id, f'facebookid_{sender_id}')
        product = g.moltin_client.get_product(product_id, sender_id)
        send_message(sender_id, f'Пицца «{product["name"]}» удалена из корзины')
        send_cart(sender_id)
    return 'CART'


def handle_users_reply(sender_id, message_text, postback_payload):
    states_functions = {
        'START': handle_start,
        'MENU': handle_menu,
        'CART': handle_cart
    }
    # redis_client.set(f'facebookid_{sender_id}', '')
    recorded_state = redis_client.get(f'facebookid_{sender_id}')
    if not recorded_state or recorded_state not in states_functions.keys():
        user_state = 'START'
    else:
        user_state = recorded_state
    if message_text == '/start':
        user_state = 'START'
    state_handler = states_functions[user_state]
    next_state = state_handler(sender_id, message_text, postback_payload)
    redis_client.set(f'facebookid_{sender_id}', next_state)


def get_menu_elements(recipient_id, category_slug='basic'):
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
    for product in g.moltin_client.get_products_by_category(category_slug):
        product = g.moltin_client.get_product(product['id'], f'facebookid_{recipient_id}')
        elements.append({
            'title': f'{product["name"]} ({product["price"]})',
            'image_url': product['image_url'],
            'subtitle': product['description'],
            'buttons': [
                {
                    'type': 'postback',
                    'title': '➕ Добавить в корзину',
                    'payload': f'+{product["id"]}'
                }
            ]
        })
    categories_buttons = []
    for category in g.moltin_client.get_categories():
        if category['slug'] == category_slug:
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


def send_menu(recipient_id, category_slug='basic'):
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
                    'elements': get_menu_elements(recipient_id, category_slug if category_slug else 'basic')
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


def get_cart_elements(recipient_id):
    cart_products, cart_cost = g.moltin_client.get_cart_data(f'facebookid_{recipient_id}')
    elements = [
        {
            'title': 'Корзина',
            'image_url': 'https://live.staticflickr.com/4815/44720247530_844525fc61_b.jpg',
            'subtitle': f'Сумма заказа {cart_cost}',
            'buttons': [
                {
                    'type': 'postback',
                    'title': '🍕 Оформить заказ',
                    'payload': 'order'
                },
                {
                    'type': 'postback',
                    'title': '🔠 В меню',
                    'payload': 'back'
                }
            ]
        }
    ]
    for product in cart_products:
        product = g.moltin_client.get_product(product['id'], f'facebookid_{recipient_id}')
        elements.append({
            'title': f'{product["name"]} ({product["price"]})',
            'image_url': product['image_url'],
            'subtitle': product['description'],
            'buttons': [
                {
                    'type': 'postback',
                    'title': '➕ Добавить ещё одну',
                    'payload': f'+{product["id"]}'
                },
                {
                    'type': 'postback',
                    'title': '➖ Убрать из корзины',
                    'payload': f'×{product["id"]}'
                }
            ]
        })
    return elements


def send_cart(recipient_id):
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
                    'elements': get_cart_elements(recipient_id)
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
