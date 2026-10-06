"""
Configuration constants and heuristic rules for the Wikipedia Crawler.
"""

from typing import List, Set

# Wikipedia namespaces and prefixes that should be ignored during crawling
DISALLOWED_PREFIXES: List[str] = [
    "File:",
    "Talk:",
    "Special:",
    "Wikipedia:",
    "Help:",
    "Category:",
    "Portal:",
    "Template:",
    "Template_talk:",
    "User:",
    "User_talk:",
    "MediaWiki:",
    "Draft:",
    "TimedText:",
    "Module:",
    "Book:",
]

# High-centrality connector hubs that span broad subjects in Wikipedia
HIGH_CENTRALITY_HUBS: Set[str] = {
    "united_states", "united_kingdom", "europe", "north_america", "asia", "africa",
    "world", "earth", "country", "city", "history", "geography", "government",
    "economy", "culture", "society", "human", "biology", "science", "technology",
    "medicine", "law", "philosophy", "psychology", "politics", "education",
    "demographics_of_the_united_states", "human_sexuality", "culture_of_the_united_states", "south_america"
}

# Narrow, dead-end patterns to penalize
DEAD_END_PATTERNS: List[str] = [
    "road", "highway", "state_road", "interstate", "route", "airport",
    "railway", "station", "school", "high_school", "elementary", "middle_school",
    "district", "season", "championship", "tournament", "cup", "election"
]

# Prefixes for index/timeline pages to penalize
INDEX_PREFIXES: List[str] = ["list_of", "timeline_of"]

# Default crawler settings and limits
DEFAULT_USER_AGENT = "WikiHopPathfinder/2.0 (WikipediaHopExplorer; https://localhost:8005; wikihop-crawler@edu.local)"
DEFAULT_REST_USER_AGENT = "WikiHopPathfinder/2.0 (WikipediaHopExplorer; https://localhost:8005; wikihop-crawler@edu.local)"
