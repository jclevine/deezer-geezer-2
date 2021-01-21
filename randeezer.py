from getpass import getpass
from input_tool import get_input_list
from pydeez import PyDeez
from random import sample


def main():
    print("Welcome to Randeezer! Let's randomize all your playlists!")
    print("")
    access_token = getpass("Let's start with your API access token: ")

    pydeez = PyDeez(access_token)

    print("Enter the prefixes of the playlists you want to include. Leave it empty when you're done:\n")
    prefixes = get_input_list()

    tracks = randeezer(pydeez, prefixes)

    pydeez.create_playlists(tracks, 'all')


def randeezer(pydeez, prefixes):
    print("Getting all the playlists that start with {}:".format(prefixes))
    playlists = pydeez.get_playlists(prefixes=prefixes)

    print([playlist.title for playlist in playlists])
    print('Total Number of Tracks: {}'.format(
        sum([playlist.track_count for playlist in playlists])))

    tracks = pydeez.get_tracks_for_playlists(playlists)
    print('Total Number of Tracks Received: {}'.format(len(tracks)))

    print('Randomizing tracks...')
    return sample(list(set(tracks)), len(list(set(tracks))))


if __name__ == "__main__":
    main()
