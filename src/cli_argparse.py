import argparse
import subprocess
import os
import pkgutil


class PrintPlatform(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        namespace.platform = os.getenv('VMPLATNAME')

        if not namespace.platform:
            namespace.platform = str(subprocess.check_output(['uname', '-s', '-r']),
                                     encoding='utf-8').strip()


class PrintVersion(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        version = pkgutil.get_data('version', 'version.txt')
        if version:
            version = str(version, encoding='utf-8').strip('\n')
        else:
            #version = 'v.?.?.?'
            # THIS is a temporary,
            version = '2.1.4'
        namespace.version = '{0} {1}'.format(parser.prog, version)


def process_cmd_line_args():
    parser = argparse.ArgumentParser(prog='java-assess',
                                     description='Assess a Java package in SWAMP VM environment')

    parser.add_argument('--printVersion',
                        nargs=0,
                        dest='version',
                        required=False,
                        action=PrintVersion,
                        help='gets the version of the program ' + parser.prog)

    parser.add_argument('--printPlatform',
                        nargs=0,
                        dest='platform',
                        required=False,
                        action=PrintPlatform,
                        help='gets the current platform name and version')

    parser.add_argument('input_dir',
                        type=str,
                        help='Path to the Input Directory')

    parser.add_argument('output_dir',
                        type=str,
                        help='Path to the Output Directory')

    parser.add_argument('build_dir',
                        type=str,
                        help='Path to the Build Directory where the package is unarchived and built')

    parser.add_argument('tool_dir',
                        type=str,
                        help='Path to the Tool Directory')

    parser.add_argument('results_dir',
                        type=str,
                        help='Path to the directory where Assessment results are placed')

    return parser.parse_args()
