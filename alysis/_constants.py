from enum import Enum


class EVMVersion(Enum):
    """
    Supported EVM versions.
    Some may not be available depending on the compiler version.
    """

    HOMESTEAD = "homestead"
    """Homestead fork, Mar 14, 2016."""

    TANGERINE_WHISTLE = "tangerineWhistle"
    """Tangerine Whistle fork, Oct 18, 2016."""

    SPURIOUS_DRAGON = "spuriousDragon"
    """Spurious Dragon fork, Nov 22, 2016."""

    BYZANTIUM = "byzantium"
    """Byzantium fork, Oct 16, 2017."""

    CONSTANTINOPLE = "constantinople"
    """Constantinople fork, Feb 28, 2019."""

    ISTANBUL = "istanbul"
    """Istanbul fork, Dec 8, 2019."""

    BERLIN = "berlin"
    """Berlin fork, Apr 15, 2021."""

    LONDON = "london"
    """London fork, Aug 5, 2021."""

    PARIS = "paris"
    """Paris fork, Sep 15, 2022."""

    SHANGHAI = "shanghai"
    """Shanghai fork, Apr 12, 2023."""

    CANCUN = "cancun"
    """Cancun fork, Mar 13, 2024."""
