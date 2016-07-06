#!/usr/bin/env python
# -*- coding: utf8 -*-

# ============================================================================
#  Copyright (c) 2013-2016 nexB Inc. http://www.nexb.com/ - All rights reserved.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#      http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ============================================================================

from __future__ import absolute_import
from __future__ import print_function

import codecs
import logging
import os
from os.path import exists, join

from about_tool import CRITICAL, ERROR, Error, INFO, NOTSET, WARNING
from about_tool import __about_spec_version__
from about_tool import __version__
from about_tool import attrib, gen, model, severities
import about_tool
from about_tool.model import About
from about_tool.util import copy_files, extract_zip, to_posix, verify_license_files
import click
import unicodecsv


__copyright__ = """
    Copyright (c) 2013-2016 nexB Inc. All rights reserved.
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
        http://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License."""


prog_name = 'AboutCode'
no_stdout = False
verbosity_num = 30

intro = '''%(prog_name)s, version %(__version__)s
ABOUT spec version: %(__about_spec_version__)s http://dejacode.org
%(__copyright__)s
''' % locals()


class AboutCommand(click.Command):
    def main(self, args=None, prog_name=None, complete_var=None,
             standalone_mode=True, **extra):
        """
        Workaround click 4.0 bug https://github.com/mitsuhiko/click/issues/365
        """
        return click.Command.main(self, args=args, prog_name=self.name,
                                  complete_var=complete_var,
                                  standalone_mode=standalone_mode, **extra)

@click.group(name='about')
@click.version_option(version=__version__, prog_name=prog_name, message=intro)
@click.option('-v', '--verbose', type=int, default=30,
              help='Increase verbosity. Repeat to print more output (Default: 30).\n'
                    '50 - CRITICAL\n'
                    '40 - ERROR\n'
                    '30 - WARNING\n'
                    '20 - INFO\n'
                    '10 - DEBUG')
@click.option('-q', '--quiet', is_flag=True, help='Do not print any output.')
def cli(verbose, quiet):
    # Update the no_stdout value globally
    global no_stdout, verbosity_num
    no_stdout = quiet
    verbosity_num = verbose
    pass
    # click.echo('Verbosity: %s' % verbose)


inventory_help = '''
LOCATION: Path to an ABOUT file or a directory containing ABOUT files
OUTPUT: Path to CSV file to write the inventory to
'''
formats = ['csv', 'json']
@cli.command(help=inventory_help,
             short_help='LOCATION: directory, OUTPUT: csv file',
             cls=AboutCommand)
@click.argument('location', nargs=1, required=True,
                type=click.Path(exists=True, file_okay=True,
                                dir_okay=True, writable=False,
                                readable=True, resolve_path=True))
@click.argument('output', nargs=1, required=True,
                type=click.Path(exists=False, file_okay=True, writable=True,
                                dir_okay=False, resolve_path=True))
@click.option('--overwrite', is_flag=True, help='Overwrites the output file if it exists')
@click.option('-f', '--format', is_flag=False, default='csv', show_default=True, metavar='<style>',
              help='Set <output_file> format <style> to one of the supported formats: %s' % ' or '.join(formats),)
def inventory(overwrite, format, location, output):
    """
    Inventory components from an ABOUT file or a directory tree of ABOUT
    files.    
    """
    click.echo('Running about-code-tool version ' + __version__)
    # Check is the <OUTPUT> valid.
    if os.path.exists(output) and not overwrite:
        click.echo('ERROR: <output> file already exists.')
        click.echo('Select a different file name or use the --overwrite option after the `inventory`.')
        click.echo()
        return
    if not exists(os.path.dirname(output)):
        click.echo('ERROR: Path to the <output> does not exists. Please check and correct the <output>.')
        click.echo()
        return
    if format not in formats:
        click.echo('ERROR: Output format: %s is not supported.' % format)
        click.echo()
        return
    if not format == 'json':
        if not output.endswith('.csv'):
            click.echo('ERROR: <output> must be a CSV file ending with ".csv".')
            click.echo()
            return

    click.echo('Collecting the inventory from location: ''%(location)s '
               'and writing output to: %(output)s' % locals())

    if location.lower().endswith('.zip'):
        # accept zipped ABOUT files as input
        location = extract_zip(location)

    errors, abouts = about_tool.model.collect_inventory(location)

    if not abouts:
        errors = [Error(ERROR, u'No ABOUT files is found. Generation halted.')]
    else:
        if format == 'json':
            model.to_json(abouts, output)
        else:
            model.to_csv(abouts, output)
    log_errors(errors, os.path.dirname(output), level=verbosity_num)


gen_help = '''
LOCATION: Path to a inventory file (CSV or JSON file)
OUTPUT: Path to the directory to write ABOUT files to
'''
@cli.command(help=gen_help,
             short_help='LOCATION: input file, OUTPUT: directory',
             cls=AboutCommand)
@click.argument('location', nargs=1, required=True,
                type=click.Path(exists=True, file_okay=True,
                                dir_okay=False, writable=False,
                                readable=True, resolve_path=True))
@click.argument('output', nargs=1, required=True,
                type=click.Path(exists=True, file_okay=False, writable=True,
                                dir_okay=True, resolve_path=True))
@click.option('--mapping', is_flag=True, help='Use the mapping between columns names'
                        'in your CSV and the ABOUT field names as defined in'
                        'the MAPPING.CONFIG mapping configuration file.')
@click.option('--license_text_location', nargs=1,
                type=click.Path(exists=True, file_okay=False,
                                dir_okay=True, writable=False,
                                readable=True, resolve_path=True),
              help = 'Copy the \'license_text_file\' from the directory to the generated location')
@click.option('--extract_license', type=str, nargs=2,
              help='Extract License text and create <license_key>.LICENSE side-by-side'
                    'with the generated .ABOUT file using data fetched from a DejaCode License Library.'
                    'The following additional options are required:\n\n'
                    'api_url - URL to the DejaCode License Library API endpoint\n\n'
                    'api_key - DejaCode API key'

                    '\nExample syntax:\n\n'
                    'about gen --extract_license \'api_url\' \'api_key\'')
def gen(mapping, license_text_location, extract_license, location, output):
    """
    Given an inventory of ABOUT files at location, generate ABOUT files in
    base directory.
    """
    click.echo('Running about-code-tool version ' + __version__)
    if not location.endswith('.csv') and not location.endswith('.json'):
        click.echo('ERROR: Input file. Only .csv and .json files are supported.')
        click.echo()
        return
    click.echo('Generating ABOUT files...')
    errors, abouts = about_tool.gen.generate(mapping, extract_license, location, output)

    if license_text_location:
        lic_loc_dict, lic_file_err = verify_license_files(abouts, license_text_location)
        if lic_loc_dict:
            copy_files(lic_loc_dict, output)
        if lic_file_err:
            update_errors = errors
            errors = []
            for err in update_errors:
                errors.append(err)
            for file_err in lic_file_err:
                errors.append(file_err)

    lea = len(abouts)
    lee = 0

    for e in errors:
        # Only count as warning/error if CRITICAL, ERROR and WARNING
        if e.severity > 20:
            lee = lee + 1
    click.echo('Generated %(lea)d ABOUT files with %(lee)d errors and/or warning' % locals())
    log_errors(errors, output)


@cli.command(cls=AboutCommand)
def export():
    click.echo('Running about-code-tool version ' + __version__)
    click.echo('Exporting zip archive...')



@cli.command(cls=AboutCommand)
def fetch(location):
    """
    Given a directory of ABOUT files at location, calls the DejaCode API and
    update or create license data fields and license texts.
    """
    click.echo('Running about-code-tool version ' + __version__)
    click.echo('Updating ABOUT files...')


@cli.command(cls=AboutCommand)
@click.argument('location', nargs=1, required=True,
                type=click.Path(exists=True, file_okay=True,
                                dir_okay=True, writable=False,
                                readable=True, resolve_path=True))
@click.argument('output', nargs=1, required=True,
                type=click.Path(exists=False, file_okay=True, writable=True,
                                dir_okay=False, resolve_path=True))
@click.argument('inventory_location', nargs=1, required=False,
                type=click.Path(exists=False, file_okay=True, writable=True,
                                dir_okay=False, resolve_path=True))
@click.option('--template', type=click.Path(exists=True), nargs=1,
              help='Use the custom template for the Attribution Generation')
@click.option('--mapping', is_flag=True, help='Configure the mapping key from the MAPPING.CONFIG')
def attrib(location, output, template, mapping, inventory_location=None,):
    """
    Generate attribution document at output using the directory of
    ABOUT files at location, the template file (or a default) and an
    inventory_location file containing a list of ABOUT files path to
    generate attribution for.
    """
    click.echo('Running about-code-tool version ' + __version__)
    click.echo('Generating attribution...')

    if location.lower().endswith('.zip'):
        # accept zipped ABOUT files as input
        location = extract_zip(location)

    errors, abouts = model.collect_inventory(location)
    no_match_errors = about_tool.attrib.generate_and_save(abouts, output, mapping,
                                             template_loc=template,
                                             inventory_location=inventory_location)

    log_errors(no_match_errors, os.path.dirname(output))
    click.echo('Finished.')

@cli.command(cls=AboutCommand)
def redist(input_dir, output, inventory_location=None,):
    """
    Collect redistributable code at output location using:
     - the input_dir of code and ABOUT files,
     - an inventory_location CSV file containing a list of ABOUT files to
     generate redistribution for.
     Only collect code when redistribute=yes
     Return a list of errors.
    """
    click.echo('Running about-code-tool version ' + __version__)
    click.echo('Collecting redistributable files...')


def log_errors(errors, base_dir=False, level=NOTSET):
    """
    Iterate of sequence of Error objects and print and log errors with a severity
    superior or equal to level.
    """
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    handler.setLevel(logging.CRITICAL)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(handler)
    file_logger = logging.getLogger(__name__ + '_file')

    msg_format = '%(sever)s: %(message)s'
    # Create error.log
    if base_dir:
        bdir = to_posix(base_dir)
        LOG_FILENAME = 'error.log'
        log_path = join(bdir, LOG_FILENAME)
        if exists(log_path):
            os.remove(log_path)

        file_handler = logging.FileHandler(log_path)
        file_logger.addHandler(file_handler)
    for severity, message in errors:
        if severity >= level:
            sever = severities[severity]
            if not no_stdout:
                print(msg_format % locals())
            if base_dir:
                file_logger.log(severity, msg_format % locals())


if __name__ == '__main__':
    cli()