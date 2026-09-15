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
