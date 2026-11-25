"""Dataset thresholds from the Obscura repository, in units of 10^-8."""

DEN = 100_000_000
NUMERATORS = {"lfw": 11_368_578, "droneface": 6_247_600}


def select_profile(bank, requested):
    if requested is not None:
        return requested
    if bank.name.startswith("embeddings_droneface_raw_sface"):
        return "droneface"
    return "lfw"


def add_profile_option(parser):
    parser.add_argument(
        "--threshold-profile",
        choices=NUMERATORS,
        help="Dealer decision threshold (default: droneface for DroneFace banks, otherwise lfw)",
    )
