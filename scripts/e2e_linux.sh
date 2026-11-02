#!/bin/bash
# End-to-end test of the Linux Wick CLI and guard daemon against a simulated power setting.
# Needs no root and never touches real logind power settings.
set -u
cd "$(dirname "$0")/.."

wick="$(realpath bin/wick)"

work=$(mktemp -d)
trap 'pkill -f "$wick guard" 2>/dev/null; rm -rf "$work"' EXIT
export WICK_STATE_DIR="$work/state" WICK_SIMULATE_POWER_FILE="$work/power"
echo 0 > "$WICK_SIMULATE_POWER_FILE"

failures=0
power() { cat "$WICK_SIMULATE_POWER_FILE"; }
guards() { pgrep -f "^[^ ]*python.* $wick guard" | grep -v "$$" | wc -l | tr -d ' '; }
settled_guards() { # expected: waits out a spare guard's lock retries
    for _ in $(seq 1 80); do [ "$(guards)" = "$1" ] && break; sleep 0.1; done
    guards
}
expect() { # description expected actual
    if [ "$2" = "$3" ]; then echo "  ok    $1"; else echo "  FAIL  $1 (expected '$2', got '$3')"; failures=$((failures + 1)); fi
}
wait_for() { # expected-power seconds
    for _ in $(seq 1 $(($2 * 10))); do [ "$(power)" = "$1" ] && return 0; sleep 0.1; done
    return 1
}
last_reason() { sed -n 's/.*"reason": *"\([^"]*\)".*/\1/p' "$WICK_STATE_DIR/last-end.json" 2>/dev/null; }

echo "=== 1. on, off ==="
"$wick" on >/dev/null
expect "on turns sleep off" 1 "$(power)"
expect "one guard is running" 1 "$(settled_guards 1)"
"$wick" off >/dev/null
expect "off turns sleep on" 0 "$(power)"
sleep 7
expect "guard exits on its own once the session is gone" 0 "$(settled_guards 0)"

echo "=== 2. only one guard ==="
"$wick" on >/dev/null; "$wick" on 2h >/dev/null; "$wick" on 1h >/dev/null
expect "repeat starts share one guard" 1 "$(settled_guards 1)"
"$wick" off >/dev/null; sleep 0.1; pkill -f "$wick guard"; sleep 0.2

echo "=== 3. timer ==="
"$wick" on 2s >/dev/null
expect "stays on before the deadline" 1 "$(power)"
wait_for 0 5; expect "sleep returns at the deadline, without the CLI running" 0 "$(power)"
expect "records why" timeUp "$(last_reason)"

echo "=== 4. crash safety ==="
"$wick" on >/dev/null
sleep 0.3
pkill -TERM -f "$wick guard"
wait_for 0 3; expect "SIGTERM on the guard (logout, shutdown) restores sleep" 0 "$(power)"

"$wick" on 2s >/dev/null
sleep 0.3
pkill -KILL -f "$wick guard"
sleep 3
expect "SIGKILL leaves the setting on until someone looks" 1 "$(power)"
"$wick" status >/dev/null
wait_for 0 3; expect "next launch restarts the guard, which ends the expired session" 0 "$(power)"

echo "=== 5. terminal closing ==="
(bash -c "\"$wick\" on 30m >/dev/null; kill -HUP \$\$" 2>/dev/null) 2>/dev/null
expect "guard survives the terminal" 1 "$(settled_guards 1)"
expect "still on" 1 "$(power)"
"$wick" off >/dev/null; sleep 0.1; pkill -f "$wick guard"; sleep 0.2

echo "=== 6. external change ==="
"$wick" on 30m >/dev/null
echo 0 > "$WICK_SIMULATE_POWER_FILE"
sleep 7
expect "guard notices sleep turned back on elsewhere" stoppedExternally "$(last_reason)"
expect "and exits" 0 "$(settled_guards 0)"

echo "=== 7. wick run ==="
"$wick" run sh -c 'cat "$WICK_SIMULATE_POWER_FILE" > "$WICK_STATE_DIR/during"; exit 7'
code=$?
expect "on while the command runs" 1 "$(cat "$WICK_STATE_DIR/during")"
expect "off once it finishes" 0 "$(power)"
expect "passes the exit code through" 7 "$code"
sleep 0.2; pkill -f "$wick guard"; sleep 0.2

"$wick" run sh -c 'kill -9 $PPID; exec sleep 9' &
held=$!
sleep 7
expect "killing wick run ends the session through the guard" 0 "$(power)"
wait "$held" 2>/dev/null
sleep 0.2; pkill -f "$wick guard"; sleep 0.2

"$wick" on 30m >/dev/null
"$wick" run true
expect "a run inside an open session leaves that session alone" 1 "$(power)"
"$wick" off >/dev/null; sleep 0.1; pkill -f "$wick guard"; sleep 0.2

"$wick" on 2s >/dev/null
"$wick" run sleep 4 &
held=$!
sleep 3
expect "a running command outlives the timer" 1 "$(power)"
wait "$held"
wait_for 0 7; expect "and the timer applies once it exits" 0 "$(power)"
sleep 0.2; pkill -f "$wick guard"; sleep 0.2

"$wick" run sleep 2 &
held=$!
sleep 0.5
"$wick" on 8h >/dev/null
wait "$held"
expect "a command's exit doesn't end a session started after it" 1 "$(power)"
"$wick" off >/dev/null; sleep 0.1; pkill -f "$wick guard"; sleep 0.2

echo "=== 8. wick run on a real terminal ==="
pty_runner="$(realpath scripts/run_pty.py)"
on_pty() { perl -e 'alarm 10; exec @ARGV' "$pty_runner" "$wick" run "$@" 2>&1 | tr -d '\r'; }

output=$( (sleep 0.5; printf 'hello\n'; sleep 0.5) | on_pty sh -c 'stty size >/dev/null; read line; echo "read: $line"; exit 3')
case "$output" in *"read: hello"*) got=yes ;; *) got=no ;; esac
expect "the command can read the terminal" yes "$got"
expect "sleep is back afterwards" 0 "$(power)"
sleep 0.2; pkill -f "$wick guard"; sleep 0.2

output=$( (sleep 0.5; printf '\003'; sleep 0.5) | on_pty sh -c 'trap "echo got-interrupt; exit 9" INT; sleep 5 & wait')
case "$output" in *got-interrupt*) got=yes ;; *) got=no ;; esac
expect "Ctrl-C reaches the command" yes "$got"
expect "and sleep still comes back" 0 "$(power)"
sleep 0.2; pkill -f "$wick guard"; sleep 0.2

echo "=== 9. losing the session file ==="
"$wick" on 30m >/dev/null
sleep 1.3
printf 'garbage' > "$WICK_STATE_DIR/session.json"
wait_for 0 8; expect "a corrupt session ends rather than running unenforced" 0 "$(power)"
sleep 0.2; expect "and the guard leaves" 0 "$(settled_guards 0)"

"$wick" on 30m >/dev/null
sleep 1.3
rm "$WICK_STATE_DIR/session.json"
wait_for 0 8; expect "so does a deleted one" 0 "$(power)"

"$wick" on 30m >/dev/null
sleep 0.3
pkill -KILL -f "$wick guard"
printf 'garbage' > "$WICK_STATE_DIR/session.json"
"$wick" status >/dev/null
expect "reconciling handles a corrupt session with no guard" 0 "$(power)"

echo "=== 10. stopping and starting in a tight loop ==="
for _ in $(seq 1 25); do "$wick" off >/dev/null; "$wick" on 30m >/dev/null; done
sleep 7
expect "the last start wins" 1 "$(power)"
expect "with its session on disk" yes "$([ -f "$WICK_STATE_DIR/session.json" ] && echo yes || echo no)"
expect "and exactly one guard" 1 "$(settled_guards 1)"
"$wick" off >/dev/null; sleep 0.1; pkill -f "$wick guard"; sleep 0.2

echo "=== 11. off --session-only ==="
echo 1 > "$WICK_SIMULATE_POWER_FILE"
"$wick" off --session-only
expect "leaves a setting Wick did not turn on" 1 "$(power)"
echo 0 > "$WICK_SIMULATE_POWER_FILE"

echo "=== 12. battery floor and thermal safety ==="
export WICK_SIMULATE_BATTERY="15,discharging"
"$wick" on 30m --floor 20 >/dev/null
wait_for 0 5; expect "battery floor restores sleep" 0 "$(power)"
expect "records lowBattery" lowBattery "$(last_reason)"
export WICK_SIMULATE_BATTERY=""
sleep 0.2; pkill -f "$wick guard"; sleep 0.2

export WICK_SIMULATE_THERMAL="critical"
"$wick" on 30m >/dev/null
wait_for 0 5; expect "critical thermal restores sleep" 0 "$(power)"
expect "records overheating" overheating "$(last_reason)"
export WICK_SIMULATE_THERMAL=""
sleep 0.2; pkill -f "$wick guard"; sleep 0.2

echo "=== 13. errors ==="
"$wick" on soon >/dev/null 2>&1
expect "bad duration fails" 1 "$?"
expect "and changes nothing" 0 "$(power)"
"$wick" on --floor 200 >/dev/null 2>&1
expect "bad floor fails" 1 "$?"
"$wick" nonsense >/dev/null 2>&1
expect "unknown command fails" 1 "$?"

echo
[ "$failures" = 0 ] && echo "All passed." || echo "$failures failed."
exit "$failures"
