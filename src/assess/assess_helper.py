import os.path as osp
import xml.etree.ElementTree as ET
import logging
import glob

from .. import directory_scanner
from .. import utillib
from ..utillib import FileNotFoundException


class JavaBuildArtifactsError(Exception):

    def __init__(self, value):
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        return repr(self.value)


class JavaBuildSummaryError(Exception):

    def __init__(self, field, filename):
        Exception.__init__(self)
        self.value = "No `{0}` tag found in `{1}` file".format(field, filename)

    def __str__(self):
        return repr(self.value)


class JavaInvalidBuildError(Exception):

    def __init__(self, value):
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        return repr(self.value)


class JavaBuildArtifacts:

    @classmethod
    def validate(cls, build_summary_file):
        '''Check if it as a valid java artifact file.

        check if it is a valid xml file
        TODO: do more validations on the file to check it is a real java
        artifacts or a plain xml file
        '''
        if not osp.isfile(build_summary_file):
            raise FileNotFoundException('Not a file: ' + build_summary_file)

        root = ET.parse(build_summary_file).getroot()

        if root.tag != 'build-summary':
            raise JavaBuildSummaryError('build-summary', build_summary_file)

        if root.find('exit-code') is None:
            raise JavaBuildSummaryError('exit-code not in build-summary-file:',
                                        build_summary_file)
        elif int(root.find('exit-code').text) != 0:
            raise JavaInvalidBuildError('exit-code not 0 in ' + build_summary_file)

        if root.find('build-root-dir') is None:
            raise JavaBuildSummaryError('build-root-dir', build_summary_file)

        # if root.find('build-artifacts') is None:
        #     raise JavaBuildArtifactsError("No Java Source Files or Class Files to Assess! "
        #                                   "Looks like no source files were compiled during the build step. "
        #                                   "Check if running '(ant|mvn|gradle) clean' command is required. "
        #                                   "Or Check if changing package configuration values is required.")

    @classmethod
    def _get_build_summary(cls, root):
        '''returns a dictionary'''
        return {elem.tag: elem.text for elem in root
                if(elem.tag not in ['package-conf', 'command', 'build-artifacts'])}

    def __init__(self, build_summary_file):

        JavaBuildArtifacts.validate(build_summary_file)

        root = ET.parse(build_summary_file).getroot()
        self._build_summary = JavaBuildArtifacts._get_build_summary(root)
        self._build_artifacts = root.find('build-artifacts')
        self._package_conf = {elem.tag: elem.text for elem in root.find('package-conf')}

    def get_pkg_name_version(self):
        return '%s-%s' % (self._package_conf.get('package-short-name', ''),
                          self._package_conf.get('package-version'))

    def __contains__(self, key):
        return True if(key in self._build_summary or key in self._package_conf) else False

    def __getitem__(self, key):
        if key in self._build_summary:
            return self._build_summary[key]
        else:
            return self._package_conf.get(key, None)

    def get_pkg_dir(self):
        return osp.join(self._build_summary['build-root-dir'],
                        self._build_summary['package-root-dir'],
                        self._package_conf['package-dir'])

    def get_pkg_conf(self):
        return self._package_conf
    
    def get_build_artifacts(self, *args):
        ''' this is a generator function
        parses through the xml elements in the tree and
        yeilds objects artifacts that we are interested in provided as a parameter
        '''

        build_artifacts = None

        if 'package-conf' in args:
            build_artifacts = PackageConfArtifact(self._build_summary, self._package_conf).artifacts
            build_artifacts['build-artifact-id'] = build_artifacts['id']
            yield build_artifacts

        if self._build_artifacts is None:
            raise JavaBuildArtifactsError("No Java Source Files or Class Files to Assess! "
                                          "Looks like no source files were compiled during the build step. "
                                          "Check if running '(ant|mvn|gradle) clean' command is required. "
                                          "Or Check if changing package configuration values is required.")

        for elem in self._build_artifacts:
            if elem.tag in args:
                if elem.tag == 'java-compile':
                    build_artifacts = JavaCompileArtifact(self._build_summary['build-root-dir'], elem).artifacts
                elif elem.tag == 'java-bytecode':
                    build_artifacts = JavaBytecodeArtifact(self._build_summary['build-root-dir'], elem).artifacts
                else:  # elif elem.tag == 'java-android-apk':
                    build_artifacts = AndroidApkArtifact(self._build_summary['build-root-dir'], elem).artifacts

                build_artifacts['build-artifact-id'] = build_artifacts['id']
                build_artifacts['package-name-version'] = self.get_pkg_name_version()
                yield build_artifacts


class BuildArtifacts:

    UTF_8 = 'utf-8'

    def __init__(self, _id):
        self._artifacts = dict()
        self._artifacts['id'] = _id

    @classmethod
    def _get_fileset(cls, build_root_dir, xml_elem):
        fileset = list()

        for _file in xml_elem:
            if not osp.isabs(_file.text):
                fileset.append(osp.join(build_root_dir, _file.text))
            else:
                fileset.append(_file.text)

        return utillib.ordered_list(fileset)


class PackageConfArtifact(BuildArtifacts):

    @property
    def artifacts(self):
        return self._artifacts

    def __init__(self, build_summary, package_conf):
        BuildArtifacts.__init__(self, '1')

        self._artifacts['build-root-dir'] = build_summary['build-root-dir']
        self._artifacts['package-root-dir'] = build_summary['package-root-dir']

        # How about pushing everything?
        for key in ['package-dir', 'build-dir',
                    'package-short-name', 'package-version',
                    'build-sys',
                    'build-file', 'build-target',
                    'android-gradle-wrapper', 'gradle-wrapper',
                    ]:
            if key in package_conf:
                self._artifacts[key] = utillib.quote_str(package_conf[key])

        # null == don't propogate keys
        for key in ['android-lint-target'
                    ]:
            if key in package_conf and \
                    (not package_conf[key].isspace()):
                self._artifacts[key] = utillib.quote_str(package_conf[key])

        if 'package-dir' in self._artifacts:
            self._artifacts['package-dir'] = '{0}/{1}'.format(self._artifacts['package-root-dir'],
                                                              self._artifacts['package-dir'])


class AndroidApkArtifact(BuildArtifacts):

    @property
    def artifacts(self):
        return self._artifacts

    def __init__(self, build_root_dir, build_artifact_elem):
        BuildArtifacts.__init__(self, build_artifact_elem.attrib['id'])

        for xml_elem in build_artifact_elem:

            if xml_elem.tag in ['apkfile']:

                fileset = BuildArtifacts._get_fileset(build_root_dir, xml_elem)

                if xml_elem.tag == 'classpath':
                    self._artifacts['classfile'] = fileset
                else:
                    self._artifacts[xml_elem.tag] = fileset


class JavaBytecodeArtifact(BuildArtifacts):

    @property
    def artifacts(self):
        return self._artifacts

    def __init__(self, build_root_dir, build_artifact_elem):
        BuildArtifacts.__init__(self, build_artifact_elem.attrib['id'])

        for xml_elem in build_artifact_elem:

            if xml_elem.tag in ['classpath', 'auxclasspath', 'srcdir']:

                fileset = BuildArtifacts._get_fileset(build_root_dir, xml_elem)

                if xml_elem.tag == 'classpath':
                    self._artifacts['classfile'] = fileset
                else:
                    self._artifacts[xml_elem.tag] = fileset


class JavaCompileArtifact(BuildArtifacts):

    @property
    def artifacts(self):
        return self._artifacts

    @classmethod
    def change_pattern(cls, pattern_list):

        new_list = list()

        for pattern in pattern_list:
            if pattern.endswith('**.java'):
                new_list.append(pattern.replace('**.java', '*.java'))
            else:
                new_list.append(pattern)
        return new_list

    def __init__(self, build_root_dir, build_artifact_elem):
        BuildArtifacts.__init__(self, build_artifact_elem.attrib['id'])

        for xml_elem in build_artifact_elem:

            if xml_elem.tag in ['srcdir', 'srcfile',
                                'destdir', 'classpath',
                                'bootclasspath', 'sourcepath']:

                fileset = BuildArtifacts._get_fileset(build_root_dir, xml_elem)

                if xml_elem.tag == 'classpath':
                    self._artifacts['auxclasspath'] = fileset
                elif xml_elem.tag == 'sourcepath':
                    self._artifacts['auxsrcpath'] = fileset
                else:
                    self._artifacts[xml_elem.tag] = fileset

            elif xml_elem.tag in ['include', 'exclude']:
                self._artifacts[xml_elem.tag] = list({pattern.text for pattern in xml_elem})
            else:
                self._artifacts[xml_elem.tag] = xml_elem.text

        self._add_src_files()
        self._add_src_dirs()
        # self._add_psjtest_file_filters()
        self._remove_invalid_artifacts()

    def _add_src_files(self):

        if 'srcfile' not in self._artifacts:
            fileset = list()

            if 'include' in self._artifacts:
                includes = self._artifacts['include']
            else:
                includes = ['**/*.java']

            includes = JavaCompileArtifact.change_pattern(includes)

            if 'exclude' in self._artifacts:
                excludes = self._artifacts['exclude']
            else:
                excludes = []

            excludes = JavaCompileArtifact.change_pattern(excludes)

            srcdirs = [srcdir for srcdir in self._artifacts['srcdir'] if osp.isdir(srcdir)]

            logging.debug('SOURCE DIRECTORIES: %s', srcdirs)
            logging.debug('INCLUDES: %s', includes)
            logging.debug('EXCLUDES: %s', excludes)

            fileset = directory_scanner.get_files_in_dirs(srcdirs, includes, excludes)
            self._artifacts['srcfile'] = utillib.ordered_list(fileset)
        else:
            self._artifacts['srcfile'] = [_file for _file in self._artifacts['srcfile'] if osp.isfile(_file)]
    
        logging.info('Found %s source file%s',
                     len(self._artifacts['srcfile']),
                     's' if(len(self._artifacts['srcfile']) > 1) else '')

    def _remove_invalid_artifacts(self):
        ''' Check for shell variable substitution characters
        in the artifacts: [srcdir, auxclasspath,
        bootclasspath, processorpath]
        Removes invalid values first,
        if all the values empty remove the key from the artifacts dictionary
        '''
        artifacts_copy = dict(self._artifacts)

        isvalid = lambda value: False if '$' in value else True

        for arttype in artifacts_copy.keys():
            if arttype not in ['srcdir', 'auxclasspath',
                               'bootclasspath', 'processorpath']:
                continue

            self._artifacts[arttype] = [val for val in self._artifacts[arttype]
                                        if isvalid(val)]
            if len(self._artifacts[arttype]) == 0:
                self._artifacts.pop(arttype)

    def _add_src_dirs(self):
        '''
        if 'srcdir'  key is not found in the build artifacts.
        '''
        if 'srcdir' not in self._artifacts:
            srcdirs = dict()

            for _file in self._artifacts['srcfile']:
                dirpath = osp.dirname(_file)

                if dirpath not in srcdirs.keys():
                    if 'encoding' in self._artifacts:
                        encoding = self._artifacts['encoding']
                    else:
                        encoding = BuildArtifacts.UTF_8

                    try:
                        pkgname = directory_scanner.JavaParser.get_pkg_name(_file, encoding)

                        if pkgname is not None:
                            pkgpath = pkgname.replace('.', '/')
                            (basedir, _, _) = _file.rpartition(pkgpath)
                            srcdirs[dirpath] = (basedir, pkgname, [osp.basename(_file)], [])
                        else:
                            srcdirs[dirpath] = (dirpath, None, [osp.basename(_file)], [])

                    except UnicodeDecodeError as err:
                        logging.error('UnicodeDecodeError: %s in the %s', str(err), _file)

                else:
                    srcdirs[dirpath][2].append(osp.basename(_file))

            include_filter = list()

            for _dir in srcdirs.keys():
                for _file in glob.glob(osp.join(_dir, '*.java')):
                    if osp.basename(_file) not in srcdirs[_dir][2]:
                        srcdirs[_dir][3].append(osp.basename(_file))

                if srcdirs[_dir][3]:
                    if srcdirs[_dir][1]:
                        include_filter.extend(['{0}.{1}'.format(srcdirs[_dir][1], _file)
                                               for _file in srcdirs[_dir][2]])
                    else:
                        include_filter.extend([_file for _file in srcdirs[_dir][2]])
                else:
                    if srcdirs[_dir][1]:
                        include_filter.append('{0}.*'.format(srcdirs[_dir][1]))
                    else:
                        include_filter.extend([_file for _file in srcdirs[_dir][2]])

            self._artifacts['srcdir'] = list({basedir for (basedir, _, _, _) in srcdirs.values()})

            if 'include' not in self._artifacts:
                self._artifacts['include'] = include_filter
            else:
                self._artifacts['include'].extend(include_filter)
