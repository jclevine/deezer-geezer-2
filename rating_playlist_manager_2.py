import time
import json
import os
import pickle
from typing import List, Dict, Any, Optional
from main import load_config


class PlaylistCache:
    """Handles playlist caching operations."""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = cache_dir
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _get_cache_file_path(self, playlist_name: str) -> str:
        """Get the cache file path for a playlist."""
        safe_name = playlist_name.replace('-', '_').replace(' ', '_')
        return os.path.join(self.cache_dir, f"playlist_{safe_name}.pkl")

    def is_cache_valid(self, playlist_name: str, max_age_hours: int = 1) -> bool:
        """Check if cached data exists and is still valid."""
        cache_file = self._get_cache_file_path(playlist_name)

        if not os.path.exists(cache_file):
            return False

        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                timestamp = cache_data.get('timestamp', 0)
                max_age_seconds = max_age_hours * 60 * 60
                return time.time() - timestamp < max_age_seconds
        except Exception:
            return False

    def load_cached_playlist(self, playlist_name: str) -> Optional[Dict]:
        """Load playlist data from cache."""
        cache_file = self._get_cache_file_path(playlist_name)

        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                playlist_data = cache_data.get('playlist')
                tracks_data = cache_data.get('tracks')

                if playlist_data and tracks_data is not None:
                    playlist_data['cached_tracks'] = tracks_data
                    return playlist_data
        except Exception as e:
            print(f"Error loading cache for '{playlist_name}': {e}")

        return None

    def save_playlist_to_cache(self, playlist_name: str, playlist_data: Dict, tracks_data: List) -> None:
        """Save playlist and tracks data to cache."""
        cache_file = self._get_cache_file_path(playlist_name)

        try:
            cache_data = {
                'timestamp': time.time(),
                'playlist': playlist_data,
                'tracks': tracks_data
            }
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            print(f"Cached playlist '{playlist_name}' with {len(tracks_data)} tracks")
        except Exception as e:
            print(f"Warning: Could not save cache for '{playlist_name}': {e}")

    def clear_cache(self, playlist_name: str = None) -> None:
        """Clear cached playlist data."""
        if playlist_name:
            cache_file = self._get_cache_file_path(playlist_name)
            if os.path.exists(cache_file):
                os.remove(cache_file)
                print(f"Cleared cache for playlist '{playlist_name}'")
            else:
                print(f"No cache found for playlist '{playlist_name}'")
        else:
            # Clear all playlist cache files
            for filename in os.listdir(self.cache_dir):
                if filename.startswith("playlist_") and filename.endswith(".pkl"):
                    os.remove(os.path.join(self.cache_dir, filename))
                    print(f"Cleared cache file: {filename}")


class RatingPlaylistManager:
    """Manages the creation and rotation of rating playlists from a music queue."""

    DEFAULT_CONFIG = {
        "source_playlist_name": "music-00",
        "rating_playlist_name": "rate-this",
        "already_rated_prefix": "already-rated",
        "tracks_per_batch": 5,
        "deezer_access_token": ""
    }

    def __init__(self, deezer_client=None, config_file: str = "rating_config.json"):
        """Initialize the rating playlist manager."""
        self.deezer = deezer_client
        self.config_file = config_file
        self.config = self._load_config()
        self.cache = PlaylistCache()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                print(f"Loaded configuration from {self.config_file}")
                return {**self.DEFAULT_CONFIG, **config}
            except Exception as e:
                print(f"Error loading config: {e}, using defaults")

        self._save_config(self.DEFAULT_CONFIG)
        return self.DEFAULT_CONFIG.copy()

    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Saved configuration to {self.config_file}")

    def update_deezer_token(self, token: str) -> None:
        """Update and save Deezer access token."""
        self.config["deezer_access_token"] = token
        self._save_config(self.config)
        print("✓ Updated Deezer access token")

    def _get_playlist_with_cache(self, playlist_name: str, use_cache: bool = True) -> Optional[Dict]:
        """Get playlist data with caching support."""
        # Try cache first if enabled
        if use_cache and self.cache.is_cache_valid(playlist_name):
            cached_playlist = self.cache.load_cached_playlist(playlist_name)
            if cached_playlist:
                print(
                    f"Using cached playlist '{playlist_name}' with "
                    f"{len(getattr(cached_playlist, 'cached_tracks', []))} tracks")
                return cached_playlist

        # Fetch from API
        print(f"Fetching playlist '{playlist_name}' from Deezer API...")
        playlist = self.deezer.get_playlist_by_name(playlist_name)

        if not playlist:
            print(f"Playlist '{playlist_name}' not found!")
            return None

        # Fetch tracks and cache
        print(f"Fetching tracks for playlist '{playlist_name}'...")
        tracks = self.deezer.get_tracks_for_playlist(playlist)

        self.cache.save_playlist_to_cache(playlist_name, playlist, tracks)
        playlist.cached_tracks = tracks

        return playlist

    def _get_tracks_from_playlist(self, playlist: Dict) -> List[Dict]:
        """Extract tracks from playlist, preferring cached tracks."""
        if hasattr(playlist, 'cached_tracks'):
            return playlist.cached_tracks
        return self.deezer.get_tracks_for_playlist(playlist)

    def _get_album_tracks(self, track: Dict) -> List[Dict]:
        """Get all tracks from the same album as the given track."""
        try:
            # Handle both dict and object formats
            if isinstance(track, dict):
                album_id = track['album']['id']
                album_title = track['album']['title']
            else:
                album_id = track.album.id if hasattr(track.album, 'id') else track.album['id']
                album_title = track.album.title if hasattr(track.album, 'title') else track.album['title']

            print(f"  Getting tracks from album: {album_title}")
            album_tracks = self.deezer.get_tracks_for_album(album_id)

            album_not_found_by_id = len(album_tracks) == 0

            if album_not_found_by_id:
                new_album_id = self.deezer.get_album_id_by_artist_name_and_album_title(track.artist, album_title)
                album_tracks = self.deezer.get_tracks_for_album(new_album_id)

            print(f"  Found {len(album_tracks)} tracks in album")

            album_tracks = self._filter_out_enormous_album_track_lists(album_tracks, track.id)
            return album_tracks

        except Exception as e:
            print(f"  Error getting album tracks: {e}")
            return []

    @staticmethod
    def _filter_out_enormous_album_track_lists(album_tracks, target_track_id: int):
        """
        Filters down a list of tracks if it's longer than 25 items, centering around
        the track with id == x and taking 5 items before and after it (11 total).

        Args:
            album_tracks: List of Track objects
            target_track_id: The id to center the slice around

        Returns:
            A new list with at most 11 tracks if original list > 25, otherwise original list
        """
        print(f"Filtering {len(album_tracks)} tracks, target_track_id: {target_track_id}")

        # If list is 25 or fewer items, return a copy of the original
        if len(album_tracks) <= 25:
            print("List ≤25 tracks, returning all")
            return album_tracks[:]

        # Find the index of the track with id == target_track_id
        matching_indices = [i for i, track in enumerate(album_tracks) if track.id == target_track_id]
        target_index = matching_indices[0] if matching_indices else None

        # If track with id == target_track_id is not found, return a copy of the original list
        if target_index is None:
            print("Target track not found, returning all")
            return album_tracks[:]

        # Calculate slice bounds
        total_length = len(album_tracks)

        if target_index < 6:
            # Take first 11 tracks
            start_index = 0
            end_index = 11
            print(f"Taking first 11 tracks (target at position {target_index})")
        elif target_index > total_length - 6:
            # Take last 11 tracks
            start_index = total_length - 11
            end_index = total_length
            print(f"Taking last 11 tracks (target at position {target_index})")
        else:
            # Take 5 before and 5 after (plus the target track = 11 total)
            start_index = target_index - 5
            end_index = target_index + 6  # +6 because slice is exclusive of end
            print(f"Taking 11 tracks centered on position {target_index}")

        result = album_tracks[start_index:end_index]
        print(f"Filtered to {len(result)} tracks")

        return result

    def _find_next_already_rated_name(self) -> str:
        """Find the next available 'already-rated-XX' playlist name."""
        prefix = self.config["already_rated_prefix"]
        existing_playlists = self.deezer.get_playlists([prefix])

        existing_numbers = []
        for playlist in existing_playlists:
            title = playlist['title']
            if title.startswith(f"{prefix}-"):
                try:
                    number = int(title.split('-')[-1])
                    existing_numbers.append(number)
                except ValueError:
                    continue

        next_number = 0
        while next_number in existing_numbers:
            next_number += 1

        return f"{prefix}-{next_number:02d}"

    def _collect_album_tracks_from_selection(self, selected_tracks: List[Dict], interactive: bool) -> List[Dict]:
        """Collect all album tracks from a selection of tracks."""
        all_album_tracks = []

        for i, track in enumerate(selected_tracks, 1):
            print(f"\nProcessing track {i}/{len(selected_tracks)}...")
            album_tracks = self._get_album_tracks(track)
            all_album_tracks.extend(album_tracks)

            if interactive and i < len(selected_tracks):
                if input("Continue to next track? (y/n): ").lower() != 'y':
                    break

        # Add original tracks at the end. Currently doesn't work since playlists can only have a track 1 time/ playlist
        # all_album_tracks.extend(self._normalize_tracks_to_dict(selected_tracks))

        return all_album_tracks

    def _normalize_tracks_to_dict(self, tracks: List) -> List[Dict]:
        """Convert track objects to dict format for consistency."""
        normalized_tracks = []

        for track in tracks:
            if isinstance(track, dict):
                normalized_tracks.append(track)
            else:
                # Convert Track object to dict
                track_dict = {
                    'id': track.id,
                    'title': track.title,
                    'artist': {'name': track.artist},
                }
                normalized_tracks.append(track_dict)

        return normalized_tracks

    def _handle_existing_rating_playlist(self, rating_name: str, interactive: bool) -> bool:
        """Handle existing rating playlist based on user choice or auto-rename."""
        existing_rating = self.deezer.get_playlist_by_name(rating_name)

        if not existing_rating:
            return True

        print(f"Warning: Playlist '{rating_name}' already exists!")

        if interactive:
            choice = input("What to do? (o)verwrite, (r)ename existing, (c)ancel: ").lower()
            if choice == 'c':
                return False
            elif choice == 'r':
                new_name = self._find_next_already_rated_name()
                print(f"Renaming existing '{rating_name}' to '{new_name}'...")
            # For 'o' (overwrite), we'll delete below
        else:
            # Auto-rename in non-interactive mode
            new_name = self._find_next_already_rated_name()
            print(f"Auto-renaming existing '{rating_name}' to '{new_name}'...")

        self.deezer.delete_playlist_by_id(existing_rating.id1)
        return True

    def _create_playlist_with_tracks(self, playlist_name: str, track_ids: List[str]) -> None:
        """Create a playlist and add tracks to it."""
        self.deezer.create_playlists(track_ids, playlist_name)
        print(f"✓ Successfully created playlist '{playlist_name}' with {len(track_ids)} tracks")

    def _extract_track_ids(self, tracks: List[Dict]) -> List[str]:
        """Extract track IDs from track data."""
        track_ids = []
        for track in tracks:
            if hasattr(track, 'id'):
                track_ids.append(str(track.id))
            else:
                track_ids.append(str(track['id']))
        return track_ids

    def create_rating_playlist(self, interactive: bool = True) -> bool:
        """Create a new rating playlist from the source playlist."""
        source_name = self.config["source_playlist_name"]
        rating_name = self.config["rating_playlist_name"]
        tracks_per_batch = self.config["tracks_per_batch"]

        print(f"\n=== Creating Rating Playlist ===")
        print(f"Source playlist: {source_name}")
        print(f"Rating playlist: {rating_name}")
        print(f"Tracks per batch: {tracks_per_batch}")

        if interactive and input("\nProceed? (y/n): ").lower() != 'y':
            return False

        # Get source playlist
        print(f"\nStep 1: Getting source playlist '{source_name}'...")
        source_playlist = self._get_playlist_with_cache(source_name)
        if not source_playlist:
            return False

        source_tracks = self._get_tracks_from_playlist(source_playlist)

        if len(source_tracks) < tracks_per_batch:
            print(f"Error: Source playlist only has {len(source_tracks)} tracks, need at least {tracks_per_batch}")
            return False

        print(f"Found {len(source_tracks)} tracks in source playlist")

        if interactive and input("Continue? (y/n): ").lower() != 'y':
            return False

        # Get first N tracks
        first_tracks = source_tracks[:tracks_per_batch]
        print(f"\nStep 2: Processing first {tracks_per_batch} tracks:")
        for i, track in enumerate(first_tracks, 1):
            if isinstance(track, dict):
                print(f"  {i}. {track['artist']['name']} - {track['title']}")
            else:
                print(f"  {i}. {track.artist} - {track.title}")

        if interactive and input("Continue? (y/n): ").lower() != 'y':
            return False

        # Collect album tracks
        print(f"\nStep 3: Collecting album tracks...")
        all_album_tracks = self._collect_album_tracks_from_selection(first_tracks, interactive)

        print(f"\nTotal tracks to add: {len(all_album_tracks)}")

        if interactive and input("Create rating playlist? (y/n): ").lower() != 'y':
            return False

        # Handle existing playlist
        if not self._handle_existing_rating_playlist(rating_name, interactive):
            return False

        # Create playlist
        print(f"\nStep 4: Creating playlist '{rating_name}'...")
        track_ids = self._extract_track_ids(all_album_tracks)
        self._create_playlist_with_tracks(rating_name, track_ids)

        return True

    def rotate_playlists(self, interactive: bool = True) -> bool:
        """Remove first N tracks from source playlist and create new rating playlist."""
        source_name = self.config["source_playlist_name"]
        rating_name = self.config["rating_playlist_name"]
        tracks_per_batch = self.config["tracks_per_batch"]

        print(f"\n=== Rotating Playlists ===")
        print(f"Will remove first {tracks_per_batch} tracks from '{source_name}'")
        print(f"Will rename existing '{rating_name}' to 'already-rated-XX'")
        print(f"Will create new '{rating_name}' with next batch")

        if interactive and input("\nProceed with rotation? (y/n): ").lower() != 'y':
            return False

        # Handle existing rating playlist
        existing_rating = self.deezer.get_playlist_by_name(rating_name)
        if existing_rating:
            new_name = self._find_next_already_rated_name()
            print(f"\nStep 1: Renaming '{rating_name}' to '{new_name}'...")

            if interactive and input("Confirm rename? (y/n): ").lower() != 'y':
                return False

            self.deezer.delete_playlist_by_id(existing_rating['id'])
            print(f"✓ Removed existing '{rating_name}'")

        # Remove first tracks from source
        print(f"\nStep 2: Removing first {tracks_per_batch} tracks from '{source_name}'...")
        source_playlist = self._get_playlist_with_cache(source_name)
        if not source_playlist:
            return False

        source_tracks = self._get_tracks_from_playlist(source_playlist)

        if len(source_tracks) < tracks_per_batch:
            print(f"Error: Source playlist only has {len(source_tracks)} tracks, need at least {tracks_per_batch}")
            return False

        self._display_tracks_to_remove(source_tracks[:tracks_per_batch])

        if interactive and input("Confirm removal? (y/n): ").lower() != 'y':
            return False

        # Recreate source playlist without first N tracks
        remaining_tracks = source_tracks[tracks_per_batch:]
        self._recreate_source_playlist(source_playlist, remaining_tracks, source_name)

        # Clear cache since we modified the playlist
        self.cache.clear_cache(source_name)

        # Create new rating playlist
        print(f"\nStep 3: Creating new rating playlist...")
        success = self.create_rating_playlist(interactive=False)

        if success:
            print(f"\n✓ Successfully rotated playlists!")
            print(f"  - Removed {tracks_per_batch} tracks from '{source_name}'")
            print(f"  - Created new '{rating_name}' playlist")
        else:
            print(f"\n✗ Failed to create new rating playlist")

        return success

    def _display_tracks_to_remove(self, tracks: List[Dict]) -> None:
        """Display the tracks that will be removed."""
        print("Tracks to be removed:")
        for i, track in enumerate(tracks, 1):
            if isinstance(track, dict):
                print(f"  {i}. {track['artist']['name']} - {track['title']}")
            else:
                print(f"  {i}. {track.artist.name} - {track.title}")

    def _recreate_source_playlist(self, original_playlist: Dict, remaining_tracks: List[Dict],
                                  playlist_name: str) -> None:
        """Recreate the source playlist with remaining tracks."""
        remaining_track_ids = self._extract_track_ids(remaining_tracks)

        # Delete and recreate
        self.deezer.delete_playlist_by_id(original_playlist['id'])
        new_source_id = self.deezer.create_playlist(playlist_name)

        if remaining_track_ids:
            # Add tracks back in chunks
            chunk_size = 50
            track_chunks = self.deezer.chunkify(remaining_track_ids, chunk_size)

            for i, chunk in enumerate(track_chunks, 1):
                print(f"Re-adding chunk {i}/{len(track_chunks)} to source playlist...")
                try:
                    self.deezer.add_tracks_to_playlist_by_track_ids(new_source_id, chunk)
                    time.sleep(1)  # Respect API limits
                except Exception as e:
                    print(f"Error adding chunk {i}: {e}")

        print(f"✓ Source playlist now has {len(remaining_tracks)} tracks")

    def display_config(self) -> None:
        """Display current configuration."""
        print("\n--- Current Configuration ---")
        for key, value in self.config.items():
            if key == "deezer_access_token" and value:
                print(f"  {key}: {'*' * 20} (hidden)")
            else:
                print(f"  {key}: {value}")

    def clear_cache(self, playlist_name: str = None) -> None:
        """Clear playlist cache."""
        self.cache.clear_cache(playlist_name)


def main():
    """Main function with menu system."""
    print("=== Rating Playlist Manager ===")

    # Initialize manager
    manager = RatingPlaylistManager()

    # Get Deezer access token
    deezer_access_token = manager.config.get("deezer_access_token")
    if not deezer_access_token:
        deezer_access_token = input("Enter your Deezer access token: ")
        manager.update_deezer_token(deezer_access_token)
        print("✓ Saved Deezer token to config file for future use")
    else:
        print("✓ Using saved Deezer token from config")

    # Initialize Deezer client
    config = load_config()
    from pydeez import PyDeez
    deezer_client = PyDeez(deezer_access_token)
    manager.deezer = deezer_client

    # Main menu loop
    while True:
        print("\n" + "=" * 50)
        print("What would you like to do?")
        print("1. Create rating playlist (first time)")
        print("2. Rotate playlists (remove rated tracks and create new rating playlist)")
        print("3. View current configuration")
        print("4. Clear playlist cache")
        print("5. Update Deezer access token")
        print("6. Exit")

        choice = input("\nEnter choice (1-6): ")

        if choice == '1':
            print("\n--- Create Rating Playlist ---")
            print("This will create a 'rate-this' playlist with albums from first 5 tracks in 'music-00'")
            manager.create_rating_playlist(interactive=True)

        elif choice == '2':
            print("\n--- Rotate Playlists ---")
            print("This will remove first 5 tracks from 'music-00' and create new 'rate-this' playlist")
            manager.rotate_playlists(interactive=True)

        elif choice == '3':
            manager.display_config()
            input("\nPress Enter to continue...")

        elif choice == '4':
            print("\n--- Clear Playlist Cache ---")
            print("1. Clear all playlist cache")
            print("2. Clear specific playlist cache")
            subchoice = input("Enter choice (1-2): ")

            if subchoice == '1':
                manager.clear_cache()
                print("All playlist cache cleared!")
            elif subchoice == '2':
                playlist_name = input("Enter playlist name to clear cache for: ")
                manager.clear_cache(playlist_name)
            input("\nPress Enter to continue...")

        elif choice == '5':
            print("\n--- Update Deezer Access Token ---")
            new_token = input("Enter new Deezer access token: ")
            manager.update_deezer_token(new_token)

            # Update the Deezer client with new token
            from pydeez import PyDeez
            manager.deezer = PyDeez(new_token)
            print("✓ Updated Deezer client with new token!")
            input("\nPress Enter to continue...")

        elif choice == '6':
            print("Goodbye!")
            break

        else:
            print("Invalid choice, please try again.")


if __name__ == "__main__":
    main()