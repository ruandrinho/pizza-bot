import json
import requests
from contextlib import suppress


def handle_users_reply(sender_id, message_text, postback_payload, app_config):
    redis_client = app_config['redis_client']
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
    next_state = state_handler(sender_id, message_text, postback_payload, app_config)
    redis_client.set(f'facebookid_{sender_id}', next_state)


def handle_start(sender_id, message_text, postback_payload, app_config):
    moltin_client = app_config['moltin_client']
    if postback_payload not in [category['slug'] for category in moltin_client.get_categories()]:
        postback_payload = 'basic'
    send_menu(sender_id, postback_payload, app_config)
    return 'MENU'


def handle_menu(sender_id, message_text, postback_payload, app_config):
    moltin_client = app_config['moltin_client']
    if postback_payload == 'cart':
        send_cart(sender_id, app_config)
        return 'CART'
    if postback_payload == 'actions':
        send_message(sender_id, 'Функция в разработке', app_config)
        return 'MENU'
    if '+' in postback_payload:
        product_id = postback_payload.replace('+', '')
        with suppress(requests.exceptions.HTTPError):
            moltin_client.add_product_to_cart(product_id, 1, f'facebookid_{sender_id}')
        product = moltin_client.get_product(product_id, sender_id)
        send_message(sender_id, f'Пицца «{product["name"]}» добавлена в корзину', app_config)
        return 'MENU'
    return handle_start(sender_id, message_text, postback_payload, app_config)


def handle_cart(sender_id, message_text, postback_payload, app_config):
    moltin_client = app_config['moltin_client']
    if postback_payload == 'back':
        send_menu(sender_id, 'basic', app_config)
        return 'MENU'
    if postback_payload == 'order':
        send_message(sender_id, 'Функция в разработке', app_config)
        return 'CART'
    if '+' in postback_payload:
        product_id = postback_payload.replace('+', '')
        with suppress(requests.exceptions.HTTPError):
            moltin_client.add_product_to_cart(product_id, 1, f'facebookid_{sender_id}')
        product = moltin_client.get_product(product_id, sender_id)
        send_message(sender_id, f'Ещё одна пицца «{product["name"]}» добавлена в корзину', app_config)
        send_cart(sender_id, app_config)
    if '×' in postback_payload:
        product_id = postback_payload.replace('×', '')
        with suppress(requests.exceptions.HTTPError):
            moltin_client.remove_product_from_cart(product_id, f'facebookid_{sender_id}')
        product = moltin_client.get_product(product_id, sender_id)
        send_message(sender_id, f'Пицца «{product["name"]}» удалена из корзины', app_config)
        send_cart(sender_id, app_config)
    return 'CART'


def get_menu_elements(category_slug, redis_client):
    elements = redis_client.get(f'elements_{category_slug}')
    if elements:
        return json.loads(elements)
    return


def send_menu(recipient_id, category_slug, app_config):
    redis_client = app_config['redis_client']
    params = {'access_token': app_config['facebook_access_token']}
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
                    'elements': get_menu_elements(category_slug if category_slug else 'basic', redis_client)
                }
            }
        }
    }
    response = requests.post(
        'https://graph.facebook.com/v2.6/me/messages',
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


def get_cart_elements(recipient_id, moltin_client):
    cart_products, cart_cost = moltin_client.get_cart_data(f'facebookid_{recipient_id}')
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
        product.update(moltin_client.get_product(product['id'], f'facebookid_{recipient_id}'))
        elements.append({
            'title': f'{product["name"]} ({product["quantity"]} шт. на {product["total_cost"]})',
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


def send_cart(recipient_id, app_config):
    moltin_client = app_config['moltin_client']
    params = {'access_token': app_config['facebook_access_token']}
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
                    'elements': get_cart_elements(recipient_id, moltin_client)
                }
            }
        }
    }
    response = requests.post(
        'https://graph.facebook.com/v2.6/me/messages',
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


def send_message(recipient_id, message_text, app_config):
    params = {'access_token': app_config['facebook_access_token']}
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
