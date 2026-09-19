# How to remove DeViDa completely

Written 2026-09-19 by Alpha, at Iker's request. **Only do this if Iker asks.**
DeViDa is live and working; this file exists so that removing it later is exact.

## 1. Stop the daily job

```
systemctl --user disable --now devida.timer
rm ~/.config/systemd/user/devida.service ~/.config/systemd/user/devida.timer
systemctl --user daemon-reload
systemctl --user list-timers --all | grep devida    # should print nothing
```

## 2. The project folder, its packages, and every built day

```
rm -rf ~/devida        # code, .venv, out/ with every day's content, audio and logs
```

`out/days/` holds every day ever built. Once deleted it cannot be rebuilt, because
the news feeds only give the last 24 hours.

## 3. The GitHub repo and the web page (Iker does this, it needs a login)

github.com/programever/devida → Settings → Delete this repository. That removes
both the code (`main`) and the page (`gh-pages`). The address
https://programever.github.io/devida/ stops working within minutes.

## 4. Old settings from the podcast plan, in `~/alpha/.env`

These are unused since 2026-09-16 and can go at any time:

```
sed -i '/^GEMINI_API_KEY=/d; /^GCS_BUCKET=/d; /^GCS_KEY_FILE=/d' ~/alpha/.env
rm -f ~/alpha/secrets/gcs-key.json
rm -rf ~/.venvs/gcs
```

In Google, on Iker's personal account (Iker does this): the empty storage
bucket `devida` and project `devida-508803`, the service account
`alpha-podcast`, and the AI Studio key from project `devida-free`. All free while
they sit there, so there is no hurry.

## 5. Leftovers on the box from the podcast tests

```
rm -f ~/beta-build.log ~/devida-full.log ~/devida-mem.log ~/devida-sample.mp3 ~/devida-test.log*
rm -rf ~/devida-samples
```

## 6. The note in Alpha's rules

`~/alpha/alpha/CLAUDE.md` has a few lines about DeViDa (the exception to "Alpha
does not write code", the auto-publish rule, the force-push permission). Delete
them, commit, push. (Never force-push the alpha repo.)

## Check it is gone

```
ls ~/devida 2>&1                                    # no such file
systemctl --user list-timers --all | grep devida    # nothing
curl -s -o /dev/null -w "%{http_code}\n" https://programever.github.io/devida/   # 404
```
