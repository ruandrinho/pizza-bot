from textwrap import dedent


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


def get_product_summary(product):
    summary = f'''\
            *{product["name"]} / {product["price"]}*

            _{product["description"]}_
            '''
    if product['quantity_in_cart']:
        summary += f'''\

            В корзине: *{product["quantity_in_cart"]} шт.*
            '''
    return dedent(summary)
