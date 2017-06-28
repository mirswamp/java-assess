import os
import os.path as osp
import logging
import logging.handlers
import sys
import time
import textwrap


class StreamHandlerCustom(logging.StreamHandler):

    def __init__(self, stream=None):
        super().__init__(stream)

    def handle(self, record):
        super().handle(record)
        self.flush()


class LogTaskStatus():
    ''' For Logging Task times and status PASS/FAIL/SKIP
    Format:
    PASS|FAIL|SKIP: <task-name> <task-msg>                                             <time-taken>
      ----------
      <task-msg-indetail-line1>
      <task-msg-indetail-line2>
      <task-msg-indetail-line3>
      ...
      ...
      ----------
    '''
    
    def __init__(self, task, exit_code=0, msg_inline=None, msg_indetail=None):

        self.task = str(task)
        self.exit_code = exit_code
        self.msg_inline = msg_inline
        self.msg_indetail = msg_indetail
        self.skip = False
        self.textwrapper = textwrap.TextWrapper(width=64,
                                                initial_indent='  ',
                                                subsequent_indent='  ',
                                                break_on_hyphens=False)

    def __enter__(self):
        self.start_time = time.time()
        return self
    
    @classmethod
    def status_begin(cls):
        logging.getLogger('.status-logger').log(60, 'NOTE: begin')

    @classmethod
    def status_end(cls):
        logging.getLogger('.status-logger').log(60, 'NOTE: end')

    @classmethod
    def log_task(cls, task, exit_code=0, msg_inline=None, msg_indetail=None):
        log_task_status = LogTaskStatus(task,
                                        exit_code,
                                        msg_inline,
                                        msg_indetail)
        log_task_status.write_notime()
        
    @classmethod
    def get_status_str_cls(cls,
                           taskname,
                           skip,
                           exit_code,
                           msg_inline,
                           time_spent):

        if skip:
            status_str = 'SKIP'
        else:
            status_str = 'PASS' if(exit_code == 0) else 'FAIL'

        if msg_inline:
            task_str = '{0} ({1})'.format(taskname, msg_inline)
        else:
            task_str = taskname

        return '{0}: {1:{text_width}} {2:{time_width}.6f}s'.format(status_str,
                                                                   task_str,
                                                                   time_spent,
                                                                   text_width=59,
                                                                   time_width=13)

    def get_status_str(self, with_time=True):

        if self.skip:
            status_str = 'SKIP'
        else:
            status_str = 'PASS' if(self.exit_code == 0) else 'FAIL'

        task_str = '{0} ({1})'.format(self.task, self.msg_inline) if self.msg_inline else self.task

        if with_time:
            return '{0}: {1:{text_width}} {2:{time_width}.6f}s'.format(status_str,
                                                                       task_str,
                                                                       self.end_time - self.start_time,
                                                                       text_width=59,
                                                                       time_width=13)
        else:
            return '{0}: {1:{text_width}}'.format(status_str,
                                                  task_str,
                                                  text_width=59,
                                                  time_width=13)

    def get_formatted_msg(self, msg_indetail):
        '''  ----------
             Multiline Message
             ----------
        '''
        sep = '-' * 10
        #msg = '\n'.join([self.textwrapper.fill(s)
        #                 for s in msg_indetail.splitlines()])
        #return '''  {0}\n{1}\n  {0}'''.format(sep, msg)
        return '''  {0}\n  {1}\n  {0}'''.format(sep,
                                                '\n  '.join([s for s in msg_indetail.splitlines()]))

    def skip_task(self, msg_inline=None, msg_indetail=None):
        self.skip = True

        if msg_inline:
            self.msg_inline = msg_inline

        if msg_indetail:
            self.msg_indetail = msg_indetail

    def update_task_status(self, exit_code, msg_inline=None, msg_indetail=None):
        self.exit_code = exit_code

        if msg_inline:
            self.msg_inline = msg_inline

        if msg_indetail:
            self.msg_indetail = msg_indetail

    def write(self, retry):
        logging.getLogger('.status-logger').log(60, self.get_status_str())

        if self.msg_indetail:
            logging.getLogger('.status-logger').log(60,
                                                    self.get_formatted_msg(self.msg_indetail))

        if retry:
            logging.getLogger('.status-logger').log(60, 'NOTE: retry')
    
    def write_notime(self):
        logging.getLogger('.status-logger').log(60, self.get_status_str(False))

        if self.msg_indetail:
            logging.getLogger('.status-logger').log(60,
                                                    self.get_formatted_msg(self.msg_indetail))

    def __exit__(self, exception_type, exception, traceback):
        self.end_time = time.time()

        if exception:
            exit_code = exception.errno if(hasattr(exception, 'errno')) else 1
            msg_indetail = str(exception) if str(exception) != "None" else None
            self.update_task_status(exit_code, None, msg_indetail)

        self.write(exception and hasattr(exception, 'retry') and exception.retry is True)


def init(output_dir=os.getcwd()):

    logging.addLevelName(60, 'STATUS')

    debug_file_handler = logging.handlers.WatchedFileHandler(osp.join(output_dir,
                                                                      'debug.out'), 'w')
    debug_file_handler.setFormatter(logging.Formatter(
        '%(module)s: %(lineno)d: %(levelname)s: %(message)s'))
    debug_file_handler.set_name('debug-file-handler')
    debug_file_handler.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(debug_file_handler)

    stream_handler = StreamHandlerCustom(sys.stdout)
    stream_handler.setFormatter(logging.Formatter('%(message)s'))
    stream_handler.set_name('stream-handler')
    stream_handler.setLevel(logging.INFO)
    logging.getLogger('').addHandler(stream_handler)

    logging.getLogger('').setLevel(logging.DEBUG)

    status_file_handler = logging.handlers.WatchedFileHandler(osp.join(output_dir,
                                                                       'status.out'), 'w')
    status_file_handler.setFormatter(logging.Formatter('%(message)s'))
    status_file_handler.set_name('status-file-handler')
    status_file_handler.setLevel(60)
    logging.getLogger('.status-logger').addHandler(status_file_handler)
    logging.getLogger('.status-logger').propagate = False

    LogTaskStatus.status_begin()


def shutdown():
    LogTaskStatus.status_end()
    logging.shutdown()

