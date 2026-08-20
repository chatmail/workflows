# cmsend-notify

Reusable Actions workflows that report run results into a Delta Chat
group via the [`cmsend`](https://github.com/chatmail/cmsend) CLI:

 - `cmsend-notify.yml` messages the alert group on state **change**, needs to be paired with
 - `cmsend-sync.yml`, which runs on an interval to keep account alive and synced
 - `cmsend-test` allows to test the workflow

## Setup

Two steps:
- Setup the cmsend profile & save it as action secret
- Add Workflows

### One-time account setup

1. In a Delta Chat client of your choice, pick or create (and send an initial
   message) the group to alert, and copy the invite link.
2. Create the bot account, name it, and join the group (feature branch right now):
   ```
   export CMSEND_SPEC="git+https://github.com/chatmail/cmsend@ci-sync-and-name"
   uvx --from "$CMSEND_SPEC" --init <relay-domain> --shared --name "CI Bot"
   uvx --from "$CMSEND_SPEC" -t LOG --join "<invite link>"
   ```
3. Test delivery:
   ```
   echo "alert test" | uv run cmsend -t LOG
   ```
4. Pack a dump of the cmsend account with `scripts/pack-cmsend-profile.sh`
   ```
   scripts/pack-cmsend-profile.sh pack ~/.config/cmsend | tee /tmp/secret.b64 | wc -c   # must be < 65536
   ```
   To verify the export works:
   ```
   scripts/pack-cmsend-profile.sh unpack /tmp/rt/cmsend < /tmp/secret.b64
   XDG_CONFIG_HOME=/tmp/rt uvx --from \
     "git+https://github.com/chatmail/cmsend@ci-sync-and-name" cmsend -l   # must list LOG
   ```
5. Finally, add the output as a repository secret named `CMSEND_ACCOUNT_TGZ_B64`

On initial run, this will be unpacked to seed a cmsend profile, which will carry across action runs in an cache file encrypted with `CMSEND_ACCOUNT_TGZ_B64` as a secret.

### Add the workflows:

### In the workflow you want to be notified about

add after the job to watch:
```yaml
  notify:
    needs: <watched-job>
    if: always()
    permissions:
      actions: read  # required to read the previous run's conclusion
    uses: chatmail/workflows/.github/workflows/cmsend-notify.yml@cmsend-notify
    with:
      result: ${{ needs.<watched-job>.result }}
    secrets:
      cmsend-account: ${{ secrets.CMSEND_ACCOUNT_TGZ_B64 }}
```

Be sure to replace both instances of <watched-job> with your job name.

### Add the sync workflow, default is nightly

`cp doc/cmsend-notify/cmsend-nightly.yml <project>/.github/workflows/`

The nightly job updates and saves an encrypted copy of the profile.

### Test action

You can also copy `notify-test.yml` which allows to run PASS/FAIL test notifies
against this repo's notify setup from the actions Web UI. If you dispatch it
twice with `force_fail=true`, then `false` should give you FAILED, then
RECOVERED. Dispatching the same result twice should not alert.

## Notes

To point at a different group, `--join` it locally again and redo step 4 + 5.
