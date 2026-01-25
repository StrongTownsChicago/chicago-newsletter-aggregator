# This module defines privacy-related patterns as module-level constants.
# These patterns are used for sanitizing content by identifying and removing
# sensitive or irrelevant information, such as unsubscribe links or social media
# sharing links from newsletters.

# List of URL patterns (regular expressions) to identify and remove.
URL_PATTERNS = [
    r"list-manage\.com/unsubscribe",
    r"list-manage\.com/profile",
    r"list-manage\.com/about",
    r"list-manage\.com/vcard",
    r"list-manage\.com/track/click",
    r"constantcontact\.com/do\?.*p=un",
    r"constantcontact\.com/do\?.*p=oo",
    r"constantcontact\.com/legal/customer-contact-data-notice",
    r"mailchimpsites\.com/manage/preferences",
    r"mailchi\.mp/.*\?e=",
    r"sparkpostmail\.com/f/a/.*/unsubscribe",
    r"forward-to-friend\.com",
    r"rs6\.net/tn\.jsp",
    r"constantcontact\.com/landing1/vr/home",
    r"login\.mailchimp\.com/signup",
    r"campaign-archive\.com",
]

# List of text patterns (regular expressions) to identify and remove.
TEXT_PATTERNS = [
    r"unsubscribe",
    r"update.*profile",
    r"manage.*preferences",
    r"subscription.*preferences",
    r"update.*preferences",
    r"forward.*friend",
    r"view.*browser",
    r"read.*browser",
    r"address.*book",
]

# List of CSS selectors to identify and remove HTML elements.
SELECTORS = [
    ".complianceLinks",
    "#footer-links",
    ".footer-links",
    ".unsubscribe",
    ".mcnViewInBrowser",
    "#mcnViewInBrowser",
]

# Dictionary combining all privacy patterns for easier import and use.
PRIVACY_PATTERNS_DICT = {
    "url_patterns": URL_PATTERNS,
    "text_patterns": TEXT_PATTERNS,
    "selectors": SELECTORS,
}
