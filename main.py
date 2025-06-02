import requests
import time
import json
import os
import pickle
from typing import Set
from fuzzywuzzy import fuzz
import csv
import re
import pylast

from track_similarity_matcher import TrackSimilarityMatcher, RecommendedConfig


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
            # TODO: Hard-coded index of 0 since it should be only one playlist.Need to assert this.
            # favorite_tracks = self.deezer.get_tracks_for_playlist(self.deezer.get_playlist_by_name('fresh-favourites')[0])

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
                except Exception as e:
                    print(f"An error occurred: {e}")
                    traceback.print_exc()
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
        matcher = TrackSimilarityMatcher(RecommendedConfig())

        # Get all favorite tracks from Deezer with caching
        favorite_tracks = self._get_favorite_tracks()
        print(f"Found {len(favorite_tracks)} favorite tracks")

        # Get all tracks listened to in the past year from Last.fm
        # Uncomment to get tracks from Lastfm
        current_time = int(time.time())
        days_ago = current_time - (365 * 24 * 60 * 60)

        # testing = self.lastfm.get_recent_tracks(None, True, days_ago, current_time, False, False)
        recently_played_tracks = self.lastfm.get_recent_tracks(None, True, days_ago, current_time, False, False)
        # Use https://benjaminbenben.com/lastfm-to-csv/ if you want to get an updateds csv!
        # recently_played_tracks = self.load_listened_tracks_from_csv()

        # Create a set of unheard favorites
        unheard_favorites = []
        track_info_cache = {}  # Cache for track info

        for i, favourite_track in enumerate(favorite_tracks):
            try:
                if i % 50 == 0 or i == len(favorite_tracks) - 1:
                    print(f'{i}/{len(favorite_tracks)}')

                # Favourite track info
                favourite_artist_name, favourite_track_name, favourite_track_id = self._extract_track_info(
                    favourite_track)
                favourite_artist = favourite_track.artist
                favourite_title = favourite_track.title

                # Check if this favourite track matches any recent tracks
                found_match = False
                for recent_track in recently_played_tracks:
                    recent_artist_name = recent_track.track.artist.name
                    recent_track_title = recent_track.track.title

                    is_match, match_result = matcher.are_tracks_similar(
                        favourite_artist,
                        favourite_title,
                        recent_artist_name,
                        recent_track_title
                    )

                    if is_match:
                        found_match = True
                        break

                # If no match found, add to unheard_favorites
                if not found_match:
                    unheard_favorites.append((favourite_track, favourite_track_id))

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

        matched_review_file, nonmatched_review_file = matcher.create_review_files()

        print(f"\nReview file created: {matched_review_file}")
        print("Please review the file, make any necessary corrections, and save it.")
        print("Then you can process the feedback using matcher.process_review_file(filename)")

        print(f"\nReview file created: {nonmatched_review_file}")
        print("Please review the file, make any necessary corrections, and save it.")
        print("Then you can process the feedback using matcher.process_review_file(filename)")

        return new_playlist_id

    def _is_track_recently_played(self, artist_name: str, track_name: str,
                                  recently_played_tracks: Set[str],
                                  similarity_threshold: int = 80) -> bool:
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
                cleaned_track_identifier = clean_track_name(track_identifier.lower())
                cleaned_recent_track = clean_track_name(recent_track.lower())

                similarity = fuzz.ratio(cleaned_track_identifier, cleaned_recent_track)

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
                print(f"Error: {e}")
                # If any error in matching, be safe and skip this comparison
                continue

        return False

def clean_track_name(track_name: str) -> str:
    """Remove common track suffixes that might interfere with matching."""
    # Common patterns to remove (case insensitive)
    patterns = [
        r'\s*\(.*?remaster.*?\)',
        r'\s*\(.*?remix.*?\)',
        r'\s*\(.*?version.*?\)',
        r'\s*\(.*?edit.*?\)',
        r'\s*\(.*?mix.*?\)',
        r'\s*\(.*?radio.*?\)',
        r'\s*\(.*?single.*?\)',
        r'\s*\(.*?album.*?\)',
        r'\s*\(.*?deluxe.*?\)',
        r'\s*\(.*?extended.*?\)',
        r'\s*\(.*?instrumental.*?\)',
        r'\s*\(.*?acoustic.*?\)',
        r'\s*\(.*?live.*?\)',
        r'\s*\(.*?feat\..*?\)',
        r'\s*\(.*?ft\..*?\)',
        r'\s*\[.*?remaster.*?\]',
        r'\s*\[.*?remix.*?\]',
        r'\s*\[.*?version.*?\]',
        r'\s*- remaster',
        r'\s*- remix',
        r'\s*- radio edit',
    ]

    cleaned = track_name
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


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
        lastfm_client = pylast.LastFMNetwork(api_key=lastfm_api_key, username=lastfm_username).get_user(lastfm_username)

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
