import requests
import json
from .playlist import Playlist
from .track import Track
from tqdm import tqdm


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
        all_playlists = self.api_call(self._MY_PLAYLISTS_URL)['data']

        if prefixes is None:
            return all_playlists

        return [Playlist.from_dict(playlist) for playlist
                in all_playlists
                if playlist['title'].startswith(tuple(prefixes))]

    def api_call(self, url):
        return json.loads(
            requests.get(url, params=self._request_params).text)

    def get_tracks_for_playlists(self, playlists):
        return self._flatten([self.get_tracks_for_playlist(playlist)
                              for playlist
                              in tqdm(playlists)])

    @staticmethod
    def _flatten(list_of_lists):
        return [item for a_list in list_of_lists for item in a_list]

    def get_tracks_for_playlist(self, playlist):
        return self._get_all_pages(
            self._PLAYLIST_TRACKS_URL.format(playlist.id),
            lambda track: Track.from_dict(track))

    def _get_all_pages(self, url, from_dict):
        page = self.api_call(url)
        if 'next' not in page:
            return [from_dict(page) for page in page['data']]
        else:
            return [page for page in tqdm(page['data'])] + self._get_all_pages(page['next'])

    def create_playlists(self, tracks, new_playlist_name_prefix):
        playlist_chunks = self.chunkify(tracks, self._MAX_PLAYLIST_SIZE)
        pass

    @staticmethod
    def chunkify(a_list, sublist_size):
        return [a_list[i:i + sublist_size] for i in range(0, len(a_list), sublist_size)]
