#!/usr/bin/env python
"""Simple tool for generating a client library.

Relevant links:
  https://developers.google.com/discovery/v1/reference/apis#resource
"""

import json
import logging
import urlparse

from apitools.base.py import base_cli
from apitools.gen import command_registry
from apitools.gen import message_registry
from apitools.gen import service_registry
from apitools.gen import util


def _StandardQueryParametersSchema(discovery_doc):
  standard_query_schema = {
      'id': 'StandardQueryParameters',
      'type': 'object',
      'description': 'Query parameters accepted by all methods.',
      'properties': discovery_doc.get('parameters', {}),
      }
  # We add an entry for the trace, since Discovery doesn't.
  standard_query_schema['properties']['trace'] = {
      'type': 'string',
      'description': base_cli.TRACE_HELP,
      'location': 'query',
      }
  return standard_query_schema


def _ComputePaths(package, version, discovery_doc):
  full_path = urlparse.urljoin(
      discovery_doc['rootUrl'], discovery_doc['servicePath'])
  api_path_component = '/'.join((package, version, ''))
  if api_path_component not in full_path:
    logging.warning('Could not find path "%s" in API path "%s"',
                    api_path_component, full_path)
    return full_path, ''
  prefix, _, suffix = full_path.rpartition(api_path_component)
  return prefix + api_path_component, suffix


class DescriptorGenerator(object):
  """Code generator for a given discovery document."""

  def __init__(self, discovery_doc, client_info, names, root_package, outdir,
               use_proto2=False):
    self.__discovery_doc = discovery_doc
    self.__client_info = client_info
    self.__outdir = outdir
    self.__use_proto2 = use_proto2
    self.__description = self.__discovery_doc.get('description', '')
    self.__package = self.__client_info.package
    self.__version = self.__client_info.version
    self.__root_package = root_package
    # TODO(craigcitro): Centralize this information ... somewhere.
    self.__base_files_package = 'apitools.base.py'
    self.__base_files_target = (
        '//cloud/bigscience/apitools/base/py:apitools_base')
    self.__names = names
    self.__base_url, self.__base_path = _ComputePaths(
        self.__package, self.__client_info.url_version, self.__discovery_doc)

    # Order is important here: we need the schemas before we can
    # define the services.
    self.__message_registry = message_registry.MessageRegistry(
        self.__client_info, self.__names, self.__description,
        self.__root_package, self.__base_files_package)
    schemas = self.__discovery_doc.get('schemas', {})
    for schema_name, schema in schemas.iteritems():
      self.__message_registry.AddDescriptorFromSchema(schema_name, schema)

    # We need to add one more message type for the global parameters.
    standard_query_schema = _StandardQueryParametersSchema(
        self.__discovery_doc)
    self.__message_registry.AddDescriptorFromSchema(
        standard_query_schema['id'], standard_query_schema)

    self.__command_registry = command_registry.CommandRegistry(
        self.__package, self.__version, self.__client_info,
        self.__message_registry, self.__root_package, self.__base_files_package,
        self.__base_url, self.__names)
    self.__command_registry.AddGlobalParameters(
        self.__message_registry.LookupDescriptorOrDie(
            'StandardQueryParameters'))

    self.__services_registry = service_registry.ServiceRegistry(
        self.__client_info,
        self.__message_registry,
        self.__command_registry,
        self.__base_url,
        self.__base_path,
        self.__names,
        self.__root_package,
        self.__base_files_package)
    services = self.__discovery_doc.get('resources', {})
    for service_name, methods in sorted(services.iteritems()):
      self.__services_registry.AddServiceFromResource(service_name, methods)
    # We might also have top-level methods.
    api_methods = self.__discovery_doc.get('methods', [])
    if api_methods:
      self.__services_registry.AddServiceFromResource(
          'api', {'methods': api_methods})
    self.__client_info = self.__client_info._replace(scopes=self.__services_registry.scopes)  # pylint:disable=protected-access,g-line-too-long

  @property
  def client_info(self):
    return self.__client_info

  @property
  def discovery_doc(self):
    return self.__discovery_doc

  @property
  def names(self):
    return self.__names

  @property
  def outdir(self):
    return self.__outdir

  @property
  def use_proto2(self):
    return self.__use_proto2

  def WriteInit(self, out):
    """Write a simple __init__.py for the generated client."""
    printer = util.SimplePrettyPrinter(out)
    printer('"""Common imports for generated %s client library."""',
            self.__client_info.package)
    printer()
    printer('from %s import credentials_lib', self.__base_files_package)
    printer('from %s.base_api import *', self.__base_files_package)
    printer('from %s.exceptions import *', self.__base_files_package)
    printer('from %s.transfer import *', self.__base_files_package)
    printer('from %s.%s import *',
            self.__root_package, self.__client_info.client_rule_name)
    printer('from %s.%s import *',
            self.__root_package, self.__client_info.messages_rule_name)

  def WriteMessagesFile(self, out):
    self.__message_registry.WriteFile(out)

  def WriteMessagesProtoFile(self, out):
    self.__message_registry.WriteProtoFile(out)

  def WriteServicesProtoFile(self, out):
    self.__services_registry.WriteProtoFile(out)

  def WriteClientLibrary(self, out):
    self.__services_registry.WriteFile(out)

  def WriteCli(self, out):
    self.__command_registry.WriteFile(out)
