#! /usr/bin/env python3

import argparse
import os.path
import os
import sys

def process_cmd_line_args():
    '''
    **archive: <Name of the archive>
	     | **dir: <Top level directory when unarchived>
	     | **config-dir: <Relative directory from <dir> to change to before configuring, default '.'>
	     | **config-cmd: <Command to configure the package (derived from <build-sys>)>
	     | **config-opt: <Configuration Options>
	     | **build-dir: <Relative directory from <dir> to change to before building, default '.'>
	     | **build-file: <Relative path from <build-dir> to the build file>
	     | **build-cmd: <Command to build the package (default derived from <build-sys>)>
	     | **build-opt: <Build Options>
	     | **build-target: <Build target>
'''
    parser = argparse.ArgumentParser(description='''Create Package.conf''')

    parser.add_argument('--package-archive',
                        dest='package-archive',
                        nargs=1,
                        type=str,
                        help='path for the directory that has infrastructure files')

    parser.add_argument('--package-dir',
                        dest='package-dir',
                        nargs=1,
                        type=str,
                        help='path for the directory that has infrastructure files')

    parser.add_argument('--build-sys',
                        dest='build-sys',
                        nargs=1,
                        choices=['Ant', 'Maven'],
                        type=str,
                        help='')

    parser.add_argument('--build-dir',
                        dest='build-dir',
                        nargs=1,
                        default='.',
                        type=str,
                        help='')

    parser.add_argument('--build-file',
                        dest='build-file',
                        nargs=1,
                        default='',
                        type=str,
                        help='')

    parser.add_argument('--build-opt',
                        dest='build-opt',
                        nargs=1,
                        default='',
                        type=str,
                        help='')

    parser.add_argument('--build-target',
                        dest='build-target',
                        nargs=1,
                        default='',
                        type=str,
                        help='')

    return vars(parser.parse_args())


def validate_cmd_line_args(args):
    pass

def write_dict_to_file(filename, dictionary):
    with open(filename, 'w') as f:
        for key in dictionary.keys():
            print('{0}={1}'.format(key, dictionary[key]), file=f)

if(__name__ == '__main__'):
    args = process_cmd_line_args()
    write_dict_to_file('package.conf',
                       {key:' '.join(args[key]) for key in args.keys()})




