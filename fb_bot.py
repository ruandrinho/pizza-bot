import requests

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
                    # message_text = messaging_event['message']['text']
                    send_menu(sender_id)
    return 'ok', 200


def send_menu(recipient_id):
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
    all_products = g.moltin_client.get_all_products()[:5]
    for product in all_products:
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
                    'elements': elements
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
