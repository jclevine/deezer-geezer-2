class Playlist:
    def __init__(self, the_id, title, track_count):
        self._id = the_id
        self._title = title
        self._track_count = track_count

    @property
    def title(self):
        return self._title

    @property
    def track_count(self):
        return self._track_count

    @staticmethod
    def from_dict(the_dict):
        return Playlist(
            the_id=the_dict['id'],
            title=the_dict['title'],
            track_count=the_dict['nb_tracks']
        )

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return str({
            'id': self._id,
            'title': self._title,
            'track_count': self._track_count
        })
