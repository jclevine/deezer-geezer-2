import requests
import json
from .playlist import Playlist
from .track import Track
from tqdm import tqdm as statusify
from time import sleep


class PyDeez:
    _BASE_URL = 'http://api.deezer.com'
    _MY_PLAYLISTS_URL = '{}{}'.format(_BASE_URL, '/user/me/playlists')
    _PLAYLIST_URL = '{}/playlist/{{}}'.format(_BASE_URL)
    _PLAYLIST_TRACKS_URL = '{}/tracks'.format(_PLAYLIST_URL)
    _MY_FAVOURITES_URL = '{}{}'.format(_BASE_URL, '/user/me/tracks')
    _TRACK_URL = '{}/track/{{}}'.format(_BASE_URL)
    _MAX_PLAYLIST_SIZE = 2000
    _MAX_TRACKS_IN_URL = 10

    def __init__(self, access_token):
        self._request_params = {
            'access_token': access_token,
            'expires': 0,
            'limit': self._MAX_PLAYLIST_SIZE
        }

    def get_playlists(self, prefixes=None):
        all_playlists = self._api_get(self._MY_PLAYLISTS_URL)['data']

        if prefixes is None:
            return all_playlists

        return [Playlist.from_dict(playlist) for playlist
                in all_playlists
                if playlist['title'].startswith(tuple(prefixes))]

    def get_playlist_by_id(self, playlist_id):
        return Playlist.from_dict(self._api_get(self._PLAYLIST_URL.format(playlist_id)))

    def get_favourite_tracks(self):
        return self._get_all_pages(self._MY_FAVOURITES_URL,
                                   lambda track: Track.from_dict(track))

    def _api_get(self, url):
        return json.loads(
            requests.get(url, params=self._request_params).text)

    def get_tracks_for_playlists(self, playlists):
        return self._flatten([self.get_tracks_for_playlist(playlist)
                              for playlist
                              in statusify(playlists, desc='Retrieving Playlist Tracks')])

    @staticmethod
    def _flatten(list_of_lists):
        return [item for a_list in list_of_lists for item in a_list]

    def get_tracks_for_playlist(self, playlist):
        return self._get_all_pages(
            self._PLAYLIST_TRACKS_URL.format(playlist.id),
            lambda track: Track.from_dict(track))

    def _get_all_pages(self, url, from_dict):
        page = self._api_get(url)
        if 'next' not in page:
            return [from_dict(page) for page in page['data']]
        else:
            return [from_dict(page) for page in statusify(page['data'], desc='{} pages'.format(url))] + \
                   self._get_all_pages(page['next'], from_dict)
    def create_playlists(self, tracks, new_playlist_name_prefix):
        playlist_chunks = self.chunkify(tracks, self._MAX_PLAYLIST_SIZE)

        for i, subplaylist in enumerate(playlist_chunks):
            if i % 3 == 0:
                print('Pausing for a minute; throttling for the Deezer API...')
                sleep(60)

            print('Creating Playlist: {}/{}'.format(i+1, len(playlist_chunks)))
            new_subplaylist_title = self._build_playlist_title(new_playlist_name_prefix, i)
            new_playlist_id = self.create_playlist(new_subplaylist_title)

            url_friendly_subplaylist_chunks = self.chunkify(subplaylist, self._MAX_TRACKS_IN_URL)

            total_added_count = 0
            for url_friendly_subplaylist_chunk in statusify(url_friendly_subplaylist_chunks, desc='Chunks of Playlist'):
                url_friendly_ids = [str(track.id) for track in url_friendly_subplaylist_chunk]
                self.add_tracks_to_playlist_by_track_ids(new_playlist_id, url_friendly_ids)
                updated_playlist = self.get_playlist_by_id(new_playlist_id)

                expected_new_playlist_size = total_added_count + self._MAX_TRACKS_IN_URL
                if updated_playlist.track_count != expected_new_playlist_size:
                    print('Not all the tracks were added for chunk: {}'.format(','.join(url_friendly_ids)))
                    track_missing_count = expected_new_playlist_size - updated_playlist.track_count
                    print('{} of the tracks were not added'.format(track_missing_count))
                total_added_count = updated_playlist.track_count

    def add_tracks_to_playlist_by_track_ids(self, playlist_id, track_ids):
        requests.post(self._PLAYLIST_TRACKS_URL.format(playlist_id), params={
            **self._request_params,
            'songs': ','.join(track_ids)
        })

    def create_playlist(self, playlist_title):
        response = requests.post(self._MY_PLAYLISTS_URL, params={
            **self._request_params,
            'title': playlist_title
        })
        return json.loads(response.text)['id']

    @staticmethod
    def _build_playlist_title(prefix, i):
        return prefix + '-{0:0>2}'.format(i)

    @staticmethod
    def chunkify(a_list, sublist_size):
        return [a_list[i:i + sublist_size] for i in range(0, len(a_list), sublist_size)]

    def delete_playlists(self, prefixes):
        raw_playlists = self._api_get(self._MY_PLAYLISTS_URL)['data']
        for raw_playlist in statusify(raw_playlists, 'Deleting Playlists If Starting With {}'.format(prefixes)):
            playlist = Playlist.from_dict(raw_playlist)
            if playlist.title.startswith(tuple(prefixes)):
                self.delete_playlist_by_id(playlist.id)

    def delete_playlist_by_id(self, playlist_id):
        requests.delete(self._PLAYLIST_URL.format(playlist_id), params={**self._request_params})

