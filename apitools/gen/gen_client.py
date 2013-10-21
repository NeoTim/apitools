#!/usr/bin/env python
"""Command-line interface to gen_client."""

import contextlib
import json
import logging
import os
import pkgutil
import sys

from google.apputils import appcommands
import gflags as flags

from apitools.base.py import exceptions
from apitools.gen import gen_client_lib
from apitools.gen import util

flags.DEFINE_string(
    'infile', '',
    'Filename for the discovery document. Mutually exclusive with '
    '--discovery_url.')
flags.DEFINE_string(
    'discovery_url', '',
    'URL of the discovery document to use. Mutually exclusive with --infile.')

flags.DEFINE_string(
    'outdir', '',
    'Directory name for output files. (Defaults to the API name.)')
flags.DEFINE_boolean(
    'overwrite', False,
    'Only overwrite the output directory if this flag is specified.')
flags.DEFINE_string(
    'root_package_dir', '',
    'Ultimate destination for generated code (used for generating '
    'correct import lines). Defaults to the value of FLAGS.outdir.'
    )

flags.DEFINE_multistring(
    'strip_prefix', [],
    'Prefix to strip from type names in the discovery document. (May '
    'be specified multiple times.)')
flags.DEFINE_string(
    'api_key', None,
    'API key to use for API access.')
flags.DEFINE_string(
    'client_id', None,
    'Client ID to use for the generated client.')
flags.DEFINE_string(
    'client_secret', None,
    'Client secret for the generated client.')
flags.DEFINE_multistring(
    'scope', [],
    'Scopes to request in the generated client. May be specified more than '
    'once.')
flags.DEFINE_string(
    'user_agent', '',
    'User agent for the generated client. Defaults to <api>-generated/0.1.')

flags.DEFINE_boolean(
    'experimental_capitalize_enums', False,
    'Dangerous: attempt to rewrite enum values to be uppercase.')
flags.DEFINE_enum(
    'experimental_name_convention', util.Names.DEFAULT_NAME_CONVENTION,
    util.Names.NAME_CONVENTIONS,
    'Dangerous: use a particular style for generated names.')
flags.DEFINE_boolean(
    'experimental_proto2_output', False,
    'Dangerous: also output a proto2 message file.')

FLAGS = flags.FLAGS

flags.MarkFlagAsRequired('client_id')
flags.MarkFlagAsRequired('client_secret')
flags.RegisterValidator(
    'infile', lambda i: not (i and FLAGS.discovery_url),
    'Cannot specify both --infile and --discovery_url')
flags.RegisterValidator(
    'discovery_url', lambda i: not (i and FLAGS.infile),
    'Cannot specify both --infile and --discovery_url')


def _CopyLocalFile(filename):
  with contextlib.closing(open(filename, 'w')) as out:
    src_data = pkgutil.get_data(
        'apitools.base.py', filename)
    if src_data is None:
      raise exceptions.GeneratedClientError('Could not find file %s' % filename)
    out.write(src_data)


def _GetCodegenFromFlags():
  """Create a codegen object from flags."""
  if FLAGS.discovery_url:
    try:
      discovery_doc = util.FetchDiscoveryDoc(FLAGS.discovery_url)
    except exceptions.CommunicationError:
      return None
  else:
    infile = os.path.expanduser(FLAGS.infile) or '/dev/stdin'
    discovery_doc = json.load(open(infile))
  names = util.Names(
      FLAGS.strip_prefix,
      FLAGS.experimental_name_convention,
      FLAGS.experimental_capitalize_enums)
  client_info = util.ClientInfo.Create(
      discovery_doc, FLAGS.scope, FLAGS.client_id, FLAGS.client_secret,
      FLAGS.user_agent, names, FLAGS.api_key)
  outdir = os.path.expanduser(FLAGS.outdir) or client_info.default_directory
  if os.path.exists(outdir) and not FLAGS.overwrite:
    raise exceptions.ConfigurationValueError(
        'Output directory exists, pass --overwrite to replace '
        'the existing files.')
  if not FLAGS.root_package_dir:
    FLAGS.root_package_dir = outdir
  FLAGS.root_package_dir = os.path.abspath(FLAGS.root_package_dir)
  root_package = util.GetPackage(FLAGS.root_package_dir)
  return gen_client_lib.DescriptorGenerator(
      discovery_doc, client_info, names, root_package, outdir,
      use_proto2=FLAGS.experimental_proto2_output)


# TODO(craigcitro): Delete this if we don't need this functionality.
def _WriteBaseFiles(codegen):
  with util.Chdir(codegen.outdir):
    _CopyLocalFile('app2.py')
    _CopyLocalFile('base_api.py')
    _CopyLocalFile('base_cli.py')
    _CopyLocalFile('credentials_lib.py')
    _CopyLocalFile('exceptions.py')


def _WriteProtoFiles(codegen):
  with util.Chdir(codegen.outdir):
    with open(codegen.client_info.messages_proto_file_name, 'w') as out:
      codegen.WriteMessagesProtoFile(out)
    with open(codegen.client_info.services_proto_file_name, 'w') as out:
      codegen.WriteServicesProtoFile(out)


def _WriteGeneratedFiles(codegen):
  if codegen.use_proto2:
    _WriteProtoFiles(codegen)
  with util.Chdir(codegen.outdir):
    with open(codegen.client_info.messages_file_name, 'w') as out:
      codegen.WriteMessagesFile(out)
    with open(codegen.client_info.client_file_name, 'w') as out:
      codegen.WriteClientLibrary(out)
    with open(codegen.client_info.cli_file_name, 'w') as out:
      codegen.WriteCli(out)


def _WriteInit(codegen):
  with util.Chdir(codegen.outdir):
    with open('__init__.py', 'w') as out:
      codegen.WriteInit(out)


class GenerateClient(appcommands.Cmd):
  """Driver for client code generation."""

  def Run(self, _):
    """Create a client library."""
    codegen = _GetCodegenFromFlags()
    if codegen is None:
      logging.error('Failed to create codegen, exiting.')
      return 128
    _WriteGeneratedFiles(codegen)
    _WriteInit(codegen)


class GenerateProto(appcommands.Cmd):
  """Generate just the two proto files for a given API."""

  def Run(self, _):
    """Create proto definitions for an API."""
    codegen = _GetCodegenFromFlags()
    _WriteProtoFiles(codegen)


# pylint: disable-msg=invalid-name


def run_main():
  """Function to be used as setuptools script entry point."""
  # Put the flags for this module somewhere the flags module will look
  # for them.

  # pylint: disable-msg=protected-access
  new_name = flags._GetMainModule()
  sys.modules[new_name] = sys.modules['__main__']
  for flag in FLAGS.FlagsByModuleDict().get(__name__, []):
    FLAGS._RegisterFlagByModule(new_name, flag)
    for key_flag in FLAGS.KeyFlagsByModuleDict().get(__name__, []):
      FLAGS._RegisterKeyFlagForModule(new_name, key_flag)
  # pylint: enable-msg=protected-access

  # Now set __main__ appropriately so that appcommands will be
  # happy.
  sys.modules['__main__'] = sys.modules[__name__]
  appcommands.Run()
  sys.modules['__main__'] = sys.modules.pop(new_name)


def main(_):
  appcommands.AddCmd('client', GenerateClient)
  appcommands.AddCmd('proto', GenerateProto)


if __name__ == '__main__':
  appcommands.Run()
