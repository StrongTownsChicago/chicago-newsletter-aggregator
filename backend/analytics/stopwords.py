"""Words excluded from the analytics term index.

English function words carry no topical signal, and newsletter boilerplate
(mailing-platform footers, share/unsubscribe links, greetings) appears in
nearly every newsletter regardless of content.
"""

ENGLISH_STOPWORDS: frozenset[str] = frozenset(
    """
    a about above after again against all also am an and any are aren't as at
    be because been before being below between both but by can can't cannot
    could couldn't did didn't do does doesn't doing don't down during each
    either etc even ever every few for from further get gets getting got had
    hadn't has hasn't have haven't having he he'd he'll he's her here here's
    hers herself him himself his how how's however i i'd i'll i'm i've if in
    into is isn't it it's its itself just let's like made make many may me
    might more most much must mustn't my myself neither no nor not now of off
    often on once one only or other others otherwise our ours ourselves out
    over own per please rather really same shall shan't she she'd she'll
    she's should shouldn't since so some still such than that that's the
    their theirs them themselves then there there's these they they'd they'll
    they're they've this those though through thus to too toward towards
    under until up upon us use used using very via was wasn't we we'd we'll
    we're we've well were weren't what what's whatever when when's where
    where's whether which while who who's whom whose why why's will with
    within without won't would wouldn't yet you you'd you'll you're you've
    your yours yourself yourselves
    """.split()
)

# Several wards publish bilingual newsletters.
SPANISH_STOPWORDS: frozenset[str] = frozenset(
    """
    al como con de del el ella ellos en es esta este esto la las le les lo
    los mas más nos para pero por que se sin su sus un una unas uno unos y ya
    """.split()
)

# Calendar words dominate "rising terms" every month without saying anything
# about content ("october 30th", "newsletter september").
CALENDAR_WORDS: frozenset[str] = frozenset(
    """
    january february march april may june july august september october
    november december jan feb mar apr jun jul aug sep sept oct nov dec monday
    tuesday wednesday thursday friday saturday sunday today tomorrow tonight
    """.split()
)

NEWSLETTER_BOILERPLATE: frozenset[str] = frozenset(
    """
    browser click copyright dear email emails forward mailchimp mailing
    newsletter newsletters powered preferences profile reserved rights share
    subscribe subscribed subscriber unsubscribe unsubscribed
    """.split()
)

EXCLUDED_TERMS: frozenset[str] = (
    ENGLISH_STOPWORDS | SPANISH_STOPWORDS | CALENDAR_WORDS | NEWSLETTER_BOILERPLATE
)

# Generic words that say how, when, or for whom rather than what. They stay in
# the term index, but a rising phrase built with one ("accessible throughout",
# "next week", "chicago residents", "help shape") is a turn of phrase many
# unrelated stories share, not a subject. Written in singular form: rising
# terms compare them with plurals folded.
TREND_FILLER_WORDS: frozenset[str] = frozenset(
    """
    across additional concern event help info information largest member
    regular resident stay throughout upcoming week whole
    two three four five several
    """.split()
)
