import json
import os
import time
from datetime import datetime
from typing import Set, Optional
import pylast
from tqdm import tqdm
import psutil

from track_similarity_matcher import TrackSimilarityMatcher, RecommendedConfig


class DeezerFavoritesAnalyzer:
    """Analyzes Deezer favorites and creates playlists of unheard tracks."""

    def __init__(self, deezer_client, lastfm_client):
        self.deezer = deezer_client
        self.lastfm = lastfm_client
        self.batch_size = 10  # Deezer API limit for adding tracks
        self.process = psutil.Process()  # For memory monitoring

    def _log_memory_usage(self, label: str = ""):
        """Log current memory usage."""
        mem_mb = self.process.memory_info().rss / 1024 / 1024
        print(f"[Memory] {label}: {mem_mb:.1f} MB")

    # 2025-10-10 - 259 days ago :: 205 tracks :: 14 hrs 27 min
    # 2026-01-15 - 309 days ago :: 309 tracks :: 21 hrs 17 min
    # 2026-01-19 - 290 days ago :: 202 tracks :: 13 hrs 51 min
    # 2026-01-22 - 280 days ago :: 207 tracks :: 13 hrs 39 min
    # 2026-02-28 - 300 days ago :: 178 tracks :: 11 hrs 40 min
    # 2026-03-01 - 270 days ago :: 808 tracks :: 54 hrs 36 min
    # 2026-03-01 - 300 days ago :: 070 tracks :: 05 hrs 11 min
    # 2026-03-01 - 285 days ago :: 320 tracks :: 21 hrs 01 min
    # 2026-03-08 - 270 days ago :: 704 tracks :: 49 hrs 34 min
    # 2026-03-08 - 296 days ago :: xxx tracks :: xx hrs xx min
    def create_unheard_favorites_playlist(
            self,
            days_lookback: int = 259,
            problematic_ids: Optional[Set[int]] = None,
            save_interval: int = 50
    ) -> Optional[str]:
        """
        Create a playlist of favorite tracks not listened to in the specified timeframe.
        Saves progress incrementally to avoid data loss.

        Args:
            days_lookback: Number of days to look back in listening history
            problematic_ids: Set of track IDs to exclude
            save_interval: Save playlist after every N unheard tracks found

        Returns:
            ID of the created playlist or None if no tracks found
        """
        if problematic_ids is None:
            problematic_ids = set()

        # Create playlist name with current date
        playlist_name = datetime.now().strftime("%Y-%m-%d")
        print(f"Creating playlist: {playlist_name}")
        self._log_memory_usage("Start")

        # Initialize matcher WITHOUT storing history (memory saver)
        matcher = TrackSimilarityMatcher(RecommendedConfig())

        # Fetch favorites
        print("Fetching favorite tracks from Deezer...")
        favorite_tracks = self.deezer.get_favourite_tracks()
        print(f"Found {len(favorite_tracks)} favorite tracks")
        self._log_memory_usage("After loading favorites")

        # Filter out problematic tracks
        favorite_tracks = [t for t in favorite_tracks if t.id not in problematic_ids]
        print(f"After filtering: {len(favorite_tracks)} tracks")

        # Get recent listening history as a memory-efficient set
        print(f"Fetching Last.fm history (past {days_lookback} days)...")
        recent_tracks_set = self._get_recent_tracks_set(days_lookback)
        print(f"Loaded {len(recent_tracks_set)} recent tracks")
        self._log_memory_usage("After loading Last.fm history")

        # Create playlist immediately (so we can add incrementally)
        playlist_id = self.deezer.create_playlist(playlist_name)
        print(f"Created playlist with ID: {playlist_id}")

        # Process favorites and add to playlist incrementally
        unheard_track_ids = []
        tracks_processed = 0

        print("Searching for unheard favorites...")
        for track in tqdm(favorite_tracks, desc="Processing favorites"):
            tracks_processed += 1

            # Check if track was recently played
            if not self._was_recently_played(
                    track.artist,
                    track.title,
                    recent_tracks_set,
                    matcher
            ):
                unheard_track_ids.append(track.id)

                # Save progress at intervals
                if len(unheard_track_ids) >= save_interval:
                    self._add_tracks_to_playlist(playlist_id, unheard_track_ids)
                    print(f"\nSaved {len(unheard_track_ids)} tracks to playlist "
                          f"(processed {tracks_processed}/{len(favorite_tracks)})")
                    self._log_memory_usage(f"After saving batch at {tracks_processed}")
                    unheard_track_ids.clear()

            # Periodic garbage collection hint for large datasets
            if tracks_processed % 1000 == 0:
                import gc
                gc.collect()
                self._log_memory_usage(f"After processing {tracks_processed} tracks")

        # Add any remaining tracks
        if unheard_track_ids:
            self._add_tracks_to_playlist(playlist_id, unheard_track_ids)
            print(f"\nAdded final batch of {len(unheard_track_ids)} tracks")

        self._log_memory_usage("Before fetching final count")

        # Get final count
        final_tracks = self.deezer.get_tracks_for_playlist(
            self.deezer.get_playlist_by_name(playlist_name)
        )
        total_count = len(list(final_tracks))

        if total_count == 0:
            print("No unheard favorites found. Deleting empty playlist.")
            # Note: Add playlist deletion if your API supports it
            return None

        print(f"\n✓ Successfully created playlist '{playlist_name}' with {total_count} unheard favorites")
        return playlist_id

    def _get_recent_tracks_set(self, days_lookback: int) -> Set[tuple]:
        """
        Fetch recent tracks from Last.fm as a memory-efficient set.

        Returns:
            Set of (artist_name, track_title) tuples
        """
        current_time = int(time.time())
        seconds_ago = current_time - (days_lookback * 24 * 60 * 60)

        recent_plays = self.lastfm.get_recent_tracks(
            None, True, seconds_ago, current_time, False, False
        )

        # Store only essential data: (artist, title) tuples
        recent_tracks_set = set()
        for play in recent_plays:
            try:
                artist = play.track.artist.name.lower().strip()
                title = play.track.title.lower().strip()
                recent_tracks_set.add((artist, title))
            except AttributeError:
                continue

        return recent_tracks_set

    def _was_recently_played(
            self,
            artist: str,
            title: str,
            recent_tracks_set: Set[tuple],
            matcher: TrackSimilarityMatcher
    ) -> bool:
        """
        Check if a track was recently played using optimized matching.

        Args:
            artist: Artist name to check
            title: Track title to check
            recent_tracks_set: Set of recent (artist, title) tuples
            matcher: TrackSimilarityMatcher instance

        Returns:
            True if track was recently played
        """
        # Quick exact match check (O(1) lookup)
        artist_lower = artist.lower().strip()
        title_lower = title.lower().strip()

        if (artist_lower, title_lower) in recent_tracks_set:
            return True

        # Fuzzy matching only if exact match fails
        # CRITICAL: store_result=False prevents memory leak
        for recent_artist, recent_title in recent_tracks_set:
            is_match, _ = matcher.are_tracks_similar(
                artist, title, recent_artist, recent_title,
                store_result=False  # DO NOT STORE - prevents memory leak
            )
            if is_match:
                return True

        return False

    def _add_tracks_to_playlist(self, playlist_id: str, track_ids: list):
        """
        Add tracks to playlist in batches respecting API limits.

        Args:
            playlist_id: Playlist ID
            track_ids: List of track IDs to add
        """
        # Remove duplicates while preserving order
        seen = set()
        unique_ids = []
        for tid in track_ids:
            if tid not in seen:
                seen.add(tid)
                unique_ids.append(tid)

        # Add in batches
        for i in range(0, len(unique_ids), self.batch_size):
            batch = unique_ids[i:i + self.batch_size]
            string_ids = [str(tid) for tid in batch]

            try:
                self.deezer.add_tracks_to_playlist_by_track_ids(playlist_id, string_ids)
                time.sleep(0.5)  # Rate limiting
            except Exception as e:
                print(f"Warning: Failed to add batch {i // self.batch_size + 1}: {e}")


def load_config() -> dict:
    """Load configuration from file or create default."""
    config_file = "config.json"
    default_config = {
        "deezer_access_token": "",
        "lastfm_api_key": "",
        "lastfm_username": ""
    }

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")

    with open(config_file, 'w') as f:
        json.dump(default_config, f, indent=4)
    print(f"Created default config at {config_file}")
    return default_config


def save_config(config: dict):
    """Save configuration to file."""
    with open("config.json", 'w') as f:
        json.dump(config, f, indent=4)


def main():
    """Main entry point."""
    print("=" * 60)
    print("Deezer Unheard Favorites Playlist Creator")
    print("=" * 60)

    try:
        # Load configuration
        config = load_config()

        # Get credentials (only prompt if missing)
        deezer_token = config.get("deezer_access_token")
        if not deezer_token:
            deezer_token = input("Enter Deezer access token: ").strip()
            config["deezer_access_token"] = deezer_token
            save_config(config)

        lastfm_key = config.get("lastfm_api_key")
        if not lastfm_key:
            lastfm_key = input("Enter Last.fm API key: ").strip()
            config["lastfm_api_key"] = lastfm_key
            save_config(config)

        lastfm_user = config.get("lastfm_username")
        if not lastfm_user:
            lastfm_user = input("Enter Last.fm username: ").strip()
            config["lastfm_username"] = lastfm_user
            save_config(config)

        # Initialize API clients
        from pydeez import PyDeez
        deezer_client = PyDeez(deezer_token)
        lastfm_network = pylast.LastFMNetwork(api_key=lastfm_key, username=lastfm_user)
        lastfm_client = lastfm_network.get_user(lastfm_user)

        # Get problematic tracks to exclude
        print("\nLoading problematic tracks...")
        try:
            problematic_playlist = deezer_client.get_playlist_by_name('problematic-list-for-results-only')
            problematic_tracks = set(
                track.id for track in deezer_client.get_tracks_for_playlist(problematic_playlist)
            )
            print(f"Loaded {len(problematic_tracks)} problematic tracks to exclude")
        except Exception as e:
            print(f"Note: Could not load problematic tracks ({e})")
            problematic_tracks = set()

        # Create analyzer and run
        analyzer = DeezerFavoritesAnalyzer(deezer_client, lastfm_client)

        # Optional: ask for days lookback
        days_input = input("\nDays of listening history to check (default 259): ").strip()
        days_lookback = int(days_input) if days_input else 259

        playlist_id = analyzer.create_unheard_favorites_playlist(
            days_lookback=days_lookback,
            # problematic_ids=problematic_tracks, Not adding any problematic tracks for now. Maybe they're fixed?
            save_interval=50  # Save every 50 tracks
        )

        if playlist_id:
            print(f"\n✓ Success! Playlist created with ID: {playlist_id}")
        else:
            print("\nNo unheard favorites found.")

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()