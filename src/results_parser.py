import os
import os.path as osp
import logging
import shutil
import re

from .logger import LogTaskStatus
from . import utillib
from . import confreader
from .utillib import FileNotFoundException


def just_parse(input_root_dir, output_root_dir):

    results_conf_file = osp.join(input_root_dir, 'results.conf')
    results_conf = confreader.read_conf_into_dict(results_conf_file)

    if int(results_conf['exit-code']) != 0:
        return int(results_conf['exit-code'])

    results_archive = osp.join(input_root_dir, results_conf['results-archive'])

    cwd = os.getcwd()
    with LogTaskStatus('results-unarchive'):
        status = utillib.unpack_archive(results_archive, cwd)
        if status != 0:
            return status

    results_root_dir = osp.join(cwd, results_conf['results-dir'])
    assessment_summary_file = osp.join(results_root_dir,
                                       results_conf['assessment-summary-file'])

    return parse_results(input_root_dir,
                         assessment_summary_file,
                         results_root_dir,
                         output_root_dir)


def _get_results_parser(input_dir):

    with LogTaskStatus('resultparser-unarchive'):

        parser_dir = osp.join(os.getcwd(), 'result-parser')
        if not osp.isdir(parser_dir):
            os.mkdir(parser_dir)

        parser_conf_file = osp.join(input_dir, 'resultparser.conf')

        if not osp.isfile(parser_conf_file):
            raise FileNotFoundException(parser_conf_file)

        parser_attr = confreader.read_conf_into_dict(parser_conf_file)
        logging.info('RESULTS PARSER CONF: ' + str(parser_attr))

        parser_archive = osp.join(input_dir, parser_attr['result-parser-archive'])

        utillib.unpack_archive(parser_archive, parser_dir)

        parser_dir = osp.join(parser_dir, parser_attr['result-parser-dir'])
        parser_exe_file = osp.join(parser_dir, parser_attr['result-parser-cmd'])

        return parser_exe_file


def read_task_info_file(weakness_count_file):

    # STATUS_DICT = {'PASS', 'FAIL', 'SKIP', 'NOTE'}

    short_msg = ''
    status = 'PASS'
    long_msg = ''

    with open(weakness_count_file) as fobj:
        short_msg = fobj.readline().strip()

        if short_msg:
            regex_sep = re.compile(r'^-+$')
            next_line = fobj.readline().strip()

            if next_line:
                if regex_sep.match(next_line) is None:
                    status = next_line
                    next_line = fobj.readline().strip()
                else:
                    status = 'PASS'

            if next_line:
                if regex_sep.match(next_line):
                    long_msg = ''.join([line for line in fobj])
                else:
                    raise Exception("Invalid long message separator '%s' in '%s'" %
                                    (next_line, weakness_count_file))

    return (short_msg, status, long_msg)


def parse_results(input_dir, assessment_summary_file, results_dir, output_dir):

    command_template = '{EXECUTABLE}\
 --summary_file={PATH_TO_SUMMARY_FILE}\
 --input_dir={PATH_TO_RESULTS_DIR}\
 --output_file={OUTPUT_FILENAME}\
 --weakness_count_file={WEAKNESS_COUNT_FILENAME}\
 --parsed_results_data_conf_file={PARSED_RESULTS_DATA_CONF_FILE}'

    if not osp.isfile(assessment_summary_file):
        raise FileNotFoundException(assessment_summary_file)

    parser_exe_file = _get_results_parser(input_dir)

    services_conf_file = osp.join(input_dir, 'services.conf')
    if osp.isfile(services_conf_file):
        command_template += ' --services_conf_file={SERVICES_CONF_FILE}'

    parse_results_dir = osp.join(os.getcwd(), 'parsed_results')
    if not osp.isdir(parse_results_dir):
        os.mkdir(parse_results_dir)

    parsed_results_data_conf_file = osp.join(parse_results_dir, 'parsed_results_data.conf')

    try:
        parse_results_logfile = osp.join(parse_results_dir, 'resultparser.log')
        parse_results_output_file = osp.join(parse_results_dir, 'parsed_results.xml')
        parse_weakness_count_file = osp.join(parse_results_dir, 'weakness_count.out')
        stdout_filename = 'resultparser_stdout.out'
        stderr_filename = 'resultparser_stderr.out'
        resultparser_stdout_file = osp.join(parse_results_dir, stdout_filename)
        resultparser_stderr_file = osp.join(parse_results_dir, stderr_filename)

        with LogTaskStatus('parse-results') as status_dot_out:

            if 'PERL5LIB' in os.environ:
                os.environ['PERL5LIB'] = '${0}:{1}'.format(os.environ['PERL5LIB'],
                                                           osp.dirname(parser_exe_file))
            else:
                os.environ['PERL5LIB'] = osp.dirname(parser_exe_file)

            command = command_template.format(EXECUTABLE=parser_exe_file,
                                              PATH_TO_SUMMARY_FILE=assessment_summary_file,
                                              PATH_TO_RESULTS_DIR=results_dir,
                                              PATH_TO_OUTPUT_DIR=parse_results_dir,
                                              OUTPUT_FILENAME=parse_results_output_file,
                                              WEAKNESS_COUNT_FILENAME=parse_weakness_count_file,
                                              SERVICES_CONF_FILE=services_conf_file,
                                              PARSED_RESULTS_DATA_CONF_FILE=parsed_results_data_conf_file,
                                              LOGFILE=parse_results_logfile)

            logging.info('RESULT PARSER CMD: ' + command)
            exit_code, environ = utillib.run_cmd(command,
                                                 cwd=osp.dirname(parser_exe_file),
                                                 outfile=resultparser_stdout_file,
                                                 errfile=resultparser_stderr_file)

            logging.info('PARSE RESULTS ERROR CODE: %d', exit_code)
            logging.info('PARSE RESULTS WORKING DIR: %s', osp.dirname(parser_exe_file))
            logging.info('PARSE RESULTS ENVIRONMENT: %s', environ)

            short_msg = ''
            status = 'PASS'
            long_msg = ''
            if osp.isfile(parse_weakness_count_file):
                short_msg, status, long_msg = read_task_info_file(parse_weakness_count_file)
            else:
                status = 'FAIL'
                long_msg = "weakness count file ({0}) not found".format(parse_weakness_count_file)

            if status == 'SKIP':
                status_dot_out.skip_task(short_msg, long_msg)
            else:
                if (exit_code != 0):
                    if long_msg:
                        long_msg += "\n"
                    long_msg += "Result Parser exit code {0}".format(exit_code)
                elif status == 'FAIL':
                    exit_code = 1
                status_dot_out.update_task_status(exit_code, short_msg, long_msg)

    except Exception as err:
        logging.exception(err)
        exit_code = 1
    finally:
        with LogTaskStatus('parsed-results-archive'):
            shutil.make_archive(osp.join(output_dir,
                                         osp.basename(parse_results_dir)),
                                'gztar',
                                osp.dirname(parse_results_dir),
                                osp.basename(parse_results_dir))

        fileFound = osp.isfile(parsed_results_data_conf_file)
        if fileFound:
            parsed_results_conf = confreader.read_conf_into_dict(parsed_results_data_conf_file)

        parsed_results_conf['parsed-results-dir'] = osp.basename(parse_results_dir)
        parsed_results_conf['parsed-results-archive'] = '{0}.tar.gz'.format(osp.basename(parse_results_dir))
        parsed_results_conf['resultparser-stdout-file'] = stdout_filename
        parsed_results_conf['resultparser-stderr-file'] = stderr_filename

        utillib.write_to_file(osp.join(output_dir, 'parsed_results.conf'),
                              parsed_results_conf)
        if not fileFound and exit_code == 0:
            raise Exception('parsed_results_data.conf file not found at {0}'.format(parsed_results_data_conf_file))

    if exit_code != 0:
        raise Exception('Result Parser Exit Code {0}'.format(exit_code))
    else:
        return 0
