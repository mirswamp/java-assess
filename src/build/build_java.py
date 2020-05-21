import os.path as osp
import os
import re
import glob
import xml.etree.ElementTree as ET
import logging
import shutil
from abc import ABCMeta

from .. import confreader
from .. import utillib
from . import nobuild
from .nobuild import CompilationFailedError
from .nobuild import NoSourceFilesFoundError
from .nobuild import NoBuildHelperError
from ..logger import LogTaskStatus
from ..utillib import UnpackArchiveError
from ..utillib import NotADirectoryException
from ..utillib import FileNotFoundException
from ..utillib import PermissionException
from .. import gencmd


class InvalidBuildSystem(NotImplementedError):
    
    def __init__(self, build_sys):
        NotImplementedError.__init__(self)
        self.build_sys = build_sys

    def __str__(self):
        return "Build system '{0}' not supported".format(self.build_sys)


class InvalidFilesetError(Exception):

    def __init__(self, fileset):
        Exception.__init__(self)
        self.fileset = fileset
        self.errno = 6

    def __str__(self):
        return "Files not found: '{0}'".format(self.fileset)


class CommandFailedError(Exception):

    def __init__(self, command, exit_code, build_summary_file, outfile, errfile):
        Exception.__init__(self)
        self.command = ' '.join(command) if isinstance(command, list) else command
        self.errno = exit_code
        self.build_summary_file = build_summary_file
        self.outfile = outfile
        self.errfile = errfile

    def __str__(self):

        disp_str = "Command '{0}' failed with exit-code '{1}'.".format(self.command, self.errno)

        if self.outfile and self.errfile:
            disp_str += "\nSee "

            if self.outfile:
                disp_str += "'{0}'".format(self.outfile)

                if self.errfile:
                    disp_str += ", "

            if self.errfile:
                disp_str += "'{0}'".format(self.errfile)

            disp_str += " for errors"

        return disp_str


class BuildSummary(metaclass=ABCMeta):

    FILENAME = 'build_summary.xml'

    @classmethod
    def _add(cls, parent, tag, text=None):
        elem = ET.SubElement(parent, tag)
        if text:
            elem.text = text
        return elem

    def __init__(self, build_root_dir, pkg_root_dir, pkg_conf):

        self._build_root_dir = build_root_dir
        self._root = ET.Element('build-summary')

        pkg_conf_xml = BuildSummary._add(self._root, 'package-conf')

        for key in pkg_conf.keys():
            BuildSummary._add(pkg_conf_xml, key, pkg_conf[key])

        BuildSummary._add(self._root, 'build-root-dir', build_root_dir)
        BuildSummary._add(self._root, 'package-root-dir', pkg_root_dir)
        BuildSummary._add(self._root, 'platform', utillib.platform())
        # TODO: BuildSummary._add(self._root, 'java-assess-version', )
        BuildSummary._add(self._root, 'uuid', utillib.get_uuid())
        # TODO: BuildSummary._add(self._root, 'start-ts', )
        # TODO: BuildSummary._add(self._root, 'end-ts', )
        BuildSummary._add(self._root, 'build-fw', 'java-assess')
        BuildSummary._add(self._root, 'build-fw-version', utillib.get_framework_version())

    def __enter__(self):
        return self

    def __exit__(self, exception_type, value, traceback):
        if value:
            logging.exception(value)

        tree = ET.ElementTree(self._root)
        build_summary_file = osp.join(self._build_root_dir, BuildSummary.FILENAME)
        tree.write(build_summary_file, encoding='UTF-8', xml_declaration=True)

    def add_command(self, tag, executable, args,
                    exit_code, environ, working_dir,
                    stdout_file, stderr_file):

        cmd_root_xml = BuildSummary._add(self._root, tag)

        BuildSummary._add(cmd_root_xml, 'cwd', working_dir)
        environ_xml = BuildSummary._add(cmd_root_xml, 'environment')
        for _env in environ.keys():
            BuildSummary._add(environ_xml, 'env',
                              '{0}={1}'.format(_env, environ[_env]))

        BuildSummary._add(cmd_root_xml, 'executable', executable)
        args_xml = BuildSummary._add(cmd_root_xml, 'args')
        BuildSummary._add(args_xml, 'arg', executable)
        for _arg in args:
            BuildSummary._add(args_xml, 'arg', _arg)

        BuildSummary._add(cmd_root_xml, 'exit-code', str(exit_code))
        BuildSummary._add(cmd_root_xml, 'stdout-file', stdout_file)
        BuildSummary._add(cmd_root_xml, 'stderr-file', stderr_file)

    def add_exit_code(self, exit_code):
        if exit_code >= 0:
            BuildSummary._add(self._root, 'exit-code', str(exit_code))
        elif exit_code < 0:
            BuildSummary._add(self._root, 'exit-signal', str(abs(exit_code)))


class BuildSummaryJavaByteCode(BuildSummary):

    def __init__(self, build_root_dir, pkg_root_dir, pkg_conf):
        BuildSummary.__init__(self, build_root_dir, pkg_root_dir, pkg_conf)

    def _add_fileset(self, parent, tag, fileset):

        if fileset:
            elem = ET.SubElement(parent, tag)
            for _file in fileset:
                BuildSummary._add(elem, 'file',
                                  osp.relpath(_file, self._build_root_dir))

    def add_build_artifacts(self, classpath, auxclasspath, srcdir):

        build_artifacts_xml = BuildSummary._add(self._root, 'build-artifacts')
        bytecode_xml = BuildSummary._add(build_artifacts_xml, 'java-bytecode')

        bytecode_xml.set("id", "1")

        self._add_fileset(bytecode_xml, 'classpath', classpath)
        self._add_fileset(bytecode_xml, 'auxclasspath', auxclasspath)
        self._add_fileset(bytecode_xml, 'srcdir', srcdir)


class BuildSummaryJavaSrc(BuildSummary):

    def __init__(self, build_root_dir, pkg_root_dir, pkg_conf):
        BuildSummary.__init__(self, build_root_dir, pkg_root_dir, pkg_conf)

    def add_nobuild_summary(self, exit_code, nobuild_summar_xmlfile):

        if exit_code > 0:
            self.add_exit_code(exit_code)
        elif exit_code < 0:
            self.add_exit_code(exit_code)

        if nobuild_summar_xmlfile:
            BuildSummary._add(self._root, 'nobuild-summary-file',
                              nobuild_summar_xmlfile)

    def add_build_artifacts(self,
                            build_artifacts_file,
                            build_root_dir):

        if not osp.isfile(build_artifacts_file):
            return

        build_artifacts = ET.parse(build_artifacts_file).getroot()
        _id = 1

        for artifacts in build_artifacts:

            if (artifacts.tag in ['java-compile', 'java-bytecode']) and \
               ('id' in artifacts.attrib):
                artifacts.attrib['id'] = str(_id)
                _id += 1

                for fileset in artifacts:
                    if fileset.tag in ['srcdir', 'srcfile',
                                       'destdir', 'classpath',
                                       'bootclasspath', 'sourcepath']:

                        for _file in fileset:
                            if _file.text.startswith(build_root_dir):
                                _file.text = osp.relpath(_file.text, build_root_dir)

        self._root.append(build_artifacts)


class BuildSummaryJavaAndroidApk(BuildSummary):

    def __init__(self, build_root_dir, pkg_root_dir, pkg_conf):
        BuildSummary.__init__(self, build_root_dir, pkg_root_dir, pkg_conf)

    def _add_fileset(self, parent, tag, fileset):

        if fileset:
            elem = ET.SubElement(parent, tag)
            for _file in fileset:
                BuildSummary._add(elem, 'file',
                                  osp.relpath(_file, self._build_root_dir))

    def add_build_artifacts(self, filepath):

        build_artifacts_xml = BuildSummary._add(self._root, 'build-artifacts')
        bytecode_xml = BuildSummary._add(build_artifacts_xml, 'java-android-apk')

        bytecode_xml.set("id", "1")
        self._add_fileset(bytecode_xml, 'apkfile', [filepath])


class JavaPkg(metaclass=ABCMeta):

    PKG_ROOT_DIR = "pkg1"

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):

        if isinstance(pkg_conf, dict):
            self._pkg_conf = pkg_conf
        else:
            self._pkg_conf = confreader.read_conf_into_dict(pkg_conf)

        self._build_conf_extras = dict()

        logging.info('PACKAGE CONF: %s', self._pkg_conf)

        with LogTaskStatus('package-unarchive'):
            pkg_archive = osp.join(input_root_dir, pkg_conf['package-archive'])
            pkg_root_dir = osp.join(build_root_dir, JavaPkg.PKG_ROOT_DIR)
            status = utillib.unpack_archive(pkg_archive, pkg_root_dir, True)

            if status != 0:
                raise UnpackArchiveError(osp.basename(pkg_archive))

            pkg_dir = osp.join(pkg_root_dir, pkg_conf['package-dir'])

            if not osp.isdir(pkg_dir):
                LogTaskStatus.log_task('chdir-package-dir', 1, None,
                                       "Directory '{0}' not found".format(osp.basename(pkg_dir)))
                raise NotADirectoryException()

            self._pkg_dir = pkg_dir

    def build(self, build_root_dir):
        # TODO: make this an abstract method
        raise NotImplementedError()

    ## return string of common java options for this build
    ## The indivual class willput the java options where they need to
    ## for the type of build sytem being used.
    ## The version of java used needs to be known, because Java has changed
    ## options through its lifetime for the "same" things.
    ## XXX This is not perfect, but by putting the non-perfect stuff
    ## in one place, we can work on making it better in the future.

    ## THe issue here is that java chooses bad default sizes for many of these
    ## things.  In the SWAMP, we want a java thing to have access to most
    ## of a VM's resources, so that it can complete it's task.  Without
    ## this, you can create a large resource intensive machine which is
    ## incapable of running java compilations or assessment tools, because
    ## java is limiting the resources available to far less than the
    ## VM has been assigned.

    ## The commented-out code in this has been copied from the 3 different
    ## versions in java-assess, so that what it used to be is documented 
    ## here for reference.
    ## The documentation here also explains what is being changed, and why
    ## it is being changed to help out modifcations in the future.

    ## XXX python inheritance and static methods are stupid.
    def common_java_opts( self, java_ver ):
        env_str = ''
        if utillib.get_cpu_type() == 64:
            # new_env['MAVEN_OPTS'] = "-Xmx2048m -XX:MaxPermSize=1024m -Xms512m"
            # new_env['MAVEN_OPTS'] = '-Xmx{0}M -Xss128M -XX:MaxPermSize=2048M -XX:+CMSClassUnloadingEnabled -XX:+UseConcMarkSweepGC'.format(two_thrids_sys_memory)
            # new_env['MAVEN_OPTS'] = '-Xmx2048M -Xss128M -XX:MaxPermSize=2048M -XX:+CMSClassUnloadingEnabled -XX:+UseConcMarkSweepGC'

            ## This is sub-optimal; for now we will keep on guessing
            ## this amount.  As memory grows larger, you actually want
            ## to use more and more of it for the assessment, and just keep
            ## a small amount for the system and its buffers.

            ## returns size in MB
            sys_mem = utillib.sys_mem_size() 
            logging.info("sys_mem_size == %d", sys_mem);


            # This example is why the ratio system falls down with
            # large memory machines.  The model is wrong:
            #   MEM      JAVA     SYS      WHAT'S-UP
            #  -----    -------  -------   ---------
            #   2 GB ->  1.3 GB   0.7 GB   OK?
            #   3 GB ->  2   GB   1   GB   OK?
            #   6 GB ->  4   GB   2   GB   SO-SO
            #  60 GB -> 40   GB  20   GB   ARE-YOU-KIDDING
            # To fix it, some % of memory should be left for the system,
            # in some log fashion (to allow for page tables & buffer cache)
            # and then most of the rest of the system given to the app.
            # As long as the memory allocation pool isn't pre-allocated,
            # it just limits the size of java, not sets the szie.

            ## cheap seats version 
            #   2 GB ->  1.3 GB   0.7 GB
            #   3 GB ->  2   GB   1   GB
            #   4 GB ->  3.4 GB   0.6 GB
            #   6 GB ->  5   GB   1   GB
            #   8 GB ->  7.1 GB   0.9 GB
            #  10 GB ->  9.2 GB   0.8 GB   SO-SO (should be scaling system)
            #  30 GB -> 27   GB   2.7 GB
            #  60 GB -> 55   GB   5   GB   BETTER
            #  90 GB -> 83.7 GB   6.3 GB

            ## XXX may want to choose mem_size "NEAR" the thresholds since
            ## the system steals some memory and we don't get sizing as
            ## aggressive as this looks.  However, we are into swap as
            ## it is, so these numbers aren't totally bad.


            if (sys_mem >= 30 * 1024):
                memory_for_java = int(sys_mem * 10 / 11)
            elif (sys_mem >= 10 * 1024):
                memory_for_java = int(sys_mem * 9 / 10)
            elif (sys_mem >= 8 * 1024):
                memory_for_java = int(sys_mem * 7 / 8)
            elif (sys_mem >= 4 * 1024):
                memory_for_java = int(sys_mem * 5 / 6)
            elif (sys_mem >= 3 * 1024):
                memory_for_java = int(sys_mem * 3 / 4)
            else:
                memory_for_java = int(sys_mem * 2 / 3)

            ## This controls the max amount of "long lived memory" in
            ## the java process.   This is NOT the memory pool, but rather
            ## the space available for long term items which will no longer
            ## be regulraily garbage collected.
            ## Think of it as 'static data size" for long term java apps
            ##
            ## java <= 7 has MaxPermSize        -- which is usually too low
            ## java >= 8 has MaxMetaspaceSize   -- which is unlimited, but 
            ##                                  recommendation is to make
            ##                                  it limited for perf. reasons.
            ## turn it off for now, it is broken
            ## XXX the 2048 should be sized to the machine; it is complex,
            ## and prevents tools that need a lot of memory from working
            if java_ver >= 8:
               extra = '-XX:MaxMetaspaceSize=2048M'
            else:
               extra = '-XX:MaxPermSize=2048M'

            ## -Xmx####S == maximum size of memory pool
            xmx = '-Xmx{0}m'.format(memory_for_java)
            
            ## XXX see notes in ant about GC options not good for servers
            ## basically server grade machines don't want that kind of GC
            ## going on, because it causes too much memory thrashing
            ## and GCs way too early.   I will need to re-find the reference
            ## for it.  Some idea of why we are doing these things should
            ## be documented here.

            env_str += ' ' + xmx
            env_str += ' ' + extra

            # The default 64bit java thread stack size is 512k.
            # That was small for some builds, I suppose.
            # Our VMs are typically 4GB in size, so this allows for
            # only 32 threads in a 4GB machine!
            env_str += ' ' + '-Xss128m'               ## thread stack size

        elif utillib.get_cpu_type() == 32:
            ## seperate calculation since 32 bit is a different beast
            ## same for now until I think about this.
            ## 3/4 memory allows 3GB on a 4GB machine, and 768K on a 1M machine
            sys_mem = utillib.sys_mem_size() 
            logging.info("sys_mem_size == %d", sys_mem);
            ## 2^32 / 2^8 / 2^8 == 
            ## still doing 3/4 of memory ... 3/4 process address space!
            ## need to save room for java long term and stack.
            if (sys_mem > 4 * 1024):
                sys_mem = 4 * 1024
                logging.info("sys_mem_size LIMIT 32 bit sys to %d", sys_mem);
            ## XXX linux uses one address space for user+kernel, unlike BSD
            ## solaris is like the BSD model, where the proc has full
            ## address space.
            ## We are only running SWAMP on linux, so need
            ## to live with only having 1/2 of the address space.
            ## Actually, we get 3 GB of 4 GB, but we'll do 2/4 for now,
            ## since that doubles what java was previously doing on 32 bit!
            if (sys_mem > 3 * 1024):
                sys_mem = 3 * 1024
                logging.info("sys_mem_size LIMIT 32 bit proc to %d", sys_mem);

            ## However, for small memory machines, may just want to let
            ## Java do it's default limits (too small for swamp, though)

            memory_for_java = int(sys_mem * 3 / 4)

            extra = ""

            xmx = '-Xmx{0}m'.format(memory_for_java)

            ## Xms increased from default because most of the tools
            ## need a lot and it made performance better ??

            env_str += ' ' + xmx              ## max size memory alloc pool
            env_str += ' ' + "-Xms512m"       ## initial size memory alloc pool

            # OK, try doing this on 32 bit VMs as well
            # Since java on linux onnly has 3GB max adrress space,
            # Our VMs are typically 4GB in size, so this allows for
            # only 24 threads in a 4GB machine!
            # XXX half the size on 32 bit, see how that works!?
            # env_str += ' ' + '-Xss128m'       ## 64 thread stack size
            # OK, so the default is 320k for 32 bit, this is 6x as large
            # but still allows for many stacks
            # THis was a big failure issue on scientific-32
            # For now, don't touch this, too memory sensitive on 32 bit
            # ... which begs why is it so large on 64 bit???
            # env_str += ' ' + '-Xss2m'         ## 32 thread stack size

        # Our VMs are categorized as server class machines by java.
        # That uses the "parallel mark sweep collector'.  UNFORTUNATELY,
        # or FORTUNATELY, that collector will error out and complain if
        # too much time is spent in garbage collection -- which means that
        # the heap size parameters are set wrongly for the application.
        # We could use another collector, but there is another issue
        # intertwined here ...
        # Yet another inter-twined issue is that if we gave more memory
        # to java to use, the garbage collection type and need to unload
        # classes may not be needed....

        # As a work-around, another collector is used to avoid the
        # GC timeout errors.  The flip side is that we are not getting any
        # feedback on POORLY CONFIGURED ASSESSMENTs and perhaps spending a
        # lot of resources (wall-time, memory and CPU) running assessments
        # which should be reconfigured to run more efficiently.
        #
        # This is required to support CMS Class Unloading.   It has the
        # affect of helping out GC as mentioned above.
        env_str += ' ' + '-XX:+UseConcMarkSweepGC'

        # Groovy (in gradle) causes problems because it generates on the fly
        # a huge number of classes used only for setup.  Even though they
        # are never used again they take up memory and resources which could
        # be used by an actual build.  This options tells java that such
        # classes can be unloaded from the image memory, instead of hung onto
        # for forever.
        # CMS == Concentric Mark Sweep -- this configures the CMS collector!
        env_str += ' ' + '-XX:+CMSClassUnloadingEnabled'

        logging.info('java_opts java_ver %d  env %s', java_ver, env_str)
        
        return env_str

    ## Determine the actual java version used for a java build
    ## This is a combination of package and environment settings
    def common_java_ver_num( self ):

        ## OK, changed to key this section on android_home to verify
        ## we are on android, otw it kicks in all the time :-(
        android_java_ver = ''
        if os.getenv('ANDROID_HOME', '') != '':
            android_java_ver = os.getenv('SWAMP_ANDROID_JAVA_VER', '')
            if android_java_ver == '':
                ## if it is not set, fall back on the old behavior
                ## for now, ajh means java8; later we'll propogate version info
                ajh = os.getenv('ANDROID_JAVA_HOME', '')
                if ajh != '':
                    android_java_ver = 'java-8'
                else:
                    android_java_ver = 'java-7'

        ## XXX this should be centralized; copied here & in maven
        java_ver = self._pkg_conf.get('package-language-version', 'java-7').lower()

        logging.info('package java_ver %s', java_ver)
        logging.info("android_java_ver '%s'", android_java_ver)

        ## take care of android-specific behavior
        if android_java_ver != '':
            java_ver = android_java_ver

        logging.info("result  java_ver '%s'", java_ver)


        java_ver = java_ver.split('-')[-1]
        java_ver_num = int(java_ver)
        logging.info('get_env java_ver %d', java_ver_num)

        return java_ver_num

    def add_build_conf_attr(self, name, value):
        self._build_conf_extras[name] = value

    def get_build_conf_extras(self):
        return self._build_conf_extras




class JavaByteCodePkg(JavaPkg):

    def _get_fileset(self, fileset_str):
        found = set()
        notfound = set()

        for _str in fileset_str.split(':'):
            _str = _str.strip()
            if _str:
                if '*' in _str:
                    _fileset = glob.glob(osp.join(self._pkg_dir, _str))

                    if _fileset:
                        found.update(_fileset)
                    else:
                        notfound.update(_str)
                else:
                    _file = osp.join(self._pkg_dir, _str)
                    if osp.exists(_file):
                        found.add(_file)
                    else:
                        notfound.add(_str)
        return (found, notfound)

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

        with LogTaskStatus('validate-package'):

            classpath, notfound = self._get_fileset(self._pkg_conf['package-classpath'])

            if notfound:
                raise InvalidFilesetError(notfound)
            elif not classpath:
                raise InvalidFilesetError(classpath)
            else:
                self._classpath = classpath

            if 'package-auxclasspath' in self._pkg_conf:
                auxclasspath, notfound = self._get_fileset(self._pkg_conf['package-auxclasspath'])

                if notfound:
                    logging.warning('Invalid Aux class path entries: %s', notfound)
                self._auxclasspath = auxclasspath
            else:
                self._auxclasspath = set()

            if 'package-srcdir' in self._pkg_conf:
                srcdir, notfound = self._get_fileset(self._pkg_conf['package-srcdir'])
                notfound.update(f for f in srcdir if not osp.isdir(f))
                srcdir.difference(f for f in srcdir if not osp.isdir(f))

                if notfound:
                    logging.warning('Invalid Source path entries: %s', notfound)
                self._srcdir = srcdir
            else:
                self._srcdir = set()

    def build(self, build_root_dir):

        with LogTaskStatus('build') as status_dot_out:
            status_dot_out.skip_task()

        with BuildSummaryJavaByteCode(build_root_dir,
                                      JavaPkg.PKG_ROOT_DIR,
                                      self._pkg_conf) as build_summary:

            build_summary.add_build_artifacts(self._classpath,
                                              self._auxclasspath,
                                              self._srcdir)

            build_summary.add_exit_code(0)

            return (0, BuildSummary.FILENAME)


# TODO: This should also be an abstract class
class JavaSrcPkg(JavaPkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)
        self._build_conf = None

    def _setup(self, build_root_dir):
        raise NotImplementedError()

    def get_env(self, pwd):
        new_env = dict(os.environ)
        if 'PWD' in new_env:
            new_env['PWD'] = pwd
        return new_env

    def _configure(self, build_root_dir, build_summary):

        with LogTaskStatus('configure') as status_dot_out:

            if 'config-cmd' not in self._pkg_conf:
                status_dot_out.skip_task()
            else:
                pkg_config_dir = osp.normpath(osp.join(build_root_dir,
                                                       JavaPkg.PKG_ROOT_DIR,
                                                       self._pkg_conf['package-dir'],
                                                       self._pkg_conf.get('config-dir', '.')))
                
                if not osp.isdir(pkg_config_dir):
                    LogTaskStatus.log_task('chdir-config-dir', 1, None,
                                           "Directory '{0}' not found".format(osp.basename(pkg_config_dir)))
                    raise NotADirectoryException()
 
                config_cmd = self._pkg_conf['config-cmd']
                config_opt = self._pkg_conf.get('config-opt', '')
                if len(config_opt):
                    config_cmd = config_cmd + ' ' + config_opt

                logging.info('CONFIGURE COMMAND: %s', config_cmd)
                logging.info('CONFIGURE WORKING DIR: %s', pkg_config_dir)

                config_stdout = 'config_stdout.out'
                config_stderr = 'config_stderr.out'
                outfile = osp.join(build_root_dir, config_stdout)
                errfile = osp.join(build_root_dir, config_stderr)

                self.add_build_conf_attr('config-stdout-file', config_stdout)
                self.add_build_conf_attr('config-stderr-file', config_stderr)

                exit_code, environ = utillib.run_cmd(config_cmd,
                                                     outfile=outfile,
                                                     errfile=errfile,
                                                     cwd=pkg_config_dir,
                                                     env=self.get_env(pkg_config_dir))

                logging.info('CONFIGURE ERROR CODE: %d', exit_code)
                logging.info('CONFIGURE ENVIRONMENT: %s', environ)

                # the command doesn't have arguments, it is a "magic cookie"
                build_summary.add_command('configure-command',
                                          config_cmd, [],
                                          exit_code, environ,
                                          osp.relpath(pkg_config_dir, build_root_dir),
                                          osp.relpath(outfile, build_root_dir),
                                          osp.relpath(errfile, build_root_dir))

                if exit_code != 0:
                    build_summary.add_exit_code(exit_code)
                    raise CommandFailedError(config_cmd, exit_code,
                                             BuildSummary.FILENAME,
                                             osp.relpath(outfile, build_root_dir),
                                             osp.relpath(errfile, build_root_dir))

    def _get_dependency_resolution_errors(self,
                                          build_stdout_file,
                                          build_stderr_file):
        return None

    def _build(self, build_root_dir, build_summary):

        self._setup(build_root_dir)

        # 2.1.8, not required
        # if 'build-opt' in self._build_conf:
        #    self._build_conf['build-opt'] = self._build_conf['build-opt'].split()

        if 'build-target' in self._build_conf:
            self._build_conf['build-target'] = self._build_conf['build-target'].split()


        build_stdout = 'build_stdout.out'
        build_stderr = 'build_stderr.out'

        self._build_conf['stdout-file'] = osp.join(build_root_dir, build_stdout)
        self._build_conf['stderr-file'] = osp.join(build_root_dir, build_stderr)
        self.add_build_conf_attr('build-stdout-file', build_stdout)
        self.add_build_conf_attr('build-stderr-file', build_stderr)

        if ('build-monitor-output-file' in self._build_conf) and \
           osp.isfile(self._build_conf['build-monitor-output-file']):
            os.remove(self._build_conf['build-monitor-output-file'])

        with LogTaskStatus('build'):

            pkg_build_dir = osp.normpath(osp.join(build_root_dir,
                                                  JavaPkg.PKG_ROOT_DIR,
                                                  self._build_conf['package-dir'],
                                                  self._build_conf.get('build-dir', '.')))

            if not osp.isdir(pkg_build_dir):
                LogTaskStatus.log_task('chdir-build-dir', 1, None,
                                       "Directory '{0}' not found".format(osp.basename(pkg_build_dir)))
                raise NotADirectoryException()
 
            build_cmd = gencmd.gencmd(self._build_conf['cmd-invoke-file'],
                                      self._build_conf)

            logging.info('BUILD CWD %s', pkg_build_dir)
            logging.info('BUILD ENVIRONMENT %s', self.get_env(pkg_build_dir))
            logging.info('BUILD COMMAND %s', build_cmd)

            (exit_code, environ) = utillib.run_cmd(' '.join(build_cmd),
                                                   cwd=pkg_build_dir,
                                                   outfile=self._build_conf['stdout-file'],
                                                   errfile=self._build_conf['stderr-file'],
                                                   env=self.get_env(pkg_build_dir))

            logging.info('BUILD EXIT CODE %s', exit_code)
            build_summary.add_command('build-command', build_cmd[0],
                                      build_cmd[1:], exit_code, environ,
                                      osp.relpath(pkg_build_dir, build_root_dir),
                                      osp.relpath(self._build_conf['stdout-file'],
                                                  build_root_dir),
                                      osp.relpath(self._build_conf['stderr-file'],
                                                  build_root_dir))

            build_summary.add_exit_code(exit_code)

            if exit_code == 0:
                build_summary.add_build_artifacts(self._build_conf['build-monitor-output-file'],
                                                  build_root_dir)
                return (exit_code, BuildSummary.FILENAME)
            else:
                error_str = self._get_dependency_resolution_errors(self._build_conf['stdout-file'],
                                                                   self._build_conf['stderr-file'])
                if error_str:
                    LogTaskStatus.log_task('fetch-pkg-dependencies',
                                           exit_code,
                                           self._build_conf['build-sys'],
                                           error_str)

                raise CommandFailedError(build_cmd, exit_code,
                                         BuildSummary.FILENAME,
                                         osp.relpath(self._build_conf['stdout-file'],
                                                     build_root_dir),
                                         osp.relpath(self._build_conf['stderr-file'],
                                                     build_root_dir))

    def build(self, build_root_dir):

        with BuildSummaryJavaSrc(build_root_dir,
                                 JavaPkg.PKG_ROOT_DIR,
                                 self._pkg_conf) as build_summary:

            self._configure(build_root_dir, build_summary)
            return self._build(build_root_dir, build_summary)


class JavaMavenPkg(JavaSrcPkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaSrcPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

    @classmethod
    def _modify_build_target(cls, build_targets):

        maven_phases = ['clean', 'validate',
                        'initialize', 'generate-sources',
                        'process-sources', 'generate-resources',
                        'process-resources', 'compile',
                        'process-classes', 'generate-test-sources',
                        'process-test-sources', 'generate-test-resources',
                        'process-test-resources', 'test-compile',
                        'process-test-classes', 'test',
                        'prepare-package', 'package',
                        'pre-integration-test', 'integration-test',
                        'post-integration-test', 'verify',
                        'install', 'deploy']

        nbt = list()

        compile_flag = False
        test_compile_flag = False

        for target in build_targets.split():
            if target in maven_phases[maven_phases.index('compile'): maven_phases.index('test-compile')]:
                if compile_flag is False:
                    nbt.append('process-resources')
                    nbt.append('org.continuousassurance.swamp:swamp-maven-plugin:1.1:getCompile')
                    compile_flag = True
                nbt.append(target)

            elif target in maven_phases[maven_phases.index('test-compile'): maven_phases.index('deploy')]:
                if compile_flag is False:
                    nbt.append('process-resources')
                    nbt.append('org.continuousassurance.swamp:swamp-maven-plugin:1.1:getCompile')
                    compile_flag = True
                if test_compile_flag is False:
                    nbt.append('process-test-resources')
                    nbt.append('org.continuousassurance.swamp:swamp-maven-plugin:1.1:getTestCompile')
                    test_compile_flag = True
                nbt.append(target)
            else:
                nbt.append(target)

        return ' '.join(nbt)
        
    def _setup(self, build_root_dir):

        res_dir = os.getenv('SCRIPTS_DIR')

        self._build_conf = {
            'executable': 'mvn',
            'build-target': 'package',
            #'swamp-maven-plugin': 'org.continuousassurance.swamp:swamp-maven-plugin:1.1:get-build-artifacts',
            #'maven-settings-xml-file' : osp.join(res_dir, 'resources/settings.xml'),
            'usr-lib-dir': osp.join(build_root_dir, 'usr_lib_dir'),
            'cmd-invoke-file': osp.join(res_dir, 'resources/maven-invoke.txt'),
            'build-monitor-output-file': osp.join(build_root_dir, 'build_artifacts.xml'),
            #'compiler-debug-levels' : 'lines,vars,source',
            #'swamp-plugin-build-clean-property' : 'false'
            #'build-file' : 'pom.xml',
        }

        self._build_conf.update(self._pkg_conf)

        # Install swamp-maven-plugin
        install_cmd = [
            'mvn',
            '-Dhttps.protocols=TLSv1.2',
            '--batch-mode',
            '-DskipTests',
            '--quiet',
            #'-s', self._build_conf['maven-settings-xml-file'],
            'install'
        ]

        logging.info('MAVEN PLUGIN INSTALL CWD: %s',
                     osp.join(res_dir, 'build-monitors/swamp-maven-plugin'))

        logging.info('MAVEN PLUGIN INSTALL ENVIRONMENT: %s', os.environ)
        logging.info('MAVEN PLUGIN INSTALL COMMAND: %s', install_cmd)

        with LogTaskStatus('swamp-maven-plugin-install'):
            exit_code, _ = utillib.run_cmd(install_cmd,
                                           cwd=osp.join(res_dir, 'build-monitors/swamp-maven-plugin'))
            logging.info('MAVEN PLUGIN INSTALL EXIT CODE: %d', exit_code)

            if exit_code != 0:
                raise CommandFailedError(install_cmd, exit_code, None, None, None)
        
        # if len(self._build_conf['build-target'].split()) == 1:
        #     self._build_conf['swamp-plugin-build-target-property'] = self._build_conf['build-target']
        # else:
        #     for build_target in self._build_conf['build-target'].split():
        #         if build_target in maven_phases:
        #             self._build_conf['swamp-plugin-build-target-property'] = build_target
        #             break

        # if 'clean' in self._build_conf['build-target'].split():
        #     self._build_conf['swamp-plugin-build-clean-property'] = 'true'

        self._build_conf['build-target'] = JavaMavenPkg._modify_build_target(self._build_conf['build-target'])
        
    def get_env(self, pwd):
        new_env = super().get_env(pwd)

        ## which numeric version of java will this build use?
        java_ver_num = self.common_java_ver_num()

        ## set common java executions options
        new_env['MAVEN_OPTS'] = self.common_java_opts(java_ver_num)

        return new_env

    def _get_dependency_resolution_errors(self,
                                          build_stdout_file,
                                          build_stderr_file):

        regex = re.compile(r'^\[ERROR\] Failed to execute goal on project [^:]+: (?P<dependencies>Could not resolve dependencies for project .+)')

        error_str = list()
        with open(build_stdout_file) as fobj:
            for line in fobj:
                line = line.strip()
                m = regex.match(line)
                if m:
                    error_str.append(m.group('dependencies'))

        if error_str:
            return '\n'.join(error_str)


class JavaAndroidMavenPkg(JavaMavenPkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaMavenPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

    def _android_update(self, build_root_dir, build_summary):
        '''
        Android Update.
        Depends on environment variable SWAMP_ANDROID_MAVEN_SETUP'''

        with LogTaskStatus('android-update'):

            pkg_config_dir = osp.normpath(osp.join(build_root_dir,
                                                   JavaPkg.PKG_ROOT_DIR,
                                                   self._pkg_conf['package-dir'],
                                                   self._pkg_conf.get('config-dir', '.')))

            update_cmd = os.getenv('SWAMP_ANDROID_MAVEN_SETUP', '')

            if update_cmd == "":
                logging.info('SWAMP_ANDROID_MAVEN_SETUP environ not set')
                return

            # convert to list for run_cmd
            update_cmd = [update_cmd]

            if 'android-maven-plugin' in self._pkg_conf and \
                    (not self._pkg_conf['android-maven-plugin'].isspace()):

                update_cmd.extend(['--android-plugin', self._pkg_conf['android-maven-plugin']])

            if 'build-file' in self._pkg_conf and \
                    (not self._pkg_conf['build-file'].isspace()):
                update_cmd.extend(['--build-file', self._pkg_conf['build-file']])

            logging.info('ANDROID UPDATE COMMAND: %s', update_cmd)

            outfile = osp.join(build_root_dir, 'android_update_stdout.out')
            errfile = osp.join(build_root_dir, 'android_update_stderr.out')

            exit_code, environ = utillib.run_cmd(update_cmd,
                                                 outfile=outfile,
                                                 errfile=errfile,
                                                 cwd=pkg_config_dir)

            logging.info('ANDROID UPDATE ERROR CODE: %d', exit_code)
            logging.info('ANDROID UPDATE ENVIRONMENT: %s', environ)

            build_summary.add_command('android-update-command',
                                      update_cmd[0], update_cmd[1:],
                                      exit_code, environ,
                                      osp.relpath(pkg_config_dir, build_root_dir),
                                      osp.relpath(outfile, build_root_dir),
                                      osp.relpath(errfile, build_root_dir))

            if exit_code != 0:
                build_summary.add_exit_code(exit_code)
                raise CommandFailedError(update_cmd, exit_code,
                                         BuildSummary.FILENAME,
                                         osp.relpath(outfile, build_root_dir),
                                         osp.relpath(errfile, build_root_dir))

    def build(self, build_root_dir):

        with BuildSummaryJavaSrc(build_root_dir,
                                 JavaPkg.PKG_ROOT_DIR,
                                 self._pkg_conf) as build_summary:

            self._android_update(build_root_dir, build_summary)
            self._configure(build_root_dir, build_summary)
            return self._build(build_root_dir, build_summary)


class JavaGradlePkg(JavaSrcPkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaSrcPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

    def _setup(self, build_root_dir):

        res_dir = os.getenv('SCRIPTS_DIR')

        self._build_conf = {
            'executable': 'gradle',
            'build-monitor': osp.join(res_dir, 'build-monitors/swamp-gradle-listener/swamp.gradle'),
            'usr-lib-dir': osp.join(build_root_dir, 'usr_lib_dir'),
            'cmd-invoke-file': osp.join(res_dir, 'resources/gradle-invoke.txt'),
            'build-monitor-output-file': osp.join(build_root_dir, 'build_artifacts.xml'),
            'build-target': 'classes',
            #'build-file' : 'build.gradle',
        }

        # need to verify gradle wrapper available, die if not
        # package-root/gradlew
        if 'gradle-wrapper' in self._pkg_conf and \
           (self._pkg_conf['gradle-wrapper'].lower() == 'true' or
                self._pkg_conf['gradle-wrapper'].lower() == 'yes'):
            self._build_conf['executable'] = './gradlew'

        self._build_conf.update(self._pkg_conf)

    def get_env(self, pwd):
        new_env = super().get_env(pwd)

        # if GRADLE_HOME is already set, the caller setup the
        # environment -- leave it alone.
        ## We used to exit early here, now we just do this if it already
        ## isn't setup so we can pass options below
        ## XXX this is still wrong, if gradle is native.
        if 'GRADLE_HOME' not in new_env:
            # XXX  Only modify the environment if gradle is
            # included w/ java-assess;
            # Perhaps log a message if it wasn't and
            # and it isn't provided by the environment either
            # HOWEVER, a system-wide gradle install may/will exist,
            # so it is NOT an error, just a notice

            gradle_home = osp.join(new_env['SCRIPTS_DIR'], 'build-sys/gradle')
            if not os.path.isdir(gradle_home):
                return new_env

            new_env['GRADLE_HOME'] = gradle_home
            new_env['PATH'] = '{0}:{1}'.format(osp.join(gradle_home, 'bin'),
                                               new_env['PATH'])

        ## which numeric version of java will this build use?
        java_ver_num = self.common_java_ver_num()

        ## set common java executions options
        common_env = self.common_java_opts(java_ver_num)

        ## fix for maven central issues .. can't pass via command line
        maven_central_env = "-Dhttps.protocols=TLSv1.2"

        ## For the other build systems, this is passed on the command
        ## line.  However, for gradle, must use GRADLE_OPTS
        new_env['GRADLE_OPTS'] = common_env + " " + maven_central_env

        return new_env

    def _get_dependency_resolution_errors(self,
                                          build_stdout_file,
                                          build_stderr_file):

        regex = re.compile(r'Could not resolve all dependencies')
        dep_res_failure = False
        error_str = list()

        with open(build_stderr_file) as fobj:
            for line in fobj:
                line = line.strip()
                m = regex.search(line)
                if m:
                    dep_res_failure = True
                    break

            if dep_res_failure:
                regex = re.compile(r'> Could not (resolve|find) (?P<artifact>.+)')

                for line in fobj:
                    line = line.strip()
                    m = regex.search(line)
                    if m:
                        error_str.append(m.group('artifact'))
                        
        if error_str:
            return 'Could not resolve|find ' + ' '.join(error_str)


class JavaAndroidGradlePkg(JavaGradlePkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaGradlePkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

    def _android_gradle(self, build_root_dir, build_summary):
        '''
        Setup workspace for android Gradle.
        Check if VM is an android VM.'''

        # if gradle wrapper, need to offer 'gradle wrapper' to set it up

        with LogTaskStatus('android-update'):

            pkg_config_dir = osp.normpath(osp.join(build_root_dir,
                                                   JavaPkg.PKG_ROOT_DIR,
                                                   self._pkg_conf['package-dir'],
                                                   self._pkg_conf.get('config-dir', '.')))

            if os.getenv('ANDROID_HOME', "") == "":
                logging.info('ANDROID_HOME: missing: VM lacks android support')
                return

            # this is optional, not a failure
            update_cmd = os.getenv('SWAMP_ANDROID_GRADLE_SETUP', "")

            if update_cmd == "":
                logging.info('SWAMP_ANDROID_GRADLE_SETUP environ not set')
                return

            # don't know what options to pass yet, so just issue diagnositcs

    def _setup(self, build_root_dir):
        super()._setup(build_root_dir)
        # need to verify gradle wrapper available, die if not
        # package-root/gradlew
        if 'android-gradle-wrapper' in self._pkg_conf and \
           (self._pkg_conf['android-gradle-wrapper'].lower() == 'true' or
                self._pkg_conf['android-gradle-wrapper'].lower() == 'yes'):
            self._build_conf['executable'] = './gradlew'

    def build(self, build_root_dir):

        with BuildSummaryJavaSrc(build_root_dir,
                                 JavaPkg.PKG_ROOT_DIR,
                                 self._pkg_conf) as build_summary:

            self._android_gradle(build_root_dir, build_summary)
            self._configure(build_root_dir, build_summary)
            return self._build(build_root_dir, build_summary)


class JavaAntPkg(JavaSrcPkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaSrcPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

    def _setup(self, build_root_dir):

        res_dir = os.getenv('SCRIPTS_DIR')

        self._build_conf = {
            'executable': 'ant',
            'logger-class': 'org.apache.tools.ant.XmlLogger',
            'build-monitor-lib': osp.join(res_dir, 'build-monitors/swamp-ant-listener/target/swamp-ant-listener-1.0.jar'),
            'build-monitor-class': 'swamp.AntBuildListener',
            'build-monitor-output-file': osp.join(build_root_dir, 'build_artifacts.xml'),
            'usr-lib-dir': osp.join(build_root_dir, 'usr_lib_dir'),
            'cmd-invoke-file': osp.join(res_dir, 'resources/ant-invoke.txt'),
            #'build-file' : 'build.xml',
        }

        self._build_conf.update(self._pkg_conf)

    def get_env(self, pwd):
        new_env = super().get_env(pwd)

        ## which numeric version of java will this build use?
        java_ver_num = self.common_java_ver_num()

        ## set common java executions options
        new_env['ANT_OPTS'] = self.common_java_opts(java_ver_num)

        # XXX in the future we need to use ivy which comes with the
        # platform, or ensure it is used in preference, or built it
        # into ant .. because it is a system issue in those envrionments
        # which support it.
        classpath = ".:${SCRIPTS_DIR}/build-monitors/swamp-ant-listener/target/swamp-ant-listener-1.0.jar:${SCRIPTS_DIR}/build-sys/ivy/ivy-2.3.0.jar"

        # XXX in the future we need to use ivy which comes with the
        # platform, or ensure it is used in preference, or built it
        # into ant .. because it is a system issue in those envrionments
        # which support it.

        new_env['CLASSPATH'] = utillib.expandvar(classpath, new_env)
        return new_env

    def _get_dependency_resolution_errors(self,
                                          build_stdout_file,
                                          build_stderr_file):

        regex = re.compile(r'^\[ivy:retrieve\]\s+module not found.+')

        error_str = list()
        with open(build_stdout_file) as fobj:
            for line in fobj:
                line = line.strip()
                m = regex.match(line)
                if m:
                    error_str.append(m.string)

        if error_str:
            return '\n'.join(error_str)


class JavaAndroidAntPkg(JavaAntPkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaAntPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

    def _android_update(self, build_root_dir, build_summary):
        '''
        Android Update.
        Depends on environment variable SWAMP_ANDROID_SETUP'''

        with LogTaskStatus('android-update'):

            pkg_config_dir = osp.normpath(osp.join(build_root_dir,
                                                   JavaPkg.PKG_ROOT_DIR,
                                                   self._pkg_conf['package-dir'],
                                                   self._pkg_conf.get('config-dir', '.')))

            update_cmd = os.getenv('SWAMP_ANDROID_ANT_SETUP', "")
            logging.info('ANDROID SWAMP_ANDROID_ANT_SETUP: %s', update_cmd)
            if update_cmd == "":
                update_cmd = os.getenv('SWAMP_ANDROID_SETUP', "")
                logging.info('ANDROID SWAMP_ANDROID_SETUP: %s', update_cmd)

            if update_cmd == "":
                logging.info('SWAMP_ANDROID_[ANT_]SETUP environ not set')
                return

            # convert to list for run_cmd
            update_cmd = [update_cmd]

            if 'android-sdk-target' in self._pkg_conf and \
                    (not self._pkg_conf['android-sdk-target'].isspace()):

                update_cmd.extend(['--target', self._pkg_conf['android-sdk-target']])

            if 'android-redo-build' in self._pkg_conf and \
               (self._pkg_conf['android-redo-build'].lower() == 'true' or
                    self._pkg_conf['android-redo-build'].lower() == 'yes'):
                update_cmd.append('--redo-build')

            logging.info('ANDROID UPDATE COMMAND: %s', update_cmd)

            outfile = osp.join(build_root_dir, 'android_update_stdout.out')
            errfile = osp.join(build_root_dir, 'android_update_stderr.out')

            exit_code, environ = utillib.run_cmd(update_cmd,
                                                 outfile=outfile,
                                                 errfile=errfile,
                                                 cwd=pkg_config_dir)

            logging.info('ANDROID UPDATE ERROR CODE: %d', exit_code)
            logging.info('ANDROID UPDATE ENVIRONMENT: %s', environ)

            build_summary.add_command('android-update-command', update_cmd[0],
                                      update_cmd[1:], exit_code, environ,
                                      osp.relpath(pkg_config_dir, build_root_dir),
                                      osp.relpath(outfile, build_root_dir),
                                      osp.relpath(errfile, build_root_dir))

            if exit_code != 0:
                build_summary.add_exit_code(exit_code)
                raise CommandFailedError(update_cmd, exit_code,
                                         BuildSummary.FILENAME,
                                         osp.relpath(outfile, build_root_dir),
                                         osp.relpath(errfile, build_root_dir))

    def build(self, build_root_dir):

        with BuildSummaryJavaSrc(build_root_dir,
                                 JavaPkg.PKG_ROOT_DIR,
                                 self._pkg_conf) as build_summary:

            self._android_update(build_root_dir, build_summary)
            self._configure(build_root_dir, build_summary)
            return self._build(build_root_dir, build_summary)


class JavaNoBuildPkg(JavaAntPkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        JavaAntPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

    def _build_nobuild(self, build_root_dir, build_summary):

        try:
            new_pkg_conf, \
                src_compiles_xmlfile = nobuild.no_build_helper(dict(self._pkg_conf),
                                                               build_root_dir,
                                                               JavaPkg.PKG_ROOT_DIR)
            self.add_build_conf_attr('source-compiles', nobuild.source_compiles_filename)
            build_summary.add_nobuild_summary(0, src_compiles_xmlfile)
            return new_pkg_conf

        except (NoBuildHelperError,
                NoSourceFilesFoundError,
                CompilationFailedError) as err:
            if isinstance(err, CompilationFailedError):
                build_summary.add_nobuild_summary(err.exit_code,
                                                  err.src_compiles_xmlfile)
            else:
                build_summary.add_nobuild_summary(err.exit_code, None)
            logging.exception(err)
            raise

    def build(self, build_root_dir):

        with BuildSummaryJavaSrc(build_root_dir,
                                 JavaPkg.PKG_ROOT_DIR,
                                 self._pkg_conf) as build_summary:

            self._pkg_conf = self._build_nobuild(build_root_dir, build_summary)
            return self._build(build_root_dir, build_summary)


class JavaAndroidApkPkg(JavaPkg):

    def __init__(self, pkg_conf, input_root_dir, build_root_dir):
        # Do not call the parent class's init, package-unarchive not required for apk files
        #JavaPkg.__init__(self, pkg_conf, input_root_dir, build_root_dir)

        ###
        ### ^^^ WHAT??????  FIX ME
        ###
        #
        # Package.__init__ needs to be called to initialize _build_conf_extras,
        # Since it isn't, do it here
        #
        self._build_conf_extras = dict()

        if isinstance(pkg_conf, dict):
            self._pkg_conf = pkg_conf
        else:
            self._pkg_conf = confreader.read_conf_into_dict(pkg_conf)

        with LogTaskStatus('package-unarchive') as status_dot_out:
            status_dot_out.skip_task()

            pkg_archive = osp.join(input_root_dir, pkg_conf['package-archive'])
            pkg_root_dir = osp.join(build_root_dir, JavaPkg.PKG_ROOT_DIR)

            if not osp.isdir(pkg_root_dir):
                os.makedirs(pkg_root_dir, exist_ok=False)

            shutil.copy2(pkg_archive, osp.join(pkg_root_dir, ''))
            #status = shutil.copy2(pkg_archive, osp.join(pkg_root_dir, ''))
            # if status != 0:
            # Not the right exception but ok for now
            #    raise UnpackArchiveError(osp.basename(pkg_archive))

            self.pkg_dir = osp.join(pkg_root_dir, '')

    def build(self, build_root_dir):

        with BuildSummaryJavaAndroidApk(build_root_dir,
                                        JavaPkg.PKG_ROOT_DIR,
                                        self._pkg_conf) as build_summary:

            build_summary.add_build_artifacts(osp.normpath(osp.join(self.pkg_dir,
                                                                    self._pkg_conf['package-archive'])))
            build_summary.add_exit_code(0)
            return (0, BuildSummary.FILENAME)


def get_pkg_obj(pkg_conf_file, input_root_dir, build_root_dir):

    pkg_conf = confreader.read_conf_into_dict(pkg_conf_file)

    # identify android assessments using the sdk.
    android_builds = {
        'android+ant'           : 1,
        'android+ant+ivy'       : 1,
        'android+maven'         : 1,
        'android+gradle'        : 1,
        # apk assessment's are their own thing at this point in time
    }

    pkg_classes = {
        'java-bytecode': JavaByteCodePkg,
        'no-build': JavaNoBuildPkg,
        'ant': JavaAntPkg,
        'ant+ivy': JavaAntPkg,
        'maven': JavaMavenPkg,
        'gradle': JavaGradlePkg,
        'android+ant': JavaAndroidAntPkg,
        'android+ant+ivy': JavaAndroidAntPkg,
        'android+maven': JavaAndroidMavenPkg,
        'android+gradle': JavaAndroidGradlePkg,
        'android-apk': JavaAndroidApkPkg,
    }

    # This is a temprory fix
    # if 'build-sys' not in pkg_conf:
    #    pkg_conf['build-sys'] = 'java-bytecode'

    build_sys = pkg_conf['build-sys'].lower()


    ## if android sdk needs specific java, it is already setup; the newer SDK
    ## controls what java is needed, it is no longer a platform issue.
    ## Otherwise (normal assessment on android VM, act normally)
    set_java_home = True
# hack for temporary VM
#    if build_sys in android_builds  and  os.getenv('JAVA_HOME') != '':
    if build_sys in android_builds and os.getenv('ANDROID_JAVA_HOME', '') != '':
           set_java_home = False
           logging.info('Android build controls JAVA_HOME')

    if set_java_home:
        utillib.setup_java_home(pkg_conf.get('package-language-version', 'java-7').lower())
     


    # set default values for some mandatory items
    # creating a dictionary of default values would be a better solution;
    # the code is already setup to use it
    key = 'package-dir'
    default_value = '.'
    if key not in pkg_conf or pkg_conf[key].isspace():
        pkg_conf[key] = default_value

    if build_sys in pkg_classes.keys():
        return pkg_classes[build_sys](pkg_conf, input_root_dir, build_root_dir)
    else:
        raise InvalidBuildSystem(build_sys)


def build(input_root_dir, output_root_dir, build_root_dir):

    ## mark as failed if exception thrown
    ## if you don't understand why this line of code is needed please see bolo
    ## To to this right (and in assess, and error for INTERNAL FAILURE
    ## should be created, and make it so it prints it out nicely too.
    ## The whole problem is that exceptions are used for ERROR handling.
    # exit_code = 99

    try:
        if not osp.isdir(build_root_dir):
            os.makedirs(build_root_dir, exist_ok=True)

        pkg_conf_file = osp.join(input_root_dir, 'package.conf')
        pkg = get_pkg_obj(pkg_conf_file, input_root_dir, build_root_dir)
        exit_code, build_summary_file = pkg.build(build_root_dir)
    except (NoBuildHelperError,
            NoSourceFilesFoundError,
            CompilationFailedError,
            UnpackArchiveError,
            InvalidFilesetError,
            CommandFailedError,
            NotADirectoryException,
            FileNotFoundException,
            PermissionException,
            InvalidBuildSystem) as err:

        logging.exception(err)
        exit_code = err.errno if hasattr(err, 'errno') else 1
        if hasattr(err, 'build_summary_file'):
            build_summary_file = err.build_summary_file
        else:
            build_summary_file = osp.join(build_root_dir, BuildSummary.FILENAME)

    finally:
        build_conf = dict()
        build_conf['exit-code'] = str(exit_code)

        if build_summary_file:
            build_conf['build-summary-file'] = osp.basename(build_summary_file)

        with LogTaskStatus('build-archive'):
            build_archive = shutil.make_archive(osp.join(output_root_dir, 'build'),
                                                'gztar',
                                                osp.dirname(build_root_dir),
                                                osp.basename(build_root_dir))

            build_conf['build-archive'] = osp.basename(build_archive)
            build_conf['build-dir'] = osp.basename(build_root_dir)
            build_conf.update(pkg.get_build_conf_extras())

            utillib.write_to_file(osp.join(output_root_dir, 'build.conf'), build_conf)

    return (exit_code, build_summary_file)
