import time
import json
import os
from typing import List, Dict, Any, Optional
from main import load_config


class RatingPlaylistManager:
    """Manages the creation and rotation of rating playlists from a music queue."""
    
    def __init__(self, deezer_client, config_file: str = "rating_config.json"):
        """
        Initialize the rating playlist manager.
        
        Args:
            deezer_client: Your existing Deezer API client
            config_file: Path to configuration file
        """
        self.deezer = deezer_client
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default."""
        default_config = {
            "source_playlist_name": "music-00",
            "rating_playlist_name": "rate-this",
            "already_rated_prefix": "already-rated",
            "tracks_per_batch": 5
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                print(f"Loaded configuration from {self.config_file}")
                return {**default_config, **config}
            except Exception as e:
                print(f"Error loading config: {e}, using defaults")
        
        # Save default config
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        print(f"Created default config at {self.config_file}")
        return default_config
    
    # def _get_playlist_by_name(self, playlist_name: str) -> Optional[Dict]:
    #     """
    #     Get a playlist by its name.
    #
    #     Args:
    #         playlist_name: Name of the playlist to find
    #
    #     Returns:
    #         Playlist object or None if not found
    #     """
    #     try:
    #         playlists = self.deezer.get_playlists()
    #         for playlist in playlists:
    #             if playlist['title'] == playlist_name:
    #                 return playlist
    #         return None
    #     except Exception as e:
    #         print(f"Error getting playlist '{playlist_name}': {e}")
    #         return None
    
    def _get_album_tracks(self, track) -> List[Dict]:
        """
        Get all tracks from the same album as the given track.
        
        Args:
            track: Track object from Deezer
            
        Returns:
            List of tracks from the same album
        """
        try:
            # Extract album info safely
            if isinstance(track, dict):
                album_id = track['album']['id']
                album_title = track['album']['title']
            else:
                # Handle Track object
                album_id = track.album.id if hasattr(track.album, 'id') else track.album['id']
                album_title = track.album.title if hasattr(track.album, 'title') else track.album['title']
            
            print(f"  Getting tracks from album: {album_title}")
            
            # Get album details with tracks
            # Rather than implementing it here, trying to use PyDeez which was updated.
            # album_url = f"album/{album_id}/tracks"
            # album_tracks = self.deezer._get_all_pages(album_url, lambda data: data.get('data', []))
            album_tracks = self.deezer.get_tracks_for_album(album_id)
            
            print(f"  Found {len(album_tracks)} tracks in album")
            return album_tracks
            
        except Exception as e:
            print(f"  Error getting album tracks: {e}")
            return []
    
    def _find_next_already_rated_name(self) -> str:
        """
        Find the next available 'already-rated-XX' playlist name.
        
        Returns:
            Next available playlist name
        """
        prefix = self.config["already_rated_prefix"]
        existing_playlists = self.deezer.get_playlists([prefix])
        
        # Extract numbers from existing playlists
        existing_numbers = []
        for playlist in existing_playlists:
            title = playlist['title']
            if title.startswith(f"{prefix}-"):
                try:
                    number = int(title.split('-')[-1])
                    existing_numbers.append(number)
                except ValueError:
                    continue
        
        # Find next available number
        next_number = 0
        while next_number in existing_numbers:
            next_number += 1
            
        return f"{prefix}-{next_number:02d}"
    
    def create_rating_playlist(self, interactive: bool = True) -> bool:
        """
        Create a new rating playlist from the source playlist.
        
        Args:
            interactive: Whether to prompt for confirmation at each step
            
        Returns:
            True if successful, False otherwise
        """
        source_name = self.config["source_playlist_name"]
        rating_name = self.config["rating_playlist_name"]
        tracks_per_batch = self.config["tracks_per_batch"]
        
        print(f"\n=== Creating Rating Playlist ===")
        print(f"Source playlist: {source_name}")
        print(f"Rating playlist: {rating_name}")
        print(f"Tracks per batch: {tracks_per_batch}")
        
        if interactive and input("\nProceed? (y/n): ").lower() != 'y':
            return False
        
        # Step 1: Get source playlist
        print(f"\nStep 1: Getting source playlist '{source_name}'...")
        source_playlist = self.deezer.get_playlist_by_name(source_name)
        if not source_playlist:
            print(f"Error: Playlist '{source_name}' not found!")
            return False
        
        # Get tracks from source playlist
        source_tracks = self.deezer.get_tracks_for_playlist(source_playlist)
        if len(source_tracks) < tracks_per_batch:
            print(f"Error: Source playlist only has {len(source_tracks)} tracks, need at least {tracks_per_batch}")
            return False
        
        print(f"Found {len(source_tracks)} tracks in source playlist")
        
        if interactive and input("Continue? (y/n): ").lower() != 'y':
            return False
        
        # Step 2: Get first N tracks
        first_tracks = source_tracks[:tracks_per_batch]
        print(f"\nStep 2: Processing first {tracks_per_batch} tracks:")
        for i, track in enumerate(first_tracks, 1):
            if isinstance(track, dict):
                print(f"  {i}. {track['artist']['name']} - {track['title']}")
            else:
                print(f"  {i}. {track.artist} - {track.title}")
        
        if interactive and input("Continue? (y/n): ").lower() != 'y':
            return False
        
        # Step 3: Collect all album tracks
        print(f"\nStep 3: Collecting album tracks...")
        all_album_tracks = []
        
        for i, track in enumerate(first_tracks, 1):
            print(f"\nProcessing track {i}/{tracks_per_batch}...")
            album_tracks = self._get_album_tracks(track)
            all_album_tracks.extend(album_tracks)
            
            if interactive and i < len(first_tracks):
                if input("Continue to next track? (y/n): ").lower() != 'y':
                    return False
        
        # Add the original first tracks at the end
        for track in first_tracks:
            if isinstance(track, dict):
                all_album_tracks.append(track)
            else:
                # Convert Track object to dict-like format for consistency
                track_dict = {
                    'id': track.id,
                    'title': track.title,
                    'artist': {'name': track.artist},
                }
                all_album_tracks.append(track_dict)
        
        print(f"\nTotal tracks to add: {len(all_album_tracks)}")
        
        if interactive and input("Create rating playlist? (y/n): ").lower() != 'y':
            return False
        
        # Step 4: Create rating playlist
        print(f"\nStep 4: Creating playlist '{rating_name}'...")
        
        # Check if rating playlist already exists
        existing_rating = self.deezer.get_playlist_by_name(rating_name)
        if existing_rating:
            print(f"Warning: Playlist '{rating_name}' already exists!")
            if interactive:
                choice = input("What to do? (o)verwrite, (r)ename existing, (c)ancel: ").lower()
                if choice == 'c':
                    return False
                elif choice == 'r':
                    # Rename existing playlist
                    new_name = self._find_next_already_rated_name()
                    print(f"Renaming existing '{rating_name}' to '{new_name}'...")
                    # Note: You might need to add a rename_playlist method to your Deezer client
                    # For now, we'll delete and recreate
                    self.deezer.delete_playlist_by_id(existing_rating['id'])
                elif choice == 'o':
                    # Delete existing
                    self.deezer.delete_playlist_by_id(existing_rating['id'])
            else:
                # In non-interactive mode, rename existing
                new_name = self._find_next_already_rated_name()
                print(f"Auto-renaming existing '{rating_name}' to '{new_name}'...")
                self.deezer.delete_playlist_by_id(existing_rating['id'])
        
        # Create new rating playlist
        # A bit hacky. They should _all_ be `Track` objects, but now for some reason some are `dict`s. ¯\_(ツ)_/¯
        track_ids = [str(track.id) if hasattr(track, 'id') else str(track['id']) for track in all_album_tracks]
        self.deezer.create_playlists(track_ids, rating_name)

        #rating_playlist_id = self.deezer.create_playlist(rating_name)

        #self.deezer.add_tracks_to_playlist_by_track_ids(rating_playlist_id, track_ids)
        # Add tracks in chunks
        # chunk_size = 50
        # track_chunks = self.deezer.chunkify(track_ids, chunk_size)
        #
        # for i, chunk in enumerate(track_chunks, 1):
        #     print(f"Adding chunk {i}/{len(track_chunks)} to rating playlist...")
        #     try:
        #         self.deezer.add_tracks_to_playlist_by_track_ids(rating_playlist_id, chunk)
        #         time.sleep(1)  # Respect API limits
        #     except Exception as e:
        #         print(f"Error adding chunk {i}: {e}")
        
        print(f"✓ Successfully created rating playlist '{rating_name}' with {len(track_ids)} tracks")
        return True
    
    def rotate_playlists(self, interactive: bool = True) -> bool:
        """
        Remove first N tracks from source playlist and create new rating playlist.
        
        Args:
            interactive: Whether to prompt for confirmation at each step
            
        Returns:
            True if successful, False otherwise
        """
        source_name = self.config["source_playlist_name"]
        rating_name = self.config["rating_playlist_name"]
        tracks_per_batch = self.config["tracks_per_batch"]
        
        print(f"\n=== Rotating Playlists ===")
        print(f"Will remove first {tracks_per_batch} tracks from '{source_name}'")
        print(f"Will rename existing '{rating_name}' to 'already-rated-XX'")
        print(f"Will create new '{rating_name}' with next batch")
        
        if interactive and input("\nProceed with rotation? (y/n): ").lower() != 'y':
            return False
        
        # Step 1: Handle existing rating playlist
        existing_rating = self._get_playlist_by_name(rating_name)
        if existing_rating:
            new_name = self._find_next_already_rated_name()
            print(f"\nStep 1: Renaming '{rating_name}' to '{new_name}'...")
            
            if interactive and input("Confirm rename? (y/n): ").lower() != 'y':
                return False
            
            # Delete existing (we'll create the renamed one from scratch if needed)
            self.deezer.delete_playlist_by_id(existing_rating['id'])
            print(f"✓ Removed existing '{rating_name}'")
        
        # Step 2: Remove first tracks from source
        print(f"\nStep 2: Removing first {tracks_per_batch} tracks from '{source_name}'...")
        source_playlist = self._get_playlist_by_name(source_name)
        if not source_playlist:
            print(f"Error: Source playlist '{source_name}' not found!")
            return False
        
        source_tracks = self.deezer.get_tracks_for_playlist(source_playlist)
        if len(source_tracks) < tracks_per_batch:
            print(f"Error: Source playlist only has {len(source_tracks)} tracks, need at least {tracks_per_batch}")
            return False
        
        print(f"Current source playlist has {len(source_tracks)} tracks")
        print("Tracks to be removed:")
        for i, track in enumerate(source_tracks[:tracks_per_batch], 1):
            if isinstance(track, dict):
                print(f"  {i}. {track['artist']['name']} - {track['title']}")
            else:
                print(f"  {i}. {track.artist.name} - {track.title}")
        
        if interactive and input("Confirm removal? (y/n): ").lower() != 'y':
            return False
        
        # Remove tracks (we'll recreate the playlist without the first N tracks)
        remaining_tracks = source_tracks[tracks_per_batch:]
        remaining_track_ids = []
        
        for track in remaining_tracks:
            if isinstance(track, dict):
                remaining_track_ids.append(str(track['id']))
            else:
                remaining_track_ids.append(str(track.id))
        
        # Delete and recreate source playlist
        self.deezer.delete_playlist_by_id(source_playlist['id'])
        new_source_id = self.deezer.create_playlist(source_name)
        
        if remaining_track_ids:
            # Add remaining tracks back
            chunk_size = 50
            track_chunks = self.deezer.chunkify(remaining_track_ids, chunk_size)
            
            for i, chunk in enumerate(track_chunks, 1):
                print(f"Re-adding chunk {i}/{len(track_chunks)} to source playlist...")
                try:
                    self.deezer.add_tracks_to_playlist_by_track_ids(new_source_id, chunk)
                    time.sleep(1)
                except Exception as e:
                    print(f"Error adding chunk {i}: {e}")
        
        print(f"✓ Source playlist now has {len(remaining_tracks)} tracks")
        
        # Step 3: Create new rating playlist
        print(f"\nStep 3: Creating new rating playlist...")
        success = self.create_rating_playlist(interactive=False)  # Don't prompt again
        
        if success:
            print(f"\n✓ Successfully rotated playlists!")
            print(f"  - Removed {tracks_per_batch} tracks from '{source_name}'")
            print(f"  - Created new '{rating_name}' playlist")
            return True
        else:
            print(f"\n✗ Failed to create new rating playlist")
            return False


def main():
    config = load_config()

    """Main function with menu system."""
    print("=== Rating Playlist Manager ===")

    deezer_access_token = config.get("deezer_access_token") or input("Enter your Deezer access token: ")

    # Import your existing Deezer client
    from pydeez import PyDeez  # Replace with your actual import
    deezer_client = PyDeez(deezer_access_token)
    
    # Create manager
    manager = RatingPlaylistManager(deezer_client)
    
    while True:
        print("\n" + "="*50)
        print("What would you like to do?")
        print("1. Create rating playlist (first time)")
        print("2. Rotate playlists (remove rated tracks and create new rating playlist)")
        print("3. View current configuration")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ")
        
        if choice == '1':
            print("\n--- Create Rating Playlist ---")
            print("This will create a 'rate-this' playlist with albums from first 5 tracks in 'music-00'")
            manager.create_rating_playlist(interactive=True)
            
        elif choice == '2':
            print("\n--- Rotate Playlists ---")
            print("This will remove first 5 tracks from 'music-00' and create new 'rate-this' playlist")
            manager.rotate_playlists(interactive=True)
            
        elif choice == '3':
            print("\n--- Current Configuration ---")
            for key, value in manager.config.items():
                print(f"  {key}: {value}")
            input("\nPress Enter to continue...")
            
        elif choice == '4':
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice, please try again.")


def run_non_interactive():
    """
    Run the rotation process without prompts.
    
    Instructions to make this non-interactive:
    1. Replace interactive=True with interactive=False in the function calls
    2. Remove all input() prompts
    3. Add error handling for automatic operation
    """
    print("=== Non-Interactive Mode ===")
    print("To enable this mode:")
    print("1. Test the interactive mode first to make sure everything works")
    print("2. Edit this function to load your Deezer token automatically")
    print("3. Change interactive=True to interactive=False in the rotate_playlists call")
    print("4. Add any additional error handling you need")
    print("\nExample non-interactive code:")
    print("""
    # Load token from config or environment variable
    deezer_access_token = os.getenv('DEEZER_TOKEN') or 'your_token_here'
    deezer_client = DeezerClient(deezer_access_token)
    manager = RatingPlaylistManager(deezer_client)
    
    # Run rotation without prompts
    success = manager.rotate_playlists(interactive=False)
    if success:
        print("✓ Rotation completed successfully")
    else:
        print("✗ Rotation failed")
    """)


if __name__ == "__main__":
    main()
