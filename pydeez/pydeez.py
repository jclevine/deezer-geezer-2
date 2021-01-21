import requests
import json
from .playlist import Playlist


class PyDeez:
    _BASE_URL = 'http://api.deezer.com'
    _MY_PLAYLISTS_URL = '{}{}'.format(_BASE_URL, '/user/me/playlists')
    _PLAYLIST_TRACKS_URL = '{}/playlist/{{}}/tracks'.format(_BASE_URL)
    _TRACK_URL = '{}/track/{{}}'.format(_BASE_URL)
    _MAX_PLAYLIST_SIZE = 2000

    def __init__(self, access_token):
        self._request_params = {
            'access_token': access_token,
            'expires': 0,
            'limit': self._MAX_PLAYLIST_SIZE
        }

    def get_playlists(self, prefixes=None):
        all_playlists = self.api_call(self._MY_PLAYLISTS_URL)

        if prefixes is None:
            return all_playlists

        return [Playlist.from_dict(playlist) for playlist
                in all_playlists
                if playlist['title'].startswith(tuple(prefixes))

    def api_call(self, url):
        return json.loads(
            requests.get(url, params=self._request_params).text)['data']
