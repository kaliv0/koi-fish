TAB_STOP = 4

class Row(object):
    def __init__(self, chars, idx):
        self.chars = chars
        self.idx = idx
        # self.hl_open_comment = 0

    @property
    def render(self):  # TODO: rename
        # equivalent to editorUpdateRow
        return self.chars.replace('\t', ' ' * TAB_STOP)