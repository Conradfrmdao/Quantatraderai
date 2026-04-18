"""Backtesting harness.

Walks a symbol's historical candles and feeds each bar through the same
`decision_maker` and `risk_manager` the live loop uses. Orders go to a
`MockVenue` that implements the `Venue` interface, so strategy behavior
is identical to live.
"""
