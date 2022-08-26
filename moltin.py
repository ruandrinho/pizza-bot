import requests
import logging
from textwrap import dedent
from time import time

logger = logging.getLogger(__name__)


class MoltinClient:
    token = ''
    token_expiration_timestamp = 0

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    def check_token(self):
        if self.token and time() < self.token_expiration_timestamp:
            return
        moltin_oauth_response = requests.post(
            'https://api.moltin.com/oauth/access_token',
            data={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials'
            }
        )
        moltin_oauth_response.raise_for_status()
        moltin_oauth_info = moltin_oauth_response.json()
        self.token = moltin_oauth_info['access_token']
        self.token_expiration_timestamp = moltin_oauth_info['expires']

    def get_all_products(self):
        self.check_token()
        moltin_products_response = requests.get(
            'https://api.moltin.com/v2/products',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_products_response.raise_for_status()
        return moltin_products_response.json()['data']

    def get_product(self, product_id):
        self.check_token()
        moltin_products_response = requests.get(
            f'https://api.moltin.com/v2/products/{product_id}',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_products_response.raise_for_status()
        moltin_product = moltin_products_response.json()['data']

        main_image_id = moltin_product['relationships']['main_image']['data']['id']
        moltin_files_response = requests.get(
            f'https://api.moltin.com/v2/files/{main_image_id}',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_files_response.raise_for_status()
        moltin_file = moltin_files_response.json()['data']

        return {
            'id': moltin_product['id'],
            'name': moltin_product['name'],
            'description': moltin_product['description'],
            'price': moltin_product['meta']['display_price']['with_tax']['formatted'],
            'stock': moltin_product['meta']['stock']['level'],
            'image_url': moltin_file['link']['href']
        }

    def get_cart_data(self, telegram_user_id):
        self.check_token()
        moltin_carts_response = requests.get(
            f'https://api.moltin.com/v2/carts/{telegram_user_id}/items',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_carts_response.raise_for_status()
        summary = ''
        cart_products = moltin_carts_response.json()['data']
        for product in cart_products:
            product = {
                'name': product['name'],
                'description': product['description'],
                'price': product['meta']['display_price']['with_tax']['unit']['formatted'],
                'quantity': product['quantity'],
                'total_cost': f'{product["value"]["amount"]} ₽'
            }
            summary += f'''\
                {product["name"]} ({product["description"]})
                {product["quantity"]} шт. на сумму {product["total_cost"]}
                \n'''
        total_cart_cost = moltin_carts_response.json()['meta']['display_price']['with_tax']['formatted']
        return (cart_products, total_cart_cost, dedent(summary))

    def add_product_to_cart(self, product_id, product_quantity, telegram_user_id):
        self.check_token()
        moltin_carts_response = requests.post(
            f'https://api.moltin.com/v2/carts/{telegram_user_id}/items',
            headers={'Authorization': f'Bearer {self.token}'},
            json={
                'data': {
                    'id': product_id,
                    'type': 'cart_item',
                    'quantity': product_quantity
                }
            }
        )
        moltin_carts_response.raise_for_status()

    def remove_product_from_cart(self, product_id, telegram_user_id):
        self.check_token()
        moltin_carts_response = requests.delete(
            f'https://api.moltin.com/v2/carts/{telegram_user_id}/items/{product_id}',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_carts_response.raise_for_status()

    def save_customer(self, email, telegram_user):
        self.check_token()
        moltin_customers_response = requests.post(
            'https://api.moltin.com/v2/customers',
            headers={'Authorization': f'Bearer {self.token}'},
            json={
                'data': {
                    'type': 'customer',
                    'name': f'Telegram user {telegram_user.username} (id {telegram_user.id})',
                    'email': email
                }
            }
        )
        moltin_customers_response.raise_for_status()
        logger.info(moltin_customers_response.json())
