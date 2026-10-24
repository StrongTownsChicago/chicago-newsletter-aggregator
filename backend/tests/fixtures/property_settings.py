"""Shared Hypothesis settings for the property-based tests."""

from hypothesis import settings

# No deadline: BeautifulSoup parsing time varies across CI runners, and a slow
# example is not a failure. 200 examples keep each property under a few seconds.
PROPERTY_SETTINGS = settings(max_examples=200, deadline=None)
