name = "bootycall"

version = "0.7.0"

description = "An interface for managing rez environments and resolving packages."

authors = ["Adrian Tsang"]

# PySide6 is the only hard runtime dependency: BootyCall reads bootstrap files
# with ast and shells out to rez, so it never imports rez itself. That is what
# lets it run in a plain Python environment and stay honest about what it can
# and cannot resolve.
requires = [
    "python-3.9+",
    "PySide6-6.5+",
]

tools = [
    "bootycall",
]

build_command = "python {root}/rezbuild.py {install}"

uuid = "ilp.bootycall"


def commands():
    env.PYTHONPATH.prepend("{root}/python")
    env.PATH.prepend("{root}/bin")

    # Site paths. Every one of these is also settable per user in the app's
    # Settings dialog, which takes precedence; setting them here moves the
    # defaults for everybody without touching the source.
    #
    # env.BOOTYCALL_SHOWS_ROOT = "/ice/shows"
    # env.BOOTYCALL_LOCAL_PACKAGES_ROOT = "/ice/rez/packages/local/{user}"
    # env.BOOTYCALL_DEV_PACKAGES_ROOT = "{local}/dev"
    #
    # The terminal emulator is detected from PATH (gnome-terminal, konsole,
    # xfce4-terminal, alacritty, kitty, xterm). Pin it if the host has several
    # and you want a particular one:
    #
    # env.BOOTYCALL_TERMINAL_EMULATOR = "gnome-terminal:--"
    #
    # Or replace the whole command, if your site wraps the launch:
    #
    # env.BOOTYCALL_LAUNCH_COMMAND = "gnome-terminal:--:bash:-c:{script}"
    # env.BOOTYCALL_TERMINAL_COMMAND = "gnome-terminal:--:bash:-c:{script}"
    #
    # When to keep the window open after the command finishes: error, always,
    # never. "always" is useful while getting a site's settings right.
    #
    # env.BOOTYCALL_HOLD_TERMINAL = "error"
    #
    # The bootstrap probe imports a show's bootstrap in a throwaway interpreter
    # and uses what the module actually says, in place of what BootyCall could
    # read out of the file. That interpreter has to be able to import rez and
    # ilp_bootstrap, which BootyCall's own is not required to do -- so point
    # this at one that can:
    #
    # env.BOOTYCALL_PROBE_COMMAND = "rez-env:ilp_bootstrap:--:python:{script}:{bootstrap}"
    #
    # Or switch it off entirely and stay with the static read:
    #
    # env.BOOTYCALL_PROBE_MODE = "off"
