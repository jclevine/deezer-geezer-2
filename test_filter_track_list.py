import unittest
from typing import NamedTuple
from rating_playlist_manager_2 import RatingPlaylistManager


# Mock Track class for testing
class Track(NamedTuple):
    id: int
    name: str = ""


_filter_out_enormous_album_track_lists = RatingPlaylistManager._filter_out_enormous_album_track_lists


class TestFilterAlbumTracks(unittest.TestCase):
    def test_small_list_unchanged(self):
        """Test that lists with <= 25 items are returned unchanged"""
        # Create a list of 20 tracks
        tracks = [Track(id=i, name=f"Track {i}") for i in range(20)]

        result = _filter_out_enormous_album_track_lists(tracks, target_track_id=10)

        # Should return the same tracks
        self.assertEqual(len(result), 20)
        self.assertEqual(result, tracks)
        # Ensure it's a copy, not the same object
        self.assertIsNot(result, tracks)

    def test_middle_index_normal_case(self):
        """Test normal case where target is in the middle of a large list"""
        # Create a list of 30 tracks (ids 0-29)
        tracks = [Track(id=i, name=f"Track {i}") for i in range(30)]

        # Target track at index 15 (id=15)
        result = _filter_out_enormous_album_track_lists(tracks, target_track_id=15)

        # Should return 11 tracks: indices 10-20 (ids 10-20)
        self.assertEqual(len(result), 11)
        self.assertEqual([track.id for track in result], list(range(10, 21)))
        # The target track should be in the middle (index 5 of the result)
        self.assertEqual(result[5].id, 15)

    def test_beginning_corner_case(self):
        """Test corner case where target is near the beginning"""
        # Create a list of 30 tracks (ids 0-29)
        tracks = [Track(id=i, name=f"Track {i}") for i in range(30)]

        # Target track at index 3 (id=3) - this is < 6
        result = _filter_out_enormous_album_track_lists(tracks, target_track_id=3)

        # Should return first 11 tracks: indices 0-10 (ids 0-10)
        self.assertEqual(len(result), 11)
        self.assertEqual([track.id for track in result], list(range(11)))
        # The target track should be at index 3 of the result
        self.assertEqual(result[3].id, 3)

    def test_end_corner_case(self):
        """Test corner case where target is near the end"""
        # Create a list of 30 tracks (ids 0-29)
        tracks = [Track(id=i, name=f"Track {i}") for i in range(30)]

        # Target track at index 26 (id=26) - this is > len-6 (24)
        result = _filter_out_enormous_album_track_lists(tracks, target_track_id=26)

        # Should return last 11 tracks: indices 19-29 (ids 19-29)
        self.assertEqual(len(result), 11)
        self.assertEqual([track.id for track in result], list(range(19, 30)))
        # The target track should be at index 7 of the result (26-19=7)
        self.assertEqual(result[7].id, 26)

    def test_target_not_found(self):
        """Test case where target id is not found"""
        # Create a list of 30 tracks (ids 0-29)
        tracks = [Track(id=i, name=f"Track {i}") for i in range(30)]

        # Try to find id=99 which doesn't exist
        result = _filter_out_enormous_album_track_lists(tracks, target_track_id=99)

        # Should return a copy of the original list
        self.assertEqual(len(result), 30)
        self.assertEqual(result, tracks)
        self.assertIsNot(result, tracks)


if __name__ == '__main__':
    unittest.main()