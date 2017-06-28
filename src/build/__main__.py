import sys
import os
import os.path as osp

from .. import logger
from . import build_java


def main(input_root_dir, output_root_dir, build_root_dir):

    if not osp.isdir(output_root_dir):
        os.makedirs(output_root_dir, exist_ok=True)

    logger.init(output_root_dir)
    build_java.build(input_root_dir, output_root_dir, build_root_dir)


if __name__ == "__main__":
    main(*sys.argv[1:])
