"""
Dispatcher API daemon
"""
import imp
import json
import logging
import os
from os import listdir
from os.path import isdir, exists

import pika
from bson import json_util
from kamerie.utilities.utilities import setup_logging
from kamerie.utilities.consts import DISPATCHER_NAME, EXCHANGE_NAME, TYPE_MOVIE, TYPE_SERIES
from media_scanner import MediaScanner

PLUGIN_DIRECTORY = os.path.join(os.path.dirname(__file__), '../../../kamerie_plugins')


class Dispatcher(object):

    def __init__(self):
        # Prepare instance
        self.name = DISPATCHER_NAME

        # Prepare logger
        setup_logging(os.getcwd())
        self._logger = logging.getLogger(__name__)
        self._logger.info("Initialized dispatcher")

        self.media_scanner = MediaScanner(self._logger)
        self.plugins = self.register_plugins()

        # rabbitmq
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        self.channel = self.connection.channel()
        self._logger.info('Connected to RabbitMQ successfully')

        self.channel.exchange_declare(exchange=EXCHANGE_NAME, type='direct')
        self.on_message({'media_path': '/home/dor/Videos/movies', 'media_type': TYPE_MOVIE})
        self.on_message({'media_path': '/home/dor/Videos/tv', 'media_type': TYPE_SERIES})

    def register_plugins(self):
        plugin_list = []
        plugin_path = lambda plugin: os.path.join(PLUGIN_DIRECTORY, plugin)
        plugins = filter(lambda x: isdir(plugin_path(x)) and x[0] is not '.', listdir(PLUGIN_DIRECTORY))

        for plugin in plugins:
            config_path = os.path.join(plugin_path(plugin), 'plugin.py')
            config_import = imp.load_source('kamerie_plugin_%s' % plugin, config_path)

            if exists(config_path):
                plugin_conf = {
                    'name': plugin,
                    'path': plugin_path(plugin),
                    'config_path': config_path,
                    'plugin_cls': config_import.Plugin(plugin)
                }
                plugin_list.append(plugin_conf)

        return plugin_list

    def start(self):
        self._logger.info("Starting" % self.name)

    def on_message(self, message):
        if isinstance(message, dict) and all(k in ['media_type', 'media_path'] for k in message.keys()):
            if not message.get('scanned', False):
                for scanner_message in self.media_scanner.scan_directory(message['media_path'], message['media_type']):
                    self.channel.basic_publish(exchange=EXCHANGE_NAME, routing_key='',
                                               body=json_util.dumps(scanner_message))
            else:
                self._logger.info('Publishing message to all plugins: %s' % str(message))
                self.channel.basic_publish(exchange=EXCHANGE_NAME, routing_key='', body=json.dumps(message))
        else:
            self._logger.error("Invalid message: %s" % str(message))

    def __exit__(self):
        self.close()

    def close(self):
        self.connection.close()


if __name__ == '__main__':
    Dispatcher()