import json
import os
from tqdm import tqdm
from pydeez import PyDeez

CONFIG_FILE = "deezer_config.json"
PLAYLIST_PREFIX = "explore-favourites"
MAX_PLAYLIST_SIZE = 2000


def load_config():
    if not os.path.exists(CONFIG_FILE):
        access_token = input("Enter your Deezer access token: ").strip()
        with open(CONFIG_FILE, "w") as f:
            json.dump({"access_token": access_token}, f)
        return access_token
    else:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)["access_token"]

def main():
    # Load Deezer API key
    access_token = load_config()
    deezer_client = PyDeez(access_token)

    # Get all favourite tracks
    favourites = deezer_client.get_favourite_tracks()
    print(f"Found {len(favourites)} favourite tracks.")

    playlist_index = 0
    current_playlist_tracks = []
    current_playlist_id = None

    # Iterate over favourites with tqdm
    for fav in tqdm(favourites, desc="Processing favourites"):
        album_id = fav.album.id
        album_tracks = deezer_client.get_tracks_for_album(album_id)

        # If adding album would exceed the playlist size, split or move to next playlist
        for track in album_tracks:
            if len(current_playlist_tracks) >= MAX_PLAYLIST_SIZE:
                # Save the current playlist
                playlist_name = f"{PLAYLIST_PREFIX}-{playlist_index:02d}"
                print(f"\nCreating playlist '{playlist_name}' with {len(current_playlist_tracks)} tracks.")
                current_playlist_id = deezer_client.create_playlist(playlist_name)
                # Add tracks in chunks of 10 (API limit)
                for chunk in [current_playlist_tracks[i:i+10] for i in range(0, len(current_playlist_tracks), 10)]:
                    deezer_client.add_tracks_to_playlist_by_track_ids(current_playlist_id, [str(t.id) for t in chunk])
                # Reset for next playlist
                playlist_index += 1
                current_playlist_tracks = []

            current_playlist_tracks.append(track)

    # Create last playlist if any tracks remain
    if current_playlist_tracks:
        playlist_name = f"{PLAYLIST_PREFIX}-{playlist_index:02d}"
        print(f"\nCreating playlist '{playlist_name}' with {len(current_playlist_tracks)} tracks.")
        current_playlist_id = deezer_client.create_playlist(playlist_name)
        for chunk in [current_playlist_tracks[i:i+10] for i in range(0, len(current_playlist_tracks), 10)]:
            deezer_client.add_tracks_to_playlist_by_track_ids(current_playlist_id, [str(t.id) for t in chunk])

    print("\nDone.")

if __name__ == "__main__":
    main()
