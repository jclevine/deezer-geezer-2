import re
import json
from typing import Tuple, Optional, List, Dict, Any
from fuzzywuzzy import fuzz
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class SimilarityConfig:
    """Configuration for similarity matching thresholds."""
    # Artist matching thresholds
    artist_similarity_threshold: int = 75
    artist_strict_threshold: int = 90  # For very close matches

    # Track matching thresholds
    track_similarity_threshold: int = 80
    track_strict_threshold: int = 95  # For very close matches

    # Combined matching thresholds
    combined_match_threshold: float = 0.8  # Weighted score threshold
    artist_weight: float = 0.2  # Weight for artist similarity in combined score
    track_weight: float = 0.7  # Weight for track similarity in combined score


@dataclass
class MatchResult:
    """Structure to hold detailed match results."""
    track1: Tuple[str, str]  # (artist, track)
    track2: Tuple[str, str]  # (artist, track)
    is_match: bool
    artist_similarity: int
    track_similarity: int
    combined_score: float
    match_reason: List[str]
    cleaned_artist1: str
    cleaned_artist2: str
    cleaned_track1: str
    cleaned_track2: str
    is_exact_match: bool


class TrackSimilarityMatcher:
    """A class to handle fuzzy matching between track artist/title pairs."""

    def __init__(self, config: Optional[SimilarityConfig] = None):
        self.config = config or SimilarityConfig()
        self.match_history: List[MatchResult] = []

    def clean_artist_name(self, artist: str) -> str:
        """Clean artist name for better matching."""
        cleaned = artist.strip()

        # Handle common substitutions
        cleaned = re.sub(r'\s*&\s*', ' and ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\+\s*', ' and ', cleaned, flags=re.IGNORECASE)

        # Remove parenthetical additions like "(feat. Someone)"
        cleaned = re.sub(r'\s*\([^)]*(?:feat|ft|featuring)[^)]*\)', '', cleaned, flags=re.IGNORECASE)

        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned.lower()

    def clean_track_name(self, track: str) -> str:
        """Clean track name by removing parenthetical content and common suffixes."""
        cleaned = track.strip()

        # Remove everything in parentheses
        cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned)

        # Remove everything in square brackets
        cleaned = re.sub(r'\s*\[[^\]]*\]', '', cleaned)

        # Remove common suffixes that might interfere with matching
        suffixes_to_remove = [
            r'\s*-\s*remaster(?:ed)?',
            r'\s*-\s*remix',
            r'\s*-\s*radio\s*edit',
            r'\s*-\s*single\s*version',
            r'\s*-\s*album\s*version',
            r'\s*-\s*extended\s*version',
        ]

        for suffix in suffixes_to_remove:
            cleaned = re.sub(suffix, '', cleaned, flags=re.IGNORECASE)

        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned.lower()

    def calculate_artist_similarity(self, artist1: str, artist2: str) -> int:
        """Calculate similarity score between two artist names."""
        clean1 = self.clean_artist_name(artist1)
        clean2 = self.clean_artist_name(artist2)

        # Quick exact match check first
        if clean1 == clean2:
            return 100

        # Use token_sort_ratio for better handling of word order differences
        return fuzz.token_sort_ratio(clean1, clean2)

    def calculate_track_similarity(self, track1: str, track2: str) -> int:
        """Calculate similarity score between two track names."""
        clean1 = self.clean_track_name(track1)
        clean2 = self.clean_track_name(track2)

        # Quick exact match check first
        if clean1 == clean2:
            return 100

        # Use token_sort_ratio for better handling of word order differences
        return fuzz.token_sort_ratio(clean1, clean2)

    def calculate_combined_score(self, artist_similarity: int, track_similarity: int) -> float:
        """Calculate a weighted combined similarity score."""
        artist_score = artist_similarity / 100.0
        track_score = track_similarity / 100.0

        combined = (artist_score * self.config.artist_weight +
                    track_score * self.config.track_weight)

        return combined

    def are_tracks_similar(self, artist1: str, track1: str, artist2: str, track2: str,
                           store_result: bool = True) -> Tuple[bool, MatchResult]:
        """
        Determine if two artist/track pairs are similar enough to be considered matches.
        Fast version with early exits and lazy evaluation.

        Returns:
            Tuple of (is_match, MatchResult)
        """
        # Quick exact match check first (fastest possible)
        artist1_clean = artist1.lower().strip()
        artist2_clean = artist2.lower().strip()
        track1_clean = track1.lower().strip()
        track2_clean = track2.lower().strip()

        is_exact_match = (artist1_clean == artist2_clean and track1_clean == track2_clean)

        if is_exact_match:
            # Skip all expensive calculations for exact matches
            result = MatchResult(
                track1=(artist1, track1),
                track2=(artist2, track2),
                is_match=True,
                artist_similarity=100,
                track_similarity=100,
                combined_score=1.0,
                match_reason=['exact_match'],
                cleaned_artist1=artist1_clean,
                cleaned_artist2=artist2_clean,
                cleaned_track1=track1_clean,
                cleaned_track2=track2_clean,
                is_exact_match=True
            )
            if store_result:
                self.match_history.append(result)
            return True, result

        # Pre-compute cleaned versions once (expensive operations)
        cleaned_artist1 = self.clean_artist_name(artist1)
        cleaned_artist2 = self.clean_artist_name(artist2)
        cleaned_track1 = self.clean_track_name(track1)
        cleaned_track2 = self.clean_track_name(track2)

        # Quick length-based early rejection (very fast heuristic)
        # If lengths are too different, likely not a match
        artist_len_diff = abs(len(cleaned_artist1) - len(cleaned_artist2))
        track_len_diff = abs(len(cleaned_track1) - len(cleaned_track2))

        # If both artist and track names are very different in length, probably not a match
        if (artist_len_diff > max(len(cleaned_artist1), len(cleaned_artist2)) * 0.6 and
                track_len_diff > max(len(cleaned_track1), len(cleaned_track2)) * 0.6):
            # Still calculate for the result object, but we expect low scores
            pass

        # Calculate similarities (expensive operations)
        artist_sim = fuzz.token_sort_ratio(cleaned_artist1, cleaned_artist2)
        track_sim = fuzz.token_sort_ratio(cleaned_track1, cleaned_track2)

        # Early exit if both are below minimum viable thresholds
        min_artist_threshold = self.config.artist_similarity_threshold - 15
        min_track_threshold = self.config.track_similarity_threshold - 15

        if artist_sim < min_artist_threshold and track_sim < min_track_threshold:
            # Very low similarity in both dimensions - definitely not a match
            result = MatchResult(
                track1=(artist1, track1),
                track2=(artist2, track2),
                is_match=False,
                artist_similarity=artist_sim,
                track_similarity=track_sim,
                combined_score=self.calculate_combined_score(artist_sim, track_sim),
                match_reason=[],
                cleaned_artist1=cleaned_artist1,
                cleaned_artist2=cleaned_artist2,
                cleaned_track1=cleaned_track1,
                cleaned_track2=cleaned_track2,
                is_exact_match=False
            )
            if store_result:
                self.match_history.append(result)
            return False, result

        # Calculate combined score
        combined_score = self.calculate_combined_score(artist_sim, track_sim)

        # Determine match using short-circuit evaluation (stops at first True)
        match_reason = []
        is_match = False

        # 1. Basic thresholds (most common case)
        if (artist_sim >= self.config.artist_similarity_threshold and
                track_sim >= self.config.track_similarity_threshold):
            is_match = True
            match_reason.append('basic_thresholds')

        # 2. Combined score (only if basic didn't match)
        elif combined_score >= self.config.combined_match_threshold:
            is_match = True
            match_reason.append('combined_score')

        # 3. High artist similarity (only if others didn't match)
        elif (artist_sim >= self.config.artist_strict_threshold and
              track_sim >= (self.config.track_similarity_threshold - 10)):
            is_match = True
            match_reason.append('high_artist_similarity')

        # 4. High track similarity (only if others didn't match)
        elif (track_sim >= self.config.track_strict_threshold and
              artist_sim >= (self.config.artist_similarity_threshold - 10)):
            is_match = True
            match_reason.append('high_track_similarity')

        result = MatchResult(
            track1=(artist1, track1),
            track2=(artist2, track2),
            is_match=is_match,
            artist_similarity=artist_sim,
            track_similarity=track_sim,
            combined_score=combined_score,
            match_reason=match_reason,
            cleaned_artist1=cleaned_artist1,
            cleaned_artist2=cleaned_artist2,
            cleaned_track1=cleaned_track1,
            cleaned_track2=cleaned_track2,
            is_exact_match=False
        )

        if store_result:
            self.match_history.append(result)

        return is_match, result

    def find_best_match(self, target_artist: str, target_track: str,
                        candidate_tracks: list) -> Tuple[Optional[tuple], Optional[MatchResult]]:
        """
        Find the best matching track from a list of candidates.

        Args:
            target_artist: Artist name to match against
            target_track: Track name to match against
            candidate_tracks: List of (artist, track) tuples to search through

        Returns:
            Tuple of (best_match_tuple, MatchResult) or (None, None) if no good match
        """
        best_match = None
        best_result = None
        best_score = 0

        for candidate_artist, candidate_track in candidate_tracks:
            is_match, result = self.are_tracks_similar(
                target_artist, target_track, candidate_artist, candidate_track,
                store_result=False  # Don't store intermediate results
            )

            if is_match and result.combined_score > best_score:
                best_match = (candidate_artist, candidate_track)
                best_result = result
                best_score = result.combined_score

        if best_result:
            self.match_history.append(best_result)

        return best_match, best_result

    def create_review_file(self, filename: str = None) -> str:
        """
        Create a human-readable review file for manual verification of matches.

        Returns:
            The filename of the created review file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"match_review_{timestamp}.txt"

        # Filter out exact matches for review
        non_exact = [r for r in self.match_history if not r.is_exact_match]

        with open(filename, 'w', encoding='utf-8') as f:
            f.write("TRACK MATCHING REVIEW FILE\n")
            f.write("=" * 50 + "\n\n")
            f.write("INSTRUCTIONS:\n")
            f.write("- Review each comparison below\n")
            f.write("- For FALSE NEGATIVES (should match but didn't): Change 'MATCH: NO' to 'MATCH: YES'\n")
            f.write("- For FALSE POSITIVES (matched but shouldn't): Change 'MATCH: YES' to 'MATCH: NO'\n")
            f.write("- Leave correct decisions unchanged\n")
            f.write("- Save this file when done and provide it back for analysis\n\n")
            f.write("=" * 50 + "\n\n")

            # Group by match status for easier review
            matched = [r for r in non_exact if r.is_match]
            not_matched = [r for r in non_exact if not r.is_match]

            if matched:
                f.write("TRACKS THAT WERE MATCHED (Review for False Positives)\n")
                f.write("-" * 50 + "\n")
                for i, result in enumerate(matched, 1):
                    self._write_comparison(f, result, i)
                f.write("\n")

            if not_matched:
                f.write("TRACKS THAT WERE NOT MATCHED (Review for False Negatives)\n")
                f.write("-" * 50 + "\n")
                for i, result in enumerate(not_matched, len(matched) + 1):
                    self._write_comparison(f, result, i)

        print(f"Review file created: {filename}")
        print(f"Total comparisons for review: {len(non_exact)}")
        print(f"- Matched pairs: {len(matched)}")
        print(f"- Not matched pairs: {len(not_matched)}")

        return filename

    def _write_comparison(self, f, result: MatchResult, index: int):
        """Write a single comparison to the review file."""
        f.write(f"COMPARISON #{index}\n")
        f.write(f"Track A: '{result.track1[0]}' - '{result.track1[1]}'\n")
        f.write(f"Track B: '{result.track2[0]}' - '{result.track2[1]}'\n")
        f.write(f"Cleaned A: '{result.cleaned_artist1}' - '{result.cleaned_track1}'\n")
        f.write(f"Cleaned B: '{result.cleaned_artist2}' - '{result.cleaned_track2}'\n")
        f.write(f"Artist Similarity: {result.artist_similarity}%\n")
        f.write(f"Track Similarity: {result.track_similarity}%\n")
        f.write(f"Combined Score: {result.combined_score:.3f}\n")
        f.write(f"MATCH: {'YES' if result.is_match else 'NO'}\n")
        if result.match_reason:
            f.write(f"Reason: {', '.join(result.match_reason)}\n")
        f.write("=" * 30 + "\n\n")

    def process_review_file(self, filename: str) -> Dict[str, Any]:
        """
        Process a reviewed file to identify false positives and false negatives.

        Returns:
            Dictionary with analysis results and suggested config changes
        """
        false_positives = []  # Was matched, should not be
        false_negatives = []  # Was not matched, should be
        correct_decisions = []

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse the file to extract comparisons and their manual review results
            comparisons = self._parse_review_file(content)

            for comp in comparisons:
                original_match = comp['original_match']
                manual_match = comp['manual_match']

                if original_match and not manual_match:
                    false_positives.append(comp)
                elif not original_match and manual_match:
                    false_negatives.append(comp)
                else:
                    correct_decisions.append(comp)

            # Analyze patterns and suggest config changes
            analysis = self._analyze_feedback(false_positives, false_negatives)

            result = {
                'false_positives': len(false_positives),
                'false_negatives': len(false_negatives),
                'correct_decisions': len(correct_decisions),
                'total_reviewed': len(comparisons),
                'accuracy': len(correct_decisions) / len(comparisons) if comparisons else 0,
                'analysis': analysis,
                'false_positive_examples': false_positives[:3],  # Show up to 3 examples
                'false_negative_examples': false_negatives[:3]  # Show up to 3 examples
            }

            return result

        except FileNotFoundError:
            raise FileNotFoundError(f"Review file '{filename}' not found")
        except Exception as e:
            raise Exception(f"Error processing review file: {str(e)}")

    def _parse_review_file(self, content: str) -> List[Dict[str, Any]]:
        """Parse the review file content to extract comparisons."""
        comparisons = []

        # Split into individual comparisons
        sections = re.split(r'COMPARISON #\d+', content)[1:]  # Skip header

        for section in sections:
            try:
                # Extract match decision
                match_line = re.search(r'MATCH: (YES|NO)', section)
                if not match_line:
                    continue

                manual_match = match_line.group(1) == 'YES'

                # Extract similarity scores
                artist_sim = int(re.search(r'Artist Similarity: (\d+)%', section).group(1))
                track_sim = int(re.search(r'Track Similarity: (\d+)%', section).group(1))
                combined_score = float(re.search(r'Combined Score: ([\d.]+)', section).group(1))

                # Extract track info
                track_a_match = re.search(r"Track A: '([^']+)' - '([^']+)'", section)
                track_b_match = re.search(r"Track B: '([^']+)' - '([^']+)'", section)

                if track_a_match and track_b_match:
                    # Determine original match decision based on current config
                    original_match = self._would_match(artist_sim, track_sim, combined_score)

                    comparisons.append({
                        'track_a': (track_a_match.group(1), track_a_match.group(2)),
                        'track_b': (track_b_match.group(1), track_b_match.group(2)),
                        'artist_similarity': artist_sim,
                        'track_similarity': track_sim,
                        'combined_score': combined_score,
                        'original_match': original_match,
                        'manual_match': manual_match
                    })
            except (AttributeError, ValueError) as e:
                print(f"Warning: Could not parse comparison section: {e}")
                continue

        return comparisons

    def _would_match(self, artist_sim: int, track_sim: int, combined_score: float) -> bool:
        """Determine if tracks would match based on current config."""
        basic_match = (artist_sim >= self.config.artist_similarity_threshold and
                       track_sim >= self.config.track_similarity_threshold)

        combined_match = combined_score >= self.config.combined_match_threshold

        high_artist_match = (artist_sim >= self.config.artist_strict_threshold and
                             track_sim >= (self.config.track_similarity_threshold - 10))
        high_track_match = (track_sim >= self.config.track_strict_threshold and
                            artist_sim >= (self.config.artist_similarity_threshold - 10))

        return basic_match or combined_match or high_artist_match or high_track_match

    def _analyze_feedback(self, false_positives: List[Dict], false_negatives: List[Dict]) -> Dict[str, Any]:
        """Analyze feedback patterns to suggest configuration improvements."""
        analysis = {
            'suggested_changes': [],
            'patterns': {}
        }

        if false_positives:
            # Analyze false positives - maybe thresholds are too low
            fp_artist_scores = [fp['artist_similarity'] for fp in false_positives]
            fp_track_scores = [fp['track_similarity'] for fp in false_positives]
            fp_combined_scores = [fp['combined_score'] for fp in false_positives]

            analysis['patterns']['false_positive_avg_artist'] = sum(fp_artist_scores) / len(fp_artist_scores)
            analysis['patterns']['false_positive_avg_track'] = sum(fp_track_scores) / len(fp_track_scores)
            analysis['patterns']['false_positive_avg_combined'] = sum(fp_combined_scores) / len(fp_combined_scores)

            # Suggest raising thresholds
            min_fp_artist = min(fp_artist_scores)
            min_fp_track = min(fp_track_scores)
            min_fp_combined = min(fp_combined_scores)

            analysis['suggested_changes'].append(f"Consider raising artist_similarity_threshold above {min_fp_artist}")
            analysis['suggested_changes'].append(f"Consider raising track_similarity_threshold above {min_fp_track}")
            analysis['suggested_changes'].append(
                f"Consider raising combined_match_threshold above {min_fp_combined:.3f}")

        if false_negatives:
            # Analyze false negatives - maybe thresholds are too high
            fn_artist_scores = [fn['artist_similarity'] for fn in false_negatives]
            fn_track_scores = [fn['track_similarity'] for fn in false_negatives]
            fn_combined_scores = [fn['combined_score'] for fn in false_negatives]

            analysis['patterns']['false_negative_avg_artist'] = sum(fn_artist_scores) / len(fn_artist_scores)
            analysis['patterns']['false_negative_avg_track'] = sum(fn_track_scores) / len(fn_track_scores)
            analysis['patterns']['false_negative_avg_combined'] = sum(fn_combined_scores) / len(fn_combined_scores)

            # Suggest lowering thresholds
            max_fn_artist = max(fn_artist_scores)
            max_fn_track = max(fn_track_scores)
            max_fn_combined = max(fn_combined_scores)

            analysis['suggested_changes'].append(
                f"Consider lowering artist_similarity_threshold to at least {max_fn_artist}")
            analysis['suggested_changes'].append(
                f"Consider lowering track_similarity_threshold to at least {max_fn_track}")
            analysis['suggested_changes'].append(
                f"Consider lowering combined_match_threshold to at least {max_fn_combined:.3f}")

        return analysis

    def apply_suggested_config(self, analysis_result: Dict[str, Any]) -> SimilarityConfig:
        """
        Create a new config based on analysis suggestions.
        This provides a starting point - you may want to fine-tune further.
        """
        new_config = SimilarityConfig(
            artist_similarity_threshold=self.config.artist_similarity_threshold,
            artist_strict_threshold=self.config.artist_strict_threshold,
            track_similarity_threshold=self.config.track_similarity_threshold,
            track_strict_threshold=self.config.track_strict_threshold,
            combined_match_threshold=self.config.combined_match_threshold,
            artist_weight=self.config.artist_weight,
            track_weight=self.config.track_weight
        )

        patterns = analysis_result.get('patterns', {})

        # Adjust based on false positives and negatives
        if 'false_positive_avg_artist' in patterns and 'false_negative_avg_artist' in patterns:
            # Find middle ground
            new_threshold = (patterns['false_positive_avg_artist'] + patterns['false_negative_avg_artist']) / 2
            new_config.artist_similarity_threshold = int(new_threshold)
        elif 'false_positive_avg_artist' in patterns:
            # Raise threshold to reduce false positives
            new_config.artist_similarity_threshold = min(95, int(patterns['false_positive_avg_artist']) + 5)
        elif 'false_negative_avg_artist' in patterns:
            # Lower threshold to reduce false negatives
            new_config.artist_similarity_threshold = max(50, int(patterns['false_negative_avg_artist']) - 5)

        # Similar logic for track similarity
        if 'false_positive_avg_track' in patterns and 'false_negative_avg_track' in patterns:
            new_threshold = (patterns['false_positive_avg_track'] + patterns['false_negative_avg_track']) / 2
            new_config.track_similarity_threshold = int(new_threshold)
        elif 'false_positive_avg_track' in patterns:
            new_config.track_similarity_threshold = min(95, int(patterns['false_positive_avg_track']) + 5)
        elif 'false_negative_avg_track' in patterns:
            new_config.track_similarity_threshold = max(50, int(patterns['false_negative_avg_track']) - 5)

        # Adjust combined threshold
        if 'false_positive_avg_combined' in patterns and 'false_negative_avg_combined' in patterns:
            new_threshold = (patterns['false_positive_avg_combined'] + patterns['false_negative_avg_combined']) / 2
            new_config.combined_match_threshold = new_threshold
        elif 'false_positive_avg_combined' in patterns:
            new_config.combined_match_threshold = min(0.95, patterns['false_positive_avg_combined'] + 0.05)
        elif 'false_negative_avg_combined' in patterns:
            new_config.combined_match_threshold = max(0.3, patterns['false_negative_avg_combined'] - 0.05)

        return new_config


# Example usage with manual review workflow
def example_usage_with_review():
    """Demonstrate the complete workflow including manual review."""

    # Create matcher
    matcher = TrackSimilarityMatcher()

    # Test some matches that might need review
    test_cases = [
        ("The Beatles", "Hey Jude", "Beatles", "Hey Jude (Remastered)"),
        ("Bob Dylan", "Like a Rolling Stone", "Bob Dylan", "Like A Rolling Stone"),
        ("Queen & David Bowie", "Under Pressure", "Queen and David Bowie", "Under Pressure (Remaster)"),
        ("Drake (feat. Rihanna)", "Work", "Drake", "Work"),
        ("Taylor Swift", "Shake It Off", "T Swift", "Shake It Off (Radio Edit)"),
        ("Nirvana", "Smells Like Teen Spirit", "Green Day", "Basket Case"),  # Should not match
        ("Led Zeppelin", "Stairway to Heaven", "Led Zeppelin", "Kashmir"),  # Should not match
        ("Pink Floyd", "Another Brick in the Wall", "Pink Floyd", "Another Brick in the Wall (Part 2)"),
    ]

    print("Running initial matching...")
    for artist1, track1, artist2, track2 in test_cases:
        is_match, result = matcher.are_tracks_similar(artist1, track1, artist2, track2)
        print(f"Match: {is_match} | '{artist1}' - '{track1}' vs '{artist2}' - '{track2}'")

    # Create review file
    review_file = matcher.create_review_file()

    print(f"\nReview file created: {review_file}")
    print("Please review the file, make any necessary corrections, and save it.")
    print("Then you can process the feedback using matcher.process_review_file(filename)")

    return matcher, review_file


if __name__ == "__main__":
    matcher, review_file = example_usage_with_review()

    # Simulate processing feedback (you would do this after manual review)
    print(f"\nTo process your review, run:")
    print(f"analysis = matcher.process_review_file('{review_file}')")
    print(f"print(json.dumps(analysis, indent=2))")
    print(f"new_config = matcher.apply_suggested_config(analysis)")
    print(f"improved_matcher = TrackSimilarityMatcher(new_config)")