
import os
import os.path as osp
import logging
import re
import shutil
import json
from abc import ABCMeta
import zipfile
import copy
import glob

from ..logger import LogTaskStatus
from .. import utillib
from .. import confreader
from .. import gencmd
from .. import directory_scanner

from ..utillib import FileNotFoundException
from ..utillib import UnpackArchiveError
from .assess_helper import JavaBuildArtifacts
from .assess_helper import BuildArtifacts
from .assess_helper import JavaBuildArtifactsError
from .assess_helper import JavaInvalidBuildError
from .assess_helper import JavaBuildSummaryError
from .assess_summary import AssessmentSummary


class ToolInstallFailedError(Exception):

    def __init__(self, value):
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        return repr(self.value)


class SwaTool(metaclass=ABCMeta):

    TOOL_DOT_CONF = 'tool.conf'

    @classmethod
    def get_services_conf(cls, tool_type, input_root_dir):

        conf_file = osp.join(input_root_dir, 'services.conf')
        if osp.isfile(conf_file):
            services_conf = confreader.read_conf_into_dict(conf_file)
            return {key: services_conf[key] for key in services_conf.keys() if key.startswith('tool' + tool_type)}
        else:
            return dict()

    @classmethod
    def _get_tool_conf(cls, input_root_dir):

        tool_conf_file = osp.join(input_root_dir, cls.TOOL_DOT_CONF)
        tool_conf = confreader.read_conf_into_dict(tool_conf_file)

        invoke_file = osp.join(input_root_dir, tool_conf['tool-invoke'])
        if osp.isfile(invoke_file):
            tool_conf['tool-invoke'] = invoke_file
        else:
            raise FileNotFoundException(invoke_file)

        default_conf_file = osp.join(input_root_dir, tool_conf['tool-defaults'])

        if not osp.isfile(default_conf_file):
            raise FileNotFoundException(default_conf_file)

        updated_conf = confreader.read_conf_into_dict(default_conf_file)
        updated_conf.update(tool_conf)

        updated_conf.update(SwaTool.get_services_conf(updated_conf['tool-type'], input_root_dir))

        updated_conf = {key: utillib.expandvar(updated_conf[key], updated_conf)
                        for key in updated_conf}
        return updated_conf

    @classmethod
    def _read_err_msg(cls, errfile, errmsg):
        msg = ''

        if osp.isfile(errfile):
            errmsg_regex = re.compile(errmsg)
            line_num = 1
            with open(errfile) as fobj:
                for line in fobj:
                    if errmsg_regex.search(line.strip()):
                        # msg += '{0}:{1}: {2}\n'.format(errfile, line_num, line.strip())
                        msg += '{0}:{1}: {2}\n'.format('/'.join(errfile.split('/')[-2:]),
                                                       line_num, line.strip())
                    line_num += 1

        return msg

    @classmethod
    def _get_class_files(cls, src_file_list,
                         dest_dir_list, encoding=BuildArtifacts.UTF_8):

        class_files = set()
        not_found_files = set()

        for destdir in dest_dir_list:
            if osp.isdir(destdir):

                all_class_files = directory_scanner.get_files(destdir, '**/*.class')
                for srcfile in src_file_list:
                    try:
                        cf = directory_scanner.get_class_file(srcfile,
                                                              encoding,
                                                              destdir,
                                                              all_class_files)
                        if cf:
                            class_files.update(cf)
                        else:
                            not_found_files.add(srcfile)
                    except UnicodeDecodeError as err:
                        logging.error('UnicodeDecodeError: %s in the %s', str(err), srcfile)
                        not_found_files.add(srcfile)

        if not_found_files:
            logging.warning('Classfiles not found for : %s',
                            ','.join(not_found_files))

        return list(class_files)

    def __init__(self, input_root_dir, tool_root_dir):

        self._tool_conf = SwaTool._get_tool_conf(input_root_dir)
        utillib.setup_java_home(self._tool_conf.get('tool-language-version', 'java-7'))

        self._unarchive(input_root_dir, tool_root_dir)
        self._install(input_root_dir, tool_root_dir)
        self._install_license(input_root_dir, tool_root_dir)

        if not osp.isabs(self._tool_conf['executable']):
            if 'tool-dir' not in self._tool_conf:
                self._tool_conf['tool-dir'] = '.'

            self._tool_conf['executable'] = osp.join(tool_root_dir,
                                                     self._tool_conf['tool-dir'],
                                                     self._tool_conf['executable'])

        if 'assessment-report-template' not in self._tool_conf:
            self._tool_conf['assessment-report-template'] = 'assessment_report{0}.xml'

        if 'tool-target-artifacts' not in self._tool_conf:
            self._tool_conf['tool-target-artifacts'] = 'java-compile'

        ## XXX this is copied code and it doesn't have all
        ## the comments.  Once everything is rolled together
        ## the copied code will go away and all the knowledge is
        ## in one place.   please see src/build/build_java.py for comments

        ## PLEASE SEE BOLO'S NOTES ON JAVA MEMORY
        ## This is a cheap seats version of doing this for real
        ## as I describe.  This does not deal with garbage collection
        ## and java versions, which could help out tools quite a bit.

        sys_mem = utillib.sys_mem_size()
        logging.info("as sys_mem_size == %d", sys_mem);

        ## old 32 bit default, fallback to avoid warnings.
        max_heap = 1024

        ## XXX wait for bolo's scaling stuff, this is a stupid version
        ## XXX with this value, we are already into swap space due
        ## to other java memory allocations.  It seems to work OK
        ## for now, so this is actually a tuned number!

        ## XXX may want to choose mem_size "NEAR" the thresholds since
        ## the system steals some memory and we don't get sizing as
        ## aggressive as this looks.  However, we are into swap as
        ## it is, so these numbers aren't totally bad.

        if utillib.get_cpu_type() == 64:
            if (sys_mem >= 30 * 1024):
                memory_for_java = int(sys_mem * 10 / 11)
            elif (sys_mem >= 10 * 1024):
                max_heap = int(sys_mem * 9 / 10)
            elif (sys_mem >= 8 * 1024):
                max_heap = int(sys_mem * 7 / 8)
            elif (sys_mem >= 4 * 1024):
                max_heap = int(sys_mem * 5 / 6)
            elif (sys_mem >= 3 * 1024):
                max_heap = int(sys_mem * 3 / 4)
            else:
                max_heap = int(sys_mem * 2 / 3)
        elif utillib.get_cpu_type() == 32:
            if (sys_mem > 3 * 1024):
                sys_mem = 3 * 1024
                logging.info("as sys_mem_size LIMIT 32 bit proc to %d", sys_mem);
            max_heap = int(sys_mem * 3 / 4)

        logging.info("as max-heap == %d", max_heap);

        self._tool_conf['max-heap'] = '-Xmx{0}M'.format(max_heap)

        ## ps-jtest uses jvm-max-heap , which is really a parasoft -J option
        ## may be better to just have a "max heap" number which can then
        ## be backfilled into any tool-dependent option via the
        ## invoke/conf rewriter.   For now, just using this which
        ## will make it work correctly with all parasofts.
        ## Need to change option name such as:
        ## -J<max-heap>
        ## or
       	## -J-Xmx<max-heap-val>
        ## XXX option should be renamed jtest-max-heap since tool specific

        self._tool_conf['jvm-max-heap'] = '-J-Xmx{0}M'.format(max_heap)

        ## XXX not addressing garbage collection and other optimizations
        ## at this time

        logging.info('TOOL CONF: %s', self._tool_conf)

        # For Exit Status and Summary
        self.passed = 0
        self.failed = 0
        self.error_msgs = ''
        self.summary_file = None
        
    def _get_report(self, results_root_dir, report, outfile):
        '''Report passed as an argument is old report path
        This method has to be overridden for AppHealthCheck
        Arguments: results_root_dir, report, outfile
        '''
        return report

    def _cleanup(self):
        pass

    def _get_stdin(self):
        return None

    def _get_env(self):
        return dict(os.environ)

    def _unarchive(self, input_root_dir, tool_root_dir):

        with LogTaskStatus('tool-unarchive') as status_dot_out:

            if 'tool-archive' not in self._tool_conf:
                status_dot_out.skip_task()
                return

            tool_archive = osp.join(input_root_dir, self._tool_conf['tool-archive'])
            status = utillib.unpack_archive(tool_archive, tool_root_dir)

            if status != 0:
                raise UnpackArchiveError(self._tool_conf['tool-archive'])

    def _install(self, input_root_dir, tool_root_dir):

        with LogTaskStatus('tool-install') as status_dot_out:

            if 'tool-install-cmd' not in self._tool_conf:
                status_dot_out.skip_task()
            else:
                install_cmd = self._tool_conf['tool-install-cmd']

                logging.info('TOOL INSTALL COMMAND: %s', install_cmd)

                exit_code, _ = utillib.run_cmd(install_cmd,
                                               shell=True,
                                               cwd=tool_root_dir)

                if exit_code != 0:
                    raise ToolInstallFailedError("Install Tool Failed, "
                                                 "Command '{0}' return {1}".format(install_cmd,
                                                                                   exit_code))

    def _install_license(self, input_root_dir, tool_root_dir):

        # spelling mistake, and this is to make it backwards compatible
        if 'tool-licence-template' in self._tool_conf or \
           'tool-license-template' in self._tool_conf:

            services_file = osp.join(input_root_dir, 'services.conf')
            services_conf = confreader.read_conf_into_dict(services_file)

            # spelling mistake, and this is to make it backwards compatible
            if 'tool-licence-template' in self._tool_conf:
                license_template_file = utillib.expandvar(self._tool_conf['tool-licence-template'], None)
            else:
                license_template_file = utillib.expandvar(self._tool_conf['tool-license-template'], None)
            
            with open(license_template_file) as fobj:
                license_blob = ''.join([s for s in fobj])
                license_string = utillib.expandvar(license_blob, services_conf)
                license_file = osp.join(tool_root_dir, 'license')

                with open(license_file, 'w') as fobj2:
                    fobj2.write(license_string)
                self._tool_conf['tool-license'] = license_file

            self._tool_conf.update(services_conf)
                
    def _get_num_failed_assessments(self, exit_code_list):
        return sum([not self._validate_exit_code(exit_code)
                    for exit_code in exit_code_list])

    def assess(self, build_summary_file, results_root_dir):

        JavaBuildArtifacts.validate(build_summary_file)
        build_summary_obj = JavaBuildArtifacts(build_summary_file)

        os.makedirs(results_root_dir, exist_ok=True)
        self.summary_file = osp.join(results_root_dir, 'assessment_summary.xml')

        exit_codes_list = list()

        with AssessmentSummary(self.summary_file,
                               build_summary_obj,
                               self._tool_conf) as assessment_summary:

            for build_artifacts in self._get_build_artifacts(build_summary_obj, results_root_dir):

                if 'report-on-stdout' in self._tool_conf \
                   and self._tool_conf['report-on-stdout'] == 'true':
                    outfile = build_artifacts['assessment-report']
                else:
                    outfile = osp.join(results_root_dir,
                                       'swa_tool_stdout{0}.out'.format(build_artifacts['build-artifact-id']))

                if 'report-on-stderr' in self._tool_conf \
                   and self._tool_conf['report-on-stderr'] == 'true':
                    errfile = build_artifacts['assessment-report']
                else:
                    errfile = osp.join(results_root_dir,
                                       'swa_tool_stderr{0}.out'.format(build_artifacts['build-artifact-id']))

                self._tool_conf['swa-tool-stdout'] = outfile
                self._tool_conf['swa-tool-stderr'] = errfile

                build_artifacts.update(self._tool_conf)
                cmd = gencmd.gencmd(self._tool_conf['tool-invoke'], build_artifacts)
                logging.info('ASSESSMENT COMMAND: %s', cmd)

                starttime = utillib.posix_epoch()

                exit_code, environ = utillib.run_cmd(cmd,
                                                     cwd=build_summary_obj.get_pkg_dir(),
                                                     outfile=outfile,
                                                     errfile=errfile,
                                                     infile=self._get_stdin(),
                                                     env=self._get_env())

                build_artifacts['assessment-report'] = self._get_report(results_root_dir,
                                                                        build_artifacts['assessment-report'],
                                                                        outfile)

                assessment_summary.add_report(build_artifacts['build-artifact-id'],
                                              cmd,
                                              exit_code,
                                              environ,
                                              build_summary_obj.get_pkg_dir(),
                                              build_artifacts['assessment-report'],
                                              outfile,
                                              errfile,
                                              self._tool_conf['tool-type'],
                                              starttime,
                                              utillib.posix_epoch(),
                                              results_root_dir)

                if not self._validate_exit_code(exit_code) and \
                   ('tool-report-exit-code' in self._tool_conf) and \
                   (exit_code == int(self._tool_conf['tool-report-exit-code'])):

                    exit_codes_list.append(exit_code)

                    if self._tool_conf['tool-type'] == 'error-prone':
                        self.error_msgs += SwaTool._read_err_msg(build_artifacts['assessment-report'],
                                                                 self._tool_conf['tool-report-exit-code-msg'])
                    elif self._tool_conf['tool-type'] == 'dependency-check':
                        self.error_msgs += SwaTool._read_err_msg(outfile,
                                                                 self._tool_conf['tool-report-exit-code-msg'])
                    elif self._tool_conf['tool-type'] == 'ps-jtest' and \
                         self._tool_conf['tool-version'].startswith('10.3'):
                        self.error_msgs += SwaTool._read_err_msg(outfile,
                                                                 self._tool_conf['tool-report-exit-code-msg'])
                    else:
                        self.error_msgs += SwaTool._read_err_msg(errfile,
                                                                 self._tool_conf['tool-report-exit-code-msg'])
                elif self._tool_conf['tool-type'] == 'error-prone' and \
                     self._tool_conf['tool-version'] not in ['2.0.15', '2.0.9', '1.1.1']:
                    # error-prone 2.0.21 does not return different exit code for tool-pkg-incompatiblity
                    error_msg = SwaTool._read_err_msg(build_artifacts['assessment-report'],
                                                      self._tool_conf['tool-report-exit-code-msg'])

                    if error_msg:
                        self.error_msgs += error_msg
                        # Differnet exit code
                        exit_codes_list.append(int(self._tool_conf['tool-report-exit-code']))
                    else:
                        exit_codes_list.append(exit_code)
                else:
                    exit_codes_list.append(exit_code)

                self._cleanup()

        self.failed = self._get_num_failed_assessments(exit_codes_list)
        self.passed = len(exit_codes_list) - self.failed
    
    def post_assess(self, results_root_dir):
        pass
    
    def _validate_exit_code(self, exit_code):
        if 'valid-exit-status' in self._tool_conf:
            regex = re.compile(self._tool_conf['valid-exit-status'])
            return True if(regex.match(str(exit_code))) else False
        else:
            return True if(exit_code == 0) else False

    def _modify_build_artifacts(self, build_artifacts, results_root_dir):
        '''Override this method, to modify/add to raw build artifacts
        return False if this method does not yield artifacts for assessment
        '''
        return True

    def _get_build_artifacts(self, build_summary_obj, results_root_dir):

        for build_artifacts in \
                build_summary_obj.get_build_artifacts(*self._tool_conf['tool-target-artifacts'].split()):

            build_artifacts['assessment-report'] = osp.join(results_root_dir,
                                                            self._tool_conf['assessment-report-template'].format(build_artifacts['build-artifact-id']))

            if self._modify_build_artifacts(build_artifacts, results_root_dir):
                yield build_artifacts


class JavaSwaTool(SwaTool):

    def __init__(self, input_root_dir, tool_root_dir):
        SwaTool.__init__(self, input_root_dir, tool_root_dir)

    def _get_build_artifacts(self, build_summary_obj, results_root_dir):
        '''yeilds dictionary objects that has all the information to run
        a swa tool'''

        for build_artifacts in \
                build_summary_obj.get_build_artifacts(*self._tool_conf['tool-target-artifacts'].split()):

            build_artifacts['assessment-report'] = osp.join(results_root_dir,
                                                            self._tool_conf['assessment-report-template'].format(build_artifacts['build-artifact-id']))

            for new_build_artifacts in self._split_build_artifact(build_artifacts,
                                                                  results_root_dir):
                yield new_build_artifacts

    def _split_build_artifact(self, build_artifacts, results_root_dir):
        '''Splits only if required'''

        # returns list of list
        file_type, max_allowed_size = self._split_artifacts_required(build_artifacts)
        if file_type:
            filelists = list()
            self._split_list(filelists,
                             build_artifacts[file_type],
                             max_allowed_size)

            build_artifacts.pop(file_type)
            build_artifacts_list = list()

            id_count = 1
            for filelist in filelists:
                new_attrs = dict(build_artifacts)
                new_attrs[file_type] = filelist
                new_attrs['build-artifact-id'] = '{0}-{1}'.format(new_attrs['id'], str(id_count))
                new_attrs['assessment-report'] = osp.join(results_root_dir,
                                                          self._tool_conf['assessment-report-template'].format(new_attrs['build-artifact-id']))
                id_count += 1
                build_artifacts_list.append(new_attrs)

            return build_artifacts_list
        else:
            return [build_artifacts]

    def _split_artifacts_required(self, build_artifacts):
        '''returns a tuple with key in attribute and an integer corresponding
        to the size '''
        build_artifacts_local = dict(build_artifacts)
        build_artifacts_local.update(self._tool_conf)

        get_cmd_size = lambda attr: len(' '.join(gencmd.gencmd(attr['tool-invoke'], attr)))

        if get_cmd_size(build_artifacts_local) > utillib.max_cmd_size():
            assess_artifact_type = JavaSwaTool._get_assess_artifact_type(build_artifacts_local['tool-invoke'],
                                                                         'classfile',
                                                                         'srcfile')
            if assess_artifact_type is None:
                raise Exception('''The filelist that needs to be split
                                has to be an explicit parameter''')

            build_artifacts_local.pop(assess_artifact_type)
            max_allowed_size = utillib.max_cmd_size() - get_cmd_size(build_artifacts_local)
            return (assess_artifact_type, max_allowed_size)
        else:
            return (None, None)

    def _split_list(self, llist, filelist, max_args_size):
        if len(' '.join(filelist)) > max_args_size:
            self._split_list(llist, filelist[0:int(len(filelist) / 2)], max_args_size)
            self._split_list(llist, filelist[int(len(filelist) / 2):], max_args_size)
        else:
            llist.append(filelist)

    @classmethod
    def _get_assess_artifact_type(cls, filename, *args):
        '''returns classfile or srcfile or raises Exception'''
        tokens = gencmd.get_param_list(filename)

        for arg in args:
            if arg in tokens:
                return arg


class Findbugs(SwaTool):

    def __init__(self, input_root_dir, tool_root_dir):
        SwaTool.__init__(self, input_root_dir, tool_root_dir)
        self._tool_conf['tool-target-artifacts'] = 'java-compile java-bytecode'
        self.stdin_file_path = None

    def _modify_build_artifacts(self, build_artifacts, results_root_dir):

        if 'classfile' not in build_artifacts:
            build_artifacts['classfile'] = SwaTool._get_class_files(build_artifacts['srcfile'],
                                                                    build_artifacts['destdir'],
                                                                    build_artifacts.get('encoding',
                                                                                        BuildArtifacts.UTF_8))

        if build_artifacts['classfile']:
            class_files_list = osp.join(results_root_dir,
                                        'class_files{0}.txt'.format(build_artifacts['build-artifact-id']))
            utillib.write_to_file(class_files_list, build_artifacts['classfile'])
            self.stdin_file_path = class_files_list
            return True
        else:
            return False
        
    def _get_stdin(self):
        return self.stdin_file_path

    def _cleanup(self):
        self.stdin_file_path = None


class Jtest(SwaTool):

    @classmethod
    def _change_file_filters(cls, file_filters):
        new_file_filters = list()

        for pattern in file_filters:
            if pattern.endswith('.java'):
                pattern = pattern.rpartition('.java')[0]
            pattern = pattern.replace('/', '.')
            new_file_filters.append(pattern)

        return new_file_filters

    @classmethod
    def _modify_jtest_srcdirs(cls, build_artifacts, results_root_dir):

        srcdirs = set(build_artifacts['srcdir'])
        include = set()

        for _dir in srcdirs:
            for _file in build_artifacts['srcfile']:

                if _file.startswith(_dir):
                    pkgpath = _file.replace(_dir, '', 1)

                    if pkgpath is not None:
                        pkgpath = osp.splitext(pkgpath)[0]
                        if pkgpath.startswith('/'):
                            pkgpath = pkgpath[1:]
                        include.add(pkgpath.replace('/', '.'))

        build_artifacts['srcdir'] = list(srcdirs)
        include_filters_file = osp.join(results_root_dir,
                                        'include_filters{0}.lst'.format(build_artifacts['build-artifact-id']))
        utillib.write_to_file(include_filters_file, list(include))
        build_artifacts['include'] = include_filters_file

    def __init__(self, input_root_dir, tool_root_dir):
        SwaTool.__init__(self, input_root_dir, tool_root_dir)

    def _modify_build_artifacts(self, build_artifacts, results_root_dir):

        if 'include' in build_artifacts and build_artifacts['include']:
            build_artifacts['include'] = Jtest._change_file_filters(build_artifacts['include'])
        else:
            Jtest._modify_jtest_srcdirs(build_artifacts, results_root_dir)

        if 'exclude' in build_artifacts and build_artifacts['exclude']:
            build_artifacts['exclude'] = Jtest._change_file_filters(build_artifacts['exclude'])

        return True


class Errorprone(SwaTool):

    def __init__(self, input_root_dir, tool_root_dir):
        SwaTool.__init__(self, input_root_dir, tool_root_dir)

    def _modify_build_artifacts(self, build_artifacts, results_root_dir):
        source_files_list = osp.join(results_root_dir,
                                     'source_files{0}.txt'.format(build_artifacts['build-artifact-id']))
        # quotes are required for files that have spaces in their paths
        source_files = {'"%s"' % _file for _file in build_artifacts['srcfile']}
        utillib.write_to_file(source_files_list, source_files)
        build_artifacts['srcfile-filename'] = source_files_list
        
        return True
        

class Lizard(JavaSwaTool):

    def __init__(self, input_root_dir, tool_root_dir):
        SwaTool.__init__(self, input_root_dir, tool_root_dir)
        self.build_artifacts_encoding = None

    def _get_env(self):
        new_env = dict(os.environ)
        if self.build_artifacts_encoding is not None:
            new_env['LANG'] = 'en_US.%s' % (self.build_artifacts_encoding)
        return new_env

    def _modify_build_artifacts(self, build_artifacts, results_root_dir):

        encoding = build_artifacts.get('encoding', None)
        if encoding and encoding != BuildArtifacts.UTF_8:
            self.build_artifacts_encoding = encoding

        return True

    def _cleanup(self):
        self.build_artifacts_encoding = None


class AppHealthCheck(SwaTool):

    USER_CONF_FILE = 'sonatype-data.conf'
    USER_CONF_KEYS = {'company-name', 'full-name', 'email-id', 'integrator-name'}
    
    def __init__(self, input_root_dir, tool_root_dir):
        SwaTool.__init__(self, input_root_dir, tool_root_dir)
        self._tool_conf['tool-target-artifacts'] = 'java-compile java-bytecode'
        self.ahc_results_archive = None
        self.ahc_results_file = None

    def _install(self, input_root_dir, tool_root_dir):

        with LogTaskStatus('tool-install'):

            user_info_conf_file = osp.join(input_root_dir,
                                           AppHealthCheck.USER_CONF_FILE)
            if osp.isfile(user_info_conf_file):
                user_info_conf = confreader.read_conf_into_dict(user_info_conf_file)
                if AppHealthCheck.USER_CONF_KEYS.issubset(set(user_info_conf)):
                    self._tool_conf.update(user_info_conf)
                else:
                    raise ToolInstallFailedError('Missing required tool options %s in the file: %s' %
                                                 (AppHealthCheck.USER_CONF_KEYS.difference(set(user_info_conf)),
                                                  AppHealthCheck.USER_CONF_FILE))
            else:
                raise ToolInstallFailedError('User info file (%s) not found' %
                                             (AppHealthCheck.USER_CONF_FILE))

    def _get_build_artifacts(self, build_summary_obj, results_root_dir):
        '''yeilds dictionary objects that has all the information to run
        a swa tool'''

        archives = set()
        new_build_artifacts = dict()

        get_jarfiles = lambda filelist: (filepath for filepath in filelist
                                         if osp.isfile(filepath) and
                                         osp.splitext(filepath)[1] == '.jar')

        for build_artifacts in \
                build_summary_obj.get_build_artifacts(*self._tool_conf['tool-target-artifacts'].split()):

            if 'auxclasspath' in build_artifacts:
                archives.update(get_jarfiles(build_artifacts['auxclasspath']))

            if 'classfile' in build_artifacts:
                archives.update(get_jarfiles(build_artifacts['classfile']))
            else:
                class_files_list = SwaTool._get_class_files(build_artifacts['srcfile'],
                                                            build_artifacts['destdir'],
                                                            build_artifacts.get('encoding',
                                                                                BuildArtifacts.UTF_8))

                archives.update(class_files_list)

        if archives:
            new_build_artifacts['build-artifact-id'] = '1'
            target_file = osp.join(results_root_dir,
                                   'class_files{0}.txt'.format(new_build_artifacts['build-artifact-id']))
            utillib.write_to_file(target_file, archives)
            new_build_artifacts['target-filepath'] = target_file
            new_build_artifacts['assessment-report'] = osp.join(results_root_dir,
                                                                self._tool_conf['assessment-report-template'].format(new_build_artifacts['build-artifact-id']))

            yield new_build_artifacts
        else:
            raise JavaBuildArtifactsError("No files found for analysis.")

    def _get_report_old(self, results_root_dir, report_file, outfile):
        '''Report passed as an argument is old report path
        This method has to be overridden for AppHealthCheck
        Arguments: results_root_dir, report
        '''
        if not osp.isfile(report_file):
            dummy_report = {
                "summary": {
                    "policyViolations": {
                        "critical": 5,
                        "severe": 3,
                        "moderate": 1,
                    }
                }
            }
            with open(report_file, 'w') as fobj:
                json.dump(dummy_report, fobj)

        return report_file

    def post_assess(self, results_root_dir):
        if osp.isfile(osp.join(results_root_dir, 'report-1.zip')):
            self.ahc_results_archive = 'report-1.zip'

            if 'index.html' in zipfile.ZipFile(osp.join(results_root_dir, 'report-1.zip')).namelist():
                self.ahc_results_file = 'index.html'


class OwaspDependencyCheck(SwaTool):

    def __init__(self, input_root_dir, tool_root_dir):
        SwaTool.__init__(self, input_root_dir, tool_root_dir)
        self._tool_conf['tool-target-artifacts'] = 'java-compile java-bytecode java-android-apk'

    def _install(self, input_root_dir, tool_root_dir):

        with LogTaskStatus('tool-install'):

            run_conf = confreader.read_conf_into_dict(osp.join(input_root_dir,
                                                               'run.conf'))
            services_conf_file = osp.join(input_root_dir, 'services.conf')

            if run_conf.get('internet-inaccessible', 'false') == 'true':
                db_file = osp.join(tool_root_dir, self._tool_conf['tool-dir'], 'data', 'dc.h2.db')

                if not osp.isfile(db_file):
                    raise ToolInstallFailedError("Tool database file '{}' not found, this is required for 'internet-inaccessible' environments".format(osp.join(self._tool_conf['tool-dir'], 'data', 'dc.h2.db')))

            elif osp.isfile(services_conf_file):

                services_conf = confreader.read_conf_into_dict(services_conf_file)

                all_odc_keys = {'tool-dependency-check-db-host',
                                'tool-dependency-check-db-port',
                                'tool-dependency-check-db-client-name',
                                'tool-dependency-check-db-client-password',
                                'tool-dependency-check-db-path'}

                if all_odc_keys.issubset(set(services_conf)):
                    connection_string = 'jdbc:h2:tcp://<tool-dependency-check-db-host>:<tool-dependency-check-db-port>/<tool-dependency-check-db-path>'
                    self._tool_conf['db-connection-string'] = utillib.expandvar(connection_string,
                                                                                services_conf)
                    self._tool_conf['db-user'] = services_conf['tool-dependency-check-db-client-name']
                    self._tool_conf['db-password'] = services_conf['tool-dependency-check-db-client-password']
                else:
                    if 'db-update-option' in self._tool_conf:
                        self._tool_conf.pop('db-update-option')
            else: # fetch db locally
                    if 'db-update-option' in self._tool_conf:
                        self._tool_conf.pop('db-update-option')
        
    def _get_build_artifacts(self, build_summary_obj, results_root_dir):
        '''yeilds dictionary objects that has all the information to run
        a swa tool'''

        archives = set()
        new_build_artifacts = dict()

        def get_libs(filelist):
            return (filepath for filepath in filelist
                    if osp.isfile(filepath) and
                    osp.splitext(filepath)[1] in ['.jar', '.ear', '.war', '.zip',
                                                  '.sar', '.apk', '.tar', '.gz', '.tgz',
                                                  '.bz2', '.tbz2'])

        for build_artifacts in \
                build_summary_obj.get_build_artifacts(*self._tool_conf['tool-target-artifacts'].split()):

            if 'auxclasspath' in build_artifacts:
                archives.update(get_libs(build_artifacts['auxclasspath']))

            if 'classpath' in build_artifacts:
                archives.update(get_libs(build_artifacts['classpath']))

            if 'apkfile' in build_artifacts:
                archives.update(get_libs(build_artifacts['apkfile']))

        if archives:
            new_build_artifacts['build-artifact-id'] = '1'
            new_build_artifacts['auxclasspath'] = list(archives)
            new_build_artifacts['assessment-report'] = osp.join(results_root_dir,
                                                                self._tool_conf['assessment-report-template'].format(new_build_artifacts['build-artifact-id']))
            new_build_artifacts['package-name-version'] = build_artifacts['package-name-version']

            yield new_build_artifacts
        else:
            raise JavaBuildArtifactsError("No package dependencies (.jar files) or .apk files found for analysis.")


class Jtest10(SwaTool):

    DATA_JSON_TEMPLATE = {
              "name": "",
              "location": "",
              "type": "classpath_project",
              "build_id": "10.3.2.20170508-20170519-0926",
              "schema_version": "1.1",
              "testoutcomes": [
                  {
                      "type": "junit",
                      "files": []
                  }
              ],
              "compilations": [
                  {
                      "id": "defaultCompile",
                      "sourcepath": [],
                      "includes": [],
                      "excludes": [],
                      "tests": [],
                      "binarypath": [],
                      "classpath": [],
                      "bootpath": [],
                      "encoding": "utf-8",
                      #"sourcelevel": "",
                  }
              ]
        }

    def __init__(self, input_root_dir, tool_root_dir):
        SwaTool.__init__(self, input_root_dir, tool_root_dir)

    ''' Jtest10 requires jar files in JAVA_HOME/jar'''
    def _get_java_home_jars(self):
        
        if 'JAVA_HOME' in os.environ:
            return glob.glob(osp.join(os.environ['JAVA_HOME'],
                                      'jre/lib/*.jar'))
            
        return list()
    
    def _get_build_artifacts(self, build_summary_obj, results_root_dir):

        for build_artifacts in \
                build_summary_obj.get_build_artifacts(*self._tool_conf['tool-target-artifacts'].split()):

            data_json = copy.deepcopy(Jtest10.DATA_JSON_TEMPLATE)
            data_json['name'] = osp.basename(build_summary_obj.get_pkg_dir())
            data_json['location'] = build_summary_obj.get_pkg_dir()
            data_json['compilations'][0]['bootpath'] = self._get_java_home_jars()
            
            if 'srcdir' in build_artifacts:
                data_json['compilations'][0]['sourcepath'] = build_artifacts['srcdir']

            if 'sourcepath' in build_artifacts:
                data_json['compilations'][0]['sourcepath'].extend(build_artifacts['sourcepath'])
            
            # if 'include' in build_artifacts:
            #    data_json['compilations'][0]['includes'] = build_artifacts['include']
            
            # if 'exclude' in build_artifacts:
            #    data_json['compilations'][0]['excludes'] = build_artifacts['exclude']
            
            if 'auxclasspath' in build_artifacts:
                data_json['compilations'][0]['classpath'] = build_artifacts['auxclasspath']
            
            if 'bootclasspath' in build_artifacts:
                data_json['compilations'][0]['bootpath'].extend(build_artifacts['bootclasspath'])
            
            if 'encoding' in build_artifacts:
                data_json['compilations'][0]['encoding'] = build_artifacts['encoding']
            
            if 'source' in build_artifacts:
                data_json['compilations'][0]['sourcelevel'] = build_artifacts['source']

            data_json_file = osp.join(results_root_dir,
                                      '{0}.data.json'.format(build_artifacts['build-artifact-id']))
            with open(data_json_file, 'w') as fp:
                json.dump(data_json, fp)

            src_file_list_file = osp.join(results_root_dir,
                                          'files{0}.lst'.format(build_artifacts['build-artifact-id']))
            with open(src_file_list_file, 'w') as fp:
                fp.writelines(['{0}\n'.format(osp.relpath(_file,
                                                          osp.dirname(data_json['location'])))
                              for _file in build_artifacts['srcfile']])

            new_build_artifacts = dict()
            new_build_artifacts['build-artifact-id'] = build_artifacts['build-artifact-id']
            new_build_artifacts['data-json-file'] = data_json_file
            new_build_artifacts['src-file-lst'] = src_file_list_file
            new_build_artifacts['results-root-dir'] = results_root_dir
            #new_build_artifacts['assessment-report'] = osp.join(results_root_dir,
            #                                               self._tool_conf['assessment-report-template'].format(build_artifacts['build-artifact-id']))
            new_build_artifacts['results-dir'] = osp.join(results_root_dir,
                                                          'report{0}'.format(build_artifacts['build-artifact-id']))

            new_build_artifacts['assessment-report'] = osp.join(new_build_artifacts['results-dir'],
                                                                'report.xml')

            yield new_build_artifacts

    def _get_report0(self, results_root_dir, report, outfile):
        '''Report passed as an argument is old report path
        This method has to be overridden for AppHealthCheck
        Arguments: results_root_dir, report, outfile
        '''
        if osp.isfile(osp.join(results_root_dir, 'report.xml')):
            shutil.move(osp.join(results_root_dir, 'report.xml'), report)

        return report


def assess(input_root_dir,
           output_root_dir,
           tool_root_dir,
           results_root_dir,
           build_summary_file):

    tool_conf_file = osp.join(input_root_dir, SwaTool.TOOL_DOT_CONF)
    tool_conf = confreader.read_conf_into_dict(tool_conf_file)

    swatool = None

    if tool_conf['tool-type'] in ['findbugs', 'spotbugs']:
        swatool = Findbugs(input_root_dir, tool_root_dir)
    elif tool_conf['tool-type'] == 'ps-jtest':
        if tool_conf['tool-version'].startswith('10'):
            swatool = Jtest10(input_root_dir, tool_root_dir)
        else:
            swatool = Jtest(input_root_dir, tool_root_dir)

    elif tool_conf['tool-type'] == 'error-prone':
        swatool = Errorprone(input_root_dir, tool_root_dir)
    elif tool_conf['tool-type'] == 'lizard':
        swatool = Lizard(input_root_dir, tool_root_dir)
    elif tool_conf['tool-type'] == 'sonatype-ahc':
        swatool = AppHealthCheck(input_root_dir, tool_root_dir)
    elif tool_conf['tool-type'] == 'dependency-check':
        swatool = OwaspDependencyCheck(input_root_dir, tool_root_dir)
    else:
        swatool = JavaSwaTool(input_root_dir, tool_root_dir)

    try:
        with LogTaskStatus('assess') as status_dot_out:

            try:
                swatool.assess(build_summary_file, results_root_dir)
                swatool.post_assess(results_root_dir)
                
                exit_code = 1 if swatool.failed else 0
                assessment_summary_file = swatool.summary_file

                if exit_code != 0 and \
                   tool_conf['tool-type'] in ['error-prone', 'android-lint']:
                    if tool_conf['tool-type'] == 'error-prone':
                        if swatool.error_msgs:
                            LogTaskStatus.log_task('tool-package-compatibility',
                                                   exit_code,
                                                   'Java language version',
                                                   swatool.error_msgs)
                    elif tool_conf['tool-type'] == 'android-lint':
                        LogTaskStatus.log_task('tool-package-compatibility',
                                               exit_code,
                                               'android+maven',
                                               swatool.error_msgs)
                    swatool.error_msgs = None

                status_dot_out.update_task_status(exit_code,
                                                  'pass: {0}, fail: {1}'.format(swatool.passed,
                                                                                swatool.failed),
                                                  swatool.error_msgs)

            except JavaBuildArtifactsError as err:
                status_dot_out.skip_task('no files')
                exit_code = 0
                assessment_summary_file = osp.join(results_root_dir, 'assessment_summary.xml')

    except (JavaInvalidBuildError,
            JavaBuildSummaryError) as err:
        logging.exception(err)
        exit_code = 1
        assessment_summary_file = None

    finally:
        # if the assess throws an error, exit_code is NOT set
        # and this fails.   Need to set exit_code to failed .. see 99 above
        results_conf = dict()
        # if the assess throws an error, exit_code is NOT set
        # and this fails.   Need to set exit_code to failed .. see 99 above
        results_conf['exit-code'] = str(exit_code)

        if assessment_summary_file and osp.isfile(assessment_summary_file):
            results_conf['assessment-summary-file'] = osp.basename(assessment_summary_file)

            with LogTaskStatus('results-archive'):
                results_archive = shutil.make_archive(osp.join(output_root_dir, 'results'),
                                                      'gztar',
                                                      osp.dirname(results_root_dir),
                                                      osp.basename(results_root_dir))

                results_conf['results-archive'] = osp.basename(results_archive)
                results_conf['results-dir'] = osp.basename(results_root_dir)

                if isinstance(swatool, AppHealthCheck) and exit_code == 0:
                    results_conf['ahc-results-archive'] = swatool.ahc_results_archive
                    results_conf['ahc-results-file'] = swatool.ahc_results_file
                    
                utillib.write_to_file(osp.join(output_root_dir, 'results.conf'), results_conf)

    return (exit_code, assessment_summary_file)
