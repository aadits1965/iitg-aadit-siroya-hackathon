"""Validated colour palette (from the project's dataviz skill reference) --
categorical hues assigned in fixed order (never cycled/reassigned when a
filter changes which series are present), one sequential blue ramp for
magnitude, one diverging blue<->red pair for signed P&L, and a fixed status
set for good/bad outcomes."""

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

EVENT_CLASS_COLORS = {
    "Geopolitical": CATEGORICAL[0],
    "Macroeconomic": CATEGORICAL[1],
    "Credit Event": CATEGORICAL[2],
    "Merger/Acquisition": CATEGORICAL[3],
    "Product Launch": CATEGORICAL[4],
    "Other": CATEGORICAL[5],
}

SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95", "#0d366b"]

DIVERGING_BLUE_RED = [[0.0, "#e34948"], [0.5, "#f0efec"], [1.0, "#2a78d6"]]

STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}
