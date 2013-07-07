#!/usr/bin/env/ python

"""Tests."""

from getpass import getuser
from igloo import Client, ClientConfig, ClientError, parse_url
from os import environ
from nose import run
from nose.tools import ok_, eq_, raises


# URL parser

def test_parse_url():
  eq_(parse_url('user@host:path'), ('user', 'host', 'path'))
  eq_(parse_url('host:path'), (getuser(), 'host', 'path'))
  eq_(parse_url('host'), (getuser(), 'host', '.'))

@raises(ValueError)
def test_empty_parse_url():
  parse_url('')

# Config

def test_client_config():
  ClientConfig.path = '/Users/Matt/.config/igloo/.test_igloorc'
  config = ClientConfig()
  eq_(config.config, {})
  config.set_url('p', 'u')
  eq_(config.get_url('p'), 'u')
  config.remove_file()

# Client

URL = ''

def test_client():
  client = Client(URL)

def test_profile_client():
  client = Client.from_profile('default')

@raises(ClientError)
def test_missing_profile_client():
  client = Client.from_profile('some_missing_profile')

@raises(ClientError)
def test_connection_with_invalid_url():
  client = Client('Foo@bar')
  with client.get_sftp_client() as sftp:
    pass


class TestIgloo(object):

  def setup(self):
    self.client = Client(URL)

  def test_sftp_connection(self):
    with self.client.get_sftp_client() as sftp:
      pass

  def test_list(self):
    client = Client(URL)
    eq_(client.list(write=False), [])


if __name__ == '__main__':
  run()
