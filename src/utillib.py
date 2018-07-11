import os
import os.path as osp
import glob
import subprocess
import sys
import datetime
import time
import re
import string
import shlex
import uuid
import pkgutil
import logging

class PermissionException(OSError):
    pass


class FileFoundException(OSError):
    pass


class FileNotFoundException(OSError):
    pass


class NotADirectoryException(OSError):
    pass


class IsADirectoryException(OSError):
    pass


class UnpackArchiveError(Exception):

    def __init__(self, filename):
        Exception.__init__(self)
        self.filename = filename
        self.errno = 5

    def __str__(self):
        return "Unpacking archive '{0}' failed".format(self.filename)


def datetime_iso8601():
    return datetime.datetime.isoformat(datetime.datetime.now())


def posix_epoch():
    return str(time.time())


def _unpack_archive_xz(archive, dirpath):

    xz_proc = subprocess.Popen(['xz', '--decompress', '--stdout', archive],
                               stdout=subprocess.PIPE,
                               stderr=sys.stderr)

    tar_proc = subprocess.Popen(['tar', '-x'],
                                stdin=xz_proc.stdout,
                                stdout=sys.stdout,
                                stderr=sys.stderr,
                                cwd=dirpath)

    xz_proc.stdout.close()
    tar_proc.communicate()

    return tar_proc.returncode


def unpack_archive(archive, dirpath, createdir=True):
    '''
    Unarchives/Extracts the file \'archive\' in the directory \'dirpath\'.
    Expects \'dirpath\' to be already present.
    Throws FileNotFoundException and NotADirectoryException if
    archive or dirpath not found
    ValueError if archive format is not supported.
    '''

    if not osp.isfile(archive):
        raise FileNotFoundException(archive)

    if not osp.isdir(dirpath):
        if createdir:
            # os.mkdir(dirpath)
            os.makedirs(dirpath)
        else:
            raise NotADirectoryException(dirpath)

    archive = osp.abspath(archive)
    dirpath = osp.abspath(dirpath)

    if archive.endswith('.tar.gz'):
        return run_cmd(['tar', '-x', '-z', '-f', archive], cwd=dirpath)[0]
    elif archive.endswith('.tgz'):
        return run_cmd(['tar', '-x', '-z', '-f', archive], cwd=dirpath)[0]
    elif archive.endswith('.tar.Z'):
        return run_cmd(['tar', '-x', '-Z', '-f', archive], cwd=dirpath)[0]
    elif archive.endswith('.tar.bz2'):
        return run_cmd(['tar', '-x', '-j', '-f', archive], cwd=dirpath)[0]
    elif archive.endswith('.tar'):
        return run_cmd(['tar', '-x', '-f', archive], cwd=dirpath)[0]
    elif archive.endswith('.tar.xz'):
        return _unpack_archive_xz(archive, dirpath)
    elif osp.splitext(archive)[1].lower() in \
            ['.zip', '.jar', '.war', '.ear']:
        return run_cmd(['unzip', '-qq', '-o', archive], cwd=dirpath)[0]
    else:
        raise ValueError('Format not supported')


def run_cmd(cmd,
            outfile=sys.stdout,
            errfile=sys.stderr,
            infile=None,
            cwd='.',
            shell=False,
            env=None):
    '''argument cmd should be a list'''
    openfile = lambda filename, mode: \
        open(filename, mode) if(isinstance(filename, str)) else filename

    out = openfile(outfile, 'w')
    err = openfile(errfile, 'w')
    inn = openfile(infile, 'r')

    if isinstance(cmd, str):
        shell = True

    environ = dict(os.environ) if env is None else env

    try:
        popen = subprocess.Popen(cmd,
                                 stdout=out,
                                 stderr=err,
                                 stdin=inn,
                                 shell=shell,
                                 cwd=cwd,
                                 env=environ)
        popen.wait()
        return (popen.returncode, environ)
    except subprocess.CalledProcessError as err:
        return (err.returncode, environ)
    finally:
        closefile = lambda filename, fileobj: \
            fileobj.close() if(isinstance(filename, str)) else None
        closefile(outfile, out)
        closefile(errfile, err)
        closefile(infile, inn)


def os_path_join(basepath, subdir):
    if subdir.startswith('/'):
        return osp.join(basepath, subdir[1:])
    else:
        return osp.join(basepath, subdir)


def glob_glob(path, pattern):
    return glob.glob(os_path_join(path, pattern))


def get_cpu_type():
    '64-bit or 32-bit'
    try:
        output = subprocess.check_output(['getconf', 'LONG_BIT'])
        return int(output.decode('utf-8').strip())
    except subprocess.CalledProcessError:
        return None


def max_cmd_size():

    # expr `getconf ARG_MAX` - `env|wc -c` - `env|wc -l` \* 4 - 2048
    arg_max = subprocess.check_output(['getconf', 'ARG_MAX'])
    arg_max = int(arg_max.decode(encoding='utf-8').strip())
    if arg_max > 131072:
        arg_max = 131072
    env_len = len(''.join([str(k) + ' ' + str(os.environ[k]) for k in os.environ.keys()]))
    env_num = len(os.environ.keys())  # for null ptr
    arg_max = arg_max - env_len - env_num * 4 - 2048  # extra caution
    return arg_max


def platform():
    if 'VMPLATNAME' in os.environ:
        return os.environ['VMPLATNAME']
    else:
        platname = os.uname()
        return platname[3] if(isinstance(platname, tuple)) else platname.version


def write_to_file(filename, obj):
    '''write a dictionary or list object to a file'''

    with open(filename, 'w') as fobj:

        if isinstance(obj, dict):
            for key in obj.keys():
                print('{0}={1}'.format(key, obj[key]), file=fobj)

        if isinstance(obj, list) or isinstance(obj, set):
            for entity in obj:
                print(entity, file=fobj)


def string_substitute_old(string_template, kwargs):

    class StringTemplate(string.Template):
        idpattern = '[_a-z][_a-z0-9-]*'

    return StringTemplate(string_template).safe_substitute(kwargs)

#PARAM_REGEX = re.compile(r'<(?P<name>[a-zA-Z][a-zA-Z_-]*)(?:[%](?P<sep>[^>]+))?>')
PARAM_REGEX = re.compile(r'<(?P<name>[a-zA-Z][a-zA-Z0-9]*([_-][a-zA-Z0-9]+)*)(?:[%](?P<sep>[^>]+))?>')

def string_substitute(string_template, symbol_table):
    '''Substitues environment variables and
    config parameters in the string.
    quotes the string and returns it'''

    new_str = string_template
    for match in PARAM_REGEX.finditer(string_template):
        name = match.groupdict()['name']
        sep = match.groupdict()['sep']

        if name in symbol_table:
            value = symbol_table[name]
            if not isinstance(value, str):
                if sep is None:
                    value = value[0]
                else:
                    value = sep.join(value)
        else:
            value = ''

        f = '<{0}>' if sep is None else '<{0}%{1}>'
        new_str = new_str.replace(f.format(match.groupdict()['name'],
                                           match.groupdict()['sep']),
                                  value, 1)

    return osp.expandvars(new_str)


def expandvar(var, kwargs):
    #val = osp.expandvars(var)
    return string_substitute(var, kwargs)

# def expandvars(kwargs):
#    new_kwargs = {key:osp.expandvars(kwargs[key]) for key in kwargs.keys()}
#    return {key:string_substitute(new_kwargs[key], new_kwargs) \
#            for key in new_kwargs.keys()}


def rmfile(filename):
    if osp.isfile(filename):
        os.remove(filename)

# Copied from Python3.3 Standard Libary shlex.py
_find_unsafe = re.compile(r'[^\w@%+=:,./-]', re.ASCII).search


def _quote(s):
    """Return a shell-escaped version of the string *s*."""
    if not s:
        return "''"
    if _find_unsafe(s) is None:
        return s

    # use single quotes, and put single quotes into double quotes
    # the string $'b is then quoted as '$'"'"'b'
    return "'" + s.replace("'", "'\"'\"'") + "'"


def quote_str(s):
    if hasattr(shlex, 'quote'):
        return shlex.quote(s)
    else:
        return _quote(s)


def get_uuid():
    return str(uuid.uuid4())


def setup_java_home(java_versions):

    # The SWAMP defaults to java8 if it is available
    java_version = 'java-8'

    # XXX should parse this for list of javas not string comparison
    # XXX breaks for java9 ... should just see what is on the platform
    # if 'java-8' in java_versions:  should work, per Vamshi for parsing
    # If multiple versions, parse them all and inf highest version!
    # XXX if 7 or 8, should choose based on other factors, for 7 gets
    # us versions of java that 8 does not.  Need to look at other things.
    # This is the wrong layer to configure this :-(
    if java_versions == 'java-7 java-8':
        java_version = 'java-8'
    elif java_versions == '' or java_versions.isspace():
        java_version = 'java-8'
    else:
        java_version = java_versions

    plat_name = os.getenv('VMPLATNAME')


    # if JAVA_HOME already setup by startup, leave it alone; this is
    # required because different android SDKs require different java
    # versions; this is a SDK issue and mandated by the SDK.
    # could tag android_java_home to make this logic easier to deal with,
    ## XXX this will break tools... the tools need to be able to specify
    ## "system java" so android lint ... prototype first!
    ## XXX still need this because assess mess
    ## XX this breaks assessments on all jobs, not just android, see
    ## notes in build.
    ## The tool default version is java-7, but now android-lint will either
    ## need that, or the android sdk java.  This takes care of that fallback.
    if java_version == 'java-android-sdk':
        android_home = os.getenv('ANDROID_HOME', '')
        if android_home != '':
            java_home = os.getenv('ANDROID_JAVA_HOME', '')
            logging.info("ANDROID_HOME '%s', ANDROID_JAVA_HOME '%s'", os.getenv('ANDROID_HOME', ''), os.getenv('ANDROID_JAVA_HOME', ''))
            if java_home != '':
                logging.info("setup_java: ANDROID controls JAVA")
                return

        # if we get here, fallback
        java_version = 'java-7'
        logging.info("setup_java: java-android-sdk: %s", java_version)
       

    # this is so wrong, this should be a PLATFORM issue, not on
    # assesment framework issue
    # This is also broken because we should really setup the
    # alternatives system so that any random java use will get the
    # right java.   Which causes problems in it's own right.
    # Same OSeshave a command to run, and this should be a part
    # of the platform layer for swamp.
    os_family = {
        'rhel-6.4-64': 'rh-like',
        'rhel-6.4-32': 'rh-like',
        'scientific-6.4-64': 'rh-like',

        'scientific-5.9-64': 'rh-like',
        'scientific-5.9-32': 'rh-like',

        'rhel-6.7-64': 'rh-like',
        'rhel-6.7-32': 'rh-like',
        'centos-6.7-64': 'rh-like',
        'centos-6.7-32': 'rh-like',
        'scientific-6.7-64': 'rh-like',
        'scientific-6.7-32': 'rh-like',

        'rhel-6.8-64': 'rh-like',
        'rhel-6.8-32': 'rh-like',
        'centos-6.8-64': 'rh-like',
        'centos-6.8-32': 'rh-like',
        'scientific-6.8-64': 'rh-like',
        'scientific-6.8-32': 'rh-like',

        'rhel-6.9-64': 'rh-like',
        'rhel-6.9-32': 'rh-like',
        'centos-6.9-64': 'rh-like',
        'centos-6.9-32': 'rh-like',
        'scientific-6.9-64': 'rh-like',
        'scientific-6.9-32': 'rh-like',

        'rhel-6.10-64': 'rh-like',
        'rhel-6.10-32': 'rh-like',
        'centos-6.10-64': 'rh-like',
        'centos-6.10-32': 'rh-like',
        'scientific-6.10-64': 'rh-like',
        'scientific-6.10-32': 'rh-like',

        'rhel-6.11-64': 'rh-like',
        'rhel-6.11-32': 'rh-like',
        'centos-6.11-64': 'rh-like',
        'centos-6.11-32': 'rh-like',
        'scientific-6.11-64': 'rh-like',
        'scientific-6.11-32': 'rh-like',

        'rhel-7.1-64': 'rh-like',
        'centos-7.1-64': 'rh-like',
        'scientific-7.1-64': 'rh-like',

        'rhel-7.2-64': 'rh-like',
        'centos-7.2-64': 'rh-like',
        'scientific-7.2-64': 'rh-like',

        'rhel-7.3-64': 'rh-like',
        'centos-7.3-64': 'rh-like',
        'scientific-7.3-64': 'rh-like',

        'centos-7.4-64': 'rh-like',
        'centos-7.4-32': 'rh-like',
        'rhel-7.4-64': 'rh-like',
        'scientific-7.4-64': 'rh-like',

        'centos-5.11-64': 'rh-like',
        'centos-5.11-32': 'rh-like',
        'rhel-5.11-64': 'rh-like',
        'rhel-5.11-32': 'rh-like',
        'scientific-5.11-64': 'rh-like',
        'scientific-5.11-32': 'rh-like',

        'centos-5.12-64': 'rh-like',
        'centos-5.12-32': 'rh-like',
        'rhel-5.12-64': 'rh-like',
        'rhel-5.12-32': 'rh-like',
        'scientific-5.12-64': 'rh-like',
        'scientific-5.12-32': 'rh-like',

        # old school fedora names; once everything is transitiond,
        # only need to retain original fedora-18.0 and fedora-19.0 -64
        'fedora-18.0-64': 'rh-like',
        'fedora-19.0-64': 'rh-like',

        'fedora-18.0-32': 'rh-like',
        'fedora-19.0-32': 'rh-like',

        # new school fedora names (matching OS) -- wave of the future
        'fedora-17-64': 'r7-like',
        'fedora-18-64': 'rh-like',
        'fedora-19-64': 'rh-like',
        'fedora-20-64': 'rh-like',
        'fedora-21-64': 'rh8-like',
        'fedora-22-64': 'rh8-like',
        'fedora-23-64': 'rh8-like',
        'fedora-24-64': 'rh8-like',
        'fedora-25-64': 'rh8-like',
        'fedora-26-64': 'rh8-like',
        'fedora-27-64': 'rh8-like',

        'fedora-17-32': 'r7-like',
        'fedora-18-32': 'rh-like',
        'fedora-19-32': 'rh-like',
        'fedora-20-32': 'rh-like',
        'fedora-21-32': 'rh8-like',
        'fedora-22-32': 'rh8-like',
        'fedora-23-32': 'rh8-like',
        'fedora-24-32': 'rh8-like',
        'fedora-25-32': 'rh8-like',
        'fedora-26-32': 'rh8-like',
        'fedora-27-32': 'rh8-like',

        # only works for 64 bit java on these platforms; need db-32-like OTW
        # java 8 isn't supporeted on debian-7 at this time
        'debian-7.0-64': 'deb-64-like',
        'debian-7.1-64': 'deb-64-like',
        'debian-7.9-64': 'deb-64-like',
        'debian-7.10-64': 'deb-64-like',
        'debian-7.11-64': 'deb-64-like',
        'debian-7.12-64': 'deb-64-like',
        'debian-7.13-64': 'deb-64-like',
        'debian-7.14-64': 'deb-64-like',

        ## debian 8 now supports java8 via backports
        'debian-8.0-64': 'deb-64-like',
        'debian-8.1-64': 'deb-64-like',
        'debian-8.2-64': 'deb-64-like',
        'debian-8.3-64': 'deb-64-like',
        'debian-8.4-64': 'deb-64-like',
        'debian-8.5-64': 'deb-64-like',
        'debian-8.6-64': 'deb-64-like',
        'debian-8.7-64': 'deb-64-like',
        'debian-8.8-64': 'deb-64-like',
        'debian-8.9-64': 'deb-64-like',
        'debian-8.10-64': 'deb-64-like',
        'debian-8.11-64': 'deb-64-like',
        'debian-8.12-64': 'deb-64-like',

        ## haven't looked at it yet, but ... at least its a check-seats tryout
        'debian-9.0-64': 'deb-64-like',
        'debian-9.1-64': 'deb-64-like',
        'debian-9.2-64': 'deb-64-like',
        'debian-9.3-64': 'deb-64-like',
        'debian-9.4-64': 'deb-64-like',
        'debian-9.5-64': 'deb-64-like',
        'debian-9.6-64': 'deb-64-like',
        'debian-9.7-64': 'deb-64-like',
        'debian-9.9-64': 'deb-64-like',
        'debian-9.10-64': 'deb-64-like',
        'debian-9.11-64': 'deb-64-like',
        'debian-9.12-64': 'deb-64-like',

        'ubuntu-10.04-64': 'deb7-64-like',
        'ubuntu-12.04-64': 'deb-64-like',
        'ubuntu-12.04.2-64': 'deb-64-like',
        'ubuntu-12.04.5-64': 'deb-64-like',
        'ubuntu-12.04.6-64': 'deb-64-like',
        'ubuntu-12.04.7-64': 'deb-64-like',
        'ubuntu-14.04-64': 'deb-64-like',
        'ubuntu-16.04-64': 'deb-64-like',
        'ubuntu-18.04-64': 'deb-64-like',

        'android-ubuntu-10.04-64': 'deb7-64-like',
        'android-ubuntu-12.04-64': 'deb-64-like',
        'android-ubuntu-12.04.2-64': 'deb-64-like',
        'android-ubuntu-12.04.5-64': 'deb-64-like',
        'android-ubuntu-12.04.6-64': 'deb-64-like',
        'android-ubuntu-12.04.7-64': 'deb-64-like',
        'android-ubuntu-14.04-64': 'deb-64-like',
        'android-ubuntu-16.04-64': 'deb-64-like',
        'android-ubuntu-18.04-64': 'deb-64-like',

        'ubuntu-10.04-32': 'deb7-32-like',
        'ubuntu-12.04-32': 'deb-32-like',
        'ubuntu-14.04-32': 'deb-32-like',
        'ubuntu-16.04-32': 'deb-32-like',
        'ubuntu-18.04-32': 'deb-32-like',

        'android-ubuntu-10.04-32': 'deb7-32-like',
        'android-ubuntu-12.04-32': 'deb-32-like',
        'android-ubuntu-14.04-32': 'deb-32-like',
        'android-ubuntu-16.04-32': 'deb-32-like',
        'android-ubuntu-18.04-32': 'deb-32-like',
    }
    if plat_name not in os_family:
        raise Exception("No configuration to set JAVA_HOME on %s", plat_name)

    # XXX on rh, we are actually using openjdk .. but not specifying it
    ## XXX if 'default' was re-looked-up as another entry, this would
    ## really do a nice job of having to copy data here.
    rh7_java = {
        'java-6':   '/usr/lib/jvm/java-1.6.0',
        'java-7':   '/usr/lib/jvm/java-1.7.0',
        'default':  '/usr/lib/jvm/java-1.7.0',
    }

    rh_java = {
        'java-6':   '/usr/lib/jvm/java-1.6.0',
        'java-7':   '/usr/lib/jvm/java-1.7.0',
        'java-8':   '/usr/lib/jvm/java-1.8.0',
        'default':  '/usr/lib/jvm/java-1.7.0',
    }

    rh8_java = {
        'java-8':   '/usr/lib/jvm/java-1.8.0',
        'default':  '/usr/lib/jvm/java-1.8.0',
    }

    # XXX could fix 32/64 bit by appending arch suffix
    deb_java7_64 = {
        'java-6':  '/usr/lib/jvm/java-6-openjdk-amd64',
        'java-7':  '/usr/lib/jvm/java-7-openjdk-amd64',
        'default': '/usr/lib/jvm/java-7-openjdk-amd64',
    }
    # no 32 bit ubuntu/debian vms; but setup if there are -- paths are correct
    deb_java7_32 = {
        'java-6':  '/usr/lib/jvm/java-6-openjdk-i386',
        'java-7':  '/usr/lib/jvm/java-7-openjdk-i386',
        'default': '/usr/lib/jvm/java-7-openjdk-i386',
    }
    deb_java_64 = {
        'java-6':  '/usr/lib/jvm/java-6-openjdk-amd64',
        'java-7':  '/usr/lib/jvm/java-7-openjdk-amd64',
        'java-8':  '/usr/lib/jvm/java-8-openjdk-amd64',
        'java-9':  '/usr/lib/jvm/java-9-openjdk-amd64',
        'default': '/usr/lib/jvm/java-7-openjdk-amd64',
    }
    # no 32 bit ubuntu/debian vms; but setup if there are -- paths are correct
    deb_java_32 = {
        'java-6':   '/usr/lib/jvm/java-6-openjdk-i386',
        'java-7':   '/usr/lib/jvm/java-7-openjdk-i386',
        'java-8':   '/usr/lib/jvm/java-8-openjdk-i386',
        'java-9':   '/usr/lib/jvm/java-9-openjdk-i386',
        'default':  '/usr/lib/jvm/java-7-openjdk-i386',
    }

    fam = os_family[plat_name]

    # getting long enough that a map could be used, but the whole
    # purpose of this thing is an interim until the platform layer
    # can provide information back to java-assess & take care of this
    # platform dependent information.

    if fam == 'rh-like':
        javas = rh_java
    elif fam == 'rh8-like':
        javas = rh8_java
    elif fam == 'rh7-like':
        javas = rh7_java
    elif fam == 'deb-64-like':
        javas = deb_java_64
    elif fam == 'deb-32-like':
        javas = deb_java_32
    elif fam == 'deb-64-like':
        javas = deb_java_64
    elif fam == 'deb-32-like':
        javas = deb_java_32
    elif fam == 'deb7-64-like':
        javas = deb_java7_64
    elif fam == 'deb7-32-like':
        javas = deb_java7_32
    else:
        logging.info("setup_java os %s -> family '%s' unknown", plat_name, fam)
        # not raising exception because we will try a fallback below

    if java_version not in javas:
        logging.info("setup_java: versions %s: version %s: not available",
                     java_versions, java_version)
        logging.info("setup_java: trying platform default")
        java_version = 'default'

    java_home = javas[java_version]
    logging.info("setup_java: version %s: home %s", java_version, java_home)

    if not java_home or not os.path.isdir(java_home):
        if java_version != 'default':
            logging.info("setup_java: java %s not found at %s",
                         java_version, java_home)
            logging.info("setup_java: versions %s trying platform default",
                         java_versions)
            java_version = 'default'
            java_home = javas[java_version]
            logging.info("setup_java: default %s, home %s", java_version,
                         java_home)

    if not os.path.isdir(java_home):
        logging.info("setup_java: version %s: NO JAVA, DEFAULT TO PLATFORM",
                     java_version)
        return

    os.environ['JAVA_HOME'] = java_home
    os.environ['PATH'] = '{0}/bin:{1}'.format(os.environ['JAVA_HOME'],
                                              os.environ['PATH'])


def ordered_list(_list):

    _set = set()
    new_list = list()

    for item in _list:
        if item not in _set:
            _set.add(item)
            new_list.append(item)

    return new_list


## XXX this has a problem.   On a 32 bit system, the most memory available
## to an assessment process to use is 4 GB.   Memory beyond 4GB
## is not considered usable on that system, due to process limitiations.
## So, we need to cap memory at 4GB on those systems.
## XXX however, the calculations for java memory use on a 32-bit machine
## with > 32 bit address lines and PAE, would allow use to use all 4GB
## of memory for that one process, still leaving plenty for the system.
## XXX This is taken care of by build_java to limit this correctly on 
## 32 bit platforms.

def sys_mem_size():
    'Returns memory in Mega bytes'
    meminfo = open('/proc/meminfo').read()
    matched = re.search(r'^MemTotal:\s+(\d+)', meminfo)
    if matched:
        # This value is in kilo bytes
        return int(int(matched.groups()[0]) / 1024)
    else:
        return 4096
        

def get_framework_version():
    
    version = pkgutil.get_data('version', 'version.txt')
    if version:
        return str(version, encoding='utf-8').strip('\n')
    else:
        return 'v.?.?.?'

