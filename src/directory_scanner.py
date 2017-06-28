import os
import os.path as osp
import glob
import re
import logging

import plyj.parser
from . import utillib


class PlyjParsingError(Exception):

    def __init__(self):
        Exception.__init__(self)


class JavaParser():

    java_parser = None

    @classmethod
    def init(cls):
        cls.java_parser = plyj.parser.Parser(logging.getLogger(''))

    @classmethod
    def get_pkg_name(cls, filepath, encoding):

        if cls.java_parser is None:
            cls.init()

        if (osp.splitext(filepath)[1] == '.java') and osp.isfile(filepath):
            parse_tree_obj = cls.java_parser.parse_file(filepath, encoding)
            if hasattr(parse_tree_obj, 'package_declaration'):
                pkg_dec = parse_tree_obj.package_declaration
                if pkg_dec:
                    return pkg_dec.name.value
                else:
                    return None

    @classmethod
    def get_class_name(cls, filepath, encoding):
        'Class name return is <packagename>.<classname>'
        if cls.java_parser is None:
            cls.init()

        if (osp.splitext(filepath)[1] == '.java') and osp.isfile(filepath):
            parse_tree_obj = cls.java_parser.parse_file(filepath, encoding)

            if parse_tree_obj is None:
                raise PlyjParsingError('JavaParser fails for %s' % filepath)

            class_name = None
            if hasattr(parse_tree_obj, 'type_declarations') and \
               parse_tree_obj.type_declarations is not None and \
               (len(parse_tree_obj.type_declarations) > 0):

                for type_dec in parse_tree_obj.type_declarations:
                    if isinstance(type_dec, plyj.model.InterfaceDeclaration) or \
                       isinstance(type_dec, plyj.model.EnumDeclaration) or \
                       isinstance(type_dec, plyj.model.AnnotationDeclaration) or \
                       isinstance(type_dec, plyj.model.ClassDeclaration):
                        class_name = type_dec.name
                        break

            if class_name is None:
                return None

            pkg_name = None
            if hasattr(parse_tree_obj, 'package_declaration') and \
               parse_tree_obj.package_declaration is not None and \
               (len(parse_tree_obj.package_declaration.name.value) > 0):
                pkg_name = parse_tree_obj.package_declaration.name.value

            if pkg_name:
                return '{0}.{1}'.format(pkg_name, class_name)
            else:
                return class_name


def _listdir(dirpath, pattern):
    '''Recurively scans the directory for files that match the pattern.

    returns a list of files in the directory that match the pattern
    '''

    if pattern is None:
        pattern = '**/*.java'

    if pattern.find('**') != -1:
        head, _, tail = pattern.partition('**')

        # if the pattern repeats call listdir recursively
        func = utillib.glob_glob if(tail.find('**') != -1) else _listdir

        all_files = list()
        for paths, _, _ in os.walk(utillib.os_path_join(dirpath, head)):
            all_files = all_files + func(paths, tail)
        return all_files
    else:
        return utillib.glob_glob(dirpath, pattern)


def get_files(dirpath, include, exclude=None):
    '''Recursively finds files in the 'dirpath'
    Filters them based on 'include and exclude files
    '''

    ifiles = set(_listdir(dirpath, include))
    if (len(ifiles) > 0) and (exclude is not None):
        efiles = set(_listdir(dirpath, exclude))
        ifiles = ifiles.difference(efiles)
    return list(ifiles)


def get_files_in_dirs(dirpaths, includes, excludes):
    '''Recursively finds files in the 'dirpath'
    Filters them based on 'include and exclude files
    dirpaths, includes, excludes here are lists/sets'''

    includefiles = set()

    for dirpath in dirpaths:
        for inc in includes:
            includefiles.update(get_files(dirpath, inc))

    excludefiles = set()

    if excludes:
        for dirpath in dirpaths:
            for exc in excludes:
                excludefiles.update(get_files(dirpath, exc))

    return includefiles.difference(excludefiles)


def get_class_file(srcfile, encoding, destdir, all_class_files):
    '''Get a .class file(s) for the given java source file.
    This method also searches for inner classes'''

    try:
        class_name = JavaParser.get_class_name(srcfile, encoding)
    except PlyjParsingError as err:
        logging.error(err)
        return None

    if class_name is None:
        return None

    class_file_prefix = utillib.os_path_join(destdir, class_name.replace('.', '/'))
    files = set()

    '''if a class files list is passed as all_class_files argument,
    searches in the list, else searches on the file system '''
    # if (all_class_files is Not None) and (len(all_class_files) > 0):
    if all_class_files:
        if (class_file_prefix + '.class') in all_class_files:
            files.add(class_file_prefix + '.class')

            pattern = re.compile(class_file_prefix + r'(?:\${1,2}[\w]+)+[.]class')
            files.update(f for f in all_class_files if(pattern.match(f) is not None))
    else:
        if osp.isfile(class_file_prefix + '.class'):
            files.add(class_file_prefix + '.class')
            #'$* as glob.glob is not a regex'
            files.update(glob.glob(class_file_prefix + '$*.class'))

    return list(files)
