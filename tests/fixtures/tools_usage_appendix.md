## Usage examples for the ML and statistical tools

These tools use pure-Python statistical methods (no external ML libraries). They all operate on data fetched from the LM API at query time. Most metric-based tools share the same core parameters: `device_id`, `device_datasource_id`, `instance_id` (find these using `get_device_datasources` and `get_device_instances`).

**Capacity forecasting** -- predict when a metric will breach a threshold:
```
"Forecast when memory usage on device 150098 will exceed 90%"
```
Uses `analyze_metric` with `analyses=["forecast"]` and `threshold=90`. Returns the least-squares and Holt-Winters slopes per hour and, for each method, when it crosses the threshold within 30 days (`breach_eta` in epoch seconds, `hours_until_breach`, `direction`), or the reason it does not. Holt-Winters fits a daily season and needs two days of samples; `hours` defaults to 168 (one week).

**Metric correlation** -- find relationships between metrics across devices:
```
"Correlate CPU usage on server A with memory usage on server B over the last 24 hours"
```
Uses `correlate_metrics` with a `sources` array. Each source requires `device_id`, `device_datasource_id`, `instance_id`, and `datapoint` name. Returns an NxN Pearson correlation matrix and highlights strong correlations (|r| > 0.7). Maximum 10 sources per call.

**Change point detection** -- find when metric behavior shifted:
```
"Detect any level shifts in CPU metrics on device 150098 over the last week"
```
Uses `analyze_metric` with `analyses=["change_points"]`. A shift is reported where the mean of the next 30 samples leaves the mean of the previous 30 by five times the noise in that comparison, with the daily cycle removed first when the window holds three days or more and that leaves less noise. Returns each shift's timestamp and the levels before and after it. A change in the last 30 samples is not reported yet.

**Alert noise scoring** -- identify tuning opportunities:
```
"Score the alert noise across all devices over the last 24 hours"
```
Uses `analyze_alerts` with `analyses=["noise"]`. Returns a 0-100 noise score combining Shannon entropy, flap detection (alerts that clear and re-fire within 30 minutes), and repeat ratio. Includes top noisy devices/datasources and tuning recommendations.

**Metric status and anomalies** -- how far the latest samples sit from the window:
```
"How far from normal are the stress-demo pod's metrics right now?"
```
Uses `analyze_metric` with `analyses=["summary", "anomalies"]`. The summary gives each datapoint's latest value, mean, standard deviation, min, max and the latest sample's signed z-score; the anomalies section gives z-score, IQR and MAD hits, each method's 20 most extreme. `health_check` runs both sections on the first instance of up to five datasources.

**Availability calculation** -- SLA reporting from alert data:
```
"Calculate 30-day availability across all devices at error severity or above"
```
Uses `calculate_availability` with `hours_back=720` and `severity_threshold="error"`. Merges overlapping alert windows and returns availability %, MTTR, incident count, longest incident, and per-device breakdown.
