class Artist:
    def __init__(self, the_id, name):
        self._id = the_id
        self._name = name

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @staticmethod
    def from_dict(the_dict):
        return Artist(
            the_id=the_dict['id'] if 'id' in the_dict else 0,
            name=the_dict['name']
        )

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return str({
            'id': self._id,
            'title': self.names
        })
