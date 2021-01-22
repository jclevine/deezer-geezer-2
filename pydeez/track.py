from pydeez.album import Album
from pydeez.artist import Artist


class Track:
    def __init__(self, the_id, artist, album, title):
        self._id = the_id
        self._artist = artist
        self._album = album
        self._title = title

    @property
    def id(self):
        return self._id

    @property
    def artist(self):
        return self._artist.name

    @property
    def album(self):
        return self._album.title

    @property
    def title(self):
        return self._title

    @staticmethod
    def from_dict(the_dict):
        return Track(
            the_id=the_dict['id'],
            artist=Artist.from_dict(the_dict['artist']),
            album=Album.from_dict(the_dict['album']),
            title=the_dict['title']
        )

    def __eq__(self, other):
        if isinstance(other, Track):
            return self.id == other.id
        raise NotImplementedError()

    @property
    def __dict__(self):
        return {
            'id': self.id, 'artist': self.artist, 'album': self.album, 'title': self.title
        }

    def __hash__(self):
        return hash(tuple(sorted(self.__dict__.items())))

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return str({
            'id': self.id,
            'artist': self.artist,
            'album': self.album,
            'title': self.title
        })
