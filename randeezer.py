from getpass import getpass
from input_tool import get_input_list, yes_no_query
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

    # proceed_to_remove_rated_tracks = yes_no_query("Would you like to remove your already rated tracks (including "
    #                                               "playlists starting with 'favourite' and 'nope')?",
    #                                               default=False)
    proceed_to_remove_rated_tracks = True

    if proceed_to_remove_rated_tracks:
        tracks = remove_tracks(pydeez, tracks, ['favourite', 'nope'], include_favourites=True)

    pydeez.create_playlists(tracks, 'all')


def randeezer(pydeez, prefixes):
    print("Getting all the playlists that start with {}:".format(prefixes))
    playlists = pydeez.get_playlists(prefixes=prefixes)

    print([playlist.title for playlist in playlists])
    print('Total Number of Tracks: {}'.format(
        sum([playlist.track_count for playlist in playlists])))

    # proceed_to_randomize = yes_no_query('Is this what you wanted?', default=False)
    proceed_to_randomize = True

    if not proceed_to_randomize:
        exit(1)

    tracks = pydeez.get_tracks_for_playlists(playlists)
    print('Total Number of Tracks Received: {}'.format(len(tracks)))

    print('Randomizing tracks...')
    return sample(list(set(tracks)), len(list(set(tracks))))


def remove_tracks(pydeez, tracks, prefixes, include_favourites):
    tracks_to_remove = set()
    if include_favourites:
        tracks_to_remove.update(pydeez.get_favourite_tracks())

    playlists_to_remove = pydeez.get_playlists(prefixes=prefixes)
    tracks_to_remove.update(pydeez.get_tracks_for_playlists(playlists_to_remove))

    tracks_to_be_pruned = list((set(tracks) & tracks_to_remove))
    proceed_remove_tracks = yes_no_query('I found {} tracks that were already rated. Should I remove them?'.
                                         format(len(tracks_to_be_pruned)),
                                         default=False)

    return list((set(tracks) - tracks_to_remove)) if proceed_remove_tracks else tracks


if __name__ == "__main__":
    main()
