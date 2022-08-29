import logging
import os
import requests
from geopy import distance
from moltin import MoltinClient
from dotenv import load_dotenv
from textwrap import dedent
from contextlib import suppress
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.constants import PARSEMODE_MARKDOWN_V2
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    PicklePersistence,
    PreCheckoutQueryHandler,
    Updater,
    Filters,
)

logger = logging.getLogger(__name__)

(
    START,
    HANDLE_MENU,
    HANDLE_PRODUCT,
    HANDLE_CART,
    AWAIT_LOCATION,
    HANDLE_DELIVERY,
    HANDLE_PAYMENT,
    HANDLE_FINISH
) = range(8)


def define_delivery_distance(pizzerias, client_longitude, client_latitude):
    for pizzeria in pizzerias:
        pizzeria['delivery_distance'] = distance.distance(
            (pizzeria['latitude'], pizzeria['longitude']),
            (client_latitude, client_longitude)
        ).km


def escape(s):
    return s.replace('-', '\-').replace('.', '\.').replace('(', '\(').replace(')', '\)')


def get_cart_summary(products, cost):
    if not products:
        return 'Здесь пока пусто.'
    summary = ''
    for product in products:
        summary += f'''\
            *{product["name"]}* (_{product["description"]}_)
            {product["quantity"]} шт. на сумму {product["total_cost"]}
            \n'''
    summary = dedent(summary) + f'*К оплате: {cost}*'
    return summary


def fetch_coordinates(apikey, address):
    base_url = 'https://geocode-maps.yandex.ru/1.x'
    response = requests.get(base_url, params={
        'geocode': address,
        'apikey': apikey,
        'format': 'json',
    })
    response.raise_for_status()
    found_places = response.json()['response']['GeoObjectCollection']['featureMember']

    if not found_places:
        return None

    most_relevant = found_places[0]
    lon, lat = most_relevant['GeoObject']['Point']['pos'].split(' ')
    return float(lon), float(lat)


def start(update, context):
    moltin_client = context.bot_data['moltin_client']
    products_per_page = context.bot_data['products_per_page']
    all_products = moltin_client.get_all_products()
    keyboard = []
    for product in all_products[0:products_per_page]:
        keyboard.append([InlineKeyboardButton(product['name'], callback_data=product['id'])])
    keyboard.append([InlineKeyboardButton('Следующие ➡️', callback_data='page1')])
    update.message.reply_text(
        'Какую пиццу выберешь сегодня?',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return HANDLE_MENU


def show_menu(update, context):
    moltin_client = context.bot_data['moltin_client']
    products_per_page = context.bot_data['products_per_page']
    query = update.callback_query
    query.answer()
    page = 0
    if 'page' in query.data:
        page = int(query.data.replace('page', ''))
    all_products = moltin_client.get_all_products()
    keyboard = []
    for product in all_products[page * products_per_page:(page + 1) * products_per_page]:
        keyboard.append([InlineKeyboardButton(product['name'], callback_data=product['id'])])
    if page == 0:
        keyboard.append([InlineKeyboardButton('Следующие ➡️', callback_data=f'page{page + 1}')])
    elif len(all_products) <= (page + 1) * products_per_page:
        keyboard.append([InlineKeyboardButton('⬅️ Предыдущие', callback_data=f'page{page - 1}')])
    else:
        keyboard.append([
            InlineKeyboardButton('⬅️ Предыдущие', callback_data=f'page{page - 1}'),
            InlineKeyboardButton('Следующие ➡️', callback_data=f'page{page + 1}')
        ])
    cart_products, _ = moltin_client.get_cart_data(query.from_user.id)
    if cart_products:
        keyboard.append([InlineKeyboardButton('🍕 Корзина', callback_data='cart')])
    query.message.reply_text(
        'Какую пиццу выберешь сегодня?',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    query.message.delete()
    return HANDLE_MENU


def show_product(update, context):
    moltin_client = context.bot_data['moltin_client']
    query = update.callback_query
    if '+' in query.data:
        query.data = query.data.replace('+', '')
        with suppress(requests.exceptions.HTTPError):
            moltin_client.add_product_to_cart(query.data, 1, query.from_user.id)
        query.answer('Пицца добавлена в корзину')
    else:
        query.answer()
        product = moltin_client.get_product(query.data)
        keyboard = []
        keyboard.append([
            InlineKeyboardButton('💰 Заказать', callback_data=f'+{product["id"]}'),
            InlineKeyboardButton('🍕 Корзина', callback_data='cart'),
            InlineKeyboardButton('🔠 В меню', callback_data='back')
        ])
        message = f'''\
                *{product["name"]} / {product["price"]}*

                _{product["description"]}_
                '''
        quantity_in_cart = moltin_client.get_product_quantity_in_cart(product['name'], query.from_user.id)
        if quantity_in_cart:
            message += f'''\

                В корзине: *{quantity_in_cart} шт.*
                '''
        query.message.reply_photo(
            photo=product['image_url'],
            caption=escape(dedent(message)),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=PARSEMODE_MARKDOWN_V2
        )
        query.message.delete()
    return HANDLE_PRODUCT


def show_cart(update, context):
    moltin_client = context.bot_data['moltin_client']
    query = update.callback_query
    query.answer()
    if query.data != 'cart':
        moltin_client.remove_product_from_cart(query.data, query.from_user.id)
    cart_products, cart_cost = moltin_client.get_cart_data(query.from_user.id)
    keyboard = []
    if cart_products:
        keyboard.append([InlineKeyboardButton('🍕 Оформить заказ', callback_data='pay')])
    for product in cart_products:
        keyboard.append(
            [InlineKeyboardButton(f'Убрать из корзины {product["name"]}', callback_data=product['id'])]
        )
    keyboard.append([InlineKeyboardButton('🔠 В меню', callback_data='back')])
    query.message.reply_text(
        escape(get_cart_summary(cart_products, cart_cost)),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=PARSEMODE_MARKDOWN_V2
    )
    query.message.delete()
    return HANDLE_CART


def ask_for_address(update, context):
    query = update.callback_query
    query.answer()
    query.message.reply_text(
        'Пожалуйста, введите адрес для оформления заказа или пришлите геолокацию'
    )
    query.message.delete()
    return AWAIT_LOCATION


def handle_location(update, context, coordinates=None):
    moltin_client = context.bot_data['moltin_client']
    if coordinates:
        longitude, latitude = coordinates
    else:
        longitude, latitude = update.message.location.longitude, update.message.location.latitude
    moltin_client.add_entry_to_flow('customer_address', {
        'customer_telegram_id': update.message.from_user.id,
        'longitude': longitude,
        'latitude': latitude
    })
    pizzerias = moltin_client.get_pizzerias()
    define_delivery_distance(pizzerias, longitude, latitude)
    nearest_pizzeria = min(pizzerias, key=lambda p: p['delivery_distance'])
    context.user_data['nearest_pizzeria'] = nearest_pizzeria
    keyboard = []
    if nearest_pizzeria['delivery_distance'] <= 0.5:
        keyboard.append([
            InlineKeyboardButton('🚶 Заберу сам', callback_data='pickup'),
            InlineKeyboardButton('🚴 Бесплатная доставка', callback_data='free_delivery')
        ])
        keyboard.append([InlineKeyboardButton('🏠 Изменить адрес', callback_data='change_address')])
        update.message.reply_text(
            f'Ближайшая пиццерия по адресу {nearest_pizzeria["address"]} '
            f'всего в {nearest_pizzeria["delivery_distance"] * 1000:.0f} м от вас. '
            f'Можем доставить бесплатно!',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif nearest_pizzeria['delivery_distance'] <= 5:
        keyboard.append([
            InlineKeyboardButton('🚗 Заберу сам', callback_data='pickup'),
            InlineKeyboardButton('🚴 Доставка за 100 ₽', callback_data='paid_delivery_1')
        ])
        keyboard.append([InlineKeyboardButton('🏠 Изменить адрес', callback_data='change_address')])
        update.message.reply_text(
            f'Ближайшая пиццерия по адресу {nearest_pizzeria["address"]} '
            f'находится в {nearest_pizzeria["delivery_distance"]:.0f} км от вас. '
            f'Выберите доставку или самовывоз.',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif nearest_pizzeria['delivery_distance'] <= 20:
        keyboard.append([
            InlineKeyboardButton('🚗 Заберу сам', callback_data='pickup'),
            InlineKeyboardButton('🚚 Доставка за 300 ₽', callback_data='paid_delivery_2')
        ])
        keyboard.append([InlineKeyboardButton('🏠 Изменить адрес', callback_data='change_address')])
        update.message.reply_text(
            f'Ближайшая пиццерия по адресу {nearest_pizzeria["address"]} '
            f'находится в {nearest_pizzeria["delivery_distance"]:.0f} км от вас. '
            f'Выберите доставку или самовывоз.',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        keyboard.append([
            InlineKeyboardButton('🚗 Заберу сам', callback_data='pickup'),
            InlineKeyboardButton('🏠 Изменить адрес', callback_data='change_address')
        ])
        update.message.reply_text(
            f'Ближайшая пиццерия находится в {nearest_pizzeria["delivery_distance"]:.0f} км от вас! '
            f'Заберёте пиццу сами?',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    return HANDLE_DELIVERY


def handle_address(update, context):
    yandex_geocoder_api_key = context.bot_data['yandex_geocoder_api_key']
    address = update.message.text
    try:
        coordinates = fetch_coordinates(yandex_geocoder_api_key, address)
    except requests.exceptions.RequestException:
        coordinates = None
    if not coordinates:
        update.message.reply_text(
            'Не удалось распознать адрес, попробуйте другой.'
        )
        return AWAIT_LOCATION
    return handle_location(update, context, coordinates)


def handle_delivery(update, context):
    query = update.callback_query
    query.answer()
    context.user_data['delivery_type'] = 'pickup' if query.data == 'pickup' else query.data
    keyboard = []
    keyboard.append([InlineKeyboardButton('💳 Оплатить', callback_data='pay')])
    query.message.reply_text(
        'Приготовьте данные вашей карты',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    query.message.delete()
    return HANDLE_PAYMENT


def handle_payment(update, context):
    moltin_client = context.bot_data['moltin_client']
    query = update.callback_query
    query.answer()
    cart_products, _ = moltin_client.get_cart_data(query.from_user.id)
    prices = []
    for product in cart_products:
        if product['quantity'] > 1:
            product['name'] += f' ({product["quantity"]} шт.)'
        product['total_cost'] = int(product['total_cost'].replace(' ₽', ''))
        prices.append(LabeledPrice(product['name'], product['total_cost'] * 100))
    if context.user_data['delivery_type'] != 'pickup':
        if context.user_data['delivery_type'] == 'free_delivery':
            delivery_cost = 0
        elif context.user_data['delivery_type'] == 'paid_delivery_1':
            delivery_cost = 100
        else:
            delivery_cost = 300
        prices.append(LabeledPrice('Доставка', delivery_cost * 100))
    context.bot.send_invoice(
        query.from_user.id,
        'Оплата пиццы',
        ' ',
        'pizzabot_payment',
        context.bot_data['payment_provider_token'],
        'RUB',
        prices
    )
    return HANDLE_PAYMENT


def handle_precheckout(update, context):
    query = update.pre_checkout_query
    if query.invoice_payload != 'pizzabot_payment':
        query.answer(ok=False, error_message='В процессе оплаты произошла ошибка')
    else:
        query.answer(ok=True)
    return HANDLE_PAYMENT


def handle_successful_payment(update, context):
    moltin_client = context.bot_data['moltin_client']
    nearest_pizzeria = context.user_data['nearest_pizzeria']
    if context.user_data['delivery_type'] == 'pickup':
        message = f'Спасибо за оплату! Ждём вас в пиццерии по адресу {nearest_pizzeria["address"]}'
    else:
        message = 'Спасибо за оплату! Ждите нашего курьера.'
    keyboard = []
    keyboard.append([InlineKeyboardButton('🆕 Новый заказ', callback_data='new_order')])
    update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    deliveryman_telegram_id = moltin_client.get_deliveryman_telegram_id(nearest_pizzeria['id'])
    user_id = update.message.from_user.id
    cart_products, cart_cost = moltin_client.get_cart_data(user_id)
    customer_location = moltin_client.get_customer_location(user_id)
    context.bot.send_message(
        deliveryman_telegram_id,
        escape(get_cart_summary(cart_products, cart_cost)),
        parse_mode=PARSEMODE_MARKDOWN_V2
    )
    context.bot.send_location(
        deliveryman_telegram_id,
        longitude=customer_location['longitude'],
        latitude=customer_location['latitude']
    )
    moltin_client.empty_cart(user_id)
    context.job_queue.run_once(notify_after_delivery_expiration, 3600, context=user_id)
    return HANDLE_FINISH


def notify_after_delivery_expiration(context):
    message = '''\
        Приятного аппетита! *место для рекламы*

        *сообщение что делать, если пицца не пришла*
        '''
    context.bot.send_message(
        context.job.context,
        dedent(message)
    )


def main():
    load_dotenv()

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    updater = Updater(
        os.getenv('TELEGRAM_TOKEN'),
        persistence=PicklePersistence(filename='conversationbot')
    )
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            HANDLE_MENU: [
                CallbackQueryHandler(show_cart, pattern='^cart$'),
                CallbackQueryHandler(show_menu, pattern='^page'),
                CallbackQueryHandler(show_product)
            ],
            HANDLE_CART: [
                CallbackQueryHandler(ask_for_address, pattern='^pay$'),
                CallbackQueryHandler(show_menu, pattern='^back$'),
                CallbackQueryHandler(show_cart)
            ],
            HANDLE_PRODUCT: [
                CallbackQueryHandler(show_cart, pattern='^cart$'),
                CallbackQueryHandler(show_menu, pattern='^back$'),
                CallbackQueryHandler(show_product)
            ],
            AWAIT_LOCATION: [
                MessageHandler(Filters.location, handle_location),
                MessageHandler(Filters.text & ~Filters.command, handle_address)
            ],
            HANDLE_DELIVERY: [
                CallbackQueryHandler(ask_for_address, pattern='^change_address$'),
                CallbackQueryHandler(handle_delivery)
            ],
            HANDLE_PAYMENT: [
                CallbackQueryHandler(handle_payment, pattern='^pay$'),
                MessageHandler(Filters.successful_payment, handle_successful_payment)
            ],
            HANDLE_FINISH: [
                CallbackQueryHandler(start, pattern='^new_order$')
            ],
        },
        fallbacks=[],
        name='pizzabot_conversation',
        persistent=True
    )

    dispatcher.bot_data['moltin_client'] = MoltinClient(
        os.getenv('MOLTIN_CLIENT_ID'),
        os.getenv('MOLTIN_CLIENT_SECRET')
    )
    dispatcher.bot_data['payment_provider_token'] = os.getenv('TELEGRAM_PAYMENT_PROVIDER_TOKEN')
    dispatcher.bot_data['yandex_geocoder_api_key'] = os.getenv('YANDEX_GEOCODER_API_KEY')
    dispatcher.bot_data['products_per_page'] = 5
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(PreCheckoutQueryHandler(handle_precheckout))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
