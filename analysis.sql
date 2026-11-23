-- SQLite: one row in sessions is one observed visit in the source.
CREATE VIEW segments AS
SELECT 'month' AS cut, month AS segment, purchased FROM sessions
UNION ALL SELECT 'visitor', visitor, purchased FROM sessions
UNION ALL SELECT 'weekend', CASE weekend WHEN 1 THEN 'Weekend' ELSE 'Weekday' END, purchased FROM sessions;

CREATE VIEW conversion AS
WITH counts AS (
  SELECT cut, segment, COUNT(*) AS sessions, SUM(purchased) AS purchases
  FROM segments GROUP BY cut, segment
)
SELECT *, purchases * 1.0 / sessions AS conversion,
       sessions * 1.0 / SUM(sessions) OVER (PARTITION BY cut) AS traffic_share,
       purchases * 1.0 / SUM(purchases) OVER (PARTITION BY cut) AS purchase_share
FROM counts;
