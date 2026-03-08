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
    _ALBUM_TRACKS = '{}{}'.format(_BASE_URL, '/album/{}/tracks')
    _TRACK_URL = '{}/track/{{}}'.format(_BASE_URL)
    _SEARCH_URL_PART = 'search'
    _SEARCH_PLAYLIST_URL = f'{_BASE_URL}/{_SEARCH_URL_PART}/playlist?q={{}}'
    _SEARCH_ALBUM_URL = f'{_BASE_URL}/{_SEARCH_URL_PART}/album?q={{}}'
    _MAX_PLAYLIST_SIZE = 2000
    _MAX_TRACKS_IN_URL = 10

    def __init__(self, access_token):
        self._request_params = {
            'access_token': access_token,
            'expires': 0,
            'limit': self._MAX_PLAYLIST_SIZE
        }

    def get_playlist_by_name(self, name):
        # Hard-coded 0 since it should only be for one playlist. Should assert.
        playlists = self._api_get(self._SEARCH_PLAYLIST_URL.format(name))['data']
        # Changed for rating_playlist_manager.py. Change back if it makes something else fail.
        # playlist = [playlist for playlist in playlists if playlist['user']['name'] == 'justin.levine'][0]
        filtered_playlists = [playlist for playlist in playlists if playlist['user']['name'] == 'justin.levine']
        if not filtered_playlists:
            return None
        playlist = filtered_playlists[0]
        # Changed this for rating_playlist_manager.py. Change back if it makes something else fail.
        # return [Playlist.from_dict(playlist)]
        return Playlist.from_dict(playlist)

    def get_album_id_by_artist_name_and_album_title(self, artist_name, album_title):
        """
        Search for an album by artist and title using advanced search syntax.
        """
        try:
            # Use Deezer's advanced search syntax for more precise matching
            search_query = f'artist:"{artist_name}" album:"{album_title}"'

            albums = self._api_get(self._SEARCH_ALBUM_URL.format(search_query))['data']

            if albums:
                return str(albums[0]['id'])
            else:
                # Fallback to simple search if advanced search returns nothing
                simple_query = f"{artist_name} {album_title}"
                albums = self._api_get(self._SEARCH_ALBUM_URL.format(simple_query))['data']

                if albums:
                    return str(albums[0]['id'])
                else:
                    print(f"No albums found for '{artist_name} - {album_title}'")
                    return None

        except Exception as e:
            print(f"Error searching for album '{artist_name} - {album_title}': {e}")
            return None

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

    def get_tracks_for_album(self, album_id):
        return self._get_all_pages(self._ALBUM_TRACKS.format(album_id),
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

    # def _get_all_pages(self, url, from_dict):
    #     page = self._api_get(url)
    #     if 'next' not in page:
    #         return [from_dict(page) for page in page['data']]
    #     else:
    #         return [from_dict(page) for page in statusify(page['data'], desc='{} pages'.format(url))] + \
    #                self._get_all_pages(page['next'], from_dict)

    def _get_all_pages(self, url, from_dict):
        page = self._api_get(url)

        is_data_exception = (
                isinstance(page, dict) and
                page.get('error', {}).get('type') == 'DataException' and
                page.get('error', {}).get('code') == 800
        )

        if is_data_exception:
            page = self._handle_data_exception_redirect(url)
            if page is None:
                return []

        # Normal processing continues here
        if 'next' not in page:
            return [from_dict(item) for item in page['data']]
        else:
            return [from_dict(item) for item in statusify(page['data'], desc='{} pages'.format(url))] + \
                self._get_all_pages(page['next'], from_dict)

    def _handle_data_exception_redirect(self, url):
        import re
        match = re.search(r'/(\d+)/', url)
        if match:
            old_id = match.group(1)
            new_id = self.resolve_redirect(old_id)

            if new_id and new_id != old_id:
                new_url = url.replace(f'/{old_id}/', f'/{new_id}/')
                print(f"Redirecting from ID {old_id} to {new_id}")

                page = self._api_get(new_url)

                if (isinstance(page, dict) and
                        page.get('error', {}).get('type') == 'DataException'):
                    print(f"Still failed after redirect for ID {new_id}")
                    return None
                return page
            else:
                print(f"No redirect found for ID {old_id}")
                return None
        else:
            print("Could not extract ID from URL")
            return None

    @staticmethod
    def resolve_redirect(deezer_id):
        """Resolve redirected Deezer ID by following web URL redirects."""
        import requests

        # Try different entity types since we don't know if it's track, album, etc.
        entity_types = ['album', 'track', 'artist', 'playlist']

        for entity_type in entity_types:
            try:
                url = f"https://www.deezer.com/{entity_type}/{deezer_id}"
                response = requests.head(url, allow_redirects=True, timeout=5)
                final_url = response.url

                if final_url != url and response.status_code == 200:
                    new_id = final_url.split("/")[-1]
                    # Make sure the new_id is actually different and numeric
                    if new_id != str(deezer_id) and new_id.isdigit():
                        return new_id
            except requests.RequestException as e:
                print(f"Error resolving redirect for {entity_type}/{deezer_id}: {e}")
                continue

        return None

    def create_playlists(self, tracks, new_playlist_name_prefix):
        playlist_chunks = self.chunkify(tracks, self._MAX_PLAYLIST_SIZE)

        for i, subplaylist in enumerate(playlist_chunks):
            if i != 0 and i % 3 == 0:
                print('Pausing for a minute; throttling for the Deezer API...')
                sleep(60)

            print('Creating Playlist: {}/{}'.format(i+1, len(playlist_chunks)))
            new_subplaylist_title = self._build_playlist_title(new_playlist_name_prefix, i)
            new_playlist_id = self.create_playlist(new_subplaylist_title)

            url_friendly_subplaylist_chunks = self.chunkify(subplaylist, self._MAX_TRACKS_IN_URL)

            total_added_count = 0
            for url_friendly_subplaylist_chunk in statusify(url_friendly_subplaylist_chunks, desc='Chunks of Playlist'):
                # Ugh. Another hack for rating_playlist_manager. Hopefully I use it more than the other thing
                # so this doesn't bother the hell out of me. Worst case scenario, I have 2 different tags in git.
                # I need to commit to git anyway...
                # url_friendly_ids = [str(track.id) for track in url_friendly_subplaylist_chunk]
                url_friendly_ids = [track for track in url_friendly_subplaylist_chunk]
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

