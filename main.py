import requests
import time
import json
import os
import pickle
from typing import Set
from fuzzywuzzy import fuzz
import csv


class LastFmClient:
    """Client for interacting with the Last.fm API."""

    def __init__(self, api_key: str, username: str, cache_dir: str = "cache"):
        """
        Initialize the Last.fm API client.

        Args:
            api_key: Last.fm API key
            username: Last.fm username
            cache_dir: Directory to store cache files
        """
        self.api_key = api_key
        self.username = username
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        self.cache_dir = cache_dir

        # Create cache directory if it doesn't exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

    def get_tracks_listened_to_past_year(self) -> Set[str]:
        """
        Get all tracks the user has listened to in the past year.
        Uses caching to avoid refetching data.

        Returns:
            A set of strings in the format "artist - track" for all tracks listened to
        """
        cache_file = os.path.join(self.cache_dir, f"lastfm_tracks_{self.username}.pkl")

        # Try to load from cache first
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    timestamp = cache_data.get('timestamp', 0)
                    all_tracks = cache_data.get('tracks', set())

                    # If cache is less than 1 day old, use it
                    if time.time() - timestamp < 24 * 60 * 60:
                        print(f"Using cached Last.fm data with {len(all_tracks)} tracks")
                        return all_tracks
                    else:
                        print("Cache is older than 24 hours, refreshing data...")
            except Exception as e:
                print(f"Error loading cache: {e}")

        print("Fetching tracks listened to in the past year from Last.fm...")

        # Set to store all tracks
        all_tracks = set()

        # Get the current timestamp and calculate one year ago
        current_time = int(time.time())
        one_year_ago = current_time - (365 * 24 * 60 * 60)

        # Initial parameters
        params = {
            'method': 'user.getrecenttracks',
            'user': self.username,
            'api_key': self.api_key,
            'format': 'json',
            'limit': 200,  # Maximum allowed by Last.fm API
            'from': one_year_ago,
            'page': 1
        }

        total_pages = 1  # Will be updated with the first API call
        current_page = 1

        try:
            while current_page <= total_pages:
                params['page'] = current_page

                # Make the API request
                response = requests.get(self.base_url, params=params)
                data = response.json()

                # Check if the request was successful
                if 'recenttracks' not in data:
                    print(f"Error fetching tracks from Last.fm: {data}")
                    break

                # Update total pages
                total_pages = int(data['recenttracks']['@attr']['totalPages'])

                # Process tracks
                tracks = data['recenttracks']['track']
                for track in tracks:
                    # Skip currently playing track (it doesn't have a date)
                    if '@attr' in track and track['@attr'].get('nowplaying') == 'true':
                        continue

                    artist_name = track['artist']['#text']
                    track_name = track['name']
                    track_identifier = f"{artist_name} - {track_name}"
                    all_tracks.add(track_identifier)

                # Save progress to cache after each page (in case of error)
                if current_page % 5 == 0 or current_page == total_pages:
                    self._save_tracks_cache(all_tracks)

                print(f"Processed page {current_page}/{total_pages} ({len(all_tracks)} unique tracks so far)")
                current_page += 1

                # Respect Last.fm API rate limits (5 requests per second)
                if current_page <= total_pages:
                    time.sleep(0.2)

        except Exception as e:
            print(f"Error occurred while fetching Last.fm data: {e}")
            print("Using partial data collected so far")

        # Save final results to cache
        self._save_tracks_cache(all_tracks)

        print(f"Found {len(all_tracks)} unique tracks listened to in the past year")
        return all_tracks

    def _save_tracks_cache(self, tracks: Set[str]):
        """
        Save fetched tracks to cache file.

        Args:
            tracks: Set of track identifiers
        """
        cache_file = os.path.join(self.cache_dir, f"lastfm_tracks_{self.username}.pkl")
        try:
            with open(cache_file, 'wb') as f:
                cache_data = {
                    'timestamp': time.time(),
                    'tracks': tracks
                }
                pickle.dump(cache_data, f)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")


class DeezerFavoritesAnalyzer:
    """Class to analyze Deezer favorites and create playlists of unheard favorites."""

    def __init__(self, deezer_client, lastfm_client, cache_dir: str = "cache"):
        """
        Initialize with Deezer and Last.fm clients.

        Args:
            deezer_client: Your existing Deezer API client
            lastfm_client: The Last.fm API client
            cache_dir: Directory to store cache files
        """
        self.deezer = deezer_client
        self.lastfm = lastfm_client
        self.cache_dir = cache_dir

        # Create cache directory if it doesn't exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

    def _get_favorite_tracks(self):
        """
        Get all favorite tracks from Deezer with caching support.

        Returns:
            List of favorite tracks
        """
        cache_file = os.path.join(self.cache_dir, "deezer_favorites.pkl")

        # Try to load from cache first
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    timestamp = cache_data.get('timestamp', 0)
                    favorite_tracks = cache_data.get('tracks', [])

                    # If cache is less than 1 day old, use it
                    if time.time() - timestamp < 24 * 60 * 60:
                        print(f"Using cached Deezer favorites with {len(favorite_tracks)} tracks")
                        return favorite_tracks
                    else:
                        print("Cache is older than 24 hours, refreshing data...")
            except Exception as e:
                print(f"Error loading cache: {e}")

        print("Fetching favorite tracks from Deezer...")
        try:
            favorite_tracks = self.deezer.get_favourite_tracks()

            # Save to cache
            with open(cache_file, 'wb') as f:
                cache_data = {
                    'timestamp': time.time(),
                    'tracks': favorite_tracks
                }
                pickle.dump(cache_data, f)

            return favorite_tracks
        except Exception as e:
            print(f"Error fetching Deezer favorites: {e}")
            # If we have a cache file, but it's old, still use it in case of error
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'rb') as f:
                        cache_data = pickle.load(f)
                        favorite_tracks = cache_data.get('tracks', [])
                        print(f"Using older cached data with {len(favorite_tracks)} tracks due to error")
                        return favorite_tracks
                except Exception:
                    pass

            # If everything fails, return empty list
            print("Failed to get favorite tracks")
            return []

    def _extract_track_info(self, track):
        """
        Safely extract artist name and track title from track object.
        Handles both dictionary-like and object-like track representations.

        Args:
            track: Track object/dict from Deezer API

        Returns:
            Tuple of (artist_name, track_name, track_id)
        """
        try:
            # Try dictionary access first (most common)
            if isinstance(track, dict):
                artist_name = track['artist']['name']
                track_name = track['title']
                track_id = track['id']
            # Try object access (if Track is a custom class)
            else:
                # Try different attribute access patterns
                if hasattr(track, 'artist') and hasattr(track.artist, 'name'):
                    artist_name = track.artist.name
                elif hasattr(track, 'get_artist_name'):
                    artist_name = track.get_artist_name()
                else:
                    artist_name = str(track.artist)

                if hasattr(track, 'title'):
                    track_name = track.title
                elif hasattr(track, 'get_title'):
                    track_name = track.get_title()
                else:
                    track_name = str(track)

                if hasattr(track, 'id'):
                    track_id = track.id
                elif hasattr(track, 'get_id'):
                    track_id = track.get_id()
                else:
                    # If we can't find an ID, use a fallback
                    track_id = hash(f"{artist_name}-{track_name}")

            return artist_name, track_name, track_id
        except Exception as e:
            # Last resort fallback
            print(f"Error extracting track info: {e}")
            print(f"Track object type: {type(track)}")
            # Try to get a string representation
            try:
                track_str = str(track)
                return "Unknown Artist", track_str, hash(track_str)
            except:
                return "Unknown Artist", "Unknown Track", 0

    def load_listened_tracks_from_csv(self) -> set[str]:
        """
        Prompts for a CSV file path and loads listened tracks as 'artist - track' strings.

        Assumes:
        - No header row
        - Column A = artist (index 0)
        - Column C = track  (index 2)

        Returns:
            A set of "artist - track" strings
        """
        file_path = input("Paste the full Windows path to your CSV file: ").strip('"')

        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        listened_tracks = set()
        with open(file_path, 'r', encoding='latin-1') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 3:
                    artist = row[0].strip()
                    track = row[2].strip()
                    if artist and track:
                        listened_tracks.add(f"{artist} - {track}")
        print(f"Loaded {len(listened_tracks)} listened tracks from CSV")
        return listened_tracks

    def create_unheard_favorites_playlist(self, playlist_name: str = "Favorites Not Played in a Year") -> str:
        """
        Create a playlist of favorite tracks not listened to in the past year.

        Args:
            playlist_name: Name for the new playlist

        Returns:
            ID of the created playlist
        """
        # Get all favorite tracks from Deezer with caching
        favorite_tracks = self._get_favorite_tracks()
        print(f"Found {len(favorite_tracks)} favorite tracks")

        # Get all tracks listened to in the past year from Last.fm
        # Uncomment to get tracks from Lastfm
        # recently_played_tracks = self.lastfm.get_tracks_listened_to_past_year()
        # Use https://benjaminbenben.com/lastfm-to-csv/ if you want to get an updateds csv!
        recently_played_tracks = self.load_listened_tracks_from_csv()

        # Create a set of unheard favorites
        unheard_favorites = []
        track_info_cache = {}  # Cache for track info
        existing_artist_track_names = []

        for track in favorite_tracks:
            try:
                # Extract track info safely
                artist_name, track_name, track_id = self._extract_track_info(track)

                # Store in cache for future use
                track_info_cache[track_id] = (artist_name, track_name)

                ARTIST_SIMILARITY_THRESHOLD = 90
                TRACK_SIMILARITY_THRESHOLD = 90

                # Check if track was recently played using fuzzy matching
                if not self._is_track_recently_played(artist_name, track_name, recently_played_tracks):
                    # Check for similarity with already-added tracks
                    is_similar = any(
                        fuzz.ratio(artist_name.lower(), existing_artist.lower()) >= ARTIST_SIMILARITY_THRESHOLD and
                        fuzz.ratio(track_name.lower(), existing_track.lower()) >= TRACK_SIMILARITY_THRESHOLD
                        for existing_artist, existing_track in existing_artist_track_names
                    )

                    if not is_similar:
                        unheard_favorites.append((track, track_id))
                        existing_artist_track_names.append((artist_name, track_name))
            except Exception as e:
                print(f"Error processing track: {e}")
                continue

        print(f"Found {len(unheard_favorites)} favorite tracks not played in the past year")

        # Create a new playlist with these tracks
        if not unheard_favorites:
            print("No unheard favorites found to add to playlist")
            return None

        # Extract track IDs for the playlist
        track_ids = list(set(track_id for _, track_id in unheard_favorites))

        # Save the track info cache
        cache_file = os.path.join(self.cache_dir, "track_info_cache.pkl")
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(track_info_cache, f)
        except Exception as e:
            print(f"Warning: Could not save track info cache: {e}")

        # Create the playlist and add tracks
        print(f"Creating playlist '{playlist_name}' with {len(track_ids)} tracks")
        new_playlist_id = self.deezer.create_playlist(playlist_name)

        # Add tracks in chunks (Deezer API has limitations)
        chunk_size = 50  # Deezer's limit for adding tracks in one request
        track_id_chunks = self.deezer.chunkify(track_ids, chunk_size)

        for i, chunk in enumerate(track_id_chunks):
            print(f"Adding chunk {i + 1}/{len(track_id_chunks)} to playlist")
            try:
                string_track_ids = [str(track_id) for track_id in chunk]
                self.deezer.add_tracks_to_playlist_by_track_ids(new_playlist_id, string_track_ids)
                time.sleep(1)  # Respect API rate limits
            except Exception as e:
                print(f"Error adding chunk {i + 1}: {e}")
                print("Continuing with next chunk...")
                continue

        print(f"Successfully created playlist '{playlist_name}' with {len(track_ids)} unheard favorites")
        return new_playlist_id

    def _is_track_recently_played(self, artist_name: str, track_name: str,
                                  recently_played_tracks: Set[str],
                                  similarity_threshold: int = 85) -> bool:
        """
        Check if a track was recently played using fuzzy matching.

        Args:
            artist_name: Name of the artist
            track_name: Name of the track
            recently_played_tracks: Set of recently played tracks in "artist - track" format
            similarity_threshold: Minimum similarity score (0-100) to consider a match

        Returns:
            True if track was recently played, False otherwise
        """
        # Exact match check first (faster)
        track_identifier = f"{artist_name} - {track_name}"
        if track_identifier in recently_played_tracks:
            return True

        # Try fuzzy matching if no exact match
        for recent_track in recently_played_tracks:
            try:
                # Calculate similarity ratio
                similarity = fuzz.ratio(track_identifier.lower(), recent_track.lower())

                # Check for high similarity
                if similarity >= similarity_threshold:
                    print(f"Fuzzy match: '{track_identifier}' ~ '{recent_track}' ({similarity}%)")
                    return True

                # Also try matching just the track name (ignoring artist differences)
                # This helps with "feat." variations or slight artist name differences
                recent_parts = recent_track.split(" - ", 1)
                if len(recent_parts) > 1:
                    recent_artist, recent_title = recent_parts

                    # Check track title similarity
                    title_similarity = fuzz.ratio(track_name.lower(), recent_title.lower())
                    if title_similarity >= 90 and fuzz.ratio(artist_name.lower(), recent_artist.lower()) >= 70:
                        print(f"Title match: '{track_name}' ~ '{recent_title}' ({title_similarity}%)")
                        return True
            except Exception as e:
                # If any error in matching, be safe and skip this comparison
                continue

        return False


def load_config():
    """
    Load configuration from file or create default one if it doesn't exist.

    Returns:
        Dictionary with configuration
    """
    config_file = "config.json"
    default_config = {
        "deezer_access_token": "",
        "lastfm_api_key": "",
        "lastfm_username": "",
        "cache_dir": "cache"
    }

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            print("Loaded configuration from config.json")
            return config
        except Exception as e:
            print(f"Error loading config file: {e}")

    # Create default config
    with open(config_file, 'w') as f:
        json.dump(default_config, f, indent=4)
    print(f"Created default config file at {config_file}")
    return default_config


def main():
    """Main function to run the script."""
    try:
        # Load or create configuration
        config = load_config()

        # Get API credentials
        deezer_access_token = config.get("deezer_access_token") or input("Enter your Deezer access token: ")
        lastfm_api_key = config.get("lastfm_api_key") or input("Enter your Last.fm API key: ")
        lastfm_username = config.get("lastfm_username") or input("Enter your Last.fm username: ")
        cache_dir = config.get("cache_dir", "cache")

        # Save the credentials for future use
        if deezer_access_token != config.get("deezer_access_token") or \
                lastfm_api_key != config.get("lastfm_api_key") or \
                lastfm_username != config.get("lastfm_username"):
            config.update({
                "deezer_access_token": deezer_access_token,
                "lastfm_api_key": lastfm_api_key,
                "lastfm_username": lastfm_username
            })
            with open("config.json", 'w') as f:
                json.dump(config, f, indent=4)
            print("Saved credentials to config.json")

        # Create API clients
        from pydeez import PyDeez  # Import your existing Deezer client
        deezer_client = PyDeez(deezer_access_token)
        lastfm_client = LastFmClient(lastfm_api_key, lastfm_username, cache_dir)

        # Create the analyzer and run
        analyzer = DeezerFavoritesAnalyzer(deezer_client, lastfm_client, cache_dir)
        playlist_name = input("Enter name for the new playlist (or press Enter for default): ")
        if not playlist_name:
            playlist_name = "Favorites Not Played in a Year"

        playlist_id = analyzer.create_unheard_favorites_playlist(playlist_name)

        if playlist_id:
            print(f"Playlist created! ID: {playlist_id}")
            print(f"You can view it in your Deezer account under '{playlist_name}'")
        else:
            print("No playlist was created.")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
