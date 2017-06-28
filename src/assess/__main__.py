import sys
import os
import os.path as osp

from .. import logger
from . import assess

def main(in_root_dir, out_root_dir, tool_root_dir,
         results_root_dir, build_summary_file):

    if not osp.isdir(out_root_dir):
        os.makedirs(out_root_dir, exist_ok=True)

    logger.init(out_root_dir)
    assess.assess(in_root_dir, out_root_dir, tool_root_dir,
                  results_root_dir, build_summary_file)

main(*sys.argv[1:])

