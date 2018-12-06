#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script pumps sensor readings from 30MHz Zensie to OSRAM Lightelligence
"""

import json
import logging
import os
import threading
import time
import urllib.request

import paho.mqtt.client
import paho.mqtt.subscribe


def init_logging():
    """
    Initializes logging for the application
    """
    pattern = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(format=pattern, level=logging.INFO)
    return logging.getLogger('pump')


def device_certificate():
    """
    Creates a certificate for a Lightelligence device
    """
    os.system('/usr/bin/openssl ecparam -out device_key.pem -name prime256v1 -genkey')  # noqa: E501  # nosec  # pylint: disable=C0301
    os.system('/usr/bin/openssl req -new -key device_key.pem -x509 -days 365 -out device_cert.pem -subj "/O=OSRAM/CN=30MHz"')  # noqa: E501  # nosec  # pylint: disable=C0301
    with open('device_cert.pem', 'rb') as handle:
        certificate = handle.read().decode('utf-8')
    with open('device_key.pem', 'rb') as handle:
        key = handle.read().decode('utf-8')
    return {'certificate': certificate, 'key': key}


def api_call(url, authorization, data=None):
    """
    Calls an API endpoint and assumes JSON as input and output
    """
    if data is not None:
        data = json.dumps(data).encode('utf-8')
    request = urllib.request.Request(url, data)
    request.add_header('Cache-Control', 'no-cache')
    request.add_header('Content-Type', 'application/json')
    request.add_header('Accept', 'application/json')
    request.add_header('Authorization', authorization)
    response = urllib.request.urlopen(request)  # nosec
    code = response.getcode()
    if code not in range(200, 202):
        error = 'Got %d from call %s with data: %s' % (code, url, data)
        raise Exception(error)
    return json.loads(response.read().decode('utf-8'))


def zensie_check(skip_organization=False):
    """
    Reads 30MHz Zensie API key and organization identifier from environment
    """
    zensie_api_key = os.getenv('ZENSIE_API_KEY')
    zensie_organization = os.getenv('ZENSIE_ORGANIZATION')
    if zensie_api_key is None:
        raise Exception('Missing ZENSIE_API_KEY variable')
    if zensie_organization is None and not skip_organization:
        raise Exception('Missing ZENSIE_ORGANIZATION variable')
    return (zensie_api_key, zensie_organization)


def zensie_list_sensors(authorization, organization):
    """
    Lists all sensors for an organization from 30MHz Zensie
    """
    url = 'https://api.30mhz.com/api/check/organization/%s' % organization
    result = api_call(url, authorization)
    banned = ['gateway_info', 'zensie_router']
    return [sensor for sensor in result if sensor['sensorType'] not in banned]


def zensie_get_sensor(authorization, identifier):
    """
    Obtains sensor information from 30MHz Zensie
    """
    url = 'https://api.30mhz.com/api/stats/check/%s' % identifier
    return api_call(url, authorization)


def zensie_list_sensor_types(authorization):
    """
    Lists all sensor types from 30MHz Zensie
    """
    url = 'https://api.30mhz.com/api/sensor-type'
    result = api_call(url, authorization)
    return {entry['typeId']: entry for entry in result}


def olt_check():
    """
    Reads OSRAM Ligthelligence token from environment
    """
    olt_token = os.getenv('LIGHTELLIGENCE_TOKEN')
    if olt_token is None:
        raise Exception('Missing LIGHTELLIGENCE_TOKEN variable')
    return olt_token


def olt_create_device_type(authorization):
    """
    Creates a device type on OSRAM Lightelligence
    """
    device_type_definition = {
        'name': '30MHz Sensor',
        'manufacturer': '30MHz',
        'model': 'V0',
        'description': '30MHz Sensor - V0',
        'schema': {'attributes': {'value': {'type': 'number'}}},
        'reportingRules': [
            {'path': '$.attributes.value', 'reportTo': ['timeseries']}]}
    url = 'https://api.lightelligence.io/v1/device-types'
    return api_call(url, authorization, device_type_definition)['data']['id']


def olt_create_device(authorization, type_id, name, certificate):
    """
    Creates a device on OSRAM Lightelligence
    """
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    data = {
        'info': {
            'name': name,
            'deviceTypeId': type_id,
            'description': name,
            'installationTimestamp': now,
            'tags': ['sensor', '30mhz']}}
    url = 'https://api.lightelligence.io/v1/devices'
    result = api_call(url, authorization, data)
    device_id = result['data']['id']
    data = {'cert': certificate, 'status': 'valid'}
    url_template = 'https://api.lightelligence.io/v1/devices/%s/certificates'
    url = url_template % device_id
    api_call(url, authorization, data)
    return device_id


def load_pump_mappings():
    """
    Loads from file the mapping of 30MHz Zensie sensors
    to OSRAM Lightelligence devices
    """
    with open('/mapping.json', 'rb') as handle:
        mappings = handle.read()
        if not mappings:
            return None
        return json.loads(mappings.decode('utf-8'))


def store_pump_mappings(mappings):
    """
    Stores into file the mapping of 30MHz Zensie sensors
    to OSRAM Lightelligence devices
    """
    with open('/mapping.json', 'wb') as handle:
        handle.write(json.dumps(mappings).encode('utf-8'))


def prepare(logger):
    """
    Lists all sensors for an organization on 30MHz Zensie
    and creates a mapping of each modality
    into a separate OSRAM Lightelligence device
    """
    olt_token = olt_check()
    zensie_authorization, zensie_organization = zensie_check()
    olt_authorization = 'Bearer %s' % olt_token
    device_type_id = olt_create_device_type(olt_authorization)
    sensors = zensie_list_sensors(zensie_authorization, zensie_organization)
    sensor_types = zensie_list_sensor_types(zensie_authorization)
    mappings = {}
    for sensor in sensors:
        zensie_sensor = sensor['checkId']
        mappings[zensie_sensor] = {}
        modalities = sensor_types[sensor['sensorType']]['jsonKeys']
        modalities = [None] if modalities is None else modalities
        for modality in modalities:
            name = sensor['name']
            name = '30MHz - %s - %s - %s' % (name, zensie_sensor, modality)
            mapping = device_certificate()
            mapping['id'] = olt_create_device(
                olt_authorization,
                device_type_id, name, mapping['certificate'])
            mappings[zensie_sensor][modality] = mapping
            logger.info('Created device: %s' % name)
    store_pump_mappings(mappings)


# pylint: disable=W0613
def on_log(mqtt_client, context, level, string):
    """
    Handles the logging for the MQTT library
    """
    context['logger'].log(10 * (level // 10), string)


# pylint: disable=W0613
def on_connect(mqtt_client, context, flags, result_code):
    """
    Handles the connecting to MQTT queue
    """
    if result_code != 0:
        context['logger'].error(
            'Connection failed, with result code: %d', result_code)


class Handler(threading.Thread):
    """
    Handles the communication over MQTT queue
    """

    def __init__(self, mapping):
        super().__init__()
        self.daemon = True
        self.identifier = mapping['id']
        self.logger = logging.getLogger(self.identifier)
        self.certificate = '%s.certificate' % self.identifier
        self.key = '%s.key' % self.identifier
        with open(self.certificate, 'wb') as handle:
            handle.write(mapping['certificate'].encode('utf-8'))
        with open(self.key, 'wb') as handle:
            handle.write(mapping['key'].encode('utf-8'))
        base = os.path.dirname(__file__)
        self.ca_certs = os.path.join(base, 'olt_ca.pem')
        self.mqtt_client = None
        self.start()

    def run(self):
        while True:
            context = {'logger': self.logger}
            self.mqtt_client = paho.mqtt.client.Client(
                str(time.time()), userdata=context)
            self.mqtt_client.tls_set(
                ca_certs=self.ca_certs,
                certfile=self.certificate, keyfile=self.key)
            self.mqtt_client.connect('mqtt.lightelligence.io', port=8883)
            self.mqtt_client.on_log = on_log
            self.mqtt_client.on_connect = on_connect
            self.mqtt_client.loop_forever()

    def report(self, value):
        """
        Reports the value for this queue / device
        """
        payload = {'type': 'attributes', 'value': {'value': value}}
        payload = json.dumps(payload)
        self.logger.debug(payload)
        self.mqtt_client.publish(
            'data-ingest', payload=payload, qos=1, retain=True)


def pump(logger, mappings):
    """
    Checks sensor readings on 30MHz Zensie every minute
    and pumps them onto OSRAM Lightelligence
    """
    zensie_authorization = zensie_check(True)[0]
    for zensie_sensor in mappings.keys():
        for modality in mappings[zensie_sensor].keys():
            mapping = mappings[zensie_sensor][modality]
            mapping['handler'] = Handler(mapping)
    timestamps = {}
    while True:
        for zensie_sensor in mappings.keys():
            try:
                reply = zensie_get_sensor(zensie_authorization, zensie_sensor)
            except urllib.error.HTTPError:
                continue
            if timestamps.get(zensie_sensor, '') != reply['timestamp']:
                stats = reply['lastRecordedStats']
                stats = stats if isinstance(stats, dict) else {None: stats}
                reported = set(stats.keys())
                expected = set(mappings[zensie_sensor].keys())
                for modality in reported.intersection(expected):
                    mapping = mappings[zensie_sensor][modality]
                    olt_sensor = mapping['id']
                    value = float(stats[modality])
                    mapping['handler'].report(value)
                    context = (zensie_sensor, modality, value, olt_sensor)
                    logger.debug('%s %s: %f -> %s' % context)
                timestamps[zensie_sensor] = reply['timestamp']
        time.sleep(60)


def main():
    """
    Main function of the script
    """
    logger = init_logging()
    mappings = load_pump_mappings()
    if mappings is None:
        prepare(logger)
    else:
        pump(logger, mappings)


if __name__ == '__main__':
    main()
