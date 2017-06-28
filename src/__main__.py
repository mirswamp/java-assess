import sys
import os
import os.path as osp
import logging

from . import swamp
from . import cli_argparse
from . import logger


def main():
    clargs = cli_argparse.process_cmd_line_args()

    if not osp.isdir(clargs.output_dir):
        os.makedirs(clargs.output_dir, exist_ok=True)

    logger.init(clargs.output_dir)

    if clargs.version:
        logging.info(clargs.version)

    if clargs.platform:
        logging.info('PLATFORM: ' + clargs.platform)

    try:
        #os.environ['SCRIPTS_DIR'] = osp.join(os.getenv('HOME'), 'scripts')
        os.environ['TOOL_DIR'] = osp.realpath(clargs.tool_dir)

        exit_code = swamp.main(osp.realpath(clargs.input_dir),
                               osp.realpath(clargs.output_dir),
                               osp.realpath(clargs.build_dir),
                               osp.realpath(clargs.tool_dir),
                               osp.realpath(clargs.results_dir))
        sys.exit(exit_code)
    finally:
        logger.shutdown()
        # os.environ.pop('SCRIPTS_DIR')
        os.environ.pop('TOOL_DIR')

if __name__ == '__main__':
    main()
