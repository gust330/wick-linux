# Wick for Linux

The Linux side of [Wick](https://github.com/s1lvazxy/wick). See the main README for how to install and use it.

```sh
./wick-dev status                 # run from a checkout
python3 -m unittest discover tests
tests/e2e.sh                      # CLI and guard against a simulated lock. No root, no logind
tests/logind/run.sh               # against real systemd-logind, in a container. Needs Docker
tests/gnome/run.sh                # loads the extension in real GNOME Shell. Needs Docker
preview/run.sh                    # a real GNOME desktop with Wick in it, in your browser. Needs Docker
```
