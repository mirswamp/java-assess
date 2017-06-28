import sys
import os
import os.path as osp
import logging

import ply.lex as lex
import ply.yacc as yacc
from . import utillib


tokens = (
    'QSTRING',
    'PARAM',
    'SEPERATER',
    'OPTIONNAME',
    'STRING',
    'NEWLINE'
)

t_QSTRING = r'[\"][^\"]+[\"]'
t_PARAM = r'<[a-zA-Z][a-zA-Z0-9_-]*(?:[%][^>]+)?>'
t_SEPERATER = r'[:=/]'
t_OPTIONNAME = r'(-{1,2}|[+])[a-zA-Z][a-zA-Z0-9]*(?:[_.-]?[a-zA-Z0-9]+)*'
t_STRING = r'[\w\d\.-]+'
t_ignore = ' \t\v\r'  # whitespace


def t_NEWLINE(t):
    r'\n+'
    t.lexer.lineno = len(t.value)
    t.value = '\n'
    return t


def t_error(t):
    logging.error("Lexer: Illegal character " + t.value)
    t.lexer.skip(1)

lexer = lex.lex(lextab='gencmd_lextab',
                debuglog=logging.getLogger(''),
                errorlog=logging.getLogger(''))


def _get_string(arg):
    '''arg : can be a filename or string'''

    if osp.isfile(arg):
        with open(arg, 'r') as f:
            return ''.join(f)
    else:
        return arg


def tokenize(input_str):
    '''
    This function uses the lexer and tokenizes
    the given input string
    '''
    result = list()
    lexer.lineno = 1
    lexer.input(input_str)
    for tok in lexer:
        if not tok:
            break
        else:
            result.append((tok.type, tok.value))
    return result


def p_command(p):
    '''command : executable NEWLINE args'''
    p[0] = ('command', p[1], p[3])


def p_executable(p):
    '''executable : param
                  | string
                  | quotedstring
    '''
    p[0] = p[1]


def p_args(p):
    '''args : arg NEWLINE args '''
    p[0] = [p[1]] + p[3]


def p_args_empty(p):
    '''args : empty'''
    p[0] = []


def p_arg(p):
    '''arg : option
            | string
            | quotedstring
            | param
    '''
    p[0] = p[1]


def p_string(p):
    '''string : STRING'''
    p[0] = ('string', p[1])


def p_quotedstring(p):
    '''quotedstring : QSTRING'''
    p[0] = ('quotedstring', p[1])


def p_option(p):
    '''option : OPTIONNAME'''
    p[0] = ('option', p[1], None, None)


def p_option_value(p):
    '''option : OPTIONNAME optionarg'''
    p[0] = ('option', p[1], None, p[2])


def p_option_sep_value(p):
    '''option : OPTIONNAME SEPERATER optionarg'''
    p[0] = ('option', p[1], p[2], p[3])


def p_optionarg(p):
    '''optionarg : param
                | quotedstring
                | string
    '''
    p[0] = p[1]


def p_param(p):
    '''param : PARAM'''
    name, seperator = _get_param(p[1])
    p[0] = ('parameter', name, seperator)


def p_empty(p):
    '''empty : '''
    pass


def p_error(p):
    logging.error("Syntax error at '%s'", p)


def _get_param(param):

    match = utillib.PARAM_REGEX.match(param)

    if not match:
        raise Exception('not a valid parameter' + param)

    name = match.group('name')
    # sep = match.group('sep') if(match.group('sep') != None) else None
    sep = match.group('sep')

    return (name, sep)

parser = yacc.yacc(debug=True,
                   tabmodule='gencmd_parsetab',
                   start='command',
                   debuglog=logging.getLogger(''),
                   errorlog=logging.getLogger(''))


def parse_str(input_str):
    '''Returns AST'''
    return parser.parse(input_str, lexer=lexer)


def process_obj(obj, symbol_table):

    if obj is None:
        return None
    elif obj[0] == 'string':
        return obj[1]
    elif obj[0] == 'quotedstring':
        return process_quotedstring(obj[1], symbol_table)
    elif obj[0] == 'parameter':
        return process_parameter(obj[1:], symbol_table)
    elif obj[0] == 'option':
        return process_option(obj[1:], symbol_table)
    else:
        raise Exception('Token type Not found:' + obj)


def _add_sep(sep, _list):

    if len(_list) > 0:
        for l in _list[:-1]:
            yield l
            yield sep

        yield _list[-1]


def process_parameter(obj, symbol_table):
    '''obj: is a tuple (symbol_name, seperator)'''

    name = obj[0]
    sep = obj[1]

    if name not in symbol_table:
        return None
    else:
        value = symbol_table[name]

    if isinstance(value, str):
        return value

    # if there is a seperator
    if sep is None:
        # value is a list
        return value[0]
    elif sep.isspace():
        return value
    elif sep.strip() == sep:
        return sep.join(value)
    else:
        return [val for val in _add_sep(sep.strip(), value)]


def process_option(obj, symbol_table):
    '''obj is a tuple optionname, sep, (value)'''

    name = obj[0]
    sep = obj[1]
    val = obj[2]

    if val is None:
        return name
    else:
        val = process_obj(val, symbol_table)
        if val is None:
            return None

        if sep is None:
            if isinstance(val, str):
                return [name, val]
            else:
                return [name] + val
        else:
            if isinstance(val, str):
                return '{0}{1}{2}'.format(name, sep, val)
            else:
                return '{0}{1}{2}'.format(name, sep, ''.join(val))


def process_quotedstring_old(qstr, symbol_table):
    '''Substitues environment variables and
    config parameters in the string.
    quotes the string and returns it'''

    qstr_new = qstr
    for match in utillib.PARAM_REGEX.finditer(qstr):
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
        qstr_new = qstr_new.replace(f.format(match.groupdict()['name'],
                                             match.groupdict()['sep']),
                                    value, 1)

    qstr_new = utillib.string_substitute(qstr_new, os.environ)

    # return utillib.quote_str(qstr_new[1:-1])
    return qstr_new[1:-1]


def process_quotedstring(string_template, symbol_table):
    '''Substitues environment variables and
    config parameters in the string.'''
    return utillib.string_substitute(string_template, symbol_table)[1:-1]


def gencmd(str_or_file, symbol_table):
    '''str_or_file: Can be a file or a string'''
    input_str = _get_string(str_or_file)
    ast = parse_str(input_str)

    if isinstance(ast, tuple) and (ast[0] == 'command'):
        cmd = list()
        exe = process_obj(ast[1], symbol_table)

        if (exe is None) or (not isinstance(exe, str)):
            raise Exception('No valid executable in the command')
        else:
            cmd.append(exe)

        for arg in ast[2]:
            val = process_obj(arg, symbol_table)
            if isinstance(val, str):
                cmd.append(val)
            if isinstance(val, list):
                cmd.extend(val)

        # return [arg.strip() for arg in cmd if arg is not None]
        return cmd
    else:
        raise Exception('AST not correct')


def get_param_list(filename):
    _tokens = tokenize(_get_string(filename))
    param_list = list()

    for name, value in _tokens:
        if name == 'PARAM':
            m = utillib.PARAM_REGEX.match(value)
            # if m is not None and 'name' in m.groupdict():
            if m and 'name' in m.groupdict():
                param_list.append(m.groupdict()['name'])
    return param_list


if __name__ == '__main__':
    # print(tokenize(_get_string(sys.argv[1])))
    print(parse_str(_get_string(sys.argv[1])))
