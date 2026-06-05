## Usage examples for the ML and statistical tools

These tools use pure-Python statistical methods (no external ML libraries). They all operate on data fetched from the LM API at query time. Most metric-based tools share the same core parameters: `device_id`, `device_datasource_id`, `instance_id` (find these using `get_device_datasources` and `get_device_instances`).

**Capacity forecasting** -- predict when a metric will breach a threshold:
```
"Forecast when memory usage on device 150098 will exceed 90%"
```
Uses `forecast_metric` with `threshold=90`. Supports `method` parameter: `"auto"` (default, selects based on data), `"linear"` (regression), or `"holt_winters"` (seasonal). Returns days until breach, trend direction, confidence interval, and method used. Use `hours_back=168` (1 week) for meaningful regression, or `hours_back=24` if the device has limited history.

**Metric correlation** -- find relationships between metrics across devices:
```
"Correlate CPU usage on server A with memory usage on server B over the last 24 hours"
```
Uses `correlate_metrics` with a `sources` array. Each source requires `device_id`, `device_datasource_id`, `instance_id`, and `datapoint` name. Returns an NxN Pearson correlation matrix and highlights strong correlations (|r| > 0.7). Maximum 10 sources per call.

**Change point detection** -- find when metric behavior shifted:
```
"Detect any regime shifts in CPU metrics on device 150098 in the last 24 hours"
```
Uses `detect_change_points` with CUSUM algorithm. The `sensitivity` parameter (default 1.0) controls detection threshold -- lower values detect smaller shifts. Returns timestamps and direction of each detected change.

**Alert noise scoring** -- identify tuning opportunities:
```
"Score the alert noise across all devices over the last 24 hours"
```
Uses `score_alert_noise`. Returns a 0-100 noise score combining Shannon entropy, flap detection (alerts that clear and re-fire within 30 minutes), and repeat ratio. Includes top noisy devices/datasources and tuning recommendations.

**Device health scoring** -- aggregate health into a single number:
```
"Give me a health score for the stress-demo pod"
```
Uses `score_device_health`. Computes z-scores for each datapoint's latest value against its historical window, then produces a weighted composite score (0-100). Status: healthy (80+), degraded (50-79), critical (<50). Use the `weights` parameter to emphasize specific datapoints.

**Availability calculation** -- SLA reporting from alert data:
```
"Calculate 30-day availability across all devices at error severity or above"
```
Uses `calculate_availability` with `hours_back=720` and `severity_threshold="error"`. Merges overlapping alert windows and returns availability %, MTTR, incident count, longest incident, and per-device breakdown.
