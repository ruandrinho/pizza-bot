import requests
import logging
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

    def add_entry_to_flow(self, flow_slug, entry_data):
        self.check_token()
        entry_data['type'] = 'entry'
        moltin_flows_response = requests.post(
            f'https://api.moltin.com/v2/flows/{flow_slug}/entries',
            headers={'Authorization': f'{self.token}'},
            json={
                'data': entry_data
            }
        )
        moltin_flows_response.raise_for_status()
        return moltin_flows_response.json()['data']['id']

    def add_product_to_cart(self, product_id, product_quantity, telegram_user_id):
        self.check_token()
        print(telegram_user_id, self.token)
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

    def empty_cart(self, telegram_user_id):
        self.check_token()
        moltin_carts_response = requests.delete(
            f'https://api.moltin.com/v2/carts/{telegram_user_id}/items/',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_carts_response.raise_for_status()

    def get_all_products(self):
        self.check_token()
        moltin_products_response = requests.get(
            'https://api.moltin.com/v2/products',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_products_response.raise_for_status()
        return moltin_products_response.json()['data']

    def get_cart_data(self, telegram_user_id):
        self.check_token()
        moltin_carts_response = requests.get(
            f'https://api.moltin.com/v2/carts/{telegram_user_id}/items',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_carts_response.raise_for_status()
        cart_products = [{
            'id': product['product_id'],
            'inner_id': product['id'],
            'name': product['name'],
            'description': product['description'],
            'price': product['meta']['display_price']['with_tax']['unit']['formatted'],
            'quantity': product['quantity'],
            'total_cost': f'{product["value"]["amount"]} ₽'
        } for product in moltin_carts_response.json()['data']]
        total_cart_cost = moltin_carts_response.json()['meta']['display_price']['with_tax']['formatted']
        return (cart_products, total_cart_cost)

    def get_categories(self):
        self.check_token()
        moltin_categories_response = requests.get(
            'https://api.moltin.com/v2/categories',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_categories_response.raise_for_status()
        return moltin_categories_response.json()['data']

    def get_customer_location(self, telegram_user_id):
        self.check_token()
        moltin_flows_response = requests.get(
            'https://api.moltin.com/v2/flows/customer_address/entries',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_flows_response.raise_for_status()
        locations = moltin_flows_response.json()['data']
        for location in locations:
            if location['customer_telegram_id'] == telegram_user_id:
                return location

    def get_deliveryman_telegram_id(self, pizzeria_id):
        self.check_token()
        moltin_flows_response = requests.get(
            f'https://api.moltin.com/v2/flows/pizzeria/entries/{pizzeria_id}',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_flows_response.raise_for_status()
        return moltin_flows_response.json()['data']['deliveryman_telegram_id']

    def get_pizzerias(self):
        self.check_token()
        moltin_flows_response = requests.get(
            'https://api.moltin.com/v2/flows/pizzeria/entries',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_flows_response.raise_for_status()
        return moltin_flows_response.json()['data']

    def get_product(self, product_id, telegram_user_id=0):
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

        quantity_in_cart = self.get_product_quantity_in_cart(moltin_product['name'], telegram_user_id)\
            if telegram_user_id else 0

        return {
            'id': moltin_product['id'],
            'name': moltin_product['name'],
            'description': moltin_product['description'],
            'price': moltin_product['meta']['display_price']['with_tax']['formatted'],
            'stock': moltin_product['meta']['stock']['level'],
            'image_url': moltin_file['link']['href'],
            'quantity_in_cart': quantity_in_cart
        }

    def get_product_quantity_in_cart(self, product_name, telegram_user_id):
        self.check_token()
        moltin_carts_response = requests.get(
            f'https://api.moltin.com/v2/carts/{telegram_user_id}/items',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_carts_response.raise_for_status()
        cart_products = moltin_carts_response.json()['data']
        for product in cart_products:
            if product['name'] == product_name:
                return product['quantity']
        return 0

    def get_products_by_category(self, category_slug='basic'):
        self.check_token()
        moltin_categories_map = {c['slug']: c['id'] for c in self.get_categories()}
        moltin_products_response = requests.get(
            f'https://api.moltin.com/v2/products?filter=eq(category.id,{moltin_categories_map[category_slug]})',
            headers={'Authorization': f'Bearer {self.token}'}
        )
        moltin_products_response.raise_for_status()
        return moltin_products_response.json()['data']

    def remove_product_from_cart(self, product_id, telegram_user_id):
        self.check_token()
        cart_products, _ = self.get_cart_data(telegram_user_id)
        product_inner_id = False
        for product in cart_products:
            if product['id'] == product_id:
                product_inner_id = product['inner_id']
        if not product_inner_id:
            return
        # print(f'https://api.moltin.com/v2/carts/{telegram_user_id}/items/{product_id}', self.token)
        moltin_carts_response = requests.delete(
            f'https://api.moltin.com/v2/carts/{telegram_user_id}/items/{product_inner_id}',
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
