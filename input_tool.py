def get_input_list():
    prefixes = []
    prefix = None
    while prefix != '':
        prefix = input(': ')

        if prefix == '':
            return prefixes
        else:
            prefixes.append(prefix)


def yes_no_query(text, default=False):
    text_response = input(text + ' ' + build_yes_no_default_text(default)).lower()

    if not text_response:
        return default
    else:
        return text_response == 'y'


def build_yes_no_default_text(default):
    return '[Y/n] ' if default else '[y/N] '
