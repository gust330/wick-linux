#!/bin/bash
# Checks the one thing no automated test can: that the Mac really keeps running with the lid shut.
# Start a Wick session, run this, close the lid for at least a minute, then open it again.
# It only reads state. It changes nothing.
set -u

timeout_seconds="${1:-1800}"
minimum_closed=45
log=$(mktemp -t wick-lid-test)
started=$(date +%s)

lid() { ioreg -r -k AppleClamshellState -d 1 | awk '/"AppleClamshellState"/ { print $NF; exit }'; }
setting() { pmset -g | awk '/SleepDisabled/ { print $NF; exit }'; }
online() { curl -s -o /dev/null -m 4 https://github.com && echo yes || echo no; }

echo "SleepDisabled is $(setting). Close the lid for at least a minute, then open it."
[ "$(setting)" = 1 ] || echo "Warning: sleep isn't disabled, so this should fail. Start a Wick session first."

closed_at=0
reopened_at=0
last=$started
longest_gap=0
ticks=0
online_ticks=0

while :; do
    now=$(date +%s)
    gap=$((now - last))
    [ "$gap" -gt "$longest_gap" ] && [ "$closed_at" -gt 0 ] && longest_gap=$gap
    last=$now
    state=$(lid)

    if [ "$state" = Yes ]; then
        [ "$closed_at" = 0 ] && closed_at=$now
        ticks=$((ticks + 1))
        [ "$(online)" = yes ] && online_ticks=$((online_ticks + 1))
    elif [ "$closed_at" -gt 0 ]; then
        reopened_at=$now
        break
    fi

    echo "$now lid=$state setting=$(setting)" >> "$log"
    [ $((now - started)) -gt "$timeout_seconds" ] && break
    sleep 2
done

if [ "$closed_at" = 0 ]; then
    echo "RESULT: not tested. The lid was never closed."
    exit 2
fi
if [ "$reopened_at" = 0 ]; then
    echo "RESULT: not tested. The lid was never reopened."
    exit 2
fi

closed=$((reopened_at - closed_at))
echo "Lid closed for ${closed}s. Samples taken while closed: $ticks. Network reachable in $online_ticks of them."
echo "Longest pause between samples: ${longest_gap}s."
echo "Sleep events since the test began:"
since=$(date -r "$started" '+%Y-%m-%d %H:%M')
pmset -g log | awk -v since="$since" '$1" "substr($2,1,5) >= since && $3 ~ /^(Sleep|Wake|DarkWake)$/' | cut -c1-110 | tail -5
echo "Log: $log"

if [ "$closed" -lt "$minimum_closed" ]; then
    echo "RESULT: too short to tell. Keep it closed for at least ${minimum_closed}s."
    exit 2
fi
# Each sample takes a few seconds with the network check. A real sleep shows up as a gap as long as the closure.
if [ "$longest_gap" -gt 20 ]; then
    echo "RESULT: FAILED. The Mac stopped running for ${longest_gap}s with the lid closed."
    exit 1
fi
echo "RESULT: PASSED. The Mac kept running the whole time the lid was closed."
