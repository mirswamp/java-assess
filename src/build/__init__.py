import os
import os.path as osp
from .. import confreader
from .. import utillib


def extract(input_root_dir):

    build_conf_file = osp.join(input_root_dir, 'build.conf')
    build_conf = confreader.read_conf_into_dict(build_conf_file)

    if int(build_conf['exit-code']) != 0:
        raise NotImplementedError()

    build_archive = osp.join(input_root_dir, build_conf['build-archive'])
    status = utillib.unpack_archive(build_archive, os.getcwd(), True)

    if status != 0:
        raise utillib.UnpackArchiveError(build_archive)

    return (int(build_conf['exit-code']), build_conf['build-summary-file'])
