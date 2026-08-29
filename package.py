name = "bootycall"

version = "0.1.0"

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
    # How a DCC is started, and how a shell is opened. Both are guesses in the
    # shipped defaults -- see the README -- and are the two settings most
    # likely to need a site value here.
    #
    # env.BOOTYCALL_LAUNCH_COMMAND = "ilp_bootstrap:{tool}"
    # env.BOOTYCALL_TERMINAL_COMMAND = "x-terminal-emulator:-e:rez-env:{packages}"
