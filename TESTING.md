# Installation and upgrade testing

You do not need a second physical computer for every check. The automated
tests use a local simulated HA server and a mocked keyring. They do not control
real devices. A real installed checkout then verifies the Omarchy integration.
A VM or another user's machine is still useful for testing a genuinely different
desktop, missing system packages and other camera codecs.

## Automated tests

```bash
~/.local/share/seigliva.ha-watch/venv/bin/python -m unittest discover -s tests -v
```

The suite includes first startup without a runtime, loading a runtime from the
data directory, migration backups and conflicts, auth, sensor states, covers,
custom messages, cooldown, and camera requests. GitHub runs it on Python 3.11
and 3.14.

## Reinstall on an existing desktop

Before removing an installation, make a private backup of the `ha.watch` or
`seigliva.ha-watch` entry in `~/.config/omarchy/shell.json`, including its bar
section and position. That entry contains the rules and connection metadata;
credentials are in the keyring. Keep backups outside this repository.

For an ID upgrade, run the new checkout's `python3 migrate.py` before removal.
For removal and reinstallation of the same ID, save its entry first and restore
that entry after reinstalling. Avoid replacing the entire shell configuration
if unrelated desktop settings changed in the meantime. Do not sign out unless
you intend to test a new login, since signing out revokes the HA session.

```bash
omarchy plugin remove seigliva.ha-watch --yes
omarchy plugin add https://github.com/Seigliva/omarchy-ha-watch.git --yes
cd ~/.config/omarchy/plugins/seigliva.ha-watch
bash setup.sh
omarchy plugin validate .
omarchy restart shell
omarchy-shell ha-watch status
```

Restore the saved plugin entry if needed, then run
`omarchy-shell shell reloadConfig`. Confirm the rule count, settings and HA
connection before using a rule's Test button. Test does not move covers.

## Upgrade an installed version

Keep the development checkout separate from the installed checkout. Push a
reviewed commit to GitHub, then run:

```bash
omarchy plugin update seigliva.ha-watch --yes
omarchy plugin validate ~/.config/omarchy/plugins/seigliva.ha-watch
omarchy-shell ha-watch status
```

Verify the installed commit matches the remote and that rules remain intact.
Rerun setup if dependencies changed. Restart the shell if cached QML still shows
the previous UI. Do not create `.venv` in the installed plugin: Omarchy's
validator rejects the symlinks it contains.

## Validation performed for 0.3.0

- Fifteen automated tests passed locally and on GitHub.
- Created the separate runtime from scratch with pinned dependencies.
- Removed the legacy development symlink and installed a fresh clone from GitHub
  using the actual `omarchy plugin add` command.
- Ran setup and successfully validated the installed plugin folder.
- Compared migrated settings to the private backup: all three rules and all
  connection metadata were preserved exactly.
- Restarted the shell and confirmed that HA reconnected without a new login.

This verifies installation on the existing desktop, not a completely clean OS.
Real camera playback and door notifications were previously tested by the
maintainer. Additional camera brands and desktop environments remain untested.

## Native panel checks

Before publishing UI changes, test the locally installed version:

- Open from the bar icon and `omarchy-shell ha-watch settings`; confirm that
  it anchors at the icon and does not create a tiled application window.
- Close with Escape, outside click and the icon. Reopen immediately and check
  keyboard focus, Tab navigation and switching to another Omarchy panel.
- Edit a cover: verify Opening/Open/Closing/Closed, existing selection and
  custom text. Cancel must leave the saved rule unchanged.
- Add, save, enable/disable and remove a temporary rule; removal takes a second
  confirmation click. Check camera selection and text-only rules.
- Open Settings and verify position, screen, duration and connection status.
- Use Test for a text rule and a camera rule; check pin, expand and close.
- Check long names/text, scrolling with many rules, another theme, bar position
  and multiple monitors when available.

Local UI previews can temporarily leave the installed checkout modified. Review
and publish the development checkout before updating that installation; do not
run an updater over unreviewed local changes.

## Validation performed for 0.4.0

- Sixteen automated tests pass, including a regression test ensuring live state
  changes do not replace the entity selector model.
- Plugin validation and shell script syntax checks pass.
- The maintainer verified all UI functions and confirmed stable sensor scrolling.
- Live camera playback, cover/contact notifications and custom text were verified
  on the existing Home Assistant installation.
- The native panel, rule editor, settings, keyboard dismissal and restored tagline
  were loaded locally before publication.

## Dependency integrity (0.4.1)

Setup and CI require hashes and accept wheels only. The setup regression tests
use offline fixture wheels and fresh temporary runtimes to verify successful
installation, rejection of tampered bytes, and rejection of missing hashes.
They do not touch the user's installed runtime or Home Assistant configuration.

The actual locked dependencies must also install in a fresh environment, followed
by `python -m pip check` and the complete test suite. CI repeats this on Python
3.11 and 3.14.

## Bounded media validation (0.5.0)

The complete suite includes bounded HTTP downloads, compression expansion,
image dimensions, URL/HLS validation, separate FFmpeg decoding, cancellation,
backpressure and fallback. A real Home Assistant/UniFi fragmented-MP4 stream
produced 216 live frames over a 25-second diagnostic run; live output was also
visually confirmed in the actual Omarchy panel.

After installation, test camera startup, Pin/Unpin, closing and replacing a
preview, text-only notifications and fallback. Camera decoding must never use
Qt Multimedia or a remote Image URL. Verify expired previews stop their helper
and local files are removed after dismissal. See MEDIA_SECURITY.md for limits.
