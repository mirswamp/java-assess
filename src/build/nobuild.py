import os
import os.path as osp
import logging

from ..logger import LogTaskStatus
from .. import utillib


class NoBuildHelperError(Exception):

    def __init__(self, exit_code):
        Exception.__init__(self)
        self.errno = exit_code

    def __str__(self):
        return 'No Build Helper returned %d' % self.errno


class NoSourceFilesFoundError(NoBuildHelperError):

    def __init__(self):
        NoBuildHelperError.__init__(self, 3)

    def __str__(self):
        return 'No Source Files Found in the Package'


class CompilationFailedError(NoBuildHelperError):

    def __init__(self, src_compiles_xmlfile):
        NoBuildHelperError.__init__(self, 4)
        self.src_compiles_xmlfile = src_compiles_xmlfile

    def __str__(self):
        return '''All Source Files Failed Compilation, See
        %s''' % self.src_compiles_xmlfile


def _get_error_msg(msg_file):
    with open(msg_file, 'r') as fobj:
        return fobj.readline().strip()


def no_build_helper(pkg_conf, build_root_dir, pkg_root_dir):
    '''Helper method for no-build.
    Returns a new pkg_conf.'''

    with LogTaskStatus('no-build-setup') as status_dot_out:

        pkg_build_dir = osp.normpath(osp.join(build_root_dir,
                                              pkg_root_dir,
                                              pkg_conf['package-dir'],
                                              pkg_conf.get('build-dir', '.')))

        build_file = osp.join(build_root_dir, 'build.xml')
        src_compiles_xmlfile = osp.join(build_root_dir, 'source-compiles.xml')
        msg_file = osp.join(build_root_dir, 'source-compiles-msg.out')
        no_build_helper_script = utillib.string_substitute('${SCRIPTS_DIR}/resources/no_build_helper',
                                                           os.environ)

        cmd = [no_build_helper_script,
               '--build-sys', 'ant',
               '--build-file', build_file,
               '--source-compiles', src_compiles_xmlfile,
               '--msg', msg_file]

        if 'package-short-name' in pkg_conf:
            cmd.extend(['--package-short-name', pkg_conf['package-short-name']])

        if 'package-version' in pkg_conf:
            cmd.extend(['--package-version', pkg_conf['package-version']])

        if 'VMPLATNAME' in os.environ:
            cmd.extend(['--platform', os.environ['VMPLATNAME']])

        cmd.extend(['--package-root-dir', pkg_conf['package-dir']])

        if 'build-dir' in pkg_conf:
            cmd.extend(['--build-root-dir', pkg_conf['build-dir']])

        logging.info('NO BUILD HELPER COMMAND: %s', cmd)
        logging.info('NO BUILD HELPER WORKING DIR: %s', pkg_build_dir)

        exit_code, environ = utillib.run_cmd(cmd, cwd=pkg_build_dir)

        logging.info('NO BUILD HELPER ERROR CODE: %d', exit_code)
        logging.info('NO BUILD HELPER ENVIRONMENT: %s', environ)

        status_dot_out.update_task_status(exit_code, _get_error_msg(msg_file))

        if exit_code == 0:
            pkg_conf['build-file'] = osp.relpath(build_file, pkg_build_dir)
            pkg_conf['build-sys'] = 'ant'
            pkg_conf['build-opt'] = '-Dbasedir=.'
            return pkg_conf, osp.relpath(src_compiles_xmlfile, build_root_dir)
        elif exit_code == 1:
            raise NoBuildHelperError(exit_code)
        elif exit_code == 2:
            raise NoSourceFilesFoundError
        elif exit_code == 3:
            raise CompilationFailedError(osp.relpath(src_compiles_xmlfile,
                                                     build_root_dir))
