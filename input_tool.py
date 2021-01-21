def get_input_list():
    prefixes = []
    prefix = None
    while prefix != '':
        prefix = input(': ')

        if prefix == '':
            return prefixes
        else:
            prefixes.append(prefix)
