
import os.path as osp
import uuid
import logging
import xml.etree.ElementTree as ET

from .. import utillib


class AssessmentSummary:

    def __init__(self,
                 filename,
                 build_summary_obj,
                 tool_attrs):

        self._filename = filename

        self._root = ET.Element('assessment-summary')
        AssessmentSummary._add(self._root, 'assessment-summary-uuid', str(uuid.uuid4()))

        AssessmentSummary._add(self._root, 'build-root-dir',
                               build_summary_obj['build-root-dir'])

        AssessmentSummary._add(self._root, 'package-root-dir',
                               osp.join(build_summary_obj['build-root-dir'],
                                        build_summary_obj['package-root-dir']))
        
        AssessmentSummary._add(self._root, 'package-name',
                               build_summary_obj.get_pkg_conf().get('package-short-name'))

        AssessmentSummary._add(self._root, 'package-version',
                               build_summary_obj.get_pkg_conf().get('package-version'))

        if 'build-summary-uuid' in build_summary_obj:
            AssessmentSummary._add(self._root, 'build-summary-uuid', build_summary_obj['build-summary-uuid'])

        AssessmentSummary._add(self._root, 'tool-type', tool_attrs['tool-type'])
        AssessmentSummary._add(self._root, 'tool-version', tool_attrs['tool-version'])
        AssessmentSummary._add(self._root, 'platform-name', utillib.platform())
        AssessmentSummary._add(self._root, 'start-ts', utillib.posix_epoch())
        self._assessment_artifacts = AssessmentSummary._add(self._root, 'assessment-artifacts')

    @classmethod
    def _add(cls, parent, tag, text=None):
        elem = ET.SubElement(parent, tag)
        if text:
            elem.text = text
        return elem

    def __enter__(self):
        return self

    def __exit__(self, exception_type, value, traceback):
        AssessmentSummary._add(self._root, 'end-ts', utillib.posix_epoch())

        tree = ET.ElementTree(self._root)
        tree.write(self._filename, encoding='UTF-8', xml_declaration=True)

    def add_report(self, build_artifact_id, cmd, exit_code,
                   environ, cwd, report, stdout,
                   stderr, tool_type, starttime, endtime):

        #logging.info('ASSESS COMMAND: {0}'.format(' '.join(cmd)))
        logging.info('ASSESSMENT WORKING DIR: %s', cwd)
        logging.info('ASSESSMENT EXIT CODE: %s', exit_code)
        logging.info('ASSESSMENT ENVIRONMENT: %s', environ)

        assess_elem = AssessmentSummary._add(self._assessment_artifacts, 'assessment')
        if build_artifact_id:
            AssessmentSummary._add(assess_elem, 'build-artifact-id', build_artifact_id)
        if osp.isfile(report):
            AssessmentSummary._add(assess_elem, 'report', osp.basename(report))
        if osp.isfile(stdout):
            AssessmentSummary._add(assess_elem, 'stdout', osp.basename(stdout))
        if osp.isfile(stderr):
            AssessmentSummary._add(assess_elem, 'stderr', osp.basename(stderr))
        AssessmentSummary._add(assess_elem, 'exit-code', str(exit_code))
        AssessmentSummary._add(assess_elem, 'start-ts', starttime)
        AssessmentSummary._add(assess_elem, 'end-ts', endtime)

        cmd_elem = AssessmentSummary._add(assess_elem, 'command')

        AssessmentSummary._add(cmd_elem, 'cwd', cwd)
        env_elem = AssessmentSummary._add(cmd_elem, 'environment')
        for key in environ.keys():
            AssessmentSummary._add(env_elem, 'env', '{0}={1}'.format(key, environ[key]))

        AssessmentSummary._add(cmd_elem, 'executable', cmd[0])
        args_elem = AssessmentSummary._add(cmd_elem, 'args')
        for arg in cmd[1:]:
            AssessmentSummary._add(args_elem, 'arg', arg)

        if tool_type == 'ps-jtest':
            srcdirs = AssessmentSummary.get_srcdirs(cmd)
            if srcdirs:
                replace_elem = AssessmentSummary._add(assess_elem, 'replace-path')
                AssessmentSummary._add(replace_elem, 'target', 'TempProject')
                for _srcdir in srcdirs:
                    AssessmentSummary._add(replace_elem, 'srcdir', _srcdir)

    @classmethod
    def get_srcdirs(cls, cmd):
        '''This method is only applicable for ps-jtest'''
        srcdirs = list()

        _iter = iter(cmd)
        try:
            while True:
                if next(_iter) == '-source':
                    srcdirs.append(next(_iter))
        except StopIteration:
            pass

        return srcdirs
