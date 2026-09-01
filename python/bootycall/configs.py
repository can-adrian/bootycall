"""
Saved setups.

A "config" is the current state of the window -- show, DCC, variant -- under a
name the user picked, so a comp artist who opens Nuke 16 on the same show every
morning gets there in two clicks.

Stored as a single JSON file so it can be inspected, hand-edited, or dropped
into a user's dotfiles. Deliberately Qt-free: the store is importable and
testable without a QApplication.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

CONFIG_VERSION = 1


def default_config_path() -> Path:
    """Where saved setups live.

    Honours ``BOOTYCALL_CONFIG_FILE``, then ``XDG_CONFIG_HOME``, then
    ``~/.config``.
    """
    override = os.environ.get("BOOTYCALL_CONFIG_FILE")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "bootycall" / "configs.json"


@dataclass(frozen=True)
class SavedConfig:
    """One named window state."""

    name: str
    show: str
    dcc: str
    tool: str
    created: str = ""
    #: Which software tiles were on the row when this was saved. A setup used
    #: to record only show/dcc/tool, and applying one whose DCC had since been
    #: hidden from the Softwares menu failed with "the show does not offer it
    #: any more" -- which was not true, and sent you looking at the show.
    #:
    #: Empty for a setup saved before this existed, which is not the same as
    #: "no software": those are restored by turning the setup's own DCC on and
    #: leaving the rest of the row alone.
    software: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        return "%s - %s" % (self.show, self.tool)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["software"] = list(self.software)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SavedConfig | None":
        try:
            name = str(data["name"]).strip()
            show = str(data["show"]).strip()
            dcc = str(data["dcc"]).strip()
            tool = str(data["tool"]).strip()
        except (KeyError, TypeError, ValueError):
            return None
        if not (name and show and dcc and tool):
            return None

        raw = data.get("software")
        software: tuple[str, ...] = ()
        if isinstance(raw, list):
            software = tuple(
                dict.fromkeys(str(v).strip() for v in raw if str(v).strip())
            )
        return cls(
            name=name,
            show=show,
            dcc=dcc,
            tool=tool,
            created=str(data.get("created", "")),
            software=software,
        )


class ConfigStore:
    """Ordered, name-keyed collection of :class:`SavedConfig`, backed by JSON.

    Never raises on read: a missing or corrupt file yields an empty store, and
    the reason is left in :attr:`load_error` for the UI to show. Losing a
    launcher's shortcut list should not stop the launcher from opening.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_config_path()
        self._configs: list[SavedConfig] = []
        self._preferences: dict = {}
        self.load_error: str = ""
        self.load()

    # -- persistence -------------------------------------------------------

    def load(self) -> None:
        self._configs = []
        self._preferences = {}
        self.load_error = ""
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.load_error = "Could not read %s: %s" % (self.path, exc)
            return

        if isinstance(raw, dict):
            entries = raw.get("configs")
            prefs = raw.get("preferences")
            if isinstance(prefs, dict):
                self._preferences = prefs
        else:
            entries = raw
        if not isinstance(entries, list):
            self.load_error = "Unexpected contents in %s" % self.path
            return

        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            config = SavedConfig.from_dict(entry)
            if config is None or config.name in seen:
                continue
            seen.add(config.name)
            self._configs.append(config)

    def save(self) -> str:
        """Write to disk. Returns an error message, or "" on success."""
        payload = {
            "version": CONFIG_VERSION,
            "configs": [c.to_dict() for c in self._configs],
            "preferences": self._preferences,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-rename so an interrupted save can't truncate the file.
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(
                json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8"
            )
            os.replace(temp, self.path)
        except OSError as exc:
            return "Could not write %s: %s" % (self.path, exc)
        return ""

    # -- collection --------------------------------------------------------

    def __len__(self) -> int:
        return len(self._configs)

    def __iter__(self):
        return iter(self._configs)

    def configs(self) -> list[SavedConfig]:
        return list(self._configs)

    def names(self) -> list[str]:
        return [c.name for c in self._configs]

    def get(self, name: str) -> SavedConfig | None:
        for config in self._configs:
            if config.name == name:
                return config
        return None

    def add(self, config: SavedConfig) -> str:
        """Insert or replace by name, keeping position on replace."""
        stamped = SavedConfig(
            name=config.name,
            show=config.show,
            dcc=config.dcc,
            tool=config.tool,
            created=config.created or datetime.now().isoformat(timespec="seconds"),
        )
        for index, existing in enumerate(self._configs):
            if existing.name == stamped.name:
                self._configs[index] = stamped
                break
        else:
            self._configs.append(stamped)
        return self.save()

    def remove(self, name: str) -> str:
        before = len(self._configs)
        self._configs = [c for c in self._configs if c.name != name]
        if len(self._configs) == before:
            return ""
        return self.save()

    def rename(self, old: str, new: str) -> str:
        """Rename in place, keeping position. Returns an error message or ""."""
        new = new.strip()
        if not new:
            return "A favourite needs a name."
        if new == old:
            return ""
        if self.get(new) is not None:
            return "A favourite named '%s' already exists." % new
        for index, existing in enumerate(self._configs):
            if existing.name == old:
                self._configs[index] = SavedConfig(
                    name=new,
                    show=existing.show,
                    dcc=existing.dcc,
                    tool=existing.tool,
                    created=existing.created,
                )
                return self.save()
        return "No favourite named '%s'." % old

    def move(self, name: str, delta: int) -> str:
        """Shift a favourite up (-1) or down (+1) in the list."""
        names = self.names()
        if name not in names:
            return "No favourite named '%s'." % name
        index = names.index(name)
        target = index + delta
        if target < 0 or target >= len(self._configs):
            return ""  # already at the end; not an error
        self._configs.insert(target, self._configs.pop(index))
        return self.save()

    # -- preferences -------------------------------------------------------

    def visible_software(self) -> tuple[str, ...] | None:
        """Names the user chose to show, or ``None`` if they never said.

        ``None`` and "an empty list" are different answers: the first means
        "use the shipped defaults", the second means "the user turned
        everything off". Collapsing them would resurrect tiles someone
        deliberately hid.
        """
        value = self._preferences.get("visible_software")
        if not isinstance(value, list):
            return None
        return tuple(str(v) for v in value if isinstance(v, str))

    def set_visible_software(self, names: Sequence[str] | None) -> str:
        """Store the visible set, or ``None`` to fall back to the defaults."""
        if names is None:
            self._preferences.pop("visible_software", None)
        else:
            self._preferences["visible_software"] = list(dict.fromkeys(names))
        return self.save()

    def pinned_shows(self) -> tuple[str, ...]:
        """Shows the user pinned as chips. Empty is a perfectly normal answer."""
        value = self._preferences.get("pinned_shows")
        if not isinstance(value, list):
            return ()
        return tuple(dict.fromkeys(str(v) for v in value if isinstance(v, str)))

    def set_pinned_shows(self, names: Sequence[str]) -> str:
        self._preferences["pinned_shows"] = list(dict.fromkeys(names))
        return self.save()

    def selected_show(self) -> str | None:
        """The chip that was selected when the app last closed."""
        value = self._preferences.get("selected_show")
        return value if isinstance(value, str) and value else None

    def set_selected_show(self, name: str | None) -> str:
        if name:
            self._preferences["selected_show"] = name
        else:
            self._preferences.pop("selected_show", None)
        return self.save()

    def path_overrides(self) -> dict[str, str]:
        """User-set roots. Absent keys mean "use the default"."""
        value = self._preferences.get("paths")
        if not isinstance(value, dict):
            return {}
        return {
            str(k): str(v)
            for k, v in value.items()
            if isinstance(k, str) and isinstance(v, str) and v.strip()
        }

    def set_path_overrides(self, overrides: dict[str, str] | None) -> str:
        if overrides:
            self._preferences["paths"] = dict(overrides)
        else:
            self._preferences.pop("paths", None)
        return self.save()

    def use_local(self) -> bool:
        """Whether local packages are in play. On unless turned off."""
        return self._preferences.get("use_local", True) is not False

    def use_dev(self) -> bool:
        """Whether dev packages are in play. On unless turned off."""
        return self._preferences.get("use_dev", True) is not False

    def set_package_use(self, use_local: bool, use_dev: bool) -> str:
        """Store both switches. Absent means on, so only False is written."""
        for key, value in (("use_local", use_local), ("use_dev", use_dev)):
            if value:
                self._preferences.pop(key, None)
            else:
                self._preferences[key] = False
        return self.save()

    def disabled_dev_packages(self) -> tuple[str, ...]:
        """Dev package names the user has switched off, by name.

        Only the *off* ones are stored: a new dev package you install should be
        in play without you having to go and tick it, and storing the on ones
        would mean the opposite.
        """
        stored = self._preferences.get("disabled_dev_packages")
        if not isinstance(stored, list):
            return ()
        return tuple(str(n) for n in stored if str(n).strip())

    def set_disabled_dev_packages(self, names: Sequence[str]) -> str:
        cleaned = sorted({str(n).strip() for n in names if str(n).strip()})
        if cleaned:
            self._preferences["disabled_dev_packages"] = cleaned
        else:
            self._preferences.pop("disabled_dev_packages", None)
        return self.save()

    def selected_dcc(self) -> str | None:
        """The software tile that was active when the state was last saved."""
        value = self._preferences.get("selected_dcc")
        return value if isinstance(value, str) and value else None

    def variants(self) -> dict[str, str]:
        """Chosen variant per DCC, so Maya stays on Ziva between sessions."""
        value = self._preferences.get("variants")
        if not isinstance(value, dict):
            return {}
        return {
            str(k): str(v)
            for k, v in value.items()
            if isinstance(k, str) and isinstance(v, str) and v
        }

    def compact(self) -> bool:
        """Whether the window was collapsed when the state was last saved."""
        return bool(self._preferences.get("compact"))

    def save_ui_state(
        self,
        selected_show: str | None,
        selected_dcc: str | None,
        variants: dict[str, str] | None,
        compact: bool = False,
    ) -> str:
        """Write the whole "where I was" set in one go.

        One save rather than three: these are always written together, and
        three round-trips to a network home directory on every launch is three
        chances to leave the file half-updated.
        """
        if selected_show:
            self._preferences["selected_show"] = selected_show
        else:
            self._preferences.pop("selected_show", None)
        if selected_dcc:
            self._preferences["selected_dcc"] = selected_dcc
        else:
            self._preferences.pop("selected_dcc", None)
        if variants:
            self._preferences["variants"] = dict(variants)
        else:
            self._preferences.pop("variants", None)
        if compact:
            self._preferences["compact"] = True
        else:
            self._preferences.pop("compact", None)
        return self.save()

    def suggest_name(self, show: str, label: str) -> str:
        """A non-colliding default name for the save dialog."""
        base = "%s - %s" % (show, label)
        if base not in self.names():
            return base
        index = 2
        while "%s (%d)" % (base, index) in self.names():
            index += 1
        return "%s (%d)" % (base, index)
