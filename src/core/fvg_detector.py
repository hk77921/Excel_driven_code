from typing import List, Optional, Tuple
from .models import FairValueGap

def detect_fvg(
    highs: List[float],
    lows: List[float],
    index: int,
    symbol: str,
) -> Optional[FairValueGap]:
    """
    Detect FVG using 3-candle rule.
    index = current candle index
    """
    if index < 2:
        return None


   # Bullish FVG
    if lows[index] > highs[index - 2]:
        low = highs[index - 2]
        high = lows[index]
        return FairValueGap(
            symbol=symbol,
            direction="BULLISH",
            high=high,
            low=low,
            size=high - low,
            created_at_index=index
        )

     # Bearish FVG
    if highs[index] < lows[index - 2]:
        high = lows[index - 2]
        low = highs[index]
        return FairValueGap(
            symbol=symbol,
            direction="BEARISH",
            high=high,
            low=low,
            size=high - low,
            created_at_index=index
        )

    return None



