import atexit
import fcntl
import os
import struct
import sys
import termios
import time
import tty
import logging

# from koi.row import Row

class Row(object):
    def __init__(self, chars, idx):
        self.chars = chars
        self.idx = idx
        # self.hl_open_comment = 0

    @property
    def render(self):  # TODO: rename
        # equivalent to editorUpdateRow
        return self.chars.replace('\t', ' ' * TAB_STOP)


fd = sys.stdin.fileno()
VERSION = '0.0.1'
QUIT_TIMES = 1 # wtf?
TAB_STOP = 4
CONFIG = {
    'original_termios': [],  # or None?

    'cx': 0, # cursor co-ordinates
    'cy': 0,
    'rx': 0, # cursor co-ordinate for 'render' field
    'row_off': 0, # current row user has scrolled to
    'col_off': 0, # current col user has scrolled to

    'screen_rows': 0,
    'screen_cols': 0,

    'row': [],
    'dirty': 0,  # probably should be bool
    'filename': None,  # or ''?
    'status_msg': '',
    'status_msg_time': 0,
    # 'syntax': None,
    'quit_times': QUIT_TIMES,
}

# ### terminal ###
# TODO: assign as sys.excepthook??
def die_hook(err_val):
    os.write(fd, '\x1b[2J'.encode('utf-8'))  # <esc>[1J -> (VT100) clear entire screen
    os.write(fd, '\x1b[H'.encode('utf-8'))   # re-position cursor back at top left
    # termios.tcsetattr(fd, termios.TCSAFLUSH, CONFIG['original_termios'])  # TODO: invoke here?
    logging.error(err_val)
    sys.exit(1)

def enable_raw_mode():
    CONFIG['original_termios'] = termios.tcgetattr(fd)
    tty.setraw(fd)

@atexit.register
def on_exit():
    os.write(fd, '\x1b[2J'.encode('utf-8'))  # <esc>[1J -> (VT100) clear entire screen
    os.write(fd, '\x1b[H'.encode('utf-8'))   # re-position cursor back at top left
    termios.tcsetattr(fd, termios.TCSAFLUSH, CONFIG['original_termios'])

def get_window_size():
    import shutil
    try:
        size = shutil.get_terminal_size()
    except IOError:  # TODO: is it IOError? Do we need this?
        os.write(fd, '\x1b[999C\x1b[999B'.encode('utf-8'))  # 999C moves cursor right, 999B -> down, 999 shows how many positions
        size = get_cursor_position()
    return dict(zip(('screen_cols', 'screen_rows'), size))

def get_cursor_position():
    os.write(fd, '\x1b[6n'.encode('utf-8'))
    output = os.read(fd, 10)  # TODO: length is 32 in C version
    left, right = output.split(';'.encode('utf-8'))  # TODO: verify
    return int(left[2:]), int(right[:2])

# ### row operations ###
def row_cx_to_rx(row, cx):
    # For each character, if it’s a tab we use rx % TAB_STOP to find out how many columns we are to the right of the last tab stop,
    # and then subtract that from TAB_STOP - 1 to find out how many columns we are to the left of the next tab stop.
    # We add that amount to rx to get just to the left of the next tab stop,
    # and then the unconditional rx++ statement gets us right on the next tab stop.
    # This works even if we are currently on a tab stop.

    rx = 0
    for i in range(cx):
        if row.chars[i] == '\t':
            rx += (TAB_STOP - 1) - (rx % TAB_STOP)
        rx += 1
    return rx

# ### editor ops
def editor_insert_row(at, string):
    # if (at < 0 || at > EDITOR_CONFIG.num_rows)
    #     return;

    rows = CONFIG['row']
    for i, row in enumerate(rows[at:], start=at + 1):
        row.idx += 1
    rows.insert(at, Row(string, at))

    # EDITOR_CONFIG.num_rows++; # de don't need this
    # EDITOR_CONFIG.dirty++;  #TODO: effectively '=1' will do

# ### file IO ###
def editor_open(filename):
    CONFIG['filename'] = filename
    # select_syntax_highlight()  # TODO: enable later

    with open(filename, 'r') as f:
        line = None
        for i, line in enumerate(f.readlines()):
            if line and line[-1] in ('\r', '\n'):
                # TODO: refactor
                editor_insert_row(i, line[:-1])
            else:
                editor_insert_row(i, line)
        else:  # wtf?!
            if line and line[-1] in ('\r', '\n'):
                editor_insert_row(i, '')
        CONFIG['dirty'] = 0  # it's been incremented when calling editorInsertRow -> TODO: fix?!

# ### output ###
def editor_scroll():
    CONFIG['rx'] = 0
    if CONFIG['cy'] < len(CONFIG['row']):
        CONFIG['rx'] = row_cx_to_rx(CONFIG['row'][CONFIG['cy']], CONFIG['cx'])

    # vertical scrolling
    # re-adjust row_offset to follow cursor above top of visible screen
    if CONFIG['cy'] < CONFIG['row_off']:
        CONFIG['row_off'] = CONFIG['cy']
    if CONFIG['cy'] >= CONFIG['row_off'] + CONFIG['screen_rows']:
        # follow cursor below bottom of visible screen
        CONFIG['row_off'] = CONFIG['cy'] - CONFIG['screen_rows'] + 1

    # horizontal scrolling
    if CONFIG['rx'] < CONFIG['col_off']:
        CONFIG['col_off'] = CONFIG['rx']
    if CONFIG['rx'] >= CONFIG['col_off'] + CONFIG['screen_cols']:
        CONFIG['col_off'] = CONFIG['rx'] - CONFIG['screen_cols'] + 1

def refresh_screen():
    editor_scroll()

    buffer = ''
    buffer += '\x1b[?25l'  # hide cursor -> avoid flickering while writing tildes etc
    buffer += '\x1b[H'     # <esc>[1J -> (VT100) clear entire screen
    buffer += draw_rows()

    buffer += draw_status_bar()
    # buffer += draw_message_bar()
    buffer += '\x1b[%d;%dH' % ((CONFIG['cy'] - CONFIG['row_off']) + 1,
                               (CONFIG['rx'] - CONFIG['col_off']) + 1)
    buffer += '\x1b[?25h'

    os.write(0, buffer.encode('utf-8'))

def draw_rows():
    # TODO: add line numbers
    width = CONFIG['screen_cols']
    buffer = ''
    for i in range(CONFIG['screen_rows']):
        file_row = i + CONFIG['row_off']
        if file_row >= len(CONFIG['row']):
            if len(CONFIG['row']) == 0 and i == CONFIG['screen_rows'] // 3:
                welcome = f"No, it's not VIM -- version {VERSION}"
                buffer += '~' + welcome[:width].center(width)[1:]
            else:
                # draws vim-like tildes
                buffer += '~'
        else:pass
            # current_color = -1
            # print >> sys.stderr, CONFIG['row'][filerow].hl
            # for s, i in zip(CONFIG['row'][filerow].render,
            #                 CONFIG['row'][filerow].hl)[CONFIG['coloff']:][:width]:
            #     color = SYNTAX_TO_COLOR[i]
            #     code = ord(s)
            #     if curses.ascii.iscntrl(code):
            #         sym = chr(ord('@') + code) if code <= 26 else '?'
            #         buffer += '\x1b[7m' + sym + '\x1b[m'
            #         if current_color != -1:
            #             buffer += '\x1b[%dm' % current_color
            #     elif color == current_color:
            #         buffer += s
            #     else:
            #         buffer += '\x1b[%dm%s' % (color, s)
            #         current_color = color
            # buffer += '\x1b[39m'

            # buffer += CONFIG['row'][file_row].render # TODO???

        # erase line to the right of cursor -> instead of clearing entire screen ("\x1b[2J")
        buffer += '\x1b[K\r\n'
    return buffer

def draw_status_bar():
    filename = CONFIG['filename'][:20] if CONFIG['filename'] else '[No Name]'
    status = '%s - %d lines %d:%d %s' % (filename, len(CONFIG['row']),
                                         CONFIG['cy'], CONFIG['cx'],
                                         "(modified)" if CONFIG['dirty'] else '')
    rstatus = '%s | %d/%d' % (
        # CONFIG['syntax']['filetype'] if CONFIG['syntax'] else 'no ft',
        'no ft',
        CONFIG['cy'] + 1,
        len(CONFIG['row']))
    rstatus = rstatus.rjust(CONFIG['screen_cols'] - len(status))
    return '\x1b[7m' + (status + rstatus)[:CONFIG['screen_cols']] + '\x1b[m\r\n'

def set_status_message(fmt, *args):  # TODO: remove args
    CONFIG['status_msg'] = fmt
    CONFIG['status_msg_time'] = time.time()

# ### init ###
def init_editor():
    CONFIG.update(get_window_size())
    CONFIG['screen_rows'] -= 2  # make space for status bar and message bar at the bottom  # FIXME
    set_status_message('HELP: Ctrl-S = save | Ctrl-Q = quit')# | Ctrl-F = find')

def main():
    # fd = sys.stdin.fileno()
    enable_raw_mode()
    init_editor()
    if len(sys.argv) > 1:
        editor_open(sys.argv[1])
    # C version -> set_status_message() here instead of in init_editor

    while True:
        refresh_screen()
    #     process_key_press(fd)

if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, Exception) as e:
        die_hook(e)
