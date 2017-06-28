import os
import os.path as osp
import logging
import logging.handlers

from .logger import LogTaskStatus
from . import confreader
from . import build
from .build import build_java
from .assess import assess
from . import install_os_dependencies
from . import results_parser
from . import utillib


def main(input_root_dir,
         output_root_dir,
         build_root_dir,
         tool_root_dir,
         results_root_dir):

    with LogTaskStatus('all') as status_dot_out:
        try:
            run_conf_file = osp.join(input_root_dir, 'run.conf')

            if not osp.isfile(run_conf_file):
                raise utillib.FileNotFoundException('File Not Found: {0}'.format(run_conf_file))

            param = confreader.read_conf_into_dict(run_conf_file)

            if 'goal' not in param:
                raise KeyError('{0} param not found in {1} file'.format('goal',
                                                                        osp.basename(run_conf_file)))

            goal = param['goal']

            swamp_goals = ['build',
                           'build+assess',
                           'build+assess+parse',
                           'assess',
                           'assess+parse',
                           'parse']

            logging.info('GOAL: %s', goal)

            if goal not in swamp_goals:
                raise ValueError('Unknown goal {0}, it should be one of {1}'.format(goal,
                                                                                    swamp_goals))

            install_os_dependencies.install(input_root_dir)

            if goal in swamp_goals[:5]:
                check_java_compatibility(goal, input_root_dir)
                exit_code = _build_assess_parse(goal,
                                                input_root_dir,
                                                output_root_dir,
                                                build_root_dir,
                                                tool_root_dir,
                                                results_root_dir)
            elif goal == swamp_goals[5]:
                exit_code = results_parser.just_parse(input_root_dir, output_root_dir)

        except (BaseException, Exception) as err:
            logging.exception(err)
            if hasattr(err, 'errno'):
                exit_code = err.errno
            else:
                exit_code = 1

        status_dot_out.update_task_status(exit_code)

    return exit_code


def _build_assess_parse(goal,
                        input_root_dir, output_root_dir,
                        build_root_dir, tool_root_dir,
                        results_root_dir):

    if 'build' in goal:
        exit_code, build_summary_file = build_java.build(input_root_dir,
                                                         output_root_dir,
                                                         build_root_dir)
    else:
        exit_code, build_summary_file = build.extract(input_root_dir)

    if (exit_code == 0) and ('assess' in goal):

        build_summary_file = osp.join(build_root_dir, build_summary_file)
        exit_code, assessment_summary_file = assess.assess(input_root_dir,
                                                           output_root_dir,
                                                           tool_root_dir,
                                                           results_root_dir,
                                                           build_summary_file)

        if (exit_code == 0) and ('parse' in goal):
            exit_code = results_parser.parse_results(input_root_dir,
                                                     assessment_summary_file,
                                                     results_root_dir,
                                                     output_root_dir)

    return exit_code


def check_java_compatibility(goal, input_root_dir):

    def _get_pkg_lang_version(input_root_dir):
        pkg_conf_file = osp.normpath(osp.join(input_root_dir, 'package.conf'))
        pkg_conf = confreader.read_conf_into_dict(pkg_conf_file)
        return pkg_conf.get('package-language-version', 'java-7').lower()

    def _get_tool_lang_version(input_root_dir):
        tool_conf_file = osp.normpath(osp.join(input_root_dir, 'tool.conf'))
        tool_conf = confreader.read_conf_into_dict(tool_conf_file)
        return tool_conf.get('supported-language-version', 'java-7').lower()

    with LogTaskStatus('tool-runtime-compatibility') as log_task_status:

        if goal in ['build+assess', 'build+assess+parse']:
            pkg_lang_version = _get_pkg_lang_version(input_root_dir)
            tool_lang_version = _get_tool_lang_version(input_root_dir)

            if pkg_lang_version not in tool_lang_version and \
               tool_lang_version not in pkg_lang_version:
                log_task_status.update_task_status(1, 'JVM version')
                raise Exception('Incompatible Java versions of the package:%s and the tool:%s' %
                                (pkg_lang_version, tool_lang_version))
        else:
            log_task_status.skip_task()
