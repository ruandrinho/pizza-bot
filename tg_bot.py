import logging
import os
from dotenv import load_dotenv
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
from moltin import MoltinClient
from handlers import (
    HANDLE_MENU,
    HANDLE_PRODUCT,
    HANDLE_CART,
    AWAIT_LOCATION,
    HANDLE_DELIVERY,
    HANDLE_PAYMENT,
    HANDLE_FINISH,
    start,
    show_cart,
    show_menu,
    show_product,
    ask_for_address,
    handle_address,
    handle_delivery,
    handle_location,
    handle_payment,
    handle_precheckout,
    handle_successful_payment
)

logger = logging.getLogger(__name__)


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
                CallbackQueryHandler(ask_for_address, pattern='^address$'),
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
                CallbackQueryHandler(ask_for_address, pattern='^address$'),
                CallbackQueryHandler(handle_delivery)
            ],
            HANDLE_PAYMENT: [
                CallbackQueryHandler(handle_payment, pattern='^pay$'),
                MessageHandler(Filters.successful_payment, handle_successful_payment)
            ],
            HANDLE_FINISH: [
                CallbackQueryHandler(start, pattern='^again$')
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
