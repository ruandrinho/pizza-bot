import json

import redis
from environs import Env

from moltin import MoltinClient


def get_menu_elements(moltin_client, category_slug='basic'):
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
    for product in moltin_client.get_products_by_category(category_slug):
        product = moltin_client.get_product(product['id'])
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
    for category in moltin_client.get_categories():
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


def main():
    env = Env()
    env.read_env()

    redis_client = redis.Redis(
        host=env('REDIS_HOST'),
        port=env('REDIS_PORT'),
        username=env('REDIS_USERNAME'),
        password=env('REDIS_PASSWORD'),
        decode_responses=True
    )

    moltin_client = MoltinClient(env('MOLTIN_CLIENT_ID'), env('MOLTIN_CLIENT_SECRET'))
    for category in moltin_client.get_categories():
        elements = get_menu_elements(moltin_client, category['slug'])
        redis_client.set(f'elements_{category["slug"]}', json.dumps(elements))


if __name__ == '__main__':
    main()
