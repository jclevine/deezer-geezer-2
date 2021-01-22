class Album:
    def __init__(self, the_id, title):
        self._id = the_id
        self._title = title

    @property
    def id(self):
        return self._id

    @property
    def title(self):
        return self._title

    @staticmethod
    def from_dict(the_dict):
        return Album(
            the_id=the_dict['id'],
            title=the_dict['title']
        )

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return str({
            'id': self._id,
            'title': self._title
        })
