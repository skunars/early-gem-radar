# EARLY GEM RADAR - CONFIG

SCAN_INTERVAL_MINUTES = 10

# Risk/liquidity filters: the previous 10k USD floor was too thin
# for a 100 TL paper position and produced extreme execution gaps.
MIN_LIQUIDITY_USD = 100000

# Require enough real trading activity to support an exit.
MIN_VOLUME_24H_USD = 50000

# Score thresholds
BUY_CANDIDATE_SCORE = 80
WATCH_SCORE = 60

# Token price itself is not used in the score.
# Cheap/expensive price is not an advantage or disadvantage.

PROJECT_NAME = "EARLY GEM RADAR"
