class Track:
    def __init__(self, the_id, artist, album, title):
        self._id = the_id
        self._artist = artist
        self._album = album
        self._title = title

    @property
    def id(self):
        return self._id

    @staticmethod
    def from_dict(the_dict):
        return Track(
            the_id=the_dict['id'],
            artist=the_dict['artist'],
            album=the_dict['album'],
            title=the_dict['title']
        )

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return str({
            'id': self._id,
            'artist': self._artist,
            'album': self._album,
            'title': self._title
        })
