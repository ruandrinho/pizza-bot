import requests
from geopy import distance


def define_delivery_distance(pizzerias, client_longitude, client_latitude):
    for pizzeria in pizzerias:
        pizzeria['delivery_distance'] = distance.distance(
            (pizzeria['latitude'], pizzeria['longitude']),
            (client_latitude, client_longitude)
        ).km


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
